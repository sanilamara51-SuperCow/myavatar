# CosyVoice Local Deployment (Windows + Docker)

This project can run Node 4 (`n4_tts_synthesizer.py`) against a local CosyVoice FastAPI service.

## 1. Prerequisites

- Docker Desktop installed and running
- NVIDIA GPU runtime enabled in Docker (`--gpus all`)
- Git installed

## 2. Clone CosyVoice upstream

```powershell
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git C:\docker\CosyVoice
```

## 3. Build and start CosyVoice FastAPI

Use the helper script in this repo:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_cosyvoice_fastapi.ps1 `
  -CosyVoiceRepoDir C:\docker\CosyVoice `
  -ImageName cosyvoice:v1.0 `
  -ContainerName cosyvoice_fastapi `
  -HostPort 50000 `
  -ModelDir iic/CosyVoice-300M
```

Check logs:

```powershell
docker logs -f cosyvoice_fastapi
```

## 4. Configure Myavatar `.env`

Set Node 4 to use local CosyVoice:

```env
AUDIO_SOURCE_MODE=cosyvoice
COSYVOICE_API_URL=http://127.0.0.1:50000
COSYVOICE_API_STYLE=official_fastapi
COSYVOICE_MODE=sft
COSYVOICE_VOICE=<speaker_id_from_cosyvoice>
COSYVOICE_SAMPLE_RATE=22050
COSYVOICE_TIMEOUT_SEC=120
```

## 5. Run the pipeline

```powershell
$env:PYTHONPATH='src'
python src/main.py
```

## Use your own voice

For local voice cloning you need a short reference audio (not per-slide recording).  
Switch mode to `zero_shot` and provide one prompt wav + prompt text:

```env
COSYVOICE_MODE=zero_shot
COSYVOICE_PROMPT_WAV_PATH=workspace\voice_ref\my_voice.wav
COSYVOICE_PROMPT_TEXT=This is my reference text.
```

Keep `AUDIO_SOURCE_MODE=cosyvoice`.  
Node 4 will auto-generate all slide audio from text.
