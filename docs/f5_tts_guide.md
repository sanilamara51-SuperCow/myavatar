# F5-TTS Voice Cloning Guide

## Overview

F5-TTS is a state-of-the-art zero-shot voice cloning model with:
- **Flow-based Diffusion + Transformer** architecture
- **3-5 seconds** reference audio required
- **Cross-lingual** support (Chinese, English, Japanese, Korean, etc.)
- **Natural prosody** and emotion
- **Fast inference** (~2-3x real-time)

GitHub: [SWivid/F5-TTS](https://github.com/SWivid/F5-TTS)

## Quick Start

### Step 1: Clone F5-TTS Repository

```powershell
git clone https://github.com/SWivid/F5-TTS.git C:\docker\F5-TTS
cd C:\docker\F5-TTS
```

### Step 2: Deploy F5-TTS Server

```powershell
# With GPU (recommended for RTX 3080Ti)
powershell -ExecutionPolicy Bypass -File scripts\start_f5tts_fastapi.ps1 `
  -F5TTSRepoDir C:\docker\F5-TTS `
  -ImageName f5tts:v1.0 `
  -ContainerName f5tts_server `
  -HostPort 7865

# Without GPU (CPU only, slower)
powershell -ExecutionPolicy Bypass -File scripts\start_f5tts_fastapi.ps1 `
  -F5TTSRepoDir C:\docker\F5-TTS `
  -NoGpu
```

### Step 3: Prepare Reference Audio

Record or prepare a 3-5 second reference audio:

```powershell
# List available audio devices
powershell -ExecutionPolicy Bypass -File scripts\record_voice.ps1 -ListDevices

# Record your voice (replace "YourDeviceName" with actual device name)
powershell -ExecutionPolicy Bypass -File scripts\record_voice.ps1 `
  -Index 0 `
  -DeviceName "YourDeviceName" `
  -DurationSec 5 `
  -OutDir workspace/voice_ref
```

Or copy an existing audio file to `workspace/voice_ref/my_voice.wav`

### Step 4: Configure Environment

Edit `.env`:

```env
# Switch to F5-TTS mode
AUDIO_SOURCE_MODE=f5tts

# F5-TTS API endpoint
F5TTS_API_URL=http://127.0.0.1:7865

# Reference audio for voice cloning
F5TTS_REF_AUDIO_PATH=workspace/voice_ref/my_voice.wav
F5TTS_REF_TEXT=这是参考文本，应该与音频内容一致

# Optional: Adjust speech speed
F5TTS_SPEED=1.0

# Optional: Enable pacing
TTS_ENABLE_PACING=1
TTS_TARGET_CPS_MIN=3.2
TTS_TARGET_CPS_MAX=4.8
```

### Step 5: Run Pipeline

```bash
set PYTHONPATH=src
python src/main.py --project demo_project --topic "Your topic"
```

## Configuration Options

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `F5TTS_API_URL` | F5-TTS FastAPI server URL | `http://127.0.0.1:7865` |
| `F5TTS_API_KEY` | Optional API key | - |
| `F5TTS_REF_AUDIO_PATH` | Path to reference audio (wav) | - |
| `F5TTS_REF_TEXT` | Text content of reference audio | - |
| `F5TTS_SAMPLE_RATE` | Output audio sample rate | `22050` |
| `F5TTS_SPEED` | Speech speed multiplier | `1.0` |
| `F5TTS_TIMEOUT_SEC` | API request timeout | `120` |

### Comparison with CosyVoice

| Feature | F5-TTS | CosyVoice-300M |
|---------|--------|----------------|
| Reference audio | 3-5 seconds | 10+ seconds |
| Voice quality | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Cross-lingual | Excellent | Good |
| Inference speed | Fast (~2-3x RT) | Fast (~2x RT) |
| GPU memory | ~6GB | ~4GB |
| Emotion control | Good | Better |

## Troubleshooting

### F5-TTS server not reachable

```powershell
# Check if container is running
docker ps | Select-String f5tts

# View container logs
docker logs -f f5tts_server

# Restart container
docker restart f5tts_server
```

### Reference audio not found

Ensure the path is correct and file exists:

```powershell
# Test with absolute path
$env:F5TTS_REF_AUDIO_PATH = "C:\docker\Myavatar\workspace\voice_ref\my_voice.wav"
```

### Out of memory (OOM)

Reduce batch size or close other GPU applications:
- F5-TTS requires ~6GB GPU memory
- RTX 3080Ti (12GB) should have plenty of headroom

## Advanced Usage

### Multiple Voice Personas

Create multiple reference audio files and switch between them:

```env
# Persona 1: Professional host
F5TTS_REF_AUDIO_PATH=workspace/voice_ref/host_pro.wav
F5TTS_REF_TEXT=欢迎收看今天的节目

# Persona 2: Casual friend (switch by updating .env)
# F5TTS_REF_AUDIO_PATH=workspace/voice_ref/casual_friend.wav
# F5TTS_REF_TEXT=嘿，好久不见
```

### Custom Speech Speed

```env
# Slower (more deliberate)
F5TTS_SPEED=0.8

# Faster (more energetic)
F5TTS_SPEED=1.2
```

### Batch Optimization

For batch processing, F5-TTS client encodes reference audio once and reuses it across all requests automatically.

## Resources

- [F5-TTS GitHub](https://github.com/SWivid/F5-TTS)
- [F5-TTS Paper](https://arxiv.org/abs/2410.06885)
- [HuggingFace Demo](https://huggingface.co/spaces/mrfakename/E2-F5-TTS)
