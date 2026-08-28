[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoPath,

    [Parameter(Mandatory = $true)]
    [string]$Ref,

    [string]$VenvPath = (Join-Path $env:LOCALAPPDATA 'Gavrik2\venv'),
    [string]$StateFile = (Join-Path $env:LOCALAPPDATA 'Gavrik2\applied-sha.txt')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Program,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE: $Program"
    }
}

$resolvedRepo = (Resolve-Path -LiteralPath $RepoPath).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedRepo '.git'))) {
    throw "RepoPath is not a Git working tree: $resolvedRepo"
}

Push-Location -LiteralPath $resolvedRepo
try {
    $dirty = (& git status --porcelain=v1 --untracked-files=all)
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to inspect the Git working tree.'
    }
    if ($dirty) {
        throw 'Refusing to sync: the Git working tree is not clean.'
    }

    Invoke-Checked git fetch --prune origin
    $commit = (& git rev-parse --verify "$Ref^{commit}").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $commit) {
        throw "Ref does not resolve to a commit: $Ref"
    }

    Invoke-Checked git switch --detach $commit

    $python = Get-Command python -ErrorAction Stop
    if (-not (Test-Path -LiteralPath $VenvPath)) {
        Invoke-Checked $python.Source -m venv $VenvPath
    }

    $venvPython = Join-Path $VenvPath 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Virtual environment is incomplete: $VenvPath"
    }

    Invoke-Checked $venvPython -m pip install --disable-pip-version-check -r requirements-dev.txt
    Invoke-Checked $venvPython -m pytest

    $stateDirectory = Split-Path -Parent $StateFile
    if ($stateDirectory) {
        New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    }
    Set-Content -LiteralPath $StateFile -Value $commit -Encoding ascii
    Write-Host "Gavrik 2 code verified at $commit. Application was not started."
}
finally {
    Pop-Location
}
