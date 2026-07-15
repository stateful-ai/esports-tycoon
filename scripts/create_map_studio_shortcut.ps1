#Requires -Version 5.1
$repoRoot = Split-Path -Parent $PSScriptRoot
$batPath = Join-Path $repoRoot 'launch-map-studio.bat'
$logoSource = Join-Path $repoRoot 'assets\logos\logo_0.webp'
$iconPath = Join-Path $repoRoot 'scripts\Map Studio.ico'
$shortcutPath = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Map Studio.lnk'

# Convert logo to .ico if PIL/pillow is installed
$python = Join-Path $repoRoot '.venv-win\Scripts\python.exe'
if (Test-Path -LiteralPath $python) {
    $tempScript = Join-Path $repoRoot 'scripts\temp_gen_icon.py'
    $iconCode = @'
from pathlib import Path
import sys
from PIL import Image

source, destination = map(Path, sys.argv[1:3])
try:
    image = Image.open(source).convert("RGBA")
    image.save(destination, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
except Exception as e:
    print(f"Icon generation skipped: {e}")
'@
    Set-Content -LiteralPath $tempScript -Value $iconCode -Encoding UTF8
    & $python $tempScript $logoSource $iconPath
    Remove-Item -LiteralPath $tempScript -Force
}

# Create shortcut that can be pinned
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
# Prefix target with cmd.exe to make it pinnable by Windows
$shortcut.TargetPath = 'cmd.exe'
$shortcut.Arguments = "/c `"$batPath`""
$shortcut.WorkingDirectory = $repoRoot
if (Test-Path -LiteralPath $iconPath) {
    $shortcut.IconLocation = $iconPath
}
$shortcut.Description = 'Launch Map Studio'
$shortcut.Save()

Write-Host ''
Write-Host 'Map Studio Start Menu Shortcut Created!'
Write-Host "  Shortcut Location : $shortcutPath"
Write-Host 'You can now find "Map Studio" in your Windows Start Menu, right-click it, and choose "Pin to taskbar"!'
Write-Host ''
