Write-Host "========================================"
Write-Host "  Local Code Assistant - Install"
Write-Host "========================================"
Write-Host ""

$installPath = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Install path: $installPath"
Write-Host ""

# PATH에 추가
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")

if ($currentPath -like "*$installPath*") {
    Write-Host "[OK] Already in PATH" -ForegroundColor Green
} else {
    Write-Host "Adding to PATH..."
    $newPath = $currentPath + ";" + $installPath
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-Host "[OK] PATH updated!" -ForegroundColor Green
}

Write-Host ""

# Python 의존성 설치
Write-Host "Installing Python dependencies..."
Set-Location "$installPath\client"
pip install -r requirements.txt -q
Write-Host "[OK] Dependencies installed!" -ForegroundColor Green

Write-Host ""
Write-Host "========================================"
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host "========================================"
Write-Host ""
Write-Host "Close this terminal, open a NEW one, and run:"
Write-Host "  llmcode" -ForegroundColor Cyan
Write-Host ""
