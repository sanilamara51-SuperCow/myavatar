# Myavatar 智能视频创作伙伴

> **项目位置**: `C:/docker/Myavatar/`
> **核心理念**: `video-as-code` — 从结构化脚本到音画同步的自动化视频生成管线

---

## 快速启动

### CLI 方式
```bash
cd C:\docker\Myavatar
set PYTHONPATH=src

# 标准流程 (文本驱动)
python src/main.py --project demo_project --template-id tech_burst

# 抖音视频理解流程
python src/main.py --douyin-url "https://v.douyin.com/xxx/"

# 覆盖内容输入
python src/main.py ^
  --project demo_project ^
  --topic "你的自定义选题" ^
  --duration-mins 2.0 ^
  --target-audience "目标受众" ^
  --template-id data_focus
```

### 桌面应用
```bash
python src/desktop_app.py
```

---

## 核心架构

### LangGraph 状态图 (hybrid_graph.py)

```
视频输入流程:
START → [有 douyin_url?] → n0_抖音下载 → n0a_关键帧提取 → n0b_视频理解 → n1c_混合内容写作 → ...

标准流程 (无视频输入):
START → n1c_混合内容写作 → n3_浏览器捕获 → n2b_混合幻灯片生成 → n4_TTS 合成 → n5_FFmpeg 组装 → END
```

### VideoGenerationState 状态定义

```python
# 工作流元数据
project_name, project_dir, run_id, run_dir

# 输入
topic, duration_mins, target_audience, template_id
reference_image_path, reference_image_url, ppt_image_paths

# 视频输入 (抖音分享链接流程)
douyin_share_url, video_path, video_metadata

# 节点输出
slides_data: List[SlideContent]  # Node 1
markdown_content, image_paths    # Node 2
audio_paths, audio_durations     # Node 4
final_video_path                 # Node 5

# 全局错误通道
error_msg: Optional[str]
```

### 节点清单

| 节点 | 文件 | 功能 |
|------|------|------|
| n0 | `nodes/n0_douyin_downloader.py` | 抖音视频下载 |
| n0a | `nodes/n0a_video_keyframe_extractor.py` | 关键帧提取 |
| n0b | `nodes/n0b_video_understanding_node.py` | 视频内容理解 |
| n1c | `nodes/n1c_hybrid_content_writer.py` | 混合内容写作 (LLM + 图像理解) |
| n3 | `nodes/n3_browser_capture.py` | 浏览器截图捕获 |
| n2b | `nodes/n2b_hybrid_slide_generator.py` | 混合幻灯片生成 |
| n4 | `nodes/n4_tts_synthesizer.py` | TTS 语音合成 |
| n5 | `nodes/n5_ffmpeg_assembler.py` | FFmpeg 视频组装 |

---

## 能力清单

| 能力 | 说明 | 配置 |
|------|------|------|
| 📥 抖音下载 | 分享链接 → 无水印视频 | `DOUYIN_PARSE_API_PRIMARY` |
| 🎬 关键帧抽取 | 镜头分割 + K-Means 聚类 | `VIDEO_KEYFRAME_SCENE_THRESHOLD` |
| 🧠 视频理解 | Qwen2.5-VL 结构化分析 | `CLOUD_VISION_BASE_URL` |
| ✍️ 剧本生成 | CrewAI 多 agent 反思 | `ENABLE_CREW_REFLECTION` |
| 🎨 幻灯片生成 | Marp + 模板系统 | `PPT_TEMPLATE_ID` |
| 🌐 浏览器捕获 | Playwright 网页截图 | `BROWSER_CAPTURE_*` |
| 🎙️ TTS 合成 | CosyVoice/F5-TTS/自录音 | `AUDIO_SOURCE_MODE` |
| 🎚️ 语速控制 | 自动 pacing 调整 | `TTS_TARGET_CPS_*` |
| 🎞️ 视频组装 | FFmpeg + OpenCV 混合方案 | `FFMPEG_BIN` |

---

## Phase 1: 项目初始化

### 项目目录结构
```
workspace/projects/<project_name>/
├── inputs/
│   ├── script.txt       # 脚本输入
│   ├── meta.txt         # 元数据 (受众、时长等)
│   └── voice_input/     # 自录音文件 (voice_000.wav, voice_001.wav...)
├── runs/
│   └── <run_id>/
│       ├── slides/      # 生成的幻灯片 PNG
│       ├── audio/       # 生成的音频文件
│       └── output.mp4   # 最终视频
```

### 环境变量 (.env)

```bash
# === LLM 路由 (Provider Registry) ===
ARK_API_KEY=xxx
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_API_MODEL=doubao-seed-2-0-pro-260215

# === 视频理解 (可选) ===
# 云端 (推荐)
CLOUD_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CLOUD_VISION_MODEL_NAME=qwen-vl-max-latest
DASHSCOPE_API_KEY=sk-xxx

# 本地 (Ollama)
# LOCAL_VISION_MODEL_BASE_URL=http://localhost:11434/v1
# LOCAL_VISION_MODEL_NAME=qwen2.5-vl-7b-instruct

# === TTS 配置 ===
AUDIO_SOURCE_MODE=cosyvoice  # mock | cosyvoice | f5tts | local_voice
COSYVOICE_API_URL=http://127.0.0.1:50000
COSYVOICE_API_KEY=xxx
COSYVOICE_MODE=sft
COSYVOICE_VOICE=longxiaochun
COSYVOICE_AUDIO_FORMAT=wav
COSYVOICE_SAMPLE_RATE=22050

# === 节奏控制 ===
TTS_ENABLE_PACING=true
TTS_TARGET_CPS_MIN=3.2    # 最小字符/秒
TTS_TARGET_CPS_MAX=4.8    # 最大字符/秒
TTS_AUTO_SPEEDUP=false
FFMPEG_BIN=C:\ffmpeg\bin\ffmpeg.exe

# === 剧本反思 ===
ENABLE_CREW_REFLECTION=true
SCRIPT_REFLECTION_ENGINE=crewai  # crewai | model
SCRIPT_REFLECTION_MAX_ROUNDS=3
SCRIPT_REFLECTION_TARGET_SCORE=85

# === 模板配置 ===
PPT_TEMPLATE_ID=tech_burst  # tech_burst | data_focus | tutorial_clean

# === Persona 配置 ===
ENABLE_PERSONA_MIX=true
DEFAULT_PERSONA_ID=host
TTS_DEFAULT_PAUSE_MS=260

# === 浏览器捕获 ===
BROWSER_CAPTURE_WIDTH=1920
BROWSER_CAPTURE_HEIGHT=1080
BROWSER_CAPTURE_WAIT_MS=2000

# === 抖音下载 API ===
DOUYIN_PARSE_API_PRIMARY=https://www.devtool.top/api/douyin/parse

# === 关键帧配置 ===
VIDEO_KEYFRAME_SCENE_THRESHOLD=30.0
VIDEO_KEYFRAME_MAX_PER_SCENE=3
```

---

## Phase 2: 内容创作 (Node 1)

### Node 1C: 混合内容写作 (`nodes/n1c_hybrid_content_writer.py`)

**输入**:
- `topic`: 视频主题
- `duration_mins`: 目标时长 (分钟)
- `target_audience`: 目标受众
- `template_id`: PPT 模板 ID
- `douyin_share_url` (可选): 抖音分享链接 (触发视频理解流程)
- `reference_image_path` (可选): 参考图片

**输出**:
```python
slides_data: List[SlideContent]  # 包含标题、内容要点、配音文本
```

### 剧本反思循环 (`agents/script_reflection.py`)

```bash
# 启用反思循环
ENABLE_CREW_REFLECTION=true
SCRIPT_REFLECTION_ENGINE=crewai  # 或 model
SCRIPT_REFLECTION_MAX_ROUNDS=3
SCRIPT_REFLECTION_TARGET_SCORE=85
```

**反思流程**:
1. Reviewer 评分 (0-100)
2. 如果 score < target_score，执行 Rewrite
3. 最多执行 max_rounds 轮
4. 输出 `script_reflection_report`

---

## Phase 3: 幻灯片生成 (Node 2)

### Node 2B: 混合幻灯片生成 (`nodes/n2b_hybrid_slide_generator.py`)

**Marp 渲染流程** (`utils/marp_helper.py`):

```bash
# Marp CLI 命令
marp temp_input.md --images png --output slide_%03d.png
```

**模板系统** (`utils/theme_manager.py`):

| 模板 ID | 风格 | 配色 |
|--------|------|------|
| `tech_burst` | 科技爆裂风 | 深色底 + 青色高亮 |
| `data_focus` | 数据聚焦风 | 浅色底 + 青色强调 |
| `tutorial_clean` | 教程清爽风 | 白底 + 蓝色强调 |

---

## Phase 4: 浏览器捕获 (Node 3)

### Node 3: 浏览器截图 (`nodes/n3_browser_capture.py`)

当脚本中包含 `capture_url` 时，自动使用 Playwright 捕获网页截图。

**配置**:
```bash
BROWSER_CAPTURE_WIDTH=1920
BROWSER_CAPTURE_HEIGHT=1080
BROWSER_CAPTURE_WAIT_MS=2000
```

---

## Phase 5: TTS 语音合成 (Node 4)

### Node 4: TTS 合成器 (`nodes/n4_tts_synthesizer.py`)

**支持的音频源模式**:
```bash
AUDIO_SOURCE_MODE=mock        # 模拟音频 (测试用)
AUDIO_SOURCE_MODE=cosyvoice   # CosyVoice TTS
AUDIO_SOURCE_MODE=f5tts       # F5-TTS
AUDIO_SOURCE_MODE=local_voice # 用户自录音
```

**CosyVoice 配置** (`utils/tts_client.py`):
```bash
COSYVOICE_API_URL=http://127.0.0.1:50000
COSYVOICE_API_KEY=xxx
COSYVOICE_MODE=sft            # sft | zero_shot | cross_lingual | instruct
COSYVOICE_VOICE=longxiaochun
COSYVOICE_AUDIO_FORMAT=wav
COSYVOICE_SAMPLE_RATE=22050
```

**Persona 混音** (`storage/persona_registry.py`):
```bash
ENABLE_PERSONA_MIX=true
DEFAULT_PERSONA_ID=host
TTS_DEFAULT_PAUSE_MS=260
```

**语速节奏控制** (`utils/ffmpeg_mixer.py`):
```bash
TTS_ENABLE_PACING=true
TTS_TARGET_CPS_MIN=3.2    # 最小字符/秒
TTS_TARGET_CPS_MAX=4.8    # 最大字符/秒
TTS_AUTO_SPEEDUP=false    # 是否自动加速
```

**输出**:
```python
{
    "audio_paths": List[str],       # 音频文件路径
    "audio_durations": List[float], # 音频时长 (秒)
    "audio_segment_report": [...],  # 详细报告
    "audio_pacing_warnings": [...]  # 节奏警告
}
```

---

## Phase 6: 视频组装 (Node 5)

### Node 5: FFmpeg 组装器 (`nodes/n5_ffmpeg_assembler.py`)

**组装流程** (`utils/ffmpeg_mixer.py`):

1. OpenCV 将静态图片渲染成无声 MP4
2. FFmpeg 将纯净 MP4 与对应音频合并
3. 使用 FFmpeg concat 协议拼接所有片段

**配置**:
```bash
FFMPEG_BIN=C:\ffmpeg\bin\ffmpeg.exe  # 或使用 PATH 中的 ffmpeg
```

**输出**:
```
workspace/projects/<project_name>/runs/<run_id>/output.mp4
```

---

## 工具脚本

### CLI 命令行工具

```bash
cd C:/docker/Myavatar

# 运行视频生成管线
python src/main.py --project demo_project --template-id tech_burst

# 覆盖内容输入
python src/main.py ^
  --project demo_project ^
  --topic "你的主题" ^
  --duration-mins 2.0 ^
  --target-audience "目标受众" ^
  --template-id data_focus

# 运行桌面应用
python src/desktop_app.py
```

### Provider Registry CLI

```bash
# 列出所有提供商
python src/provider_registry_cli.py list providers

# 列出所有模型
python src/provider_registry_cli.py list models

# 列出项目路由
python src/provider_registry_cli.py list project-routes

# 列出节点覆盖
python src/provider_registry_cli.py list node-overrides

# 设置项目默认值
python src/provider_registry_cli.py set-project-defaults ^
  --project demo_project ^
  --text-model-id my_text_model ^
  --vision-model-id my_vision_model ^
  --reflection-model-id my_reflect_model
```

### Persona Registry CLI

```bash
# 列出所有 Persona
python src/persona_registry_cli.py list

# 创建/更新 Persona
python src/persona_registry_cli.py upsert --persona-id host --name "主持人"
```

---

## 输出产物

### 最终输出
- 视频：`workspace/projects/<project_name>/runs/<run_id>/output.mp4`

### 中间产物
- `slides/` - Marp 渲染的 PNG 幻灯片
- `audio/` - TTS 合成的音频文件
- `script_reflection_report` - 剧本反思报告
- `audio_segment_report` - 音频分段报告
- `debug/video_understanding.json` - 视频结构化分析 (抖音流程)
- `keyframes/` - 关键帧图片 (抖音流程)

---

## 成功标准

### 功能标准
- [ ] 视频可正常播放
- [ ] 音画同步
- [ ] 无技术错误

### 质量标准
- [ ] 剧本反思分数 ≥ 85
- [ ] CPS 在 3.2-4.8 范围内
- [ ] 所有节点执行成功

---

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| API key 错误 | 检查 `DASHSCOPE_API_KEY` / `ARK_API_KEY` |
| 抖音下载失败 | 确认链接格式正确，检查 `DOUYIN_PARSE_API_PRIMARY` |
| 抽帧为空 | 降低 `VIDEO_KEYFRAME_SCENE_THRESHOLD` |
| JSON 解析失败 | 换用更大模型 (72B+) |
| TTS 无声 | 检查 `COSYVOICE_API_URL` 是否可达 |
| FFmpeg 报错 | 确认 `FFMPEG_BIN` 路径正确 |
| Marp 渲染失败 | 运行 `npm install -g @marp-team/marp-cli` |

---

## 详细文档

- `docs/video_understanding_feature.md` - 视频理解完整技术文档
- `docs/arch.md` - 架构设计
- `docs/implementation_master_plan.md` - 实施主计划
- `docs/provider_registry.md` - 模型路由配置
- `docs/persona_mixing_and_pacing.md` - Persona 混音与节奏控制
- `docs/script_reflection_workflow.md` - 剧本反思工作流
- `docs/browser_capture_workflow.md` - 浏览器捕获工作流
- `docs/template_system.md` - 模板系统
- `docs/cosyvoice_local_deploy.md` - CosyVoice 本地部署
- `CLAUDE.md` - 项目概览

---

## 版本

- v1.0 - 初始版本 (抖音驱动流程)
- v2.0 - 与项目代码完全对齐，新增标准文本驱动流程、完整节点清单、环境变量配置
