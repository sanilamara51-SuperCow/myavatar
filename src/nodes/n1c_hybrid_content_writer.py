import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI
from pydantic import BaseModel, Field

from agents.script_reflection import refine_slides_with_reflection
from orchestrator.state import SlideContent, VideoGenerationState
from utils.llm_config import load_vision_model_config as _load_model_config


class ScriptResponse(BaseModel):
    """Wrapper for model output parsing."""

    slides: List[SlideContent] = Field(
        description="Ordered slide list. For each slide, if it corresponds to an uploaded image, set image_source to the image filename."
    )


def _local_image_to_data_url(image_path: str) -> str:
    path = Path(image_path)
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "image/png"

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    text = raw_text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("Model output does not contain a valid JSON object.")

    candidate = text[start : end + 1]
    return json.loads(candidate)


def _write_image_manifest(
    run_dir: str,
    image_paths: List[str],
    script_image_markers: List[str],
) -> None:
    if not run_dir:
        return

    debug_dir = Path(run_dir) / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = debug_dir / "n1c_image_manifest.json"
    payload = {
        "total_images": len(image_paths),
        "images": [
            {
                "index": idx + 1,
                "filename": os.path.basename(path),
                "path": path,
            }
            for idx, path in enumerate(image_paths)
        ],
        "script_image_markers": script_image_markers,
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _build_marker_alignment_report(
    slides: List[SlideContent],
    script_image_markers: List[str],
) -> Dict[str, Any]:
    if not script_image_markers:
        return {
            "enabled": False,
            "score": 100,
            "matched": 0,
            "total_markers": 0,
            "missing_markers": [],
            "actual_image_sequence": [],
            "expected_marker_sequence": [],
        }

    expected = [Path(marker).name for marker in script_image_markers]
    actual = [
        Path(str(slide.image_source)).name
        for slide in slides
        if getattr(slide, "image_source", None)
    ]

    matched = 0
    missing_markers: List[str] = []
    start_pos = 0

    for marker_name in expected:
        found = False
        for idx in range(start_pos, len(actual)):
            if actual[idx].lower() == marker_name.lower():
                matched += 1
                start_pos = idx + 1
                found = True
                break
        if not found:
            missing_markers.append(marker_name)

    score = int((matched / len(expected)) * 100) if expected else 100
    return {
        "enabled": True,
        "score": score,
        "matched": matched,
        "total_markers": len(expected),
        "missing_markers": missing_markers,
        "actual_image_sequence": actual,
        "expected_marker_sequence": expected,
    }


def _build_messages(
    topic: str,
    image_paths: List[str],
    duration_mins: float,
    script_image_markers: List[str],
) -> List[Dict[str, Any]]:
    estimated_slides = max(3, int((duration_mins * 60) / 20))

    system_prompt = (
        "You are an expert video scriptwriter. The user will provide a TOPIC, and OPTIONALLY some REFERENCE IMAGES.\n"
        "Your task is to design a complete, persuasive video presentation.\n\n"
        "Return strict JSON only. No markdown, no explanation. Schema:\n"
        "{\n"
        '  "slides": [\n'
        "    {\n"
        '      "page_number": 1,\n'
        '      "title": "string",\n'
        '      "content_points": ["string", "string"],\n'
        '      "voiceover": "string",\n'
        '      "image_source": null,\n'
        '      "layout": "text_only",\n'
        '      "capture_url": null,\n'
        '      "capture_selector": null,\n'
        '      "capture_wait_ms": null,\n'
        '      "capture_full_page": true,\n'
        '      "capture_viewport_width": 1920,\n'
        '      "capture_viewport_height": 1080,\n'
        '      "speaker_segments": [\n'
        "        {\n"
        '          "persona_id": "host",\n'
        '          "text": "string",\n'
        '          "pause_ms": 260\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        f"- The video should be roughly {duration_mins} minutes long, meaning roughly {estimated_slides} slides overall.\n"
        "- If a slide should use one of the user's reference images, set 'image_source' to the EXACT filename.\n"
        "- Reference images are provided one by one; inspect each image before deciding placement.\n"
        "- ALSO set 'layout' field to determine how the image appears with text:\n"
        "  * 'text_only' - Pure text slide (no image)\n"
        "  * 'image_right' - Text on left (60%), screenshot on right (35%) - DEFAULT for most image slides\n"
        "  * 'image_left' - Screenshot on left (35%), text on right (60%)\n"
        "  * 'image_bottom' - Text on top (55%), screenshot below (35%) - good for tall screenshots\n"
        "  * 'image_full' - Screenshot fills entire slide (no text overlay) - for full-screen evidence\n"
        "- Choose layout based on image content: use 'image_right' for side-by-side comparison, 'image_bottom' for workflow screenshots, 'image_full' for full UI captures.\n"
        "- If a slide should show a webpage screenshot, set 'capture_url' and optionally 'capture_selector'.\n"
        "- For capture slides, keep 'image_source' as null.\n"
        "- If neither user image nor webpage capture is needed, keep both image_source and capture_url as null.\n"
        "- Keep capture fields null when not used.\n"
        "- speaker_segments should split long narration into natural spoken chunks.\n"
        "- Use persona_id='host' by default unless a different role is truly needed.\n"
        "- The voiceover text must naturally match the slide's content and flow.\n"
        "- Keep language in Simplified Chinese.\n"
        "- If script image markers exist, follow marker order as priority anchors.\n"
    )

    user_content: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": f"Topic / Outline: {topic}\n\nPlease generate the full sequence of slides. If I provided images, decide where they best fit in the sequence and map their filenames to 'image_source'.",
        }
    ]

    if image_paths:
        user_content.append(
            {"type": "text", "text": "Here are the reference images I provided:"}
        )
        for img_path in image_paths:
            filename = os.path.basename(img_path)
            data_url = _local_image_to_data_url(img_path)
            user_content.append({"type": "text", "text": f"Filename: {filename}"})
            user_content.append(
                {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}}
            )

    if script_image_markers:
        marker_lines = [
            f"{idx}. {name}" for idx, name in enumerate(script_image_markers, start=1)
        ]
        user_content.append(
            {
                "type": "text",
                "text": "Script image markers (ordered):\n" + "\n".join(marker_lines),
            }
        )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def hybrid_content_writer_node(state: VideoGenerationState) -> Dict[str, Any]:
    """
    [Node 1C] Takes a topic + optional images, generates full slide structs.
    """
    topic = state.get("topic") or "No generic topic provided."
    duration_mins = float(state.get("duration_mins") or 1.0)
    image_paths = state.get("ppt_image_paths", [])
    script_image_markers = state.get("script_image_markers", [])
    run_dir = (state.get("run_dir") or "").strip()

    config = _load_model_config(state=state, node_name="n1c_hybrid_content_writer")
    print(
        "[Node 1C: Hybrid Scriptwriter] "
        f"Topic='{topic[:30]}...', Images={len(image_paths)}, markers={len(script_image_markers)}, model='{config['model']}' "
        f"via {config['provider']} ({config.get('provider_id', 'n/a')}), "
        f"source={config.get('source', 'unknown')}..."
    )

    for idx, image_path in enumerate(image_paths, start=1):
        print(f"  - Image {idx}: {os.path.basename(image_path)}")

    _write_image_manifest(run_dir, image_paths, script_image_markers)

    if not config["api_key"]:
        return {
            "error_msg": (
                "Missing API key for hybrid vision scriptwriter. "
                f"Expected env var '{config.get('api_key_env', 'OPENAI_VISION_API_KEY')}'."
            )
        }

    client = OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        default_headers=config.get("extra_headers") or None,
    )
    messages = _build_messages(
        topic,
        image_paths,
        duration_mins,
        script_image_markers,
    )

    try:
        response = client.chat.completions.create(
            model=config["model"],
            messages=messages,
            temperature=0.4,
        )

        if not response.choices:
            raise RuntimeError("Model response has no choices.")

        raw_text = response.choices[0].message.content
        if not raw_text:
            raise RuntimeError("Model response is empty.")

        if run_dir:
            debug_dir = Path(run_dir) / "debug"
        else:
            debug_dir = (
                Path(__file__).resolve().parents[2]
                / "workspace"
                / "run_output"
                / "debug"
            )
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_file = debug_dir / "n1c_raw_response.txt"
        debug_file.write_text(raw_text, encoding="utf-8")

        parsed = _extract_json_object(raw_text)
        slide_response = ScriptResponse.model_validate(parsed)

        if not slide_response.slides:
            raise RuntimeError("Model returned empty slide list.")

        reflection_result = refine_slides_with_reflection(
            slides=slide_response.slides,
            topic=topic,
            state=state,
        )
        final_slides = reflection_result.get("slides") or slide_response.slides
        reflection_report = reflection_result.get("report", {})

        # Re-map the short filenames returned by the model back to the absolute file paths.
        filename_to_path = {os.path.basename(p): p for p in image_paths}
        for slide in final_slides:
            if slide.image_source and slide.image_source in filename_to_path:
                slide.image_source = filename_to_path[slide.image_source]
            else:
                slide.image_source = None

        alignment_report = _build_marker_alignment_report(
            final_slides,
            script_image_markers,
        )
        if alignment_report.get("enabled"):
            alignment_report_path = debug_dir / "n1c_marker_alignment_report.json"
            alignment_report_path.write_text(
                json.dumps(alignment_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(
                "[Node 1C: Marker Alignment] "
                f"score={alignment_report.get('score')}, "
                f"matched={alignment_report.get('matched')}/{alignment_report.get('total_markers')}"
            )

        print(
            "[Node 1C: Hybrid Scriptwriter] "
            f"Successfully generated {len(final_slides)} slides."
        )
        return {
            "slides_data": final_slides,
            "script_reflection_report": reflection_report,
            "script_image_alignment_report": alignment_report,
        }

    except Exception as exc:
        import traceback

        error_msg = f"[Node 1C: Hybrid Scriptwriter] Model call failed. Error: {exc}\n{traceback.format_exc()}"
        print(error_msg)
        return {"error_msg": error_msg}
