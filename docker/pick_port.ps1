# Checks the dashboard port from .env. If it is busy, picks the next free port and saves it in .env.
# Prints one line:  <port>            (port is free, nothing changed)
#                   <newport> <old>   (old port was busy, .env was updated)
param([string]$EnvFile = ".env", [switch]$KeepIfOurs)

function Test-PortFree([int]$p) {
    if (Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue) { return $false }
    try {
        $l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $p)
        $l.Start(); $l.Stop(); return $true
    } catch { return $false }
}

$port = 8010
$lines = @()
if (Test-Path $EnvFile) {
    $lines = @(Get-Content $EnvFile)
    foreach ($l in $lines) { if ($l -match '^\s*APP_PORT\s*=\s*(\d+)') { $port = [int]$Matches[1] } }
}
if ($KeepIfOurs -or (Test-PortFree $port)) { Write-Output $port; exit 0 }

$new = 0
foreach ($p in ($port + 1)..($port + 80)) { if (Test-PortFree $p) { $new = $p; break } }
if ($new -eq 0) { Write-Output "0 $port"; exit 1 }

$found = $false
$out = foreach ($l in $lines) {
    if ($l -match '^\s*APP_PORT\s*=') { "APP_PORT=$new"; $found = $true } else { $l }
}
if (-not $found) { $out = @($out) + "APP_PORT=$new" }
Set-Content -Path $EnvFile -Value $out
Write-Output "$new $port"
