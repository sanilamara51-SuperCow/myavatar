param(
    [string]$CosyVoiceRepoDir = "C:\docker\CosyVoice",
    [string]$ImageName = "cosyvoice:v1.0",
    [string]$ContainerName = "cosyvoice_fastapi",
    [int]$HostPort = 50000,
    [string]$ModelDir = "iic/CosyVoice-300M",
    [switch]$RebuildImage,
    [switch]$NoGpu,
    [switch]$UseAliyunMirror
)

$runtimePythonDir = Join-Path $CosyVoiceRepoDir "runtime\python"
$dockerfilePath = Join-Path $runtimePythonDir "Dockerfile"
$dockerfileBuildPath = Join-Path $runtimePythonDir "Dockerfile.localbuild"

if (-not (Test-Path $dockerfilePath)) {
    Write-Error "CosyVoice Dockerfile not found: $dockerfilePath"
    Write-Error "Clone the upstream repo first: git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git $CosyVoiceRepoDir"
    exit 1
}

$dockerfileContent = Get-Content $dockerfilePath -Raw
if (-not $UseAliyunMirror) {
    # Upstream Dockerfile rewrites apt source to mirrors.aliyun.com.
    # This mirror often fails outside mainland China; keep default Ubuntu source instead.
    $dockerfileContent = $dockerfileContent -replace "RUN sed -i s@/archive\.ubuntu\.com/@/mirrors\.aliyun\.com/@g /etc/apt/sources\.list", "# mirror rewrite disabled"
    # Upstream Dockerfile also pins pip index to mirrors.aliyun.com.
    # Replace it with the default PyPI index for global connectivity.
    $dockerfileContent = $dockerfileContent -replace "pip3 install -r requirements\.txt -i https://mirrors\.aliyun\.com/pypi/simple/ --trusted-host=mirrors\.aliyun\.com --no-cache-dir", "pip3 install -r requirements.txt --no-cache-dir"
}

# Ensure build backend tooling is present before installing complex python deps,
# disable build isolation for packages that depend on pkg_resources,
# and drop optional heavy deps that frequently break public builds.
$dockerfileContent = $dockerfileContent -replace "RUN cd CosyVoice && pip3 install -r requirements\.txt.*", "RUN pip3 install --no-cache-dir --upgrade ""pip<25"" ""setuptools<81"" wheel && cd CosyVoice && sed -i '/^deepspeed==/d;/^openai-whisper==/d;/^tensorrt-cu12==/d;/^tensorrt-cu12-bindings==/d;/^tensorrt-cu12-libs==/d' requirements.txt && pip3 install -r requirements.txt --no-cache-dir --no-build-isolation"
$dockerfileContent | Set-Content -Path $dockerfileBuildPath -Encoding UTF8

if ($RebuildImage) {
    Write-Host "Rebuilding image: $ImageName"
    & docker build -f $dockerfileBuildPath -t $ImageName $runtimePythonDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
else {
    & docker image inspect $ImageName *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Image not found. Building: $ImageName"
        & docker build -f $dockerfileBuildPath -t $ImageName $runtimePythonDir
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}

& docker rm -f $ContainerName *> $null

$runArgs = @(
    "run",
    "-d",
    "--name", $ContainerName,
    "-p", "$HostPort`:50000",
    "-v", "cosyvoice_model_cache:/root/.cache/modelscope",
    "-v", "c:\docker\Myavatar\cosy_server_utf8.py:/opt/CosyVoice/CosyVoice/runtime/python/fastapi/server.py",
    "-v", "c:\docker\Myavatar\cosyvoice_model.py:/opt/CosyVoice/CosyVoice/cosyvoice/cli/model.py"
)

if (-not $NoGpu) {
    $runArgs += @("--gpus", "all")
}

$serverCmd = "cd /opt/CosyVoice/CosyVoice/runtime/python/fastapi && pip3 install openai-whisper && python3 server.py --port 50000 --model_dir $ModelDir"

$runArgs += @(
    $ImageName,
    "/bin/bash",
    "-lc",
    $serverCmd
)

Write-Host "Starting container: $ContainerName"
& docker @runArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "CosyVoice FastAPI started."
Write-Host "URL: http://127.0.0.1:$HostPort"
Write-Host "Check logs: docker logs -f $ContainerName"
