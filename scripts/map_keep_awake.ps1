param([string]$StateDirectory = (Join-Path $PSScriptRoot '../runs/layout-review'))
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null
$StateDirectory = (Resolve-Path $StateDirectory).Path
$TaskStatusPath = Join-Path $StateDirectory 'codex-map-awake.status.json'
$TaskStopPath = Join-Path $StateDirectory 'codex-map-awake.stop'
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class MapAwake {
  [StructLayout(LayoutKind.Sequential)] public struct ReasonContext {
    public uint Version, Flags;
    public IntPtr SimpleReason, Reserved1, Reserved2;
  }
  [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr PowerCreateRequest(ref ReasonContext context);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool PowerSetRequest(IntPtr handle, int type);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool PowerClearRequest(IntPtr handle, int type);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern uint SetThreadExecutionState(uint flags);
  [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle);
}
'@
$TaskReason = [Runtime.InteropServices.Marshal]::StringToHGlobalUni('Codex autonomous map authoring')
$TaskContext = [MapAwake+ReasonContext]::new()
$TaskContext.Flags = 1
$TaskContext.SimpleReason = $TaskReason
$TaskHandle = [MapAwake]::PowerCreateRequest([ref]$TaskContext)
if ($TaskHandle -eq [IntPtr]::Zero -or $TaskHandle -eq [IntPtr]::new(-1)) { throw 'PowerCreateRequest failed' }
$TaskStarted = [DateTime]::UtcNow.ToString('o')
$TaskHeartbeat = 0
$TaskRequests = @{}
try {
  while (-not (Test-Path -LiteralPath $TaskStopPath)) {
    foreach ($TaskType in @(0, 1, 3)) {
      if ($TaskRequests[$TaskType]) { [MapAwake]::PowerClearRequest($TaskHandle, $TaskType) | Out-Null }
      $TaskRequests[$TaskType] = [MapAwake]::PowerSetRequest($TaskHandle, $TaskType)
      if (-not $TaskRequests[$TaskType]) { throw "PowerSetRequest failed for $TaskType" }
    }
    $TaskPrevious = [MapAwake]::SetThreadExecutionState([uint32]2147483651)
    if ($TaskPrevious -eq 0) { throw 'SetThreadExecutionState failed' }
    $TaskHeartbeat++
    @{state='active';pid=$PID;started_utc=$TaskStarted;heartbeat_utc=[DateTime]::UtcNow.ToString('o');heartbeat=$TaskHeartbeat;execution_flags='0x80000003';display_request=$TaskRequests[0];system_request=$TaskRequests[1];execution_request=$TaskRequests[3];stop_file=$TaskStopPath} | ConvertTo-Json | Set-Content -LiteralPath "$TaskStatusPath.tmp"
    Move-Item -Force -LiteralPath "$TaskStatusPath.tmp" -Destination $TaskStatusPath
    Start-Sleep -Seconds 30
  }
} finally {
  foreach ($TaskType in @(0, 1, 3)) { if ($TaskRequests[$TaskType]) { [MapAwake]::PowerClearRequest($TaskHandle, $TaskType) | Out-Null } }
  [MapAwake]::SetThreadExecutionState([uint32]2147483648) | Out-Null
  [MapAwake]::CloseHandle($TaskHandle) | Out-Null
  [Runtime.InteropServices.Marshal]::FreeHGlobal($TaskReason)
  @{state='stopped';pid=$PID;heartbeat_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $TaskStatusPath
}
