import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from pydantic import BaseModel, Field

from orchestrator.state import SlideContent, VideoGenerationState
from utils.llm_config import load_text_model_config as _load_model_config


class SlideResponse(BaseModel):
    """Wrapper for model output parsing."""

    slides: List[SlideContent] = Field(
        description="Ordered slide list. page_number starts from 1 and increments by 1."
    )


def _estimate_slide_count(duration_mins: float) -> int:
    """Roughly one slide per ~20 seconds, with a minimum of 3."""
    return max(3, int((duration_mins * 60) / 20))


def _normalize_reference_image_url(raw: Any) -> Optional[str]:
    """Return a normalized HTTP(S) image URL or None."""
    if raw is None:
        return None

    value = str(raw).strip()
    if not value:
        return None

    lowered = value.lower()
    if lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("data:image/"):
        return value
    return None


def _resolve_reference_image_path(raw: Any) -> Optional[Path]:
    """Resolve a local image path from absolute or relative input."""
    if raw is None:
        return None

    value = str(raw).strip()
    if not value:
        return None

    raw_path = Path(value).expanduser()
    candidates = [raw_path]

    if not raw_path.is_absolute():
        project_root = Path(__file__).resolve().parents[2]
        candidates.append(project_root / raw_path)
        candidates.append(Path.cwd() / raw_path)

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if resolved.is_file():
            return resolved
    return None


def _local_image_to_data_url(image_path: Path) -> str:
    """Convert a local image file to a data URL for multimodal input."""
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = "image/png"

    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _resolve_reference_image_payload(
    reference_image_path_raw: Any,
    reference_image_url_raw: Any,
) -> Tuple[Optional[str], str]:
    """
    Resolve image payload with priority:
    1) Local file path (converted to data URL)
    2) HTTP(S) URL
    """
    local_path = _resolve_reference_image_path(reference_image_path_raw)
    if local_path:
        try:
            return _local_image_to_data_url(local_path), f"local:{local_path.name}"
        except Exception as exc:
            print(
                "[Node 1: Content Writer] "
                f"Failed to encode local reference image '{local_path}': {exc}"
            )
    elif reference_image_path_raw:
        print(
            "[Node 1: Content Writer] "
            f"Local reference image not found: '{reference_image_path_raw}'"
        )

    remote_url = _normalize_reference_image_url(reference_image_url_raw)
    if remote_url:
        return remote_url, "url"

    return None, "none"


def _extract_text_from_message_content(content: Any) -> str:
    """Normalize chat completion message content to plain text."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                continue

            text_attr = getattr(item, "text", None)
            if text_attr:
                parts.append(str(text_attr))
        return "\n".join(part for part in parts if part).strip()

    return ""


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    """
    Extract the outermost JSON object from model output.
    Handles accidental prose/code fences around JSON.
    """
    text = raw_text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("Model output does not contain a valid JSON object.")

    candidate = text[start : end + 1]
    return json.loads(candidate)


def _build_messages(
    topic: str,
    target_audience: str,
    estimated_slides: int,
    reference_image: Optional[str] = None,
) -> List[Dict[str, Any]]:
    system_prompt = (
        "You are an expert educational short-video script writer.\n"
        "Return strict JSON only. No markdown, no explanation.\n"
        "Output schema:\n"
        "{\n"
        '  "slides": [\n'
        "    {\n"
        '      "page_number": 1,\n'
        '      "title": "string",\n'
        '      "content_points": ["string", "string"],\n'
        '      "voiceover": "string"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        f"- Produce exactly {estimated_slides} slides.\n"
        "- Slide 1 must be a strong hook/intro.\n"
        "- Last slide must summarize and include a CTA.\n"
        "- content_points must contain 2-4 concise bullets.\n"
        "- voiceover should sound natural spoken narration.\n"
        "- Keep language in Simplified Chinese.\n"
        "- If a reference image is provided, use it only as supporting context."
    )

    user_prompt = (
        f"Topic: {topic}\n"
        f"Target audience: {target_audience}\n"
        f"Expected slide count: {estimated_slides}"
    )

    user_content: Any = user_prompt
    if reference_image:
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": reference_image}},
        ]

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _generate_slides_via_model(
    topic: str,
    target_audience: str,
    estimated_slides: int,
    config: Dict[str, Any],
    reference_image: Optional[str] = None,
) -> List[SlideContent]:
    client = OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        default_headers=config.get("extra_headers") or None,
    )
    messages = _build_messages(
        topic=topic,
        target_audience=target_audience,
        estimated_slides=estimated_slides,
        reference_image=reference_image,
    )

    response = client.chat.completions.create(
        model=config["model"],
        messages=messages,
        temperature=0.4,
    )

    if not response.choices:
        raise RuntimeError("Model response has no choices.")

    raw_text = _extract_text_from_message_content(response.choices[0].message.content)
    if not raw_text:
        raise RuntimeError("Model response is empty.")

    parsed = _extract_json_object(raw_text)
    slide_response = SlideResponse.model_validate(parsed)

    if not slide_response.slides:
        raise RuntimeError("Model returned empty slide list.")

    return slide_response.slides


def _build_mock_slides(topic: str, estimated_slides: int) -> List[SlideContent]:
    """Fallback slides to keep the pipeline runnable when API fails."""
    slide_count = max(3, estimated_slides)
    slides: List[SlideContent] = [
        SlideContent(
            page_number=1,
            title=f"{topic}: Why it matters",
            content_points=[
                "What problem this topic solves",
                "A quick preview of key ideas",
                "What you will learn in the next slides",
            ],
            voiceover=(
                f"Welcome. In this short lesson, we will break down {topic} in a simple way. "
                "First, we will build intuition, then look at practical examples, and finally summarize."
            ),
        )
    ]

    for page in range(2, slide_count):
        slides.append(
            SlideContent(
                page_number=page,
                title=f"{topic}: Core idea {page - 1}",
                content_points=[
                    "One key concept explained in plain language",
                    "A practical example or analogy",
                    "A common misunderstanding to avoid",
                ],
                voiceover=(
                    "Here is the key idea for this part. "
                    "Think about how it works in a real-world scenario, and focus on the intuition first."
                ),
            )
        )

    slides.append(
        SlideContent(
            page_number=slide_count,
            title=f"{topic}: Summary and next step",
            content_points=[
                "Recap the three most important takeaways",
                "How to apply this in real learning",
                "Follow for deeper examples in the next lesson",
            ],
            voiceover=(
                "Let us wrap up. You now have the core picture and practical intuition. "
                "Review the key points once, then try explaining the topic in your own words."
            ),
        )
    )

    return slides


def content_writer_node(state: VideoGenerationState) -> Dict[str, Any]:
    """
    [Node 1] Generate structured slide + narration content.
    """
    topic = (state.get("topic") or "").strip()
    target_audience = (state.get("target_audience") or "General audience").strip()
    duration_mins = float(state.get("duration_mins") or 1.0)
    reference_image, image_source = _resolve_reference_image_payload(
        state.get("reference_image_path"),
        state.get("reference_image_url"),
    )

    if not topic:
        return {"error_msg": "Missing input topic for content generation."}

    estimated_slides = _estimate_slide_count(duration_mins)
    config = _load_model_config(state=state, node_name="n1_content_writer")
    has_image_context = "yes" if reference_image else "no"

    print(
        "[Node 1: Content Writer] "
        f"topic='{topic}', slides~{estimated_slides}, model='{config['model']}' "
        f"via {config['provider']} ({config.get('provider_id', 'n/a')}), "
        f"source={config.get('source', 'unknown')}, "
        f"image_context={has_image_context}, image_source={image_source}"
    )

    if not config["api_key"]:
        print("[Node 1: Content Writer] No API key found. Falling back to mock slides.")
        return {"slides_data": _build_mock_slides(topic, estimated_slides)}

    try:
        slides = _generate_slides_via_model(
            topic=topic,
            target_audience=target_audience,
            estimated_slides=estimated_slides,
            config=config,
            reference_image=reference_image,
        )
        print(f"[Node 1: Content Writer] Generated {len(slides)} slides from model.")
        return {"slides_data": slides}
    except Exception as exc:
        print(f"[Node 1: Content Writer] Model call failed, fallback to mock. Error: {exc}")
        return {"slides_data": _build_mock_slides(topic, estimated_slides)}
