import os
from langgraph.graph import StateGraph, START, END

# 导入共享状态数据模型
from orchestrator.state import VideoGenerationState

# 导入所有实现了的执行节点
from nodes.n1_content_writer import content_writer_node
from nodes.n2_slide_generator import slide_generator_node
from nodes.n4_tts_synthesizer import tts_synthesizer_node
from nodes.n5_ffmpeg_assembler import ffmpeg_assembler_node

def build_video_generation_graph():
    """
    构建视频生成管线的状态图 (Workflow)
    """
    # 1. 实例化图并绑定状态 Schema
    workflow = StateGraph(VideoGenerationState)
    
    # 2. 注册图节点
    workflow.add_node("n1_content_writer", content_writer_node)
    workflow.add_node("n2_slide_generator", slide_generator_node)
    workflow.add_node("n4_tts_synthesizer", tts_synthesizer_node)
    workflow.add_node("n5_ffmpeg_assembler", ffmpeg_assembler_node)
    
    # 3. 定义全局异常拦截校验函数
    def check_error(state: VideoGenerationState) -> str:
        """如果上一个节点写入了 error_msg，则阻断后续执行，直接走向 END"""
        if state.get("error_msg"):
            return "error"
        return "continue"
        
    # 为节点之间加上带错误拦截的条件边
    def add_safe_edge(from_node: str, to_node: str):
        workflow.add_conditional_edges(
            from_node,
            check_error,
            {
                "continue": to_node,
                "error": END
            }
        )
    
    # 4. 定义数据流图边的流转结构
    workflow.add_edge(START, "n1_content_writer")
    
    add_safe_edge("n1_content_writer", "n2_slide_generator")
    add_safe_edge("n2_slide_generator", "n4_tts_synthesizer")
    add_safe_edge("n4_tts_synthesizer", "n5_ffmpeg_assembler")
    
    # 最后一个节点正常组装完以后，直接指向终点
    workflow.add_conditional_edges(
        "n5_ffmpeg_assembler", 
        check_error, 
        {"continue": END, "error": END}
    )
    
    # 5. 编译整张有向无环图
    return workflow.compile()
