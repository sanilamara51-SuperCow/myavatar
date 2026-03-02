# Myavatar 口播视频智能体

**核心技能**: 抖音链接 → 自动理解 → 口播视频生成

---

## 快速启动

```bash
cd C:\docker\Myavatar
set PYTHONPATH=src
python src/main.py --douyin-url "https://v.douyin.com/xxx/"
```

## 能力清单

| 能力 | 说明 |
|------|------|
| 📥 抖音下载 | 分享链接 → 无水印视频 |
| 🎬 关键帧抽取 | 镜头分割 + K-Means 聚类 |
| 🧠 视频理解 | Qwen2.5-VL 结构化分析 |
| ✍️ 剧本生成 | CrewAI 多 agent 反思 |
| 🎨 幻灯片生成 | Marp + 网页截图 |
| 🎙️ TTS 合成 | CosyVoice / Mock |
| 🎞️ 视频组装 | FFmpeg + OpenCV |

## 环境配置

```env
# 视频理解 (必选其一)
## 云端 (推荐)
CLOUD_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CLOUD_VISION_MODEL_NAME=qwen-vl-max-latest
DASHSCOPE_API_KEY=sk-xxx

## 本地 (Ollama)
LOCAL_VISION_MODEL_BASE_URL=http://localhost:11434/v1
LOCAL_VISION_MODEL_NAME=qwen2.5-vl-7b-instruct

# 抖音下载 API
DOUYIN_PARSE_API_PRIMARY=https://www.devtool.top/api/douyin/parse

# 关键帧配置
VIDEO_KEYFRAME_SCENE_THRESHOLD=30.0
VIDEO_KEYFRAME_MAX_PER_SCENE=3
```

## 命令行参数

```bash
# 基础用法
python src/main.py --douyin-url "https://v.douyin.com/xxx/"

# 自定义模型
python src/main.py \
  --douyin-url "https://v.douyin.com/xxx/" \
  --node-model-override n0b_video_understanding=qwen_vision::qwen-vl-max-latest

# 指定项目
python src/main.py \
  --project my_project \
  --douyin-url "https://v.douyin.com/xxx/"
```

## 流程架构

```
START → [douyin_url?]
  ├─ YES → n0 下载 → n0a 抽帧 → n0b 理解 → n1c 剧本 → n3 截图 → n2b 幻灯 → n4 TTS → n5 组装 → END
  └─ NO  → n1c 剧本 → n3 截图 → n2b 幻灯 → n4 TTS → n5 组装 → END
```

## 输出位置

```
workspace/projects/{project}/runs/{run_id}/
├── video_input/douyin_video.mp4       # 下载的视频
├── keyframes/*.jpg                     # 关键帧
├── debug/video_understanding.json      # 结构化分析
├── slides/*.png                        # 幻灯片
├── audio/*.wav                         # 音频片段
└── final.mp4                           # 最终视频
```

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| API key 错误 | 检查 `DASHSCOPE_API_KEY` |
| 下载失败 | 确认抖音链接格式正确 |
| 抽帧为空 | 降低 `VIDEO_KEYFRAME_SCENE_THRESHOLD` |
| JSON 解析失败 | 换用更大模型 (72B) |

## 详细文档

- `docs/video_understanding_feature.md` - 完整技术文档
- `docs/arch.md` - 架构设计
- `CLAUDE.md` - 项目概览
