param(
    [string]$F5TTSRepoDir = "C:\docker\F5-TTS",
    [string]$ImageName = "f5tts:v1.0",
    [string]$ContainerName = "f5tts_server",
    [int]$HostPort = 7865,
    [switch]$RebuildImage,
    [switch]$NoGpu,
    [switch]$UseAliyunMirror
)

Write-Host "=== F5-TTS FastAPI Server Deployment ==="
Write-Host "Repository: https://github.com/SWivid/F5-TTS"
Write-Host ""

# Check if repository is cloned
if (-not (Test-Path $F5TTSRepoDir)) {
    Write-Error "F5-TTS repository not found: $F5TTSRepoDir"
    Write-Host "Please clone it first:"
    Write-Host "  git clone https://github.com/SWivid/F5-TTS.git $F5TTSRepoDir"
    exit 1
}

$dockerfilePath = Join-Path $F5TTSRepoDir "Dockerfile"
if (-not (Test-Path $dockerfilePath)) {
    Write-Error "Dockerfile not found: $dockerfilePath"
    exit 1
}

# Build Docker image if needed
if ($RebuildImage) {
    Write-Host "Rebuilding image: $ImageName"
    & docker build -t $ImageName $F5TTSRepoDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
else {
    & docker image inspect $ImageName *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Image not found. Building: $ImageName"
        & docker build -t $ImageName $F5TTSRepoDir
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}

# Stop and remove existing container
& docker rm -f $ContainerName *> $null

# Build run command
$runArgs = @(
    "run",
    "-d",
    "--name", $ContainerName,
    "-p", "$HostPort`:7865"
)

# Add GPU support if not disabled
if (-not $NoGpu) {
    $runArgs += @("--gpus", "all")
}

# Add volume mounts for custom models and cache
$runArgs += @(
    "-v", "f5tts_model_cache:/root/.cache",
    "-v", "$F5TTSRepoDir\/checkpoints:/app/checkpoints"
)

# Run container
$runArgs += @(
    $ImageName,
    "python",
    "-m",
    "f5_tts.infer.infer_cli",
    "--port",
    "7865",
    "--host",
    "0.0.0.0"
)

Write-Host "Starting container: $ContainerName"
Write-Host "F5-TTS API will be available at: http://127.0.0.1:$HostPort"
Write-Host ""

& docker @runArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "=== F5-TTS Server Started ==="
Write-Host "API URL: http://127.0.0.1:$HostPort"
Write-Host "Health check: http://127.0.0.1:$HostPort/health"
Write-Host ""
Write-Host "To view logs: docker logs -f $ContainerName"
Write-Host "To stop: docker stop $ContainerName"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Set F5TTS_API_URL=http://127.0.0.1:$HostPort in .env"
Write-Host "2. Prepare reference audio (3-5 seconds wav file)"
Write-Host "3. Set AUDIO_SOURCE_MODE=f5tts"
Write-Host "4. Run: python src/main.py"
