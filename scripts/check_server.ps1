# Diagnostic script for iCORE server
# Usage: run from project root in PowerShell: .\scripts\check_server.ps1
$out = Join-Path $PSScriptRoot '..\server_diag.txt'
if (Test-Path $out) { Remove-Item $out -Force }
"===== Diagnostic run at $(Get-Date -Format o) =====" | Out-File -FilePath $out -Encoding utf8
"--- Python processes ---" | Out-File -FilePath $out -Append
try {
    Get-Process -Name python -ErrorAction SilentlyContinue | Format-Table Id,ProcessName,StartTime -AutoSize | Out-String | Out-File -FilePath $out -Append
} catch { $_ | Out-String | Out-File -FilePath $out -Append }

"--- Listening on :5000 (netstat) ---" | Out-File -FilePath $out -Append
try {
    netstat -ano | Select-String ':5000' | Out-String | Out-File -FilePath $out -Append
} catch { $_ | Out-String | Out-File -FilePath $out -Append }

"--- Try GET http://127.0.0.1:5000/health ---" | Out-File -FilePath $out -Append
try {
    $h = Invoke-RestMethod -Uri http://127.0.0.1:5000/health -UseBasicParsing -TimeoutSec 5
    $h | ConvertTo-Json -Depth 5 | Out-File -FilePath $out -Append
} catch {
    "HEALTH_FETCH_FAILED: $($_.Exception.Message)" | Out-File -FilePath $out -Append
}

"--- End of diagnostic ---" | Out-File -FilePath $out -Append
Write-Host "Diagnostic written to: $out"
