#Requires -Version 5.1

$ErrorActionPreference = 'Stop'

$configPath = Join-Path $PSScriptRoot 'launcher.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Launcher configuration is missing: $configPath"
}
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$repoRoot = [string]$config.repo_root
$port = [int]$config.port
$configVersion = if ($null -ne $config.schema_version) { [int]$config.schema_version } else { 1 }
if ($configVersion -lt 2) {
    # v1 had no way to distinguish an explicitly selected 8421 from its old
    # default. Migrate that legacy default to the standard LAN playing port;
    # users who intentionally want 8421 can reinstall with -Port 8421.
    if ($port -eq 8421) { $port = 8420 }
    @{
        schema_version = 2
        repo_root = $repoRoot
        port = $port
        port_is_default = $true
    } | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
}
$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
$url = "http://127.0.0.1:$port/"
$stdoutLog = Join-Path $PSScriptRoot 'server.stdout.log'
$stderrLog = Join-Path $PSScriptRoot 'server.stderr.log'
$pidFile = Join-Path $PSScriptRoot 'server.pid'
$commitFile = Join-Path $PSScriptRoot 'server.commit'
$dependencyStampFile = Join-Path $PSScriptRoot 'pyproject.sha256'
$mutex = New-Object System.Threading.Mutex($false, "Local\ESportsSimulatorTaskbarLauncher-$port")

function Write-Line {
    param([string]$Message = '')
    Write-Output $Message
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
    Write-Line '[vllm] vLLM server started in background.'
}

function Show-LauncherError {
    param([Parameter(Mandatory = $true)][string]$Message)

    Set-Content -LiteralPath (Join-Path $PSScriptRoot 'launcher-error.txt') -Value $Message -Encoding UTF8
    try {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(
            $Message,
            'ESports Simulator launcher',
            [System.Windows.MessageBoxButton]::OK,
            [System.Windows.MessageBoxImage]::Error
        ) | Out-Null
    } catch {
        # launcher-error.txt remains available if the dialog cannot be shown.
    }
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )

    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = @(& $FilePath @ArgumentList 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    $output = ($lines | ForEach-Object { "$_" }) -join [Environment]::NewLine
    return [pscustomobject]@{ ExitCode = $exitCode; Output = $output.Trim() }
}

function Test-GameReady {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -eq 200 -and $response.Content -match '<title>esports-sim</title>')
    } catch {
        return $false
    }
}

function Test-PortInUse {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $pending = $client.BeginConnect('127.0.0.1', $port, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Update-LocalMain {
    $gitCommand = Get-Command -Name 'git.exe' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $gitCommand) {
        throw 'Git was not found. Install Git or add it to PATH so the launcher can update the game.'
    }

    $branchResult = Invoke-NativeCommand -FilePath $gitCommand.Source -ArgumentList @(
        '-C', $repoRoot, 'branch', '--show-current'
    )
    if ($branchResult.ExitCode -ne 0) {
        throw "Could not inspect the local game checkout:$([Environment]::NewLine)$([Environment]::NewLine)$($branchResult.Output)"
    }
    if ($branchResult.Output -ne 'main') {
        throw "The configured checkout is on '$($branchResult.Output)', not 'main'. Switch it back to main before launching."
    }

    $pullResult = Invoke-NativeCommand -FilePath $gitCommand.Source -ArgumentList @(
        '-C', $repoRoot, 'pull', '--ff-only', 'origin', 'main'
    )
    if ($pullResult.ExitCode -ne 0) {
        throw "The game could not be updated with 'git pull --ff-only origin main'. No files were overwritten.$([Environment]::NewLine)$([Environment]::NewLine)$($pullResult.Output)"
    }

    $commitResult = Invoke-NativeCommand -FilePath $gitCommand.Source -ArgumentList @(
        '-C', $repoRoot, 'rev-parse', 'HEAD'
    )
    if ($commitResult.ExitCode -ne 0 -or -not $commitResult.Output) {
        throw "The updated game commit could not be identified.$([Environment]::NewLine)$([Environment]::NewLine)$($commitResult.Output)"
    }
    return $commitResult.Output
}

function Sync-InstalledLauncherRuntime {
    $runtimeSource = Join-Path $repoRoot 'scripts\taskbar_launcher.ps1'
    if (-not (Test-Path -LiteralPath $runtimeSource)) {
        throw "The updated launcher source is missing: $runtimeSource"
    }

    $sourcePath = [IO.Path]::GetFullPath($runtimeSource)
    $runningPath = [IO.Path]::GetFullPath($PSCommandPath)
    if ($sourcePath.Equals($runningPath, [StringComparison]::OrdinalIgnoreCase)) {
        return $false
    }
    $sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
    $runningHash = (Get-FileHash -LiteralPath $runningPath -Algorithm SHA256).Hash
    if ($sourceHash -eq $runningHash) { return $false }

    Copy-Item -LiteralPath $sourcePath -Destination $runningPath -Force
    return $true
}

function Get-LauncherDependencyState {
    $pyproject = Join-Path $repoRoot 'pyproject.toml'
    if (-not (Test-Path -LiteralPath $pyproject)) {
        throw "The dependency file is missing: $pyproject"
    }

    $currentHash = (Get-FileHash -LiteralPath $pyproject -Algorithm SHA256).Hash
    $installedHash = ''
    if (Test-Path -LiteralPath $dependencyStampFile) {
        $installedHash = (Get-Content -LiteralPath $dependencyStampFile -Raw -ErrorAction SilentlyContinue).Trim()
    }
    return [pscustomobject]@{
        CurrentHash = $currentHash
        Changed = ($currentHash -ne $installedHash)
    }
}

function Sync-LauncherDependencies {
    param([Parameter(Mandatory = $true)][string]$CurrentHash)

    $installTarget = $repoRoot + '[web]'
    $uvCommand = Get-Command -Name 'uv.exe' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($uvCommand) {
        $installResult = Invoke-NativeCommand -FilePath $uvCommand.Source -ArgumentList @(
            'pip', 'install', '--python', $python, '-e', $installTarget
        )
    } else {
        $installResult = Invoke-NativeCommand -FilePath $python -ArgumentList @(
            '-m', 'pip', 'install', '-e', $installTarget
        )
    }
    if ($installResult.ExitCode -ne 0) {
        throw "The game updated, but its Python dependencies could not be refreshed:$([Environment]::NewLine)$([Environment]::NewLine)$($installResult.Output)"
    }

    Set-Content -LiteralPath $dependencyStampFile -Value $CurrentHash -Encoding Ascii
}

function Test-LauncherProcess {
    param($Process)

    if (-not $Process) { return $false }
    $commandLine = "$($Process.CommandLine)"
    return (
        $commandLine.IndexOf($python, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $commandLine -match '-m\s+esports_sim\s+--web'
    )
}

function Stop-LauncherServer {
    $serverPid = 0
    if (Test-Path -LiteralPath $pidFile) {
        $rawPid = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue).Trim()
        [void][int]::TryParse($rawPid, [ref]$serverPid)
    }

    $rootProcess = $null
    if ($serverPid -gt 0) {
        $rootProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $serverPid" -ErrorAction SilentlyContinue
    }
    if (-not (Test-LauncherProcess -Process $rootProcess) -and
        (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
        $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($listener) {
            $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
            if (Test-LauncherProcess -Process $candidate) {
                $rootProcess = $candidate
                $serverPid = [int]$candidate.ProcessId
            }
        }
    }
    if (-not (Test-LauncherProcess -Process $rootProcess)) { return $false }

    $processIds = New-Object System.Collections.Generic.List[int]
    $processIds.Add($serverPid)
    for ($index = 0; $index -lt $processIds.Count; $index++) {
        $parentId = $processIds[$index]
        Get-CimInstance Win32_Process -Filter "ParentProcessId = $parentId" -ErrorAction SilentlyContinue |
            ForEach-Object { $processIds.Add([int]$_.ProcessId) }
    }
    for ($index = $processIds.Count - 1; $index -ge 0; $index--) {
        Stop-Process -Id $processIds[$index] -Force -ErrorAction SilentlyContinue
    }

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (-not (Test-PortInUse)) { return $true }
        Start-Sleep -Milliseconds 200
    }
    return $false
}

$haveMutex = $false
try {
    $haveMutex = $mutex.WaitOne(10000)
    if (-not $haveMutex) {
        throw 'Another launcher instance is still starting the game. Try again in a few seconds.'
    }
    if (-not (Test-Path -LiteralPath $repoRoot)) {
        throw "The game checkout was not found at: $repoRoot"
    }
    if (-not (Test-Path -LiteralPath $python)) {
        throw "The launcher runtime is missing. Expected: $python"
    }

    $currentCommit = Update-LocalMain
    if (Sync-InstalledLauncherRuntime) {
        # PowerShell parsed this script before the replacement. Start the fresh
        # copy now; it will wait briefly for this process to release the mutex.
        $powershell = Join-Path $PSHOME 'powershell.exe'
        $relaunchArgs = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $PSCommandPath
        Start-Process -FilePath $powershell -ArgumentList $relaunchArgs -WindowStyle Hidden
        exit 0
    }
    $dependencyState = Get-LauncherDependencyState
    $dependenciesChanged = $dependencyState.Changed

    if (Test-GameReady) {
        $serverCommit = ''
        if (Test-Path -LiteralPath $commitFile) {
            $serverCommit = (Get-Content -LiteralPath $commitFile -Raw -ErrorAction SilentlyContinue).Trim()
        }
        if ($serverCommit -eq $currentCommit -and -not $dependenciesChanged) {
            Start-Process $url
            exit 0
        }
        if (-not (Stop-LauncherServer)) {
            throw 'The game updated, but the running server was started outside the taskbar launcher. Close that server once, then launch again.'
        }
    }
    if ($dependenciesChanged) {
        Sync-LauncherDependencies -CurrentHash $dependencyState.CurrentHash
    }
    if (Test-PortInUse) {
        throw "Port $port is already in use by another application. Close that application, then launch again."
    }

    Start-VllmServer -PythonExe $python -RepoRoot $repoRoot -NoVllm $false

    $arguments = @(
        '-m', 'esports_sim', '--web',
        '--host', '0.0.0.0',
        '--port', "$port",
        '--no-browser'
    )
    $processParameters = @{
        FilePath = $python
        ArgumentList = $arguments
        WorkingDirectory = $repoRoot
        WindowStyle = 'Hidden'
        RedirectStandardOutput = $stdoutLog
        RedirectStandardError = $stderrLog
        PassThru = $true
    }
    $process = Start-Process @processParameters
    Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding Ascii
    Set-Content -LiteralPath $commitFile -Value $currentCommit -Encoding Ascii

    $ready = $false
    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        Start-Sleep -Milliseconds 500
        $process.Refresh()
        if ($process.HasExited) { break }
        if (Test-GameReady) {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        $detail = ''
        if (Test-Path -LiteralPath $stderrLog) {
            $detail = (Get-Content -LiteralPath $stderrLog -Tail 12 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
        }
        if ($detail) {
            throw "The game server did not start. Recent log output:$([Environment]::NewLine)$([Environment]::NewLine)$detail"
        }
        throw "The game server did not become ready. Check: $stderrLog"
    }

    Remove-Item -LiteralPath (Join-Path $PSScriptRoot 'launcher-error.txt') -Force -ErrorAction SilentlyContinue
    Start-Process $url
} catch {
    Show-LauncherError -Message $_.Exception.Message
    exit 1
} finally {
    if ($haveMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
