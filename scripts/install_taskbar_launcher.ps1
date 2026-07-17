#Requires -Version 5.1
<#
.SYNOPSIS
    Install a Start-menu/taskbar-ready launcher for ESports Simulator.

.DESCRIPTION
    Creates an isolated local Python runtime, a small Windows launcher, and a
    Start-menu shortcut. Every launch fast-forwards the configured main
    checkout from origin/main before starting the web server. If main moved,
    the launcher restarts its owned server before opening the browser.

.PARAMETER Port
    LAN playing port for the taskbar instance. Defaults to 8420.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\install_taskbar_launcher.ps1
#>
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8420,

    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'ESports Simulator'),

    [switch]$SkipShortcut
)

$ErrorActionPreference = 'Stop'
$portWasExplicit = $PSBoundParameters.ContainsKey('Port')
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeSource = Join-Path $PSScriptRoot 'taskbar_launcher.ps1'
$csharpSource = Join-Path $PSScriptRoot 'taskbar_launcher.cs'
$venvRoot = Join-Path $InstallRoot 'venv'
$python = Join-Path $venvRoot 'Scripts\python.exe'
$icon = Join-Path $InstallRoot 'ESports Simulator.ico'
$launcherExe = Join-Path $InstallRoot 'ESports Simulator.exe'
$runtimeTarget = Join-Path $InstallRoot 'taskbar_launcher.ps1'
$configTarget = Join-Path $InstallRoot 'launcher.json'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw ('Command failed with exit code {0}: {1} {2}' -f $LASTEXITCODE, $FilePath, ($ArgumentList -join ' '))
    }
}

if (-not (Test-Path -LiteralPath $runtimeSource) -or -not (Test-Path -LiteralPath $csharpSource)) {
    throw 'Launcher source files are missing from scripts/.'
}
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null

$uvCommand = Get-Command -Name 'uv.exe' -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not (Test-Path -LiteralPath $python)) {
    if ($uvCommand) {
        Invoke-Checked -FilePath $uvCommand.Source -ArgumentList @(
            'venv', '--seed', '--python', '3.13', $venvRoot
        )
    } else {
        $pyCommand = Get-Command -Name 'py.exe' -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if (-not $pyCommand) {
            throw 'Install uv or Python 3.12+ before installing the taskbar launcher.'
        }
        $selectedVersion = $null
        foreach ($version in @('-3.13', '-3.12')) {
            $previousErrorPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                & $pyCommand.Source $version --version *> $null
                if ($LASTEXITCODE -eq 0) {
                    $selectedVersion = $version
                    break
                }
            } finally {
                $ErrorActionPreference = $previousErrorPreference
            }
        }
        if (-not $selectedVersion) {
            throw 'Python 3.12 or 3.13 is required to install the taskbar launcher.'
        }
        Invoke-Checked -FilePath $pyCommand.Source -ArgumentList @(
            $selectedVersion, '-m', 'venv', $venvRoot
        )
    }
}

$installTarget = $repoRoot + '[web]'
if ($uvCommand) {
    Invoke-Checked -FilePath $uvCommand.Source -ArgumentList @(
        'pip', 'install', '--python', $python, '-e', $installTarget, 'pillow'
    )
} else {
    Invoke-Checked -FilePath $python -ArgumentList @(
        '-m', 'pip', 'install', '-e', $installTarget, 'pillow'
    )
}

Copy-Item -LiteralPath $runtimeSource -Destination $runtimeTarget -Force
@{
    schema_version = 2
    repo_root = $repoRoot
    port = $Port
    port_is_default = (-not $portWasExplicit)
} |
    ConvertTo-Json |
    Set-Content -LiteralPath $configTarget -Encoding UTF8

$logoSource = Join-Path $repoRoot 'assets\logos\logo_0.webp'
$iconCode = @'
from pathlib import Path
import sys
from PIL import Image

source, destination = map(Path, sys.argv[1:3])
image = Image.open(source).convert(bytes([82, 71, 66, 65]).decode())
image.save(destination, format=bytes([73, 67, 79]).decode(), sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
'@
Invoke-Checked -FilePath $python -ArgumentList @('-c', $iconCode, $logoSource, $icon)

$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $csc)) {
    throw "The Windows C# compiler was not found: $csc"
}
Invoke-Checked -FilePath $csc -ArgumentList @(
    '/nologo',
    '/target:winexe',
    '/optimize+',
    '/reference:System.Windows.Forms.dll',
    "/win32icon:$icon",
    "/out:$launcherExe",
    $csharpSource
)

# Authenticode-sign the freshly built launcher so Windows (SmartScreen /
# Smart App Control / AV) trusts this machine's own binary. A self-signed
# certificate is created once and trusted locally; see scripts/sign_launcher.ps1.
$signScript = Join-Path $PSScriptRoot 'sign_launcher.ps1'
if (Test-Path -LiteralPath $signScript) {
    try {
        & $signScript -ExePath $launcherExe
    } catch {
        Write-Warning ("Could not sign the launcher: {0}" -f $_.Exception.Message)
        Write-Warning 'The launcher will still run but Windows may warn about an unknown publisher.'
    }
} else {
    Write-Warning "Signing helper not found ($signScript); launcher left unsigned."
}

if (-not $SkipShortcut) {
    $shortcutPath = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\ESports Simulator.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launcherExe
    $shortcut.WorkingDirectory = $InstallRoot
    $shortcut.IconLocation = $launcherExe + ',0'
    $shortcut.Description = 'Launch ESports Simulator'
    $shortcut.Save()
}

Write-Host ''
Write-Host 'ESports Simulator launcher installed.'
Write-Host "  Checkout : $repoRoot"
Write-Host "  Port     : $Port"
Write-Host "  Launcher : $launcherExe"
if (-not $SkipShortcut) {
    Write-Host 'Open Start, right-click ESports Simulator, and choose Pin to taskbar.'
}
