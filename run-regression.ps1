param(
    [ValidateSet('quick', 'full')]
    [string]$Mode = 'quick',

    [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )

    Write-Host ''
    Write-Host "=== $Title ===" -ForegroundColor Cyan
    & $Action
}

function Invoke-CommandChecked {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$File,
        [Parameter(Mandatory = $false)][string[]]$Arguments = @()
    )

    Push-Location $WorkingDirectory
    try {
        & $File @Arguments
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            $argsText = $Arguments -join ' '
            throw ("Command failed with exit code {0}: {1} {2}" -f $exitCode, $File, $argsText)
        }
    }
    finally {
        Pop-Location
    }
}

Write-Host "Running regression in mode: $Mode" -ForegroundColor Yellow
Write-Host "Repository root: $repoRoot" -ForegroundColor DarkGray

if ($Mode -eq 'full') {
    Write-Host 'Full mode includes LLM live tests in ai-engine (requires provider API keys).' -ForegroundColor Yellow
}

try {
    Invoke-Step -Title 'Backend' -Action {
        $backendDir = Join-Path $repoRoot 'backend'

        if (-not $SkipInstall) {
            Invoke-CommandChecked -WorkingDirectory $backendDir -File 'uv' -Arguments @('sync')
        }

        Invoke-CommandChecked -WorkingDirectory $backendDir -File 'uv' -Arguments @('run', 'pytest', 'tests/', '-v')
    }

    Invoke-Step -Title 'AI Engine' -Action {
        $aiEngineDir = Join-Path $repoRoot 'ai-engine'

        if (-not $SkipInstall) {
            Invoke-CommandChecked -WorkingDirectory $aiEngineDir -File 'uv' -Arguments @('sync', '--python', '3.12')
        }

        Invoke-CommandChecked -WorkingDirectory $aiEngineDir -File 'uv' -Arguments @(
            'run', '--python', '3.12', 'pytest', 'tests/unit/', 'tests/integration/', '-v'
        )

        Invoke-CommandChecked -WorkingDirectory $aiEngineDir -File 'uv' -Arguments @(
            'run', '--python', '3.12', 'pytest', 'tests/', '-m', 'not slow', '-v'
        )

        if ($Mode -eq 'full') {
            Invoke-CommandChecked -WorkingDirectory $aiEngineDir -File 'uv' -Arguments @(
                'run', '--python', '3.12', 'pytest', 'tests/evals/', '-m', 'slow and llm_live', '-v'
            )

            Invoke-CommandChecked -WorkingDirectory $aiEngineDir -File 'uv' -Arguments @(
                'run', '--python', '3.12', 'pytest', 'tests/stress/', '-m', 'slow and llm_live', '-v'
            )
        }
    }

    Invoke-Step -Title 'Frontend' -Action {
        $frontendDir = Join-Path $repoRoot 'frontend'

        if (-not $SkipInstall) {
            Invoke-CommandChecked -WorkingDirectory $frontendDir -File 'npm.cmd' -Arguments @('install')
        }

        Invoke-CommandChecked -WorkingDirectory $frontendDir -File 'npm.cmd' -Arguments @('test', '--', '--watch=false')
    }

    Write-Host ''
    Write-Host 'Regression completed successfully.' -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ''
    Write-Host 'Regression failed.' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
