# Prints this laptop's home Wi-Fi / network IPv4 address (used for links from phones at home).
$c = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
  Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq 'Up' } |
  Select-Object -First 1
if ($c) { ($c.IPv4Address | Select-Object -First 1).IPAddress }
