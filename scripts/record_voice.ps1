param(
    [int]$Index = -1,
    [int]$DurationSec = 20,
    [string]$DeviceName = "",
    [string]$OutDir = "workspace/voice_input",
    [string]$FfmpegPath = "C:\Users\liuzh\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe",
    [switch]$ListDevices
)

if (-not (Test-Path $FfmpegPath)) {
    Write-Error "ffmpeg not found: $FfmpegPath"
    exit 1
}

if ($ListDevices) {
    & $FfmpegPath -hide_banner -list_devices true -f dshow -i dummy
    # ffmpeg returns non-zero here after listing devices because "dummy" is not an input source.
    exit 0
}

if ($Index -lt 0) {
    Write-Error "Please provide -Index (0-based), e.g. -Index 0"
    exit 1
}

if ($DurationSec -le 0) {
    Write-Error "DurationSec must be > 0"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($DeviceName)) {
    Write-Error "Please provide -DeviceName. Run with -ListDevices first."
    exit 1
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$outFile = Join-Path $OutDir ("voice_{0:D3}.wav" -f $Index)

Write-Host "Recording '$DeviceName' for $DurationSec seconds..."
Write-Host "Output: $outFile"

& $FfmpegPath -y -f dshow -i ("audio=" + $DeviceName) -t $DurationSec -ac 1 -ar 44100 $outFile
if ($LASTEXITCODE -ne 0) {
    Write-Error "Recording failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "Saved: $outFile"
