import os
import shutil
from typing import Dict, Any, List

from orchestrator.state import VideoGenerationState
from utils.slide_composer import compose_slide
from utils.theme_manager import resolve_template_profile


def hybrid_slide_generator_node(state: VideoGenerationState) -> Dict[str, Any]:
    """
    [Node 2B] Mixed visual generation node with layout support.

    Layout modes:
    - text_only: Marp text slide
    - image_right: Text left 60%, screenshot right 35%
    - image_left: Screenshot left 35%, text right 60%
    - image_bottom: Text top 55%, screenshot bottom 35%
    - image_full: Screenshot fullscreen (original behavior)
    """
    slides_data = state.get("slides_data", [])
    if not slides_data:
        return {"error_msg": "No slides data found from the previous node."}

    template_id, template_profile = resolve_template_profile(state)
    print(
        "[Node 2B: Hybrid Generator] "
        f"Generating/Aligning visuals for {len(slides_data)} slides with template='{template_id}' ({template_profile['name']})..."
    )

    run_dir = state.get("run_dir")
    if run_dir:
        output_dir = os.path.join(run_dir, "slides")
    else:
        output_dir = os.path.join(os.getcwd(), "workspace", "run_output", "slides")
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)

    os.makedirs(output_dir, exist_ok=True)

    final_image_paths = []

    try:
        for idx, slide in enumerate(slides_data):
            page_index = idx + 1
            dest_path = os.path.join(output_dir, f"slide_{page_index:03d}.png")
            temp_dir = os.path.join(output_dir, f"temp_{page_index}")
            os.makedirs(temp_dir, exist_ok=True)

            # Use new composer with layout support
            compose_slide(slide, state, dest_path, temp_dir)
            final_image_paths.append(dest_path)

            # Report layout
            layout = getattr(slide, "layout", "text_only") or "text_only"
            img_name = (
                os.path.basename(slide.image_source) if slide.image_source else "none"
            )
            print(f"  - Slide {page_index}: layout='{layout}', image='{img_name}'")

            # Cleanup temp
            shutil.rmtree(temp_dir, ignore_errors=True)

        return {"image_paths": final_image_paths}
    except Exception as e:
        error_msg = f"Mixed hybrid slide generation failed: {str(e)}"
        print(f"[Node 2B ERROR] {error_msg}")
        return {"error_msg": error_msg}
