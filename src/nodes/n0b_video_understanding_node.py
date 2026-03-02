"""
Node 0b: Video Understanding

Uses Qwen2.5-VL (or compatible vision-language models) to analyze video keyframes
and produce structured content understanding.
"""

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI
from pydantic import BaseModel

from orchestrator.state import VideoGenerationState
from utils.llm_config import load_vision_model_config as _load_vision_config
from utils.video_understanding_schema import VideoUnderstanding


class VideoUnderstandingResponse(BaseModel):
    """Wrapper for model output parsing."""

    understanding: VideoUnderstanding


def _local_image_to_base64(image_path: str) -> str:
    """Convert local image to base64-encoded data URL."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Determine MIME type
    suffix = path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    mime_type = mime_map.get(suffix, "image/jpeg")

    # Read and encode
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    """Extract JSON object from potentially noisy model output."""
    text = raw_text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Look for JSON block
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("Model output does not contain a valid JSON object.")

    candidate = text[start : end + 1]
    return json.loads(candidate)


def _build_video_understanding_prompt(
    keyframe_count: int,
    timestamps: List[float],
) -> str:
    """Build the system prompt for video understanding."""

    # Format timestamps for reference
    time_refs = []
    for i, ts in enumerate(timestamps[:10]):  # Limit to first 10 for brevity
        mins = int(ts // 60)
        secs = int(ts % 60)
        time_refs.append(f"Frame {i + 1}: {mins:02d}:{secs:02d}")

    time_ref_text = "\n".join(time_refs) if time_refs else "N/A"

    return f"""You are an expert video content analyst. Your task is to analyze video keyframes and produce a structured, detailed understanding of the video content.

INPUT: You will receive {keyframe_count} keyframe images extracted from a video. These frames represent the key visual moments across the entire video.

Frame timestamps (for reference):
{time_ref_text}

YOUR TASK: Analyze these frames and produce a comprehensive structured analysis including:

1. **High-level Summary**: One-sentence summary + detailed 2-3 paragraph description
2. **Main Topics**: 3-5 core themes or topics covered
3. **Key Points**: 5-10 specific takeaways
4. **Scene Breakdown**: For each distinct scene, describe:
   - Time range
   - Visual content (people, objects, actions, setting)
   - Any on-screen text
   - Mood/atmosphere
5. **Content Elements**: Notable quotes, statistics, products, people, or actions
6. **Style Analysis**: Video style, target audience, presentation style
7. **Tags**: 10-15 searchable tags for content discovery
8. **Reusable Elements**: Specific clips, quotes, or examples that could be referenced in new content

OUTPUT FORMAT: Return a strict JSON object matching this schema:

```json
{{
    "understanding": {{
        "title_suggestion": "string",
        "duration_category": "short|medium|long",
        "one_sentence_summary": "string",
        "detailed_summary": "string",
        "main_topics": ["string"],
        "key_points": ["string"],
        "scenes": [
            {{
                "scene_index": 0,
                "time_range": "mm:ss - mm:ss",
                "visual_content": "string",
                "on_screen_text": "string or null",
                "mood_atmosphere": "string"
            }}
        ],
        "content_elements": [
            {{
                "type": "key_message|quote|statistic|product|person|action",
                "content": "string",
                "timestamp": "mm:ss",
                "importance": 5
            }}
        ],
        "video_style": "string",
        "target_audience": "string",
        "presentation_style": "string",
        "suggested_tags": ["string"],
        "reusable_elements": ["string"],
        "production_quality": "unknown|low|medium|high|professional",
        "audio_quality": "unknown|poor|acceptable|good|excellent"
    }}
}}
```

IMPORTANT:
- Return ONLY the JSON object, no markdown, no explanation
- Be specific and detailed in your analysis
- Infer as much as possible from the visual content
- If audio quality cannot be determined from images, set to "unknown"
- Use Simplified Chinese for the analysis content"""


def _build_messages(
    keyframe_paths: List[str],
    prompt: str,
) -> List[Dict[str, Any]]:
    """Build the messages array for the API call."""

    system_prompt = prompt

    user_content: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": "Please analyze these video keyframes and produce a comprehensive structured understanding of the video content. Return ONLY the JSON object, no explanation.",
        }
    ]

    # Add all keyframe images
    for i, kf_path in enumerate(keyframe_paths):
        try:
            data_url = _local_image_to_base64(kf_path)
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": data_url, "detail": "high"},
                }
            )
        except FileNotFoundError as e:
            print(f"[Video Understanding] Warning: Skipping missing frame: {e}")

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def video_understanding_node(state: VideoGenerationState) -> Dict[str, Any]:
    """
    [Node 0b] Video understanding node.

    Takes keyframe_paths from state and uses a vision-language model
    to produce structured video understanding.

    Output:
    - video_understanding: Structured analysis dictionary
    """
    keyframe_paths = state.get("keyframe_paths", [])

    if not keyframe_paths:
        print("[Node 0b: Video Understanding] No keyframe_paths provided. Skipping.")
        return {}

    print(
        f"[Node 0b: Video Understanding] Analyzing {len(keyframe_paths)} keyframes..."
    )

    # Load vision model configuration
    config = _load_vision_config(
        state=state,
        node_name="n0b_video_understanding",
    )

    print(
        f"[Node 0b: Video Understanding] Using model: {config['model']} "
        f"via {config['provider']} ({config.get('provider_id', 'n/a')})"
    )

    if not config.get("api_key"):
        error_msg = (
            f"Missing API key for video understanding. "
            f"Expected env var '{config.get('api_key_env', 'OPENAI_VISION_API_KEY')}'."
        )
        return {"error_msg": error_msg}

    # Build prompt
    keyframe_timestamps = state.get("keyframe_timestamps", [])
    prompt = _build_video_understanding_prompt(
        keyframe_count=len(keyframe_paths),
        timestamps=keyframe_timestamps,
    )

    # Build messages
    messages = _build_messages(keyframe_paths, prompt)

    # Initialize client
    client = OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        default_headers=config.get("extra_headers") or None,
    )

    run_dir = state.get("run_dir", "")

    try:
        # Make API call
        response = client.chat.completions.create(
            model=config["model"],
            messages=messages,
            temperature=0.3,  # Lower temperature for more structured output
            max_tokens=4096,
        )

        if not response.choices:
            raise RuntimeError("Model response has no choices.")

        raw_text = response.choices[0].message.content
        if not raw_text:
            raise RuntimeError("Model response is empty.")

        # Save raw response for debugging
        if run_dir:
            debug_dir = Path(run_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / "n0b_raw_response.txt"
            debug_file.write_text(raw_text, encoding="utf-8")

        # Parse JSON response
        parsed = _extract_json_object(raw_text)
        understanding_response = VideoUnderstandingResponse.model_validate(parsed)

        # Convert to dictionary for state
        understanding_dict = understanding_response.understanding.model_dump()

        # Save structured output
        if run_dir:
            output_file = debug_dir / "video_understanding.json"
            output_file.write_text(
                json.dumps(understanding_dict, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        print(
            f"[Node 0b: Video Understanding] Analysis complete: "
            f"'{understanding_dict.get('title_suggestion', 'N/A')[:50]}...'"
        )
        print(
            f"[Node 0b: Video Understanding] Main topics: "
            f"{', '.join(understanding_dict.get('main_topics', [])[:3])}"
        )

        return {
            "video_understanding": understanding_dict,
        }

    except Exception as e:
        import traceback

        error_msg = (
            f"[Node 0b: Video Understanding] Model call failed: {e}\n"
            f"{traceback.format_exc()}"
        )
        print(error_msg)
        return {"error_msg": error_msg}
