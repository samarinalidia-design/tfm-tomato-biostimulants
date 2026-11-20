param([Parameter(Mandatory=$true)][string]$Corpus,[string]$Workbook="")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "Install Python 3.12 from python.org, reopen PowerShell, then retry." }
$tfmArgs = @("-3.12", "tools/bootstrap.py", "--corpus", $Corpus)
if ($Workbook) { $tfmArgs += @("--workbook",$Workbook) }
& py @tfmArgs
if ($LASTEXITCODE -ne 0) { throw "Setup failed. Read the precise error above; no final data release was created." }
Write-Host "Next: .\.venv\Scripts\Activate.ps1 ; claude ; /tfm-finalize"
