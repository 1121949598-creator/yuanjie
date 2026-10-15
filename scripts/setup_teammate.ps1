param([string]$PythonExe = "")
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $RepoRoot
$CacheRoot = Join-Path $RepoRoot ".cache"
New-Item -ItemType Directory -Force -Path $CacheRoot | Out-Null
$env:TEMP = $CacheRoot
$env:TMP = $CacheRoot
$env:PIP_CACHE_DIR = Join-Path $CacheRoot "pip"
$env:PYTHONPYCACHEPREFIX = Join-Path $CacheRoot "pycache"
$env:HF_HOME = Join-Path $CacheRoot "huggingface"
if (-not $PythonExe) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $PythonExe = (& py -3 -c "import sys; print(sys.executable)")
        if ($LASTEXITCODE -ne 0) { throw "Install Python 3.11+ or specify -PythonExe." }
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonExe = (Get-Command python).Source
    } else { throw "Python missing. Install Python 3.12, then retry." }
}
& $PythonExe -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'"
if ($LASTEXITCODE -ne 0) { throw "Python version check failed." }
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $PythonExe -m venv (Join-Path $RepoRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
}
& $VenvPython -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "Project dependencies failed to install; check network/package source." }
$ModelRoot = Join-Path $RepoRoot "models\paraphrase-multilingual-MiniLM-L12-v2"
if (Test-Path -LiteralPath (Join-Path $ModelRoot "config.json")) {
    & $VenvPython -m pip install torch --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) { throw "CPU PyTorch installation failed." }
    & $VenvPython -m pip install -e ".[model]"
    if ($LASTEXITCODE -ne 0) { throw "sentence-transformers installation failed." }
    & $VenvPython -c "import torch, sentence_transformers; print('Model dependencies available')"
    if ($LASTEXITCODE -ne 0) { throw "Model dependency import check failed." }
    & $VenvPython (Join-Path $RepoRoot "experiments\fetch_contract_model.py") --directory $ModelRoot --verify-only
    if ($LASTEXITCODE -ne 0) { throw "Pinned model weight verification failed. Use the documented model snapshot." }
}
& $VenvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependency consistency check failed." }
Write-Host "Installation complete. Run the start launcher; then open http://127.0.0.1:8002/app/"
