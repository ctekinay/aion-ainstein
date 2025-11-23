$process = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1
if ($process) {
    Stop-Process -Id $process -Force
    Write-Host "Elysia server stopped (PID: $process)"
} else {
    Write-Host "No process found on port 8000"
}
