#Requires -Version 5.1
<#
.SYNOPSIS
    Launch the esports-sim web UI (FastAPI/uvicorn) with friendly LAN or
    local-only boot options.

.DESCRIPTION
    Thin, robust wrapper around:

        <python> -m esports_sim --web --host <addr> --port <n> [--no-browser]

    Defaults to LAN mode (binds 0.0.0.0) so other players on your network can
    join. Use -Local to restrict the server to this PC (binds 127.0.0.1).

    The Python app prints its own banner with the exact local and LAN URLs and
    auto-opens the local browser unless -NoBrowser is given, so this launcher
    only adds a short pre-flight summary, robust interpreter discovery, and an
    optional Windows Firewall rule for LAN play.

    All console output is ASCII-only (legacy Windows consoles are cp1252).

.PARAMETER Local
    Bind to 127.0.0.1 (this PC only). Default is LAN (0.0.0.0). Alias: -LocalOnly.

.PARAMETER Port
    TCP port to serve on (1-65535). Default 8420. When -Port is omitted the
    environment variable PORT is honored if it is a valid integer in range.

.PARAMETER NoBrowser
    Do not auto-open a browser on this PC (passthrough to --no-browser).

.PARAMETER OpenFirewall
    Add an inbound Windows Firewall allow rule for the TCP port so LAN players
    can reach the server. Requires Administrator rights; if this shell is not
    elevated the script prints the exact elevated command and offers to
    self-elevate a one-shot helper (UAC prompt).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\serve.ps1
    LAN mode on port 8420; auto-opens the local browser.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\serve.ps1 -OpenFirewall
    LAN mode and open the firewall so other PCs can connect.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\serve.ps1 -Local -Port 9000 -NoBrowser
    This-PC-only on port 9000, no browser auto-open.
#>
[CmdletBinding()]
param(
    [Alias('LocalOnly')]
    [switch]$Local,

    [ValidateRange(1, 65535)]
    [int]$Port = 8420,

    [switch]$NoBrowser,

    [switch]$OpenFirewall,

    # Internal: used by the self-elevation path to add ONLY the firewall rule.
    [switch]$AddFirewallRuleOnly,
    [string]$StatusFile,
    [switch]$NoVllm
)

# ------------------------------------------------------------------ helpers
function Write-Line {
    param([string]$Message = '')
    Write-Host $Message
}

function Get-EnvVariable {
    param (
        [string]$Name,
        [string]$Default
    )
    $envPath = Join-Path $repoRoot '.env'
    if (Test-Path -LiteralPath $envPath) {
        $lines = Get-Content -LiteralPath $envPath -ErrorAction SilentlyContinue
        if ($null -ne $lines) {
            foreach ($line in $lines) {
                $line = $line.Trim()
                if ($line.StartsWith('#') -or $line -notlike '*=*') { continue }
                $parts = $line.Split('=', 2)
                $k = $parts[0].Trim()
                $v = $parts[1].Trim().Trim("'").Trim('"')
                if ($k -eq $Name) {
                    return $v
                }
            }
        }
    }
    $envVal = [System.Environment]::GetEnvironmentVariable($Name)
    if ($null -ne $envVal -and $envVal -ne "") {
        return $envVal
    }
    return $Default
}

function Start-VllmServer {
    param (
        [string]$PythonExe,
        [string]$RepoRoot,
        [switch]$NoVllm
    )
    
    $script:VllmAvailable = $false
    $startVllm = Get-EnvVariable -Name 'START_VLLM' -Default 'true'
    if ($NoVllm -or $startVllm.ToLower() -eq 'false' -or $startVllm -eq '0') {
        Write-Line '[vllm] Startup skipped (disabled by parameter or config).'
        return
    }

    $vllmModel = Get-EnvVariable -Name 'VLLM_MODEL' -Default 'Qwen/Qwen2.5-7B-Instruct'
    $vllmPort = Get-EnvVariable -Name 'VLLM_PORT' -Default '8000'

    $portInUse = $false
    try {
        $connection = [System.Net.Sockets.TcpClient]::new()
        $ar = $connection.BeginConnect('127.0.0.1', [int]$vllmPort, $null, $null)
        $wait = $ar.AsyncWaitHandle.WaitOne(200)
        if ($connection.Connected) {
            $portInUse = $true
            $connection.Close()
        }
    } catch {
        # ignore
    }

    if ($portInUse) {
        $script:VllmAvailable = $true
        Write-Line "[vllm] Port $vllmPort is already in use. Assuming vLLM server is already running."
        return
    }

    $hasVllm = $false
    try {
        $result = Start-Process -FilePath $PythonExe -ArgumentList @('-c', 'import vllm') -NoNewWindow -Wait -PassThru -ErrorAction SilentlyContinue
        if ($result.ExitCode -eq 0) {
            $hasVllm = $true
        }
    } catch {
        # ignore
    }

    if (-not $hasVllm) {
        Write-Line '[vllm] vLLM module not found in Python environment. Skipping startup.'
        return
    }

    Write-Line "[vllm] Starting vLLM server with model '$vllmModel' on port $vllmPort..."
    $vllmArgs = @(
        '-m', 'vllm.entrypoints.openai.api_server',
        '--model', $vllmModel,
        '--port', $vllmPort
    )
    Start-Process -FilePath $PythonExe -ArgumentList $vllmArgs -WorkingDirectory $RepoRoot -WindowStyle Minimized
    $script:VllmAvailable = $true
    Write-Line '[vllm] vLLM server started in background.'
}

function Enable-VllmFlavor {
    <#
    Point optional serving-layer prose at local OpenAI-compatible vLLM.
    Explicit SOCIAL_LLM / FLAVOR_LLM settings always take precedence.
    #>
    param(
        [string]$Model,
        [string]$Port
    )

    $baseUrl = "http://127.0.0.1:$Port/v1"
    $socialMode = Get-EnvVariable -Name 'SOCIAL_LLM' -Default ''
    if ([string]::IsNullOrWhiteSpace($socialMode)) {
        $env:SOCIAL_LLM = 'local'
        $env:SOCIAL_LLM_BASE_URL = $baseUrl
        $env:SOCIAL_LLM_LOCAL_MODEL = $Model
        Write-Line "[vllm] Social posts and 1:1 replies will use $baseUrl."
    } else {
        Write-Line '[vllm] Keeping explicit SOCIAL_LLM configuration.'
    }

    $flavorMode = Get-EnvVariable -Name 'FLAVOR_LLM' -Default ''
    if ([string]::IsNullOrWhiteSpace($flavorMode)) {
        $env:FLAVOR_LLM = 'local'
        $env:FLAVOR_LLM_BASE_URL = $baseUrl
        $env:FLAVOR_LLM_LOCAL_MODEL = $Model
        Write-Line "[vllm] Campaign decision copy will use $baseUrl."
    } else {
        Write-Line '[vllm] Keeping explicit FLAVOR_LLM configuration.'
    }
}

function Get-RuleName {
    param([int]$Port)
    return "esports-sim web (TCP $Port)"
}

function Test-IsAdmin {
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($id)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

function Get-QuotedToken {
    param([string]$Text)
    if ($Text -match '\s') { return '"' + $Text + '"' }
    return $Text
}

function Format-Command {
    param([string]$Exe, [string[]]$ArgList)
    $parts = @()
    $parts += (Get-QuotedToken $Exe)
    foreach ($a in $ArgList) { $parts += (Get-QuotedToken $a) }
    return ($parts -join ' ')
}

function Test-PythonRuns {
    # Confirm a candidate interpreter actually runs (skips dead Store stubs).
    param([string]$Exe, [string[]]$Prefix)
    try {
        $probe = @()
        $probe += $Prefix
        $probe += '--version'
        & $Exe @probe *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Resolve-PythonLauncher {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    # 1) Preferred: the repo's Windows venv. Trust it if present.
    $venvPython = Join-Path $RepoRoot '.venv-win\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) {
        return [pscustomobject]@{
            Exe    = $venvPython
            Prefix = @()
            Label  = 'repo venv (.venv-win)'
            IsVenv = $true
        }
    }

    # 2) A real 'python' on PATH - skip the Microsoft Store app-execution stub
    #    (a 0-byte reparse point under \WindowsApps\ that just opens the Store),
    #    and require that it actually reports a version.
    $pythonCandidates = Get-Command -Name 'python' -CommandType Application -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -and ($_.Source -notmatch '\\WindowsApps\\') }
    foreach ($c in $pythonCandidates) {
        if (Test-PythonRuns -Exe $c.Source -Prefix @()) {
            return [pscustomobject]@{
                Exe    = $c.Source
                Prefix = @()
                Label  = 'python on PATH'
                IsVenv = $false
            }
        }
    }

    # 3) The py launcher (py -3), validated the same way.
    $pyCmd = Get-Command -Name 'py' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($pyCmd -and $pyCmd.Source -and (Test-PythonRuns -Exe $pyCmd.Source -Prefix @('-3'))) {
        return [pscustomobject]@{
            Exe    = $pyCmd.Source
            Prefix = @('-3')
            Label  = 'py launcher (py -3)'
            IsVenv = $false
        }
    }

    return $null
}

function Get-ActiveNetworkCategories {
    # Returns an array of active connection-profile categories
    # (e.g. 'Public','Private','DomainAuthenticated'), or $null if unknown.
    if (-not (Get-Command -Name 'Get-NetConnectionProfile' -ErrorAction SilentlyContinue)) {
        return $null
    }
    try {
        $cats = @(Get-NetConnectionProfile -ErrorAction Stop |
            ForEach-Object { "$($_.NetworkCategory)" })
        if ($cats.Count -eq 0) { return $null }
        return $cats
    } catch {
        return $null
    }
}

function Add-EsportsFirewallRule {
    # Idempotent. Adds an inbound TCP allow rule for the Private+Domain profiles.
    # Returns [pscustomobject] @{ Success = [bool]; Message = [string] }.
    # Does not print - the caller surfaces Message so both the in-process and
    # the elevated-helper paths report identically.
    param([Parameter(Mandatory = $true)][int]$Port)

    $ruleName = Get-RuleName -Port $Port
    $haveCmdlets = [bool](Get-Command -Name 'New-NetFirewallRule' -ErrorAction SilentlyContinue)

    if ($haveCmdlets) {
        $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
        if ($existing) {
            return [pscustomobject]@{ Success = $true; Message = "Rule '$ruleName' already present - left unchanged." }
        }
        try {
            $params = @{
                DisplayName = $ruleName
                Direction   = 'Inbound'
                Action      = 'Allow'
                Protocol    = 'TCP'
                LocalPort   = $Port
                Profile     = @('Private', 'Domain')
                ErrorAction = 'Stop'
            }
            New-NetFirewallRule @params | Out-Null
            return [pscustomobject]@{ Success = $true; Message = "Added inbound allow rule '$ruleName' (TCP $Port; Private+Domain profiles)." }
        } catch {
            # Fall through to the netsh fallback below.
        }
    }

    # Fallback for hosts without the NetSecurity cmdlets. Scope matches the
    # cmdlet path (profile=private,domain) so both paths behave identically.
    & netsh advfirewall firewall add rule "name=$ruleName" dir=in action=allow protocol=TCP "localport=$Port" profile=private,domain | Out-Null
    if ($LASTEXITCODE -eq 0) {
        return [pscustomobject]@{ Success = $true; Message = "Added inbound allow rule '$ruleName' via netsh (TCP $Port; Private+Domain profiles)." }
    }
    return [pscustomobject]@{ Success = $false; Message = "Failed to add firewall rule (netsh exit $LASTEXITCODE)." }
}

# ---------------------------------------------------------------------------
# Internal mode: add ONLY the firewall rule (invoked elevated by the parent).
# Writes its outcome to -StatusFile so the parent can surface it, then exits.
# ---------------------------------------------------------------------------
if ($AddFirewallRuleOnly) {
    if (-not (Test-IsAdmin)) {
        if ($StatusFile) { Set-Content -LiteralPath $StatusFile -Value 'ERR: elevated helper is not running as Administrator.' -Encoding Ascii }
        exit 3
    }
    $res = Add-EsportsFirewallRule -Port $Port
    if ($StatusFile) {
        if ($res.Success) { $tag = 'OK: ' } else { $tag = 'ERR: ' }
        Set-Content -LiteralPath $StatusFile -Value ($tag + $res.Message) -Encoding Ascii
    }
    if ($res.Success) { exit 0 } else { exit 1 }
}

# --------------------------------------------------------------------- main
# scripts/serve.ps1 lives one level below the repo root.
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $repoRoot -or -not (Test-Path -LiteralPath $repoRoot)) {
    Write-Line "[error] Could not determine the repository root from '$PSScriptRoot'."
    exit 1
}

# Honor $env:PORT only when -Port was not explicitly supplied on the command
# line ([ValidateRange] does not apply to defaults, so validate it here).
if (-not $PSBoundParameters.ContainsKey('Port') -and $env:PORT) {
    $envPort = 0
    if ([int]::TryParse($env:PORT, [ref]$envPort) -and $envPort -ge 1 -and $envPort -le 65535) {
        $Port = $envPort
    } else {
        Write-Line "[warn] Ignoring PORT='$($env:PORT)' (not an integer in 1-65535); using $Port."
    }
}

$py = Resolve-PythonLauncher -RepoRoot $repoRoot
if (-not $py) {
    Write-Line '[error] No usable Python interpreter found.'
    Write-Line '        Looked for (in order):'
    Write-Line "          1) $repoRoot\.venv-win\Scripts\python.exe"
    Write-Line '          2) "python" on PATH (Microsoft Store alias ignored)'
    Write-Line '          3) "py -3" launcher on PATH'
    Write-Line ''
    Write-Line '        Fix (from the repo root): create the Windows venv and install the app:'
    Write-Line '          py -3 -m venv .venv-win'
    Write-Line '          .venv-win\Scripts\python.exe -m pip install -e ".[web]"'
    exit 1
}

if ($Local) {
    $bindHost  = '127.0.0.1'
    $modeLabel = 'Local-only (this PC)'
} else {
    $bindHost  = '0.0.0.0'
    $modeLabel = 'LAN (share with players on your network)'
}
$localUrl = "http://127.0.0.1:$Port"

# Build the argument vector passed through to the Python module.
$moduleArgs = @('-m', 'esports_sim', '--web', '--host', $bindHost, '--port', "$Port")
if ($NoBrowser) { $moduleArgs += '--no-browser' }
$allArgs = @()
$allArgs += $py.Prefix
$allArgs += $moduleArgs

# ----------------------------------------------------------- pre-flight
$bar = ('=' * 62)
$sub = ('-' * 62)
Write-Line $bar
Write-Line ' esports-sim web launcher'
Write-Line $bar
Write-Line " Python   : $($py.Label)"
Write-Line "            $($py.Exe)"
Write-Line " Mode     : $modeLabel"
Write-Line " Bind     : ${bindHost}:$Port"
Write-Line " This PC  : $localUrl"
if ($Local) {
    Write-Line ' Share    : (local-only mode - not reachable from other PCs)'
} else {
    Write-Line ' Share    : the "(LAN)" URL the server prints just below'
}
if ($NoBrowser) {
    Write-Line ' Browser  : disabled (--no-browser)'
} else {
    Write-Line ' Browser  : auto-open on this PC'
}
if ($OpenFirewall) {
    Write-Line " Firewall : add inbound TCP $Port rule (requested)"
} else {
    Write-Line ' Firewall : not requested (add -OpenFirewall for LAN players)'
}
Write-Line " Command  : $(Format-Command -Exe $py.Exe -ArgList $allArgs)"
Write-Line $sub

if (-not $py.IsVenv) {
    Write-Line ' [note] Not using the repo venv (.venv-win). If you hit ModuleNotFoundError,'
    Write-Line '        install deps:  <python> -m pip install -e ".[web]"'
    Write-Line $sub
}

# ------------------------------------------------------------ firewall
if ($OpenFirewall) {
    if ($Local) {
        Write-Line '[firewall] -OpenFirewall ignored: local-only mode never accepts LAN connections.'
    } else {
        # Warn up front if the active network is Public: a Private+Domain rule
        # matches nothing there, so the rule would be a silent no-op for peers.
        $cats = Get-ActiveNetworkCategories
        if ($null -ne $cats) {
            Write-Line ("[firewall] Active network profile(s): {0}" -f ($cats -join ', '))
            if ($cats -contains 'Public') {
                Write-Line '[firewall] WARNING: your active network is Public. The allow rule covers only'
                Write-Line '           the Private and Domain profiles, so LAN peers will still be blocked'
                Write-Line '           until you set the network to Private, e.g. in an elevated PowerShell:'
                Write-Line '             Set-NetConnectionProfile -InterfaceAlias <name> -NetworkCategory Private'
                Write-Line '           (find <name> with: Get-NetConnectionProfile)'
            }
        }

        if (Test-IsAdmin) {
            $res = Add-EsportsFirewallRule -Port $Port
            Write-Line "[firewall] $($res.Message)"
            if (-not $res.Success) {
                Write-Line '[firewall] LAN peers cannot connect until an inbound rule for the port exists.'
            }
        } else {
            $ruleName = Get-RuleName -Port $Port
            $manualPs    = "New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private,Domain"
            $manualNetsh = "netsh advfirewall firewall add rule name=""$ruleName"" dir=in action=allow protocol=TCP localport=$Port profile=private,domain"

            Write-Line '[firewall] Adding an inbound rule needs Administrator rights (this shell is not elevated).'
            Write-Line '[firewall] Run ONE of these once in an elevated (Run as administrator) PowerShell:'
            Write-Line ''
            Write-Line "    $manualPs"
            Write-Line '  - or, using netsh:'
            Write-Line "    $manualNetsh"
            Write-Line ''
            Write-Line '[firewall] Trying to self-elevate a one-shot helper now (accept the UAC prompt)...'

            $statusFile = Join-Path ([IO.Path]::GetTempPath()) ("esports-sim-fw-{0}.txt" -f ([guid]::NewGuid().ToString('N')))
            $scriptPath = $PSCommandPath
            # Pass ArgumentList as ONE pre-quoted string so the (possibly spaced)
            # script path survives; an array would be space-joined unquoted.
            $innerArgs = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -AddFirewallRuleOnly -Port {1} -StatusFile "{2}"' -f $scriptPath, $Port, $statusFile
            $ensured = $false
            try {
                $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $innerArgs `
                    -Verb RunAs -Wait -PassThru -ErrorAction Stop
                if ($proc.ExitCode -eq 0) { $ensured = $true }
            } catch {
                Write-Line "[firewall] Self-elevation did not complete: $($_.Exception.Message)"
            }

            $status = $null
            if (Test-Path -LiteralPath $statusFile) {
                $status = (Get-Content -LiteralPath $statusFile -Raw -ErrorAction SilentlyContinue)
                Remove-Item -LiteralPath $statusFile -Force -ErrorAction SilentlyContinue
            }
            if ($status) { Write-Line "[firewall] $($status.Trim())" }

            if ($ensured) {
                Write-Line '[firewall] Inbound rule ensured via the elevated helper.'
            } else {
                Write-Line '[firewall] Rule NOT added automatically (elevation declined or failed).'
                Write-Line '[firewall] Run one of the commands above once; LAN peers cannot connect until it exists.'
            }
        }
    }
    Write-Line $sub
}

# -------------------------------------------------------------- launch
$vllmPort = Get-EnvVariable -Name 'VLLM_PORT' -Default '8000'
$vllmModel = Get-EnvVariable -Name 'VLLM_MODEL' -Default 'Qwen/Qwen2.5-7B-Instruct'
Start-VllmServer -PythonExe $py.Exe -RepoRoot $repoRoot -NoVllm $NoVllm
if ($script:VllmAvailable) {
    Enable-VllmFlavor -Model $vllmModel -Port $vllmPort
}
Write-Line ' Starting server... press Ctrl+C to stop.'
Write-Line $bar

$exe = $py.Exe
$exitCode = 0
Push-Location -LiteralPath $repoRoot
try {
    & $exe @allArgs
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($null -eq $exitCode) { $exitCode = 0 }
if ($exitCode -ne 0) {
    Write-Line ''
    Write-Line "Server exited with code $exitCode."
    Write-Line 'If that was an import error, install the web extras and retry:'
    Write-Line '  .venv-win\Scripts\python.exe -m pip install -e ".[web]"'
}
exit $exitCode
