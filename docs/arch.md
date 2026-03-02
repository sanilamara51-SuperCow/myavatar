# 抖音知识教学视频全自动生成管线 - 架构设计文档

## 1. 项目概述 (Project Overview)

本项目旨在构建一个基于大模型 (LLM) 和开源工具链的、代码驱动的“知识教学类视频”全自动/半自动生成管线。
核心思想为 **“视频即代码 (Video-as-Code)”**，弃用极耗资源的逐帧渲染库（如 `MoviePy`），转而通过解析结构化数据调用轻量级命令行工具进行拼装。

硬件基准：本地单卡 RTX 3060（12GB/8GB VRAM 均可适配）。

## 2. 核心架构设计 (Architecture Design)

系统采用 **分层解耦架构**，顶层由多智能体工作流引擎驱动，底层由专业的多媒体渲染与处理模块组成。

### 2.1 顶层调度与状态机控制 (Orchestration Layer)
- **核心框架**: LangGraph
- **职责**: 作为全局状态机，负责在不同管线节点间传递上下文（State），处理条件分支，并在关键节点保存检查点（Checkpoint）以便于失败重试断点续传。
- **混合编排**: 在“文案策划”节点，可按需挂载 CrewAI 定义的多角色小队（如编剧、审核员）以激发创意。

### 2.2 视觉合成层 (Visual Synthesis Layer)
将所有视觉元素生成转换为“文本到图像（Text-to-Image / Text-to-Slide）”的过程。
- **幻灯片渲染引擎**: Marp + `marp-cli`
  - 将大模型产出的 Markdown 动态渲染为精美排版的静态无界 PNG 图片序列。
- **实操录屏抓取引擎**: Playwright (Headless Browser)
  - 自动根据脚本指令控制无头浏览器跳转特定 URL（如 GitHub 源码页、Wiki 页面），执行精确高分辨率截图或录屏操作。

### 2.3 听觉合成层 (Audio Synthesis Layer)
- **TTS 引擎**: 云端成熟 API (如 阿里 CosyVoice API 等，初期接入，解耦本地算力墙)。
- **职责**: 解析附带情感标签的文案（如 `[laugh]`, `[emphasis]`），返回高仿真口播音频切片（WAV/MP3），并向管线同步该切片的**精确毫秒级时长（Duration）**。

### 2.4 底层封装层 (Final Render Layer)
- **核心工具**: FFmpeg (搭配 `ffmpeg-python`)
- **拼装原理 (Concat Demuxer)**: 彻底抛弃视频逐帧重新编码计算。基于音频切片的精确时长，动态生成包含绝对时间的时序清单 (`inputs.txt`)，拉长对应图像素材的展示时间，最后通过底层的 stream copy 或极低开销转码直接复合出最终视频 (.mp4)。

## 3. 模块划分与目录结构 (Module & Directory Structure)

推荐采用领域驱动的目录划分，每个核心节点为一个独立的 Python Package。

```text
c:/docker/Myavatar/                      # 项目根目录
├── docs/                                # 文档目录
│   ├── arch.md                          # 架构设计文档 (本文件)
│   ├── research_report.md               # 核心研究报告
├── src/                                 # 源码核心目录
│   ├── orchestrator/                    # 顶层调度与状态机
│   │   ├── graph.py                     # LangGraph 状态机定义与边路由
│   │   ├── state.py                     # 全局状态字典 Schema 定义
│   │   ├── crew_agents.py               # (可选) CrewAI 的群智协同节点包装
│   ├── nodes/                           # LangGraph 节点具体实现
│   │   ├── n1_content_writer.py         # 基础文案生成节点
│   │   ├── n1b_ppt_vision_scriptwriter.py # PPT 视觉编剧版
│   │   ├── n1c_hybrid_content_writer.py # 混合模式文案生成节点
│   │   ├── n2_slide_generator.py        # 基础 Marp 幻灯片渲染节点
│   │   ├── n2b_hybrid_slide_generator.py # 混合排版渲染节点
│   │   ├── n3_browser_capture.py        # Playwright网页捕获节点 (待实现)
│   │   ├── n4_tts_synthesizer.py        # TTS请求与时长获取节点 (CosyVoice 3.0接入)
│   │   ├── n5_ffmpeg_assembler.py       # FFmpeg终极封包节点
│   ├── utils/                           # 通用工具类
│   │   ├── file_io.py                   # 临时文件清理、目录确保
│   │   ├── llm_client.py                # LLM API统一调用封装 (含 Doubao 集成)
│   ├── assets/                          # 系统静态资产 (不入版控)
│   │   ├── themes/                      # Marp 的自定义 CSS 样式文件
│   │   ├── fonts/                       # 渲染需要的专属字体
├── workspace/                           # 运行时的临时输出工作区 (按任务ID建目录)
│   ├── task_id_xxx/                     
│   │   ├── markdown_slides/             # LLM 吐出的原始 MD 
│   │   ├── images/                      # Marp/Playwright 截图的 PNG
│   │   ├── audios/                      # TTS 语音切片
│   │   ├── meta_inputs.txt              # FFmpeg concat 读取的文本清单
│   │   ├── final_output.mp4             # 压制的最终成品
├── main.py                              # 入口文件 (通过 CLI 或 API 启动管线)
├── requirements.txt                     # Python 依赖清单
├── .env.example                         # 环境变量模板 (包含各种 API Key)
```

## 4. 关键数据流协议 (Data Flow Protocol)

为了保证多智能体管道的健壮性，节点间流转的 `State` 必须是强类型的。核心状态包含：

```python
from typing import TypedDict, List, Dict, Optional

class SlideAsset(TypedDict):
    slide_id: str             # 页面ID, 例如 "slide_01"
    content_md: str           # LLM 生成的该页 Markdown
    speaker_script: str       # 该页对应的口播稿文案
    action: Optional[str]     # 附加动作，如 "capture:https://github.com..."
    image_path: Optional[str] # 渲染完毕后的本地图片路径
    audio_path: Optional[str] # TTS 语音切片本地路径
    duration: float           # 动态获取的音频时长 (秒)

class GraphState(TypedDict):
    task_id: str              # 全局任务唯一标识
    topic: str                # 用户输入的选题
    slides: List[SlideAsset]  # 存储每一页的复合资产状态
    final_video: str          # 最终压制视频路径
    errorlog: str             # 记录中断或告警信息
```

## 5. 开发实施路径 (Roadmap)

### Phase 1: 基础设施搭建极其打点测试 (MVP)
1. 配置好目录树结构的创建。
2. 搭建极简的 `Marp` 测试流：输入一段手工写的 Markdown，验证能成功转出 `.png`。
3. 搭建极简的 `TTS (API)` 测试流：手工给一段文本，调用 API 存下 `.wav` 并用 Python 探出毫秒级时长。
4. 搭建核心脏器 `FFmpeg Assembler`：手工给 2 张图和 2 份音频以及一个手写的 `inputs.txt`，验证 FFmpeg Concat 能秒出且音画严格同步的视频。

### Phase 2: 编排层接入与闭环 (Workflow Orchestration)
1. 引入 LangGraph 骨架。 **(已完成)**
2. 将 Phase 1 的小脚本封装进 `n2_slide_generator`, `n4_tts_synthesizer`, `n5_ffmpeg_assembler` 节点。 **(已完成)**
3. 增加大模型参与的节点，包含基础编剧 (`n1_content_writer`) 与后续衍生的混合模型编排 (`n1c_hybrid_content_writer`)。 **(已完成)**
4. 跑通第一根全自动管线——给定一个词条，自动输出短视频。 **(已完成)**
5. 独立各类核心组件的 API 测试 (`test_api_doubao.py`, `test_cosy.py` 等)，并在 RTX 3060 下深度优化了 CosyVoice 显存受限并发问题。 **(已完成)**

### Phase 3: 多模态扩容 (Capabilities Expansion)
1. 激活 `n3_browser_capture` 节点，加入 Playwright 的代码动态截图。 **(进行中)**
2. 完善异常重试机制 (引入 LangGraph Checkpointer)，确保断网死机后可恢复。

---
> [!NOTE] 
> 这是一个优雅解耦的系统，所有的 I/O 开销都被隔离在了独立的节点中。得益于您的 RTX 3060 ，在开发 Phase 1 和 Phase 2 时完全毫无压力。当一切跑通后，如果需要引入本地开源 TTS 重器，3060 的 12G 显存（部分为 8G）也足够应对离线批量推理。
