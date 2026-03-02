"""
Slide composer for mixed text + screenshot layouts.

Supports layouts:
- text_only: Marp slide only
- image_right: Text left 60%, image right 35%
- image_left: Image left 35%, text right 60%
- image_bottom: Text top 60%, image bottom 35%
- image_full: Screenshot fullscreen (original behavior)
"""

import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from utils.marp_helper import render_markdown_to_images
from utils.theme_manager import build_marp_frontmatter, resolve_template_profile


# Canvas dimensions (16:9 at 1920x1080)
CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080

# Layout configurations
LAYOUT_CONFIGS = {
    "text_only": {"has_image": False},
    "image_right": {
        "text_w": 0.60,
        "text_h": 1.0,
        "img_w": 0.35,
        "img_h": 0.8,
        "img_x": 0.625,
        "img_y": 0.1,
    },
    "image_left": {
        "text_w": 0.60,
        "text_h": 1.0,
        "img_w": 0.35,
        "img_h": 0.8,
        "img_x": 0.025,
        "img_y": 0.1,
    },
    "image_bottom": {
        "text_w": 1.0,
        "text_h": 0.55,
        "img_w": 0.9,
        "img_h": 0.35,
        "img_x": 0.05,
        "img_y": 0.6,
    },
    "image_full": {"has_image": True, "fullscreen": True},
}


def _generate_text_only_slide(slide, state, output_path: str, temp_dir: str) -> str:
    """Generate a pure text slide using Marp."""
    from orchestrator.state import VideoGenerationState

    md_lines = build_marp_frontmatter(state=state, paginate=False)
    md_lines.append(f"# {slide.title}")
    md_lines.append("")
    for point in slide.content_points:
        md_lines.append(f"- {point}")
    md_lines.append("")

    markdown_content = "\n".join(md_lines)
    generated = render_markdown_to_images(markdown_content, temp_dir)

    if not generated:
        raise RuntimeError("Marp failed to generate text slide")

    # Copy to final destination
    shutil.copy2(generated[0], output_path)
    return output_path


def _compose_text_with_image(
    slide,
    state,
    image_path: str,
    layout: str,
    output_path: str,
    temp_dir: str,
) -> str:
    """Compose a slide with text and embedded image."""
    config = LAYOUT_CONFIGS.get(layout, LAYOUT_CONFIGS["image_right"])

    # Step 1: Generate text background using Marp
    md_lines = build_marp_frontmatter(state=state, paginate=False)
    md_lines.append(f"# {slide.title}")
    md_lines.append("")
    for point in slide.content_points:
        md_lines.append(f"- {point}")
    md_lines.append("")

    markdown_content = "\n".join(md_lines)
    text_images = render_markdown_to_images(markdown_content, temp_dir)

    if not text_images:
        raise RuntimeError("Marp failed to generate text background")

    # Step 2: Load and resize images
    text_bg = Image.open(text_images[0])
    text_bg = text_bg.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS)

    screenshot = Image.open(image_path)

    # Calculate image position and size
    img_w = int(CANVAS_WIDTH * config["img_w"])
    img_h = int(CANVAS_HEIGHT * config["img_h"])
    img_x = int(CANVAS_WIDTH * config["img_x"])
    img_y = int(CANVAS_HEIGHT * config["img_y"])

    # Resize screenshot maintaining aspect ratio
    screenshot.thumbnail((img_w, img_h), Image.Resampling.LANCZOS)

    # Center in allocated space
    actual_w, actual_h = screenshot.size
    centered_x = img_x + (img_w - actual_w) // 2
    centered_y = img_y + (img_h - actual_h) // 2

    # Step 3: Composite
    canvas = text_bg.copy()

    # Optional: Add subtle shadow/background for screenshot
    shadow_padding = 8
    shadow_box = (
        centered_x - shadow_padding,
        centered_y - shadow_padding,
        centered_x + actual_w + shadow_padding,
        centered_y + actual_h + shadow_padding,
    )
    draw = ImageDraw.Draw(canvas)
    draw.rectangle(shadow_box, fill=(0, 0, 0, 40))

    # Paste screenshot
    canvas.paste(screenshot, (centered_x, centered_y))

    # Step 4: Save
    canvas.save(output_path, "PNG", quality=95)
    return output_path


def compose_slide(
    slide,
    state,
    output_path: str,
    temp_dir: str,
) -> str:
    """
    Compose a single slide based on its layout configuration.

    Args:
        slide: SlideContent object
        state: VideoGenerationState
        output_path: Final output image path
        temp_dir: Temporary directory for intermediate files

    Returns:
        Path to generated slide image
    """
    layout = getattr(slide, "layout", "text_only") or "text_only"
    image_source = getattr(slide, "image_source", None)

    # Validate layout
    if layout not in LAYOUT_CONFIGS:
        print(f"[SlideComposer] Unknown layout '{layout}', falling back to text_only")
        layout = "text_only"

    # Handle image_full or missing image
    if layout == "image_full" or not image_source or not os.path.exists(image_source):
        if image_source and os.path.exists(image_source) and layout == "image_full":
            # Just copy the image
            shutil.copy2(image_source, output_path)
            return output_path
        else:
            # Generate text-only slide
            return _generate_text_only_slide(slide, state, output_path, temp_dir)

    # Compose text + image
    return _compose_text_with_image(
        slide, state, image_source, layout, output_path, temp_dir
    )
