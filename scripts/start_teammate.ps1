param([int]$Port = 8002)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) { throw "Run the setup launcher first." }
$ModelRoot = Join-Path $RepoRoot "models\paraphrase-multilingual-MiniLM-L12-v2"
$Params = @{ Port = $Port; PythonExe = $PythonExe; DataDir = (Join-Path $RepoRoot ".local-phase2"); ModelDir = "" }
if (Test-Path -LiteralPath (Join-Path $ModelRoot "config.json")) {
    & $PythonExe -c "import sentence_transformers"
    if ($LASTEXITCODE -ne 0) { throw "Model dependencies missing. Run the setup launcher again." }
    & $PythonExe (Join-Path $RepoRoot "experiments\fetch_contract_model.py") --directory $ModelRoot --verify-only
    if ($LASTEXITCODE -ne 0) { throw "Pinned model weight verification failed; website was not started." }
    $Params.ModelDir = $ModelRoot
} else {
    Remove-Item Env:YUANJIAN_COMPONENT_MODEL_DIR -ErrorAction SilentlyContinue
}
& (Join-Path $PSScriptRoot "start_phase2.ps1") @Params
