param(
  [int]$Port = 8002,
  [string]$DataDir = "",
  [string]$PythonExe = $env:OPENGUARD_PYTHON,
  [string]$ModelDir = $env:YUANJIAN_COMPONENT_MODEL_DIR
)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $DataDir) { $DataDir = Join-Path $RepoRoot ".local-phase2" }
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$DataDir = (Resolve-Path -LiteralPath $DataDir).Path
$RuntimeCache = Join-Path $DataDir "cache"
New-Item -ItemType Directory -Force -Path $RuntimeCache | Out-Null
$env:TEMP = $RuntimeCache
$env:TMP = $RuntimeCache
$env:PYTHONPYCACHEPREFIX = Join-Path $RuntimeCache "pycache"
$env:HF_HOME = Join-Path $RuntimeCache "huggingface"
$env:PYTHONIOENCODING = "utf-8"
if (-not $PythonExe) {
  $PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonExe)) { throw "Python environment missing. Set OPENGUARD_PYTHON or create .venv; see the phase-2 handoff document in the project root." }
if ($ModelDir) {
  if (-not (Test-Path -LiteralPath (Join-Path $ModelDir "config.json"))) { throw "Invalid local model directory." }
  $env:YUANJIAN_COMPONENT_MODEL_DIR = (Resolve-Path -LiteralPath $ModelDir).Path
  $env:HF_HUB_OFFLINE = "1"
  $env:TRANSFORMERS_OFFLINE = "1"
}
$Existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Existing) {
  Write-Host "Port $Port is already in use. Check http://127.0.0.1:$Port/app/ or choose another -Port."
  exit 0
}
$Runner = Join-Path $RepoRoot "scripts\run_web.py"
$Process = Start-Process -FilePath $PythonExe -ArgumentList @('"' + $Runner + '"', "--port", "$Port", "--data-dir", '"' + $DataDir + '"') -WorkingDirectory $RepoRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $DataDir "server.out.log") -RedirectStandardError (Join-Path $DataDir "server.err.log") -PassThru
$Process.Id | Set-Content -LiteralPath (Join-Path $DataDir "launcher.pid") -Encoding ascii
Write-Host "源界 is starting: http://127.0.0.1:$Port/app/"
Write-Host "Logs and scan records: $DataDir"
