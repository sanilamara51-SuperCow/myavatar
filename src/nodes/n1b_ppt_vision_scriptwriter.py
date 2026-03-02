import base64
import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI
from pydantic import BaseModel, Field

from orchestrator.state import SlideContent, VideoGenerationState
from utils.llm_config import load_vision_model_config as _load_model_config

class ScriptResponse(BaseModel):
    """Wrapper for model output parsing."""
    slides: List[SlideContent] = Field(
        description="Ordered slide list corresponding to the images. page_number starts from 1 and increments by 1."
    )

def _local_image_to_data_url(image_path: str) -> str:
    """Convert a local image file to a data URL for multimodal input."""
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

def _build_messages(image_paths: List[str]) -> List[Dict[str, Any]]:
    system_prompt = (
        "You are an expert video scriptwriter. The user will provide a sequence of presentation slides as images.\n"
        "Your task is to analyze each slide in order and create an engaging voiceover script for it.\n"
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
        f"- Produce exactly {len(image_paths)} slide entries, matching the order of the images.\n"
        "- The voiceover text MUST naturally match what is shown on the screen.\n"
        "- The voiceover must be spoken natively in Simplified Chinese.\n"
    )

    user_content: List[Dict[str, Any]] = [
        {"type": "text", "text": "Please analyze these slides in sequence and generate the voiceover script for each."}
    ]
    
    for img_path in image_paths:
        data_url = _local_image_to_data_url(img_path)
        user_content.append({
            "type": "image_url", 
            "image_url": {"url": data_url, "detail": "high"}
        })

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

def ppt_vision_scriptwriter_node(state: VideoGenerationState) -> Dict[str, Any]:
    """
    [Node 1B] Takes a list of image paths and generates a voiceover for each slide using a Vision LLM.
    """
    # Use image_paths from state as input
    image_paths = state.get("image_paths", [])
    
    if not image_paths:
        return {"error_msg": "Missing 'image_paths' in state to generate script from."}

    config = _load_model_config(state=state, node_name="n1b_ppt_vision_scriptwriter")
    print(
        "[Node 1B: Vision Script] "
        f"Analyzing {len(image_paths)} images using model='{config['model']}' "
        f"via {config['provider']} ({config.get('provider_id', 'n/a')}), "
        f"source={config.get('source', 'unknown')}..."
    )

    if not config["api_key"]:
        return {
            "error_msg": (
                "Missing API key for vision scriptwriter. "
                f"Expected env var '{config.get('api_key_env', 'OPENAI_VISION_API_KEY')}'."
            )
        }

    client = OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        default_headers=config.get("extra_headers") or None,
    )
    messages = _build_messages(image_paths)

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

        parsed = _extract_json_object(raw_text)
        slide_response = ScriptResponse.model_validate(parsed)

        if not slide_response.slides:
            raise RuntimeError("Model returned empty slide list.")
            
        if len(slide_response.slides) != len(image_paths):
            print(f"[Warning] Model returned {len(slide_response.slides)} slides but provided {len(image_paths)} images.")

        print(f"[Node 1B: Vision Script] Successfully generated scripts for {len(slide_response.slides)} slides.")
        # Override slides_data in state
        return {"slides_data": slide_response.slides}

    except Exception as exc:
        error_msg = f"[Node 1B: Vision Script] Model call failed. Error: {exc}"
        print(error_msg)
        return {"error_msg": error_msg}
