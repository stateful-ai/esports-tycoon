#Requires -Version 5.1
<#
.SYNOPSIS
    One-shot (idempotent) Cloudflare provisioning for remote play:
    Tunnel + DNS + Zero Trust Access allow-list for esports-sim.

.DESCRIPTION
    Uses the Cloudflare API (CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID from
    the repo .env) to set up everything needed so friends outside your LAN can
    play WITHOUT your PC being exposed to the open internet:

      1. A remotely-managed Cloudflare Tunnel named "esports-sim".
      2. Tunnel ingress: <Hostname> -> http://127.0.0.1:<Port> (everything
         else 404s).
      3. A proxied CNAME record for <Hostname> pointing at the tunnel.
      4. Zero Trust Access: One-Time PIN login enabled, a self-hosted Access
         app on <Hostname>, and an allow policy restricted to the given
         emails. Anyone not on the list never reaches your PC.

    Safe to re-run: every step is find-or-create / update-in-place.

    REQUIRED API TOKEN PERMISSIONS (dashboard: My Profile -> API Tokens, or
    Account API Tokens):
      - Account | Cloudflare Tunnel | Edit
      - Account | Access: Apps and Policies | Edit
      - Account | Access: Organizations, Identity Providers, and Groups | Edit
      - Zone    | DNS | Edit   (zone: your apex, e.g. stateful-ai.com)
    Zero Trust must also be enabled once on the account (free plan is fine):
    https://one.dash.cloudflare.com -> pick a team name.

    All console output is ASCII-only.

.PARAMETER Hostname
    Public hostname to serve the game on. Default: esports.stateful-ai.com.

.PARAMETER Port
    Local port the game listens on. Default 8420.

.PARAMETER AllowedEmails
    Emails allowed through Cloudflare Access. Merged with the comma-separated
    REMOTE_PLAY_ALLOWED_EMAILS value from .env. The policy is REPLACED with
    exactly this merged list on every run, so removing an email from both
    sources revokes them.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\setup_remote_play.ps1 `
        -AllowedEmails you@example.com,friend@example.com
#>
[CmdletBinding()]
param(
    [string]$Hostname = 'esports.stateful-ai.com',

    [ValidateRange(1, 65535)]
    [int]$Port = 8420,

    [string[]]$AllowedEmails = @()
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

$token = Get-DotenvValue 'CLOUDFLARE_API_TOKEN'
$account = Get-DotenvValue 'CLOUDFLARE_ACCOUNT_ID'
if (-not $token -or -not $account) {
    Write-Line '[error] CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must be set in .env.'
    exit 1
}

$base = 'https://api.cloudflare.com/client/v4'
$headers = @{ Authorization = "Bearer $token" }

function Invoke-CfApi {
    # Returns the parsed response. On HTTP error, returns an object with
    # success=$false plus _status/_body so callers can print a useful message.
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        $Body = $null
    )
    $params = @{ Method = $Method; Uri = ($base + $Path); Headers = $headers }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 12)
        $params.ContentType = 'application/json'
    }
    try {
        return Invoke-RestMethod @params
    } catch {
        $status = 0
        $text = $_.Exception.Message
        if ($_.Exception.Response) {
            $status = [int]$_.Exception.Response.StatusCode
            try {
                $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
                $text = $reader.ReadToEnd()
            } catch {}
        }
        return [pscustomobject]@{ success = $false; _status = $status; _body = $text; _path = $Path }
    }
}

function Assert-CfOk {
    param($Resp, [string]$What)
    if ($Resp.success) { return }
    Write-Line "[error] $What failed."
    if ($Resp._status -eq 403) {
        Write-Line '        HTTP 403: the API token is missing a permission for this step.'
        Write-Line '        Required token permissions are listed in this script header.'
    } elseif ($Resp._status) {
        Write-Line "        HTTP $($Resp._status): $($Resp._body)"
    } elseif ($Resp.errors) {
        foreach ($e in $Resp.errors) { Write-Line "        [$($e.code)] $($e.message)" }
        if (($Resp.errors | Where-Object { $_.message -like '*not_enabled*' })) {
            Write-Line '        Zero Trust is not enabled yet. One-time step: open'
            Write-Line '        https://one.dash.cloudflare.com , pick a team name (free plan), re-run.'
        }
    }
    exit 1
}

# ---------------------------------------------------------------- allow-list
$fromEnv = Get-DotenvValue 'REMOTE_PLAY_ALLOWED_EMAILS'
$emails = @()
if ($fromEnv) { $emails += ($fromEnv -split ',') }
$emails += $AllowedEmails
$emails = @($emails | ForEach-Object { $_.Trim().ToLowerInvariant() } |
    Where-Object { $_ -match '^[^@\s]+@[^@\s]+\.[^@\s]+$' } | Sort-Object -Unique)
if ($emails.Count -eq 0) {
    Write-Line '[error] No allowed emails. Pass -AllowedEmails or set'
    Write-Line '        REMOTE_PLAY_ALLOWED_EMAILS=you@x.com,friend@y.com in .env.'
    Write-Line '        Without an allow-list the Access app would lock everyone out.'
    exit 1
}

$bar = ('=' * 62)
Write-Line $bar
Write-Line ' esports-sim remote play setup (Cloudflare Tunnel + Access)'
Write-Line $bar
Write-Line " Hostname : $Hostname"
Write-Line " Origin   : http://127.0.0.1:$Port"
Write-Line " Allowed  : $($emails -join ', ')"
Write-Line $bar

# --------------------------------------------------------------------- zone
$apex = ($Hostname -split '\.', 2)[1]
$zones = Invoke-CfApi GET "/zones?name=$apex"
Assert-CfOk $zones 'Zone lookup'
if (-not $zones.result -or $zones.result.Count -eq 0) {
    Write-Line "[error] Zone '$apex' not found on this Cloudflare account."
    exit 1
}
$zoneId = $zones.result[0].id
Write-Line "[zone] $apex -> $zoneId"

# ------------------------------------------------------------------- tunnel
$tunnelName = 'esports-sim'
$found = Invoke-CfApi GET "/accounts/$account/cfd_tunnel?is_deleted=false&name=$tunnelName"
Assert-CfOk $found 'Tunnel lookup'
if ($found.result -and $found.result.Count -gt 0) {
    $tunnel = $found.result[0]
    Write-Line "[tunnel] Reusing existing tunnel '$tunnelName' ($($tunnel.id))."
} else {
    $created = Invoke-CfApi POST "/accounts/$account/cfd_tunnel" @{
        name = $tunnelName; config_src = 'cloudflare'
    }
    Assert-CfOk $created "Tunnel create ('$tunnelName')"
    $tunnel = $created.result
    Write-Line "[tunnel] Created tunnel '$tunnelName' ($($tunnel.id))."
}
$tunnelId = $tunnel.id

# Ingress: our hostname -> local game port; everything else 404.
$cfg = Invoke-CfApi PUT "/accounts/$account/cfd_tunnel/$tunnelId/configurations" @{
    config = @{
        ingress = @(
            @{ hostname = $Hostname; service = "http://127.0.0.1:$Port" },
            @{ service = 'http_status:404' }
        )
    }
}
Assert-CfOk $cfg 'Tunnel ingress configuration'
Write-Line "[tunnel] Ingress set: $Hostname -> http://127.0.0.1:$Port (else 404)."

# ---------------------------------------------------------------------- dns
$target = "$tunnelId.cfargotunnel.com"
$recs = Invoke-CfApi GET "/zones/$zoneId/dns_records?type=CNAME&name=$Hostname"
Assert-CfOk $recs 'DNS record lookup'
$recBody = @{ type = 'CNAME'; name = $Hostname; content = $target; proxied = $true; ttl = 1 }
if ($recs.result -and $recs.result.Count -gt 0) {
    $rec = $recs.result[0]
    if ($rec.content -eq $target -and $rec.proxied) {
        Write-Line "[dns] CNAME $Hostname already points at the tunnel."
    } else {
        $upd = Invoke-CfApi PUT "/zones/$zoneId/dns_records/$($rec.id)" $recBody
        Assert-CfOk $upd 'DNS record update'
        Write-Line "[dns] Updated CNAME $Hostname -> $target (proxied)."
    }
} else {
    $mk = Invoke-CfApi POST "/zones/$zoneId/dns_records" $recBody
    Assert-CfOk $mk 'DNS record create'
    Write-Line "[dns] Created CNAME $Hostname -> $target (proxied)."
}

# ------------------------------------------------------------------- access
# One-Time PIN login method (friends get a 6-digit email code, no accounts).
$idps = Invoke-CfApi GET "/accounts/$account/access/identity_providers"
Assert-CfOk $idps 'Access identity provider lookup'
$hasOtp = $false
foreach ($p in @($idps.result)) { if ($p.type -eq 'onetimepin') { $hasOtp = $true } }
if ($hasOtp) {
    Write-Line '[access] One-Time PIN login already enabled.'
} else {
    $otp = Invoke-CfApi POST "/accounts/$account/access/identity_providers" @{
        name = 'One-time PIN'; type = 'onetimepin'; config = @{}
    }
    Assert-CfOk $otp 'One-Time PIN enable'
    Write-Line '[access] Enabled One-Time PIN email login.'
}

$appName = 'esports-sim'
$apps = Invoke-CfApi GET "/accounts/$account/access/apps"
Assert-CfOk $apps 'Access app lookup'
$app = $null
foreach ($a in @($apps.result)) {
    if ($a.domain -eq $Hostname -or $a.name -eq $appName) { $app = $a; break }
}
$appBody = @{
    name                     = $appName
    domain                   = $Hostname
    type                     = 'self_hosted'
    session_duration         = '24h'
    auto_redirect_to_identity = $false
    app_launcher_visible     = $false
}
if ($app) {
    $upd = Invoke-CfApi PUT "/accounts/$account/access/apps/$($app.id)" $appBody
    Assert-CfOk $upd 'Access app update'
    $app = $upd.result
    Write-Line "[access] Updated Access app '$appName' on $Hostname."
} else {
    $mk = Invoke-CfApi POST "/accounts/$account/access/apps" $appBody
    Assert-CfOk $mk 'Access app create'
    $app = $mk.result
    Write-Line "[access] Created Access app '$appName' on $Hostname."
}

$include = @()
foreach ($e in $emails) { $include += @{ email = @{ email = $e } } }
$policyName = 'friends allow-list'
$pols = Invoke-CfApi GET "/accounts/$account/access/apps/$($app.id)/policies"
Assert-CfOk $pols 'Access policy lookup'
$pol = $null
foreach ($p in @($pols.result)) { if ($p.name -eq $policyName) { $pol = $p; break } }
$polBody = @{
    name = $policyName; decision = 'allow'; include = $include; precedence = 1
}
if ($pol) {
    $upd = Invoke-CfApi PUT "/accounts/$account/access/apps/$($app.id)/policies/$($pol.id)" $polBody
    Assert-CfOk $upd 'Access policy update'
    Write-Line "[access] Policy '$policyName' now allows: $($emails -join ', ')."
} else {
    $mk = Invoke-CfApi POST "/accounts/$account/access/apps/$($app.id)/policies" $polBody
    Assert-CfOk $mk 'Access policy create'
    Write-Line "[access] Created policy '$policyName' allowing: $($emails -join ', ')."
}

# ------------------------------------------------------------------ wrap-up
Write-Line $bar
Write-Line ' Done. Next steps:'
Write-Line "   1. Start hosting:  powershell -ExecutionPolicy Bypass -File .\scripts\serve_tunnel.ps1"
Write-Line "   2. Friends visit:  https://$Hostname"
Write-Line '      They enter their email, get a 6-digit PIN, then use your'
Write-Line '      lobby code in the game as usual.'
Write-Line '   To add/remove friends later: re-run this script with the new'
Write-Line '   full email list (or edit REMOTE_PLAY_ALLOWED_EMAILS in .env).'
Write-Line $bar
