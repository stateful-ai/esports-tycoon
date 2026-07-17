#Requires -Version 5.1
<#
.SYNOPSIS
    Authenticode-sign the locally built ESports Simulator launcher.

.DESCRIPTION
    The taskbar launcher is compiled on this machine by csc.exe, so it ships
    unsigned. Modern Windows (SmartScreen, Smart App Control, most AV) blocks
    or quarantines unknown-publisher executables, which is why an unsigned
    launcher can suddenly stop opening.

    Because the binary is built and run on the same machine, the appropriate
    fix is a self-signed code-signing certificate that is trusted LOCALLY:
    the certificate is created once in the current user's personal store,
    added to the current user's Trusted Root and Trusted Publishers stores,
    and reused on every rebuild. The launcher is then signed with SHA-256 and
    (best effort) RFC-3161 timestamped so the signature outlives the cert.

    This does NOT build Microsoft SmartScreen cloud reputation and is not a
    substitute for a purchased OV/EV certificate when DISTRIBUTING software.
    It only makes the current machine trust a binary it built itself. To use a
    real certificate instead, pass -Thumbprint (an installed cert) or
    -PfxPath / -PfxPassword.

.PARAMETER ExePath
    Path to the compiled launcher .exe to sign.

.PARAMETER CertSubject
    Subject/CN of the self-signed certificate. Reused across rebuilds.

.PARAMETER Thumbprint
    Use an existing code-signing certificate (from Cert:\CurrentUser\My)
    instead of creating a self-signed one. Skips local-trust installation.

.PARAMETER PfxPath
    Sign with a certificate loaded from a .pfx file instead of the store.

.PARAMETER PfxPassword
    Password for -PfxPath, as a SecureString.

.PARAMETER TimestampServer
    RFC-3161 timestamp URL. Timestamping is best effort; signing still
    succeeds offline (the signature is just not countersigned).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\sign_launcher.ps1 `
        -ExePath "$env:LOCALAPPDATA\ESports Simulator\ESports Simulator.exe"
#>
[CmdletBinding(DefaultParameterSetName = 'SelfSigned')]
param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath,

    [Parameter(ParameterSetName = 'SelfSigned')]
    [string]$CertSubject = 'CN=ESports Simulator Launcher',

    [Parameter(Mandatory = $true, ParameterSetName = 'Thumbprint')]
    [string]$Thumbprint,

    [Parameter(Mandatory = $true, ParameterSetName = 'Pfx')]
    [string]$PfxPath,

    [Parameter(ParameterSetName = 'Pfx')]
    [System.Security.SecureString]$PfxPassword,

    [string]$TimestampServer = 'http://timestamp.digicert.com'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Launcher executable not found: $ExePath"
}

function Add-CertToStore {
    param(
        [Parameter(Mandatory = $true)][System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
        [Parameter(Mandatory = $true)][System.Security.Cryptography.X509Certificates.StoreName]$StoreName
    )

    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
        $StoreName, [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser)
    $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    try {
        $already = $store.Certificates.Find(
            [System.Security.Cryptography.X509Certificates.X509FindType]::FindByThumbprint,
            $Certificate.Thumbprint, $false)
        if ($already.Count -eq 0) {
            # Add only the public certificate (no private key) to trust stores.
            $public = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(
                $Certificate.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))
            $store.Add($public)
            Write-Host ("  Trusted certificate in CurrentUser\{0}." -f $StoreName)
        }
    } finally {
        $store.Close()
    }
}

# ---- Resolve the signing certificate -----------------------------------
$cert = $null
switch ($PSCmdlet.ParameterSetName) {
    'Thumbprint' {
        $clean = ($Thumbprint -replace '[^0-9A-Fa-f]', '')
        $cert = Get-ChildItem -Path Cert:\CurrentUser\My |
            Where-Object { $_.Thumbprint -eq $clean } |
            Select-Object -First 1
        if (-not $cert) {
            throw "No certificate with thumbprint $clean in Cert:\CurrentUser\My."
        }
        if (-not $cert.HasPrivateKey) {
            throw "Certificate $clean has no private key; cannot sign with it."
        }
    }
    'Pfx' {
        if (-not (Test-Path -LiteralPath $PfxPath)) {
            throw "PFX file not found: $PfxPath"
        }
        if ($PfxPassword) {
            $cert = Get-PfxCertificate -FilePath $PfxPath -Password $PfxPassword
        } else {
            $cert = Get-PfxCertificate -FilePath $PfxPath
        }
    }
    default {
        # Reuse an existing, currently-valid self-signed cert if present.
        $now = Get-Date
        $cert = Get-ChildItem -Path Cert:\CurrentUser\My |
            Where-Object {
                $_.Subject -eq $CertSubject -and
                $_.HasPrivateKey -and
                $_.NotAfter -gt $now -and
                $_.NotBefore -le $now -and
                ($_.EnhancedKeyUsageList.ObjectId -contains '1.3.6.1.5.5.7.3.3')
            } |
            Sort-Object NotAfter -Descending |
            Select-Object -First 1

        if (-not $cert) {
            Write-Host "Creating self-signed code-signing certificate ($CertSubject)..."
            $cert = New-SelfSignedCertificate `
                -Type CodeSigningCert `
                -Subject $CertSubject `
                -FriendlyName 'ESports Simulator Launcher signing key' `
                -CertStoreLocation Cert:\CurrentUser\My `
                -KeyExportPolicy NonExportable `
                -KeyUsage DigitalSignature `
                -KeySpec Signature `
                -HashAlgorithm SHA256 `
                -NotAfter (Get-Date).AddYears(5)
        }

        # Trust it locally so Authenticode / SmartScreen accept the signature.
        Add-CertToStore -Certificate $cert `
            -StoreName ([System.Security.Cryptography.X509Certificates.StoreName]::Root)
        Add-CertToStore -Certificate $cert `
            -StoreName ([System.Security.Cryptography.X509Certificates.StoreName]::TrustedPublisher)
    }
}

Write-Host ("Signing {0}" -f $ExePath)
Write-Host ("  Certificate : {0}" -f $cert.Subject)
Write-Host ("  Thumbprint  : {0}" -f $cert.Thumbprint)

# ---- Sign --------------------------------------------------------------
$signArgs = @{
    FilePath      = $ExePath
    Certificate   = $cert
    HashAlgorithm = 'SHA256'
}

$result = $null
try {
    $result = Set-AuthenticodeSignature @signArgs -TimestampServer $TimestampServer
    if ($result.Status -ne 'Valid') {
        throw $result.StatusMessage
    }
} catch {
    Write-Warning ("Timestamping failed ({0}); signing without a timestamp." -f $_.Exception.Message)
    $result = Set-AuthenticodeSignature @signArgs
}

if ($result.Status -ne 'Valid') {
    throw ("Signing failed: {0}" -f $result.StatusMessage)
}

Write-Host ("Signature status: {0}" -f $result.Status)
if ($result.TimeStamperCertificate) {
    Write-Host 'Signature is timestamped.'
}
