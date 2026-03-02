# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Myavatar is an AI-powered video generation pipeline that creates "talking head + slides" style videos for platforms like Douyin (TikTok). It uses a multi-agent architecture orchestrated by LangGraph to transform text topics into complete videos with synchronized audio and visual assets.

**Core Philosophy**: Video-as-Code — every step is abstracted as data structures controlled by LLMs.

## Architecture

### Hybrid Graph Pipeline (`src/orchestrator/`)

The main workflow is a LangGraph state machine with video understanding support:

```
START → [has douyin_url?]
  ├─ YES → n0_douyin_downloader → n0a_keyframe_extractor → n0b_video_understanding → n1c_hybrid_content_writer → ...
  └─ NO  → n1c_hybrid_content_writer → n3_browser_capture → n2b_hybrid_slide_generator → n4_tts_synthesizer → n5_ffmpeg_assembler → END
```

| Node | Purpose | Key Files |
|------|---------|-----------|
| n0_douyin_downloader | Douyin share URL parsing + video download | `src/nodes/n0_douyin_downloader.py` |
| n0a_keyframe_extractor | PySceneDetect + K-Means keyframe extraction | `src/nodes/n0a_video_keyframe_extractor.py` |
| n0b_video_understanding | Qwen2.5-VL multimodal video analysis | `src/nodes/n0b_video_understanding_node.py` |
| n1c_hybrid_content_writer | LLM-driven script writing with CrewAI reflection | `src/nodes/n1c_hybrid_content_writer.py` |
| n3_browser_capture | Playwright-based webpage screenshots for slides | `src/nodes/n3_browser_capture.py` |
| n2b_hybrid_slide_generator | Marp-based markdown→PNG slide rendering | `src/nodes/n2b_hybrid_slide_generator.py` |
| n4_tts_synthesizer | TTS synthesis (mock/CosyVoice/local_voice modes) | `src/nodes/n4_tts_synthesizer.py` |
| n5_ffmpeg_assembler | OpenCV+FFmpeg video assembly | `src/nodes/n5_ffmpeg_assembler.py` |

### Graph Variants (`src/orchestrator/`)

Three graph implementations share the same state schema:

| Graph | File | Purpose |
|-------|------|---------|
| **Basic** | `graph.py` | Text-only script → slides → video |
| **Hybrid** | `hybrid_graph.py` | Full pipeline with browser capture for web screenshots |
| **PPT** | `ppt_graph.py` | PPT image input → script → video (vision-first) |

### State Management (`src/orchestrator/state.py`)

`VideoGenerationState` is a TypedDict that flows through all nodes, carrying:
- Workflow metadata: `project_name`, `run_id`, `run_dir`
- Input: `topic`, `duration_mins`, `target_audience`, `ppt_image_paths`
- Intermediate outputs: `slides_data`, `markdown_content`, `image_paths`, `audio_paths`
- Final output: `final_video_path`
- Error handling: `error_msg` (triggers early termination)

### Key Dependencies

- **LangGraph**: State machine orchestration
- **CrewAI**: Multi-agent script reflection (optional)
- **Playwright**: Headless browser capture for web screenshots
- **Marp (marp-cli)**: Markdown→PNG slide rendering
- **CosyVoice**: Local TTS service (FastAPI-based)
- **F5-TTS**: Advanced voice cloning (recommended for quality)
- **FFmpeg + OpenCV**: Video assembly pipeline
- **PySceneDetect + scikit-learn**: Video keyframe extraction
- **PySide6**: Desktop GUI framework

### Provider Registry (`src/storage/provider_registry.py`)

SQLite-based model routing system that manages:
- **Provider profiles**: API endpoints, credentials, capabilities
- **Model specs**: Text/vision/reflection models per provider
- **Project routes**: Per-project model defaults
- **Node overrides**: Per-node model overrides for fine-grained control

```bash
# Query the registry database
python -c "from storage.provider_registry import *; init_provider_registry(); print(list_models())"
```

## Commands

### Prerequisites

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install marp-cli (required for slide generation)
npm install -g @marp-team/marp-cli

# Install Playwright browsers
playwright install

# Ensure ffmpeg is available (set FFMPEG_BIN if not in PATH)
```

### Run the Pipeline

```bash
# Basic run (uses default topic)
cd C:\docker\Myavatar
set PYTHONPATH=src
python src/main.py

# Run with custom topic
python src/main.py --topic "Your topic here" --duration-mins 2.0

# Run with Douyin URL (video understanding flow)
python src/main.py --douyin-url "https://v.douyin.com/xxx/"

# Run with custom model overrides
python src/main.py --text-model-id doubao-seed-2-0-pro-260215 --vision-model-id gpt-4o

# Override per-node models
python src/main.py --node-model-override n1_content_writer=model_id --node-model-override n2_slide_generator=vision_model_id
```

### Video Understanding Configuration

Configure via `.env`:

```env
# Video Understanding (Qwen2.5-VL)
# Local deployment (Ollama/vLLM)
LOCAL_VISION_MODEL_BASE_URL=http://localhost:11434/v1
LOCAL_VISION_MODEL_NAME=qwen2.5-vl-7b-instruct

# Cloud deployment (阿里云百炼)
CLOUD_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CLOUD_VISION_MODEL_NAME=qwen-vl-max-latest
DASHSCOPE_API_KEY=your-dashscope-api-key

# Douyin Download API
DOUYIN_PARSE_API_PRIMARY=https://www.devtool.top/api/douyin/parse

# Keyframe Extraction Settings
VIDEO_KEYFRAME_SCENE_THRESHOLD=30.0
VIDEO_KEYFRAME_MAX_PER_SCENE=3
```

See [docs/video_understanding_feature.md](docs/video_understanding_feature.md) for detailed documentation.

### TTS Modes

Configure via `.env`:

```env
# Mock mode (for testing)
AUDIO_SOURCE_MODE=mock

# CosyVoice (requires running CosyVoice FastAPI service)
AUDIO_SOURCE_MODE=cosyvoice
COSYVOICE_API_URL=http://127.0.0.1:50000
COSYVOICE_API_STYLE=official_fastapi
COSYVOICE_MODE=sft
COSYVOICE_VOICE=<speaker_id>

# F5-TTS (Advanced voice cloning - recommended for RTX 3080Ti)
AUDIO_SOURCE_MODE=f5tts
F5TTS_API_URL=http://127.0.0.1:7865
F5TTS_REF_AUDIO_PATH=workspace/voice_ref/my_voice.wav
F5TTS_REF_TEXT=这是参考文本

# Local voice files (user-recorded)
AUDIO_SOURCE_MODE=local_voice
VOICE_INPUT_DIR=workspace/voice_input
```

### CosyVoice Local Deployment

```powershell
# Build and start CosyVoice FastAPI (see docs/cosyvoice_local_deploy.md)
powershell -ExecutionPolicy Bypass -File scripts\start_cosyvoice_fastapi.ps1 `
  -CosyVoiceRepoDir C:\docker\CosyVoice `
  -ImageName cosyvoice:v1.0 `
  -HostPort 50000
```

### F5-TTS Local Deployment (Recommended)

```powershell
# Clone F5-TTS repository first
git clone https://github.com/SWivid/F5-TTS.git C:\docker\F5-TTS

# Build and start F5-TTS FastAPI (see docs/f5_tts_guide.md)
powershell -ExecutionPolicy Bypass -File scripts\start_f5tts_fastapi.ps1 `
  -F5TTSRepoDir C:\docker\F5-TTS `
  -ImageName f5tts:v1.0 `
  -HostPort 7865
```

## Windows-Specific Commands

```powershell
# Set environment variables for current session
$env:PYTHONPATH='src'
$env:ARK_API_KEY='your-key-here'

# Run the pipeline
python src/main.py

# Launch desktop GUI
python src/desktop_app.py

# CosyVoice Docker deployment
powershell -ExecutionPolicy Bypass -File scripts\start_cosyvoice_fastapi.ps1 `
  -CosyVoiceRepoDir C:\docker\CosyVoice `
  -ImageName cosyvoice:v1.0 `
  -ContainerName cosyvoice_fastapi `
  -HostPort 50000 `
  -ModelDir iic/CosyVoice-300M
```

## Project Structure

```
Myavatar/
├── src/
│   ├── main.py                    # CLI entry point
│   ├── desktop_app.py             # GUI entry point (PySide6)
│   ├── orchestrator/
│   │   ├── state.py               # VideoGenerationState TypedDict
│   │   ├── graph.py               # Basic graph (text-only)
│   │   ├── hybrid_graph.py        # Full pipeline with browser capture
│   │   └── ppt_graph.py           # PPT-only graph variant
│   ├── nodes/
│   │   ├── n1_content_writer.py   # Script generation
│   │   ├── n1b_ppt_vision_scriptwriter.py
│   │   ├── n1c_hybrid_content_writer.py
│   │   ├── n2_slide_generator.py  # Marp slide generation
│   │   ├── n2b_hybrid_slide_generator.py
│   │   ├── n3_browser_capture.py  # Playwright screenshots
│   │   ├── n4_tts_synthesizer.py  # TTS synthesis
│   │   └── n5_ffmpeg_assembler.py # Video assembly
│   ├── agents/
│   │   ├── __init__.py
│   │   └── script_reflection.py   # CrewAI reflection agents
│   ├── utils/
│   │   ├── marp_helper.py         # Marp CLI wrapper
│   │   ├── tts_client.py          # CosyVoice API client
│   │   ├── ffmpeg_mixer.py        # OpenCV+FFmpeg assembly
│   │   ├── slide_composer.py      # Slide layout utilities
│   │   └── theme_manager.py       # PPT theme management
│   ├── storage/
│   │   ├── provider_registry.py   # LLM provider management
│   │   └── persona_registry.py    # TTS persona configuration
│   ├── models/
│   │   ├── provider.py            # ProviderProfile, ModelSpec, ResolvedModelRoute
│   │   └── persona.py             # TTS persona data model
│   └── desktop/                   # PySide6 GUI components
│       ├── app.py                 # Desktop app entry
│       ├── main_window.py         # Main window UI
│       └── pages/                 # Tab pages (dashboard, providers, personas, projects)
├── workspace/
│   ├── projects/                  # Per-project workspace dirs
│   │   └── <project_name>/
│   │       ├── inputs/            # Input assets (images, script.txt)
│   │       └── runs/              # Generated outputs per run
│   ├── voice_input/               # User-recorded voice files
│   └── .myavatar/app.db           # Provider registry SQLite database
├── CosyVoice/                     # Upstream CosyVoice submodule
└── docs/
    ├── arch.md                    # Architecture design (Chinese)
    ├── cosyvoice_local_deploy.md  # CosyVoice Docker deployment
    ├── f5_tts_guide.md            # F5-TTS voice cloning guide
    ├── provider_registry.md       # Provider registry documentation
    ├── persona_mixing_and_pacing.md
    └── ...
```

## Configuration

### Environment Variables (`.env`)

See `.env.example` for full list. Key configurations:

**LLM Providers:**
- `ARK_API_KEY`, `ARK_BASE_URL`, `ARK_API_MODEL` - Doubao (Volces) API
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_API_MODEL` - OpenAI fallback
- `OPENAI_VISION_*` - Vision model for slide analysis

**Script Reflection:**
- `ENABLE_CREW_REFLECTION=1` - Enable CrewAI multi-agent review
- `SCRIPT_REFLECTION_MAX_ROUNDS` - Max reflection iterations
- `SCRIPT_REFLECTION_TARGET_SCORE` - Quality threshold (0-100)

**Browser Capture:**
- `BROWSER_CAPTURE_WAIT_MS` - Extra wait before screenshot
- `BROWSER_CAPTURE_VIEWPORT_WIDTH/HEIGHT` - Viewport size

**TTS Pacing:**
- `TTS_ENABLE_PACING=1` - Enable auto speed adjustment
- `TTS_TARGET_CPS_MIN/MAX` - Characters per second range
- `TTS_AUTO_SPEEDUP` - Allow speeding up slow audio

### Persona Configuration

Personas are registered in `workspace/personas.json` (or via CLI):

```json
{
  "host": {
    "id": "host",
    "name": "Default Host",
    "enabled": 1,
    "cosyvoice_mode": "sft",
    "voice": "longxiaochun",
    "sample_rate": 22050
  }
}
```

### Slide Templates

Templates are CSS themes for Marp. Located in `workspace/themes/`.
Configure via `PPT_TEMPLATE_ID` env var or `--template-id` CLI flag.

## Desktop GUI

```bash
# Launch the PySide6 desktop application
python src/desktop_app.py
```

The GUI provides:
- **Dashboard**: Pipeline status and quick actions
- **Providers**: LLM provider configuration (ARK, OpenAI, etc.)
- **Personas**: TTS voice persona management
- **Projects**: Project workspace management

## Testing

```bash
# Set PYTHONPATH for all commands
set PYTHONPATH=src

# Test individual components
python src/utils/tts_client.py         # TTS mock generation
python src/utils/marp_helper.py        # Marp rendering
python src/utils/ffmpeg_mixer.py       # FFmpeg assembly (requires sample inputs)

# Component test files
python test_api_doubao.py              # Doubao LLM API test
python test_cosy.py                    # CosyVoice TTS test
python test_hybrid_api.py              # Full hybrid pipeline test
python test_vision_standalone.py       # Vision model test
```

## Design Principles

1. **Deterministic State Machine**: LangGraph ensures reproducible pipelines with explicit error boundaries
2. **Declarative Visuals**: Marp Markdown > imperative layout code (LLM-friendly)
3. **Absolute Time Alignment**: Audio duration drives slide timing via FFmpeg concat demuxer
4. **Hybrid Input Modes**: Support both fully automated generation and human-injected assets
5. **Persona-based TTS**: Multi-speaker support via segment-level persona switching

## Common Issues

**Marp not found**: Ensure `marp` is in PATH (`npm install -g @marp-team/marp-cli`)

**Playwright browser errors**: Run `playwright install` to download browser binaries

**FFmpeg not found**: Set `FFMPEG_BIN` env var to ffmpeg executable path

**CosyVoice connection failed**: Ensure Docker container is running and port 50000 is accessible

**Audio/video sync issues**: Check that `audio_paths` and `image_paths` have matching lengths; verify TTS duration detection
