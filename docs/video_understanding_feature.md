# Video Understanding + Douyin Download Feature

**创建时间**: 2026-03-02
**版本**: v1.0

---

## Overview

This feature enables end-to-end video content processing:

```
Douyin Share URL → Download → Keyframe Extraction → AI Understanding → Structured JSON → Video Script → Final Video
```

### Core Capabilities

1. **Douyin Video Download**: Parse share URLs and download watermark-free videos
2. **Keyframe Extraction**: Scene detection + K-Means clustering for optimal frame selection
3. **Video Understanding**: Qwen2.5-VL multimodal analysis for structured content extraction
4. **Seamless Integration**: Automatically feeds into existing Hybrid Graph pipeline

---

## Architecture

### New Nodes (added to Hybrid Graph)

```
START → [has douyin_url?]
  ├─ YES → n0_douyin_downloader → n0a_keyframe_extractor → n0b_video_understanding → n1c_hybrid_content_writer → ...
  └─ NO  → n1c_hybrid_content_writer → ... (original flow)
```

| Node | File | Purpose |
|------|------|---------|
| **n0_douyin_downloader** | `src/nodes/n0_douyin_downloader.py` | API parsing + video download |
| **n0a_keyframe_extractor** | `src/nodes/n0a_video_keyframe_extractor.py` | PySceneDetect + K-Means keyframe extraction |
| **n0b_video_understanding** | `src/nodes/n0b_video_understanding_node.py` | Qwen2.5-VL multimodal analysis |

### New Utility Modules

| Module | Purpose |
|--------|---------|
| `src/utils/douyin_api_client.py` | Douyin API client for URL parsing and video download |
| `src/utils/video_keyframe_extractor.py` | Scene detection + K-Means clustering |
| `src/utils/video_understanding_schema.py` | Pydantic schema for structured output |

### State Extensions

New fields added to `VideoGenerationState`:

```python
# Input
douyin_share_url: str

# Node 0 output
video_path: str
video_metadata: Dict[str, Any]  # {title, author, duration_sec, share_url, file_size_bytes}

# Node 0a output
keyframe_paths: List[str]
keyframe_timestamps: List[float]
scene_boundaries: List[Dict[str, Any]]

# Node 0b output
video_understanding: Optional[Dict[str, Any]]
```

---

## Quick Start

### 1. Configure Environment

Add to `.env`:

```env
# Video Understanding (choose one)
# Option A: Local (Ollama)
LOCAL_VISION_MODEL_BASE_URL=http://localhost:11434/v1
LOCAL_VISION_MODEL_NAME=qwen2.5-vl-7b-instruct

# Option B: Cloud (阿里云百炼)
CLOUD_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CLOUD_VISION_MODEL_NAME=qwen-vl-max-latest
DASHSCOPE_API_KEY=your-dashscope-api-key

# Douyin Download API (default: devtool.top free API)
DOUYIN_PARSE_API_PRIMARY=https://www.devtool.top/api/douyin/parse

# Keyframe Extraction Settings
VIDEO_KEYFRAME_SCENE_THRESHOLD=30.0
VIDEO_KEYFRAME_MAX_PER_SCENE=3
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
# New dependencies:
# - pyscenedetect[opencv]>=0.6.3
# - scikit-learn>=1.4.0
```

### 3. Run with Douyin URL

```bash
cd C:\docker\Myavatar
set PYTHONPATH=src
python src/main.py --douyin-url "https://v.douyin.com/xxx/"
```

### 4. Combined with Other Options

```bash
# With custom model overrides
python src/main.py \
  --douyin-url "https://v.douyin.com/xxx/" \
  --node-model-override n0b_video_understanding=qwen_vision::qwen-vl-max-latest \
  --project my_video_project
```

---

## Component Details

### 1. Douyin Downloader (`n0_douyin_downloader`)

**API Provider**: devtool.top (free, no auth required)

**Response Schema**:
```json
{
  "video_path": "C:\\docker\\Myavatar\\workspace\\projects\\demo_project\\runs\\20260302_120000\\video_input\\douyin_video.mp4",
  "video_metadata": {
    "title": "视频标题",
    "author": "作者名",
    "duration_sec": 45.5,
    "share_url": "https://v.douyin.com/xxx/",
    "file_size_bytes": 12345678
  }
}
```

**Alternative APIs**:
- Self-hosted: Evil0ctal/Douyin_TikTok_Download_API
- Other free APIs: adjust `DOUYIN_PARSE_API_PRIMARY` env var

### 2. Keyframe Extractor (`n0a_keyframe_extractor`)

**Algorithm**:
1. **Scene Detection**: PySceneDetect with ContentDetector
2. **Frame Sampling**: Uniform sampling within each scene
3. **Clustering**: K-Means on color histograms
4. **Selection**: Centroid-closest frames as keyframes

**Configuration**:
- `VIDEO_KEYFRAME_SCENE_THRESHOLD`: Higher = fewer scenes (default: 30.0)
- `VIDEO_KEYFRAME_MAX_PER_SCENE`: Max keyframes per scene (default: 3)

**Output**:
- `keyframe_paths`: List of JPEG file paths
- `keyframe_timestamps`: Timestamps in seconds
- `scene_boundaries`: Scene metadata with time ranges

### 3. Video Understanding (`n0b_video_understanding`)

**Model**: Qwen2.5-VL (7B local or 72B cloud)

**Prompt Strategy**:
- System prompt defines structured JSON schema
- All keyframes passed as image inputs
- Chain-of-thought for detailed analysis

**Output Schema** (simplified):
```json
{
  "understanding": {
    "title_suggestion": " descriptive title",
    "one_sentence_summary": "Core message in one sentence",
    "detailed_summary": "2-3 paragraph detailed summary",
    "main_topics": ["topic1", "topic2", "topic3"],
    "key_points": ["point1", "point2", ...],
    "scenes": [
      {
        "scene_index": 0,
        "time_range": "00:00 - 00:15",
        "visual_content": "Description of visual elements",
        "on_screen_text": "Visible text or null",
        "mood_atmosphere": "energetic, professional, etc."
      }
    ],
    "content_elements": [
      {
        "type": "key_message|quote|statistic|product|person|action",
        "content": "The actual content",
        "timestamp": "mm:ss",
        "importance": 5
      }
    ],
    "video_style": "tutorial|vlog|documentary|...",
    "target_audience": "Inferred audience",
    "suggested_tags": ["tag1", "tag2", ...],
    "reusable_elements": ["Clips/quotes for future use"]
  }
}
```

**Output Location**: `{run_dir}/debug/video_understanding.json`

---

## Model Configuration

### Provider Registry Entries

New provider and model registered in `src/storage/provider_registry.py`:

```python
# Provider
{
  "provider_id": "qwen_vision",
  "name": "Qwen2.5-VL (Video Understanding)",
  "kind": "openai_compatible",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "api_key_env": "DASHSCOPE_API_KEY"
}

# Model
{
  "model_id": "qwen_vision::qwen-vl-max-latest",
  "provider_id": "qwen_vision",
  "model_name": "qwen-vl-max-latest",
  "capability": "vision",
  "supports_vision": True,
  "supports_json_mode": True
}
```

### Model Routing

Use `--node-model-override` to specify models per node:

```bash
# Use cloud model for video understanding
python src/main.py \
  --node-model-override n0b_video_understanding=qwen_vision::qwen-vl-max-latest

# Use local Ollama model
python src/main.py \
  --node-model-override n0b_video_understanding=qwen_vision::qwen2.5-vl-7b-instruct
```

---

## Testing

### Unit Test: Douyin Download

```bash
python -c "
from utils.douyin_api_client import DouyinAPIClient
client = DouyinAPIClient()
result = client.parse_share_url('https://v.douyin.com/xxx/')
print(result)
"
```

### Unit Test: Keyframe Extraction

```bash
python -c "
from utils.video_keyframe_extractor import extract_keyframes
result = extract_keyframes(
    video_path='path/to/video.mp4',
    output_dir='path/to/output',
    scene_threshold=30.0,
    max_keyframes_per_scene=3
)
print(f\"Extracted {result['stats']['total_keyframes']} keyframes\")
"
```

### Integration Test: Full Pipeline

```bash
# With a real Douyin URL
python src/main.py --douyin-url "https://v.douyin.com/xxx/"

# Check outputs in:
# workspace/projects/demo_project/runs/{run_id}/
#   - video_input/douyin_video.mp4
#   - keyframes/scene_000_keyframe_00.jpg
#   - debug/video_understanding.json
```

---

## Troubleshooting

### Douyin Download Fails

**Symptom**: `DouyinAPIError: API returned error code X`

**Solutions**:
1. Try alternative API endpoint
2. Check if URL format is valid (should be `v.douyin.com` or `douyin.com`)
3. Verify network connectivity

### Keyframe Extraction Returns Empty

**Symptom**: No keyframes extracted

**Solutions**:
1. Lower `VIDEO_KEYFRAME_SCENE_THRESHOLD` (try 20.0)
2. Check if video file exists and is readable
3. Verify OpenCV is installed correctly (`pip install opencv-python`)

### Video Understanding Returns Garbage

**Symptom**: JSON parsing fails or output is nonsensical

**Solutions**:
1. Increase model temperature for more deterministic output (currently 0.3)
2. Use larger model (72B instead of 7B)
3. Check if keyframes are being passed correctly (verify non-empty `keyframe_paths`)

### Out of Memory (Local Models)

**Symptom**: CUDA out of memory error

**Solutions**:
1. Reduce `VIDEO_KEYFRAME_MAX_PER_SCENE` to 2
2. Use INT4 quantized model
3. Increase `--max-new-tokens` if using vLLM

---

## Future Enhancements (P2)

### Video Asset Retrieval (P2)

- SQLite database for storing video metadata and understanding
- Semantic search via embeddings
- Clip-level retrieval for reuse

### Improved Keyframe Selection

- Motion-based keyframe scoring
- Face detection for keyframes with people
- OCR for frames with text

### Multi-Modal Understanding

- Audio transcription integration
- Speaker diarization
- Emotion/tone detection

---

## Compliance Notes

⚠️ **Important**: This feature is for **personal learning and research** only.

- Respect content creators' copyrights
- Do not use for commercial purposes without permission
- Comply with Douyin's Terms of Service
- Watermark removal should only be used for personal analysis

---

## Related Documentation

- [Architecture Overview](arch.md)
- [Provider Registry](provider_registry.md)
- [Hybrid Graph Workflow](../src/orchestrator/hybrid_graph.py)
- [CosyVoice Local Deploy](cosyvoice_local_deploy.md)
