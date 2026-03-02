import os
from langgraph.graph import StateGraph, START, END

# 导入共享状态数据模型
from orchestrator.state import VideoGenerationState

# 导入所有实现了的执行节点
from nodes.n0_douyin_downloader import douyin_downloader_node
from nodes.n0a_video_keyframe_extractor import video_keyframe_extractor_node
from nodes.n0b_video_understanding_node import video_understanding_node
from nodes.n1c_hybrid_content_writer import hybrid_content_writer_node
from nodes.n3_browser_capture import browser_capture_node
from nodes.n2b_hybrid_slide_generator import hybrid_slide_generator_node
from nodes.n4_tts_synthesizer import tts_synthesizer_node
from nodes.n5_ffmpeg_assembler import ffmpeg_assembler_node


def should_process_video(state: VideoGenerationState) -> str:
    """Check if video processing pipeline should be triggered."""
    douyin_url = state.get("douyin_share_url")
    video_path = state.get("video_path")

    if douyin_url or video_path:
        return "process_video"
    return "skip_video"


def check_error(state: VideoGenerationState) -> str:
    """Global error boundary check."""
    if state.get("error_msg"):
        return "error"
    return "continue"


def add_safe_edge(from_node: str, to_node: str, workflow: StateGraph):
    """Add an edge with error boundary check."""
    workflow.add_conditional_edges(
        from_node,
        check_error,
        {
            "continue": to_node,
            "error": END,
        },
    )


def build_hybrid_graph():
    """
    构建图像 + 文本混合驱动的视频生成管线 (Hybrid Workflow)

    Extended with video understanding support:

    Video Input Flow:
    START -> [has douyin_url?] -> n0_douyin_downloader -> n0a_keyframe_extractor -> n0b_video_understanding -> n1c_hybrid_content_writer -> ...

    Standard Flow (no video input):
    START -> n1c_hybrid_content_writer -> n3_browser_capture -> n2b_hybrid_slide_generator -> n4_tts_synthesizer -> n5_ffmpeg_assembler -> END
    """
    # 1. 实例化图并绑定状态 Schema
    workflow = StateGraph(VideoGenerationState)

    # 2. 注册图节点
    # Video processing nodes (new)
    workflow.add_node("n0_douyin_downloader", douyin_downloader_node)
    workflow.add_node("n0a_keyframe_extractor", video_keyframe_extractor_node)
    workflow.add_node("n0b_video_understanding", video_understanding_node)

    # Original nodes
    workflow.add_node("n1c_hybrid_content_writer", hybrid_content_writer_node)
    workflow.add_node("n3_browser_capture", browser_capture_node)
    workflow.add_node("n2b_hybrid_slide_generator", hybrid_slide_generator_node)
    workflow.add_node("n4_tts_synthesizer", tts_synthesizer_node)
    workflow.add_node("n5_ffmpeg_assembler", ffmpeg_assembler_node)

    # 3. 定义条件路由：检查是否有视频输入
    workflow.add_conditional_edges(
        START,
        should_process_video,
        {
            "process_video": "n0_douyin_downloader",
            "skip_video": "n1c_hybrid_content_writer",
        },
    )

    # 4. 视频处理流程 (Video processing pipeline)
    add_safe_edge("n0_douyin_downloader", "n0a_keyframe_extractor", workflow)
    add_safe_edge("n0a_keyframe_extractor", "n0b_video_understanding", workflow)
    add_safe_edge("n0b_video_understanding", "n1c_hybrid_content_writer", workflow)

    # 5. 原有流程 (Original pipeline)
    add_safe_edge("n1c_hybrid_content_writer", "n3_browser_capture", workflow)
    add_safe_edge("n3_browser_capture", "n2b_hybrid_slide_generator", workflow)
    add_safe_edge("n2b_hybrid_slide_generator", "n4_tts_synthesizer", workflow)
    add_safe_edge("n4_tts_synthesizer", "n5_ffmpeg_assembler", workflow)

    workflow.add_conditional_edges(
        "n5_ffmpeg_assembler",
        check_error,
        {"continue": END, "error": END},
    )

    # 6. 编译整张有向无环图
    return workflow.compile()
