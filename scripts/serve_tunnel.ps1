#Requires -Version 5.1
<#
.SYNOPSIS
    Host esports-sim for remote friends: Cloudflare Tunnel + local-only server.

.DESCRIPTION
    Starts cloudflared (connected to the "esports-sim" tunnel provisioned by
    scripts\setup_remote_play.ps1) and then launches the game via
    scripts\serve.ps1 in LOCAL-ONLY mode (bind 127.0.0.1), so the ONLY path
    into your PC is the outbound-only tunnel, and every visitor must pass the
    Cloudflare Access email allow-list first. No firewall rule, no port
    forwarding, no inbound exposure.

    The tunnel connector token is fetched fresh from the Cloudflare API each
    run (never written to disk) and handed to cloudflared via the TUNNEL_TOKEN
    environment variable.

    When the game server exits, the cloudflared process is stopped too.

    All console output is ASCII-only.

.PARAMETER Port
    Local port the game listens on. Default 8420. Must match the ingress
    configured by setup_remote_play.ps1.

.PARAMETER NoVllm
    Passed through to serve.ps1 (skip local vLLM startup).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\serve_tunnel.ps1
#>
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8420,

    [switch]$NoVllm
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

function Write-Line { param([string]$Message = '') Write-Host $Message }

function Get-DotenvValue {
    param([string]$Name)
    $envPath = Join-Path $repoRoot '.env'
    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in (Get-Content -LiteralPath $envPath -ErrorAction SilentlyContinue)) {
            $line = $line.Trim()
            if ($line.StartsWith('#') -or $line -notlike '*=*') { continue }
            $parts = $line.Split('=', 2)
            if ($parts[0].Trim() -eq $Name) {
                return $parts[1].Trim().Trim("'").Trim('"')
            }
        }
    }
    $v = [Environment]::GetEnvironmentVariable($Name)
    if ($v) { return $v }
    return $null
}

function Find-Cloudflared {
    $cmd = Get-Command cloudflared -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'cloudflared\cloudflared.exe'),
        (Join-Path $env:ProgramFiles 'cloudflared\cloudflared.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'cloudflared\cloudflared.exe'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\cloudflared.exe')
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

$token = Get-DotenvValue 'CLOUDFLARE_API_TOKEN'
$account = Get-DotenvValue 'CLOUDFLARE_ACCOUNT_ID'
if (-not $token -or -not $account) {
    Write-Line '[error] CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must be set in .env.'
    exit 1
}

$cloudflared = Find-Cloudflared
if (-not $cloudflared) {
    Write-Line '[error] cloudflared not found. Install it once with:'
    Write-Line '        winget install --id Cloudflare.cloudflared'
    exit 1
}

$base = 'https://api.cloudflare.com/client/v4'
$headers = @{ Authorization = "Bearer $token" }

# Resolve the provisioned tunnel and fetch a connector token for this run.
try {
    $found = Invoke-RestMethod -Headers $headers -Uri "$base/accounts/$account/cfd_tunnel?is_deleted=false&name=esports-sim"
} catch {
    Write-Line "[error] Cloudflare API tunnel lookup failed: $($_.Exception.Message)"
    exit 1
}
if (-not $found.result -or $found.result.Count -eq 0) {
    Write-Line '[error] Tunnel "esports-sim" does not exist yet. Provision it first:'
    Write-Line '        powershell -ExecutionPolicy Bypass -File .\scripts\setup_remote_play.ps1'
    exit 1
}
$tunnelId = $found.result[0].id
try {
    $tok = Invoke-RestMethod -Headers $headers -Uri "$base/accounts/$account/cfd_tunnel/$tunnelId/token"
} catch {
    Write-Line "[error] Could not fetch the tunnel connector token: $($_.Exception.Message)"
    exit 1
}
$tunnelToken = $tok.result

$bar = ('=' * 62)
Write-Line $bar
Write-Line ' esports-sim remote play host'
Write-Line $bar
Write-Line " Tunnel   : esports-sim ($tunnelId)"
Write-Line " Server   : http://127.0.0.1:$Port (local-only bind)"
Write-Line ' Exposure : Cloudflare Tunnel only (outbound), Access allow-list in front'
Write-Line $bar

$proc = $null
try {
    $env:TUNNEL_TOKEN = $tunnelToken
    $proc = Start-Process -FilePath $cloudflared -ArgumentList @('tunnel', 'run') `
        -WindowStyle Minimized -PassThru
    Write-Line "[tunnel] cloudflared started (pid $($proc.Id))."

    $serveArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', (Join-Path $PSScriptRoot 'serve.ps1'),
        '-Local', '-Port', "$Port")
    if ($NoVllm) { $serveArgs += '-NoVllm' }
    & powershell.exe @serveArgs
    $exitCode = $LASTEXITCODE
} finally {
    Remove-Item Env:TUNNEL_TOKEN -ErrorAction SilentlyContinue
    if ($proc -and -not $proc.HasExited) {
        try { Stop-Process -Id $proc.Id -Force -Confirm:$false } catch {}
        Write-Line '[tunnel] cloudflared stopped.'
    }
}
if ($null -eq $exitCode) { $exitCode = 0 }
exit $exitCode
