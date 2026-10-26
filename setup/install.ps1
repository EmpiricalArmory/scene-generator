# Empirical Armory - Scene Generator setup.
#
# Installs everything inside this folder: ComfyUI (portable), the generator, and the free models.
# Nothing is installed anywhere else on the computer. It is safe to run again: finished steps are
# skipped, and interrupted downloads carry on where they stopped.
#
#   Install.bat              everything
#   Install.bat -SkipModels  ComfyUI and the generator only
#   Install.bat -UpdateApp   also replace the generator with the latest from GitHub
#   Install.bat -NoStart     do not start the generator while the models download

param(
  [switch]$SkipModels,
  [switch]$NoStart,
  [switch]$UpdateApp
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root      = Split-Path -Parent $PSScriptRoot
$Setup     = Join-Path $Root 'setup'
$Logs      = Join-Path $Setup 'logs'
$Tools     = Join-Path $Root 'tools'
$Downloads = Join-Path $Root 'downloads'
$Models    = Join-Path $Root 'models'
$Nodes     = Join-Path $Root 'nodes'
$Data      = Join-Path $Root 'data'
$Secrets   = Join-Path $Data 'secrets'
$Portable  = Join-Path $Root 'ComfyUI_windows_portable'
$Python    = Join-Path $Portable 'python_embeded\python.exe'
$AppDir    = Join-Path $Nodes 'scene-generator'
$SevenZr   = Join-Path $Tools '7zr.exe'

$COMFY = @{
  Tag    = 'v0.42.1'
  File   = 'ComfyUI_windows_portable_nvidia.7z'
  Size   = [long]2018444114
  Sha256 = '496afd18790ec685d99ebba2edf200d7371a29fbdd3a992bb0f4f52f244a6874'
  Url    = 'https://github.com/Comfy-Org/ComfyUI/releases/download/v0.42.1/ComfyUI_windows_portable_nvidia.7z'
}
$SEVEN = @{
  Size   = [long]602624
  Sha256 = '9bf582b894dfa665f852d7e9112b02290a1c303c2d95a21fcdc41ffcb03143b7'
  Url    = 'https://github.com/ip7z/7zip/releases/download/26.05/7zr.exe'
}
$APP_ZIP    = 'https://github.com/EmpiricalArmory/scene-generator/archive/refs/heads/main.zip'
$MIN_DRIVER = 580.0      # the portable build uses PyTorch with CUDA 13.0
$FLUX_PAGE  = 'https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy'

foreach ($d in @($Logs, $Tools, $Downloads, $Models, $Nodes, $Data, $Secrets)) {
  New-Item -ItemType Directory -Force -Path $d | Out-Null
}
$LogFile    = Join-Path $Logs ('install-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
$StatusFile = Join-Path $Setup 'status.json'
$SystemFile = Join-Path $Setup 'system.json'
$AuthFile   = Join-Path $Secrets 'curl-auth.cfg'

function Log {
  param([string]$Msg, [string]$Color = 'Gray')
  $line = (Get-Date -Format 'HH:mm:ss') + '  ' + $Msg
  Write-Host $line -ForegroundColor $Color
  Add-Content -LiteralPath $LogFile -Value $line
}

function Status {
  param([string]$Step, [string]$State, [string]$Detail = '')
  $o = [ordered]@{ step = $Step; state = $State; detail = $Detail; time = (Get-Date).ToString('s'); log = (Split-Path -Leaf $LogFile) }
  Set-Content -LiteralPath $StatusFile -Value ($o | ConvertTo-Json -Compress) -Encoding Ascii
}

function Stop-Setup {
  param([string]$Step, [string]$Msg)
  Status $Step 'error' $Msg
  throw $Msg
}

function Format-GB { param([double]$Bytes) return ('{0:N1} GB' -f ($Bytes / 1e9)) }

function Test-Sha256 {
  param([string]$Path, [string]$Expected)
  if (-not $Expected) { return $true }
  $h = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower()
  return ($h -eq $Expected.ToLower())
}

# Downloads Url to Dest with curl.exe, resuming a .part file, then checks its size and SHA-256.
function Get-Download {
  param([string]$Url, [string]$Dest, [long]$Size, [string]$Sha256, [string]$Label, [string]$Auth = '')
  if ((Test-Path -LiteralPath $Dest) -and ((Get-Item -LiteralPath $Dest).Length -eq $Size)) {
    Log ('Already here: ' + $Label)
    return
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Dest) | Out-Null
  $part = $Dest + '.part'
  for ($attempt = 1; $attempt -le 40; $attempt++) {
    $have = [long]0
    if (Test-Path -LiteralPath $part) { $have = (Get-Item -LiteralPath $part).Length }
    if ($have -eq $Size) { break }
    if ($have -gt $Size) { Remove-Item -LiteralPath $part -Force; $have = 0 }
    $note = ''
    if ($have -gt 0) { $note = ', carrying on from ' + (Format-GB $have) }
    Log ('Downloading ' + $Label + ' (' + (Format-GB $Size) + $note + ')') 'Cyan'
    $cargs = @('-L', '--fail', '--connect-timeout', '30', '--speed-time', '90', '--speed-limit', '2048',
               '-C', '-', '-o', $part, '-w', '%{http_code}')
    if ($Auth) { $cargs += @('-K', $Auth) }
    $cargs += $Url
    $http = & curl.exe @cargs
    $code = $LASTEXITCODE
    Write-Host ''
    if ($code -eq 0) { continue }
    if ($http -eq '401' -or $http -eq '403') {
      Stop-Setup 'models' ('Hugging Face refused ' + $Label + ' (HTTP ' + $http + '). Accept the licence at ' + $FLUX_PAGE + ' with the same account as the token, then run Install again.')
    }
    if ($http -eq '404') { Stop-Setup 'models' ('Not found on the server: ' + $Url) }
    Log ('The download stopped (curl ' + $code + ', HTTP ' + $http + '). Trying again in 15 seconds...') 'Yellow'
    Start-Sleep -Seconds 15
  }
  $have = [long]0
  if (Test-Path -LiteralPath $part) { $have = (Get-Item -LiteralPath $part).Length }
  if ($have -ne $Size) { Stop-Setup 'download' ($Label + ' did not finish downloading. Run Install again to carry on.') }
  Log ('Checking ' + $Label + '...')
  if (-not (Test-Sha256 $part $Sha256)) {
    Remove-Item -LiteralPath $part -Force
    Stop-Setup 'download' ($Label + ' was damaged in the download and has been removed. Run Install again.')
  }
  Move-Item -LiteralPath $part -Destination $Dest -Force
  Log ('Done: ' + $Label) 'Green'
}

function Get-HfToken {
  $tf = Join-Path $Secrets 'hf_token.txt'
  if (Test-Path -LiteralPath $tf) {
    $t = ([string](Get-Content -LiteralPath $tf -Raw)).Trim()
    if ($t) { return $t }
  }
  Write-Host ''
  Write-Host 'FLUX 3 Image Klein needs a free Hugging Face account, with its licence accepted:' -ForegroundColor Cyan
  Write-Host '  1. Sign in at https://huggingface.co (or create an account).'
  Write-Host ('  2. Open ' + $FLUX_PAGE + ' and accept the FLUX Kommunity License.')
  Write-Host '  3. Create a token at https://huggingface.co/settings/tokens (type: Read) and copy it.'
  Write-Host ''
  $sec = Read-Host 'Paste the token and press Enter (or press Enter alone to skip FLUX 3 for now)' -AsSecureString
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
  try { $t = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
  $t = ([string]$t).Trim()
  if ($t) { Set-Content -LiteralPath $tf -Value $t -Encoding Ascii -NoNewline }
  return $t
}

try {
  Write-Host ''
  Write-Host 'Empirical Armory - Scene Generator setup' -ForegroundColor White
  Write-Host ('Everything goes into ' + $Root) -ForegroundColor DarkGray
  Write-Host ''

  # ---------------------------------------------------------------- the computer
  Status 'system' 'running'
  if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { Stop-Setup 'system' 'curl.exe is missing (it comes with Windows 10 and 11).' }
  if (-not (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)) { Stop-Setup 'system' 'nvidia-smi was not found: is the NVIDIA driver installed?' }
  $q = @(& nvidia-smi.exe --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits)[0]
  $g = $q.Split(',') | ForEach-Object { $_.Trim() }
  $gpuName = $g[0]; $driver = $g[1]; $vramMB = [int]$g[2]
  $dv = $driver.Split('.')
  $driverNum = [double]::Parse($dv[0] + '.' + $dv[1], [Globalization.CultureInfo]::InvariantCulture)
  $os = Get-CimInstance Win32_OperatingSystem
  $ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
  $driveName = (Get-Item -LiteralPath $Root).PSDrive.Name
  $freeBytes = (Get-PSDrive -Name $driveName).Free
  $sys = [ordered]@{
    gpu = $gpuName; driver = $driver; vram_mb = $vramMB; ram_gb = $ramGB
    os = ($os.Caption + ' ' + $os.Version); free_gb = [math]::Round($freeBytes / 1e9); root = $Root
    curl = (@(& curl.exe --version)[0])
  }
  Set-Content -LiteralPath $SystemFile -Value ($sys | ConvertTo-Json) -Encoding Ascii
  Log ('GPU: ' + $gpuName + ', ' + [math]::Round($vramMB / 1024) + ' GB, driver ' + $driver)
  Log ('Memory: ' + $ramGB + ' GB. Free on ' + $driveName + ': ' + (Format-GB $freeBytes) + '. ' + $os.Caption)
  if ($driverNum -lt $MIN_DRIVER) {
    Stop-Setup 'system' ('The NVIDIA driver is ' + $driver + '; ComfyUI needs ' + $MIN_DRIVER + ' or newer. Update the driver (a normal system install), then run Install again.')
  }
  if ($freeBytes -lt 150e9) { Log 'Less than 150 GB is free here: the models need about 120 GB.' 'Yellow' }

  # ---------------------------------------------------------------- 7-Zip's small unpacker
  Status 'tools' 'running'
  Get-Download $SEVEN.Url $SevenZr $SEVEN.Size $SEVEN.Sha256 '7-Zip unpacker (7zr.exe)'

  # ---------------------------------------------------------------- ComfyUI
  if (-not (Test-Path -LiteralPath $Python)) {
    Status 'comfyui' 'running' 'downloading'
    $arch = Join-Path $Downloads $COMFY.File
    Get-Download $COMFY.Url $arch $COMFY.Size $COMFY.Sha256 ('ComfyUI ' + $COMFY.Tag + ' (portable, NVIDIA)')
    Status 'comfyui' 'running' 'unpacking'
    Log 'Unpacking ComfyUI (a few minutes)...'
    & $SevenZr x $arch ('-o' + $Root) -y -bso0 -bsp1
    Write-Host ''
    if ($LASTEXITCODE -ne 0) { Stop-Setup 'comfyui' ('Unpacking ComfyUI failed (7zr ' + $LASTEXITCODE + ').') }
    if (-not (Test-Path -LiteralPath $Python)) { Stop-Setup 'comfyui' 'ComfyUI unpacked, but its Python was not where expected.' }
    Log 'ComfyUI is unpacked.' 'Green'
  } else {
    Log 'Already here: ComfyUI'
  }
  Status 'comfyui' 'running' 'checking the GPU'
  $probe = @(& $Python -s -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-')")
  Log ('PyTorch ' + $probe[0] + ', CUDA ' + $probe[1] + ', GPU available: ' + $probe[2] + ' (' + $probe[3] + ')')
  $sys['torch'] = $probe[0]; $sys['torch_cuda'] = $probe[1]; $sys['cuda_ok'] = $probe[2]
  Set-Content -LiteralPath $SystemFile -Value ($sys | ConvertTo-Json) -Encoding Ascii
  if ($probe[2] -ne 'True') { Stop-Setup 'comfyui' 'PyTorch cannot reach the GPU. Updating the NVIDIA driver usually fixes this.' }

  # Models and the generator live beside ComfyUI, not inside it, so ComfyUI can be replaced freely.
  foreach ($d in @('checkpoints', 'diffusion_models', 'text_encoders', 'vae', 'loras')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Models $d) | Out-Null
  }
  $yaml = @"
# Written by the Empirical Armory installer: the models and the generator live beside ComfyUI.
empirical_armory:
    base_path: ../..
    checkpoints: models/checkpoints
    diffusion_models: models/diffusion_models
    text_encoders: models/text_encoders
    vae: models/vae
    loras: models/loras
    custom_nodes: nodes
"@
  Set-Content -LiteralPath (Join-Path $Portable 'ComfyUI\extra_model_paths.yaml') -Value $yaml -Encoding Ascii

  # ---------------------------------------------------------------- the generator
  Status 'app' 'running'
  if ($UpdateApp -or -not (Test-Path -LiteralPath (Join-Path $AppDir '__init__.py'))) {
    $zip = Join-Path $Downloads 'scene-generator-main.zip'
    & curl.exe -L --fail -s -o $zip $APP_ZIP
    if ($LASTEXITCODE -ne 0) { Stop-Setup 'app' 'Could not download the generator from GitHub.' }
    $tmp = Join-Path $Downloads 'scene-generator-unpack'
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
    Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
    if (Test-Path -LiteralPath $AppDir) { Remove-Item -LiteralPath $AppDir -Recurse -Force }
    Move-Item -LiteralPath (Join-Path $tmp 'scene-generator-main') -Destination $AppDir
    Log 'The generator is installed.' 'Green'
  } else {
    Log 'Already here: the generator'
  }

  # ---------------------------------------------------------------- start it while the models download
  if (-not $NoStart) {
    Log 'Starting the generator in its own window...'
    Start-Process -FilePath (Join-Path $Root 'Start.bat') -WorkingDirectory $Root
  }

  # ---------------------------------------------------------------- the models
  if (-not $SkipModels) {
    $manifest = Get-Content -LiteralPath (Join-Path $Setup 'models.json') -Raw | ConvertFrom-Json
    $files = @($manifest.files | Where-Object { -not $_.optional }) + @($manifest.files | Where-Object { $_.optional })
    $missingGated = @($files | Where-Object { $_.gated -and -not (Test-Path -LiteralPath (Join-Path $Models ($_.dest -replace '/', '\'))) })
    $auth = ''
    if ($missingGated.Count -gt 0) {
      $token = Get-HfToken
      if ($token) {
        Set-Content -LiteralPath $AuthFile -Value ('header = "Authorization: Bearer ' + $token + '"') -Encoding Ascii
        $who = & curl.exe -s -o NUL -w '%{http_code}' -K $AuthFile 'https://huggingface.co/api/whoami-v2'
        if ($who -ne '200') {
          Remove-Item -LiteralPath (Join-Path $Secrets 'hf_token.txt') -Force -ErrorAction SilentlyContinue
          Stop-Setup 'models' ('Hugging Face did not accept the token (HTTP ' + $who + '). Run Install again and paste a Read token.')
        }
        $probeUrl = @($missingGated)[0].url
        $acc = & curl.exe -s -L -r 0-0 -o NUL -w '%{http_code}' -K $AuthFile $probeUrl
        if ($acc -ne '200' -and $acc -ne '206') {
          Stop-Setup 'models' ('The token works, but FLUX 3 is not unlocked for this account (HTTP ' + $acc + '). Accept the licence at ' + $FLUX_PAGE + ', then run Install again.')
        }
        $auth = $AuthFile
        Log 'Hugging Face token accepted; FLUX 3 Image Klein is unlocked.' 'Green'
      } else {
        Log 'Skipping FLUX 3 Image Klein for now. Run Install again to add it.' 'Yellow'
      }
    }
    $i = 0
    foreach ($f in $files) {
      $i++
      if ($f.gated -and -not $auth) { continue }
      $dest = Join-Path $Models ($f.dest -replace '/', '\')
      Status 'models' 'running' ('' + $i + '/' + $files.Count + ' ' + $f.label)
      $a = ''
      if ($f.gated) { $a = $auth }
      Get-Download $f.url $dest ([long]$f.size) $f.sha256 $f.label $a
    }
    if (Test-Path -LiteralPath $AuthFile) { Remove-Item -LiteralPath $AuthFile -Force }
  }

  Status 'done' 'ok'
  Write-Host ''
  Log 'Setup is finished. Start.bat starts the generator; it opens in your browser.' 'Green'
}
catch {
  if (Test-Path -LiteralPath $AuthFile) { Remove-Item -LiteralPath $AuthFile -Force -ErrorAction SilentlyContinue }
  $msg = $_.Exception.Message
  Write-Host ''
  Log ('Setup stopped: ' + $msg) 'Red'
  $cur = $null
  if (Test-Path -LiteralPath $StatusFile) { $cur = Get-Content -LiteralPath $StatusFile -Raw | ConvertFrom-Json }
  if (-not $cur -or $cur.state -ne 'error') { Status 'unknown' 'error' $msg }
  exit 1
}
