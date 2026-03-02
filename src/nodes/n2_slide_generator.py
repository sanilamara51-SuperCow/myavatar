import os
import shutil
from typing import Dict, Any

from orchestrator.state import VideoGenerationState
from utils.marp_helper import render_markdown_to_images
from utils.theme_manager import build_marp_frontmatter, resolve_template_profile

def format_slide_markdown(slides_data: list, state: VideoGenerationState) -> str:
    """
    将字典格式的 slides_data 转化为符合 Marp 格式的 Markdown
    """
    md_lines = build_marp_frontmatter(state=state, paginate=True)
    
    for i, slide in enumerate(slides_data):
        # 每一张卡片都是一个新的 section
        if i > 0:
            md_lines.append("---")
            md_lines.append("")
        
        # 渲染标题
        md_lines.append(f"# {slide.title}")
        md_lines.append("")
        
        # 渲染要点列表
        for point in slide.content_points:
            md_lines.append(f"- {point}")
        
        md_lines.append("")
    
    return "\n".join(md_lines)

def slide_generator_node(state: VideoGenerationState) -> Dict[str, Any]:
    """
    [Node 2] 卡片渲染节点
    作用：接收 SlideContent 数据，动态拼接为 Marp 风格的 Markdown 长文本，再调用底层引擎渲染出序列图片
    """
    slides_data = state.get("slides_data", [])
    if not slides_data:
        return {"error_msg": "No slides data found from the previous node."}
        
    template_id, template_profile = resolve_template_profile(state)
    print(
        "[Node 2: Slide Generator] "
        f"Generating slides for {len(slides_data)} pages with template='{template_id}' ({template_profile['name']})..."
    )
    
    # 构造 Marp Markdown
    markdown_content = format_slide_markdown(slides_data, state)
    
    # 从全局流转状态中安全提取本次的时序抽屉，防止抹除同行者的快照
    run_dir = state.get("run_dir")
    if run_dir:
        output_dir = os.path.join(run_dir, "slides")
    else:
        output_dir = os.path.join(os.getcwd(), "workspace", "run_output", "slides")
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
            
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # 使用 marp_helper 输出静态图片
        image_paths = render_markdown_to_images(markdown_content, output_dir)
        print(f"[Node 2: Slide Generator] Rendered {len(image_paths)} images successfully.")
        return {
            "markdown_content": markdown_content,
            "image_paths": image_paths
        }
    except Exception as e:
        error_msg = f"Slide generation failed via Marp: {str(e)}"
        print(f"[Node 2 ERROR] {error_msg}")
        return {"error_msg": error_msg}
