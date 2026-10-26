# Opens the generator in the default browser once ComfyUI answers (called by Start.bat).
$ProgressPreference = 'SilentlyContinue'
for ($i = 0; $i -lt 600; $i++) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri 'http://127.0.0.1:8188/ea/api/ping'
    if ($r.StatusCode -eq 200) { Start-Process 'http://127.0.0.1:8188/ea/'; exit 0 }
  } catch {
    $resp = $_.Exception.Response
    if ($resp -and ([int]$resp.StatusCode -eq 404)) { Start-Process 'http://127.0.0.1:8188/'; exit 0 }
  }
  Start-Sleep -Seconds 2
}
