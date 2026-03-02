import json
import os
from typing import Any, Dict, Optional

from storage.provider_registry import init_provider_registry, resolve_model_route


def _extract_project_name(state: Optional[Dict[str, Any]] = None) -> Optional[str]:
    if not state:
        return None
    value = state.get("project_name")
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _safe_parse_json_object(raw: str) -> Dict[str, str]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    safe: Dict[str, str] = {}
    for k, v in parsed.items():
        safe[str(k)] = str(v)
    return safe


def _build_registry_config(route: Dict[str, str]) -> Dict[str, Any]:
    api_key_env = (route.get("api_key_env") or "").strip()
    api_key = (os.getenv(api_key_env) or "").strip() if api_key_env else ""

    return {
        "provider": (route.get("provider_kind") or "openai_compatible").strip(),
        "provider_id": (route.get("provider_id") or "").strip(),
        "base_url": (route.get("base_url") or "").strip(),
        "model": (route.get("model_name") or "").strip(),
        "api_key_env": api_key_env,
        "api_key": api_key,
        "extra_headers": _safe_parse_json_object(route.get("extra_headers_json") or ""),
        "source": "provider_registry",
    }


def _load_legacy_text_model_config() -> Dict[str, Any]:
    # Legacy behavior: prefer ARK if key exists, otherwise use OPENAI_*.
    ark_key = (os.getenv("ARK_API_KEY") or "").strip()
    if ark_key:
        return {
            "provider": "openai_compatible",
            "provider_id": "legacy_ark",
            "api_key_env": "ARK_API_KEY",
            "api_key": ark_key,
            "base_url": (os.getenv("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3").strip(),
            "model": (os.getenv("ARK_API_MODEL") or "doubao-seed-2-0-pro-260215").strip(),
            "extra_headers": {},
            "source": "legacy_env",
        }

    return {
        "provider": "openai_compatible",
        "provider_id": "legacy_openai",
        "api_key_env": "OPENAI_API_KEY",
        "api_key": (os.getenv("OPENAI_API_KEY") or "").strip(),
        "base_url": (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip(),
        "model": (os.getenv("OPENAI_API_MODEL") or "gpt-4o-mini").strip(),
        "extra_headers": {},
        "source": "legacy_env",
    }


def _load_legacy_vision_model_config() -> Dict[str, Any]:
    vision_key = (os.getenv("OPENAI_VISION_API_KEY") or "").strip()
    if vision_key:
        return {
            "provider": "openai_compatible",
            "provider_id": "legacy_vision",
            "api_key_env": "OPENAI_VISION_API_KEY",
            "api_key": vision_key,
            "base_url": (
                os.getenv("OPENAI_VISION_BASE_URL")
                or "https://ark.cn-beijing.volces.com/api/v3"
            ).strip(),
            "model": (os.getenv("VISION_API_MODEL") or "doubao-seed-2-0-pro-260215").strip(),
            "extra_headers": {},
            "source": "legacy_env",
        }

    # If no dedicated vision key is configured, fallback to text model route.
    text_fallback = _load_legacy_text_model_config()
    text_fallback["source"] = "legacy_env_fallback"
    return text_fallback


def _load_legacy_reflection_model_config() -> Dict[str, Any]:
    # Reflection model defaults to text model unless explicitly routed by registry.
    cfg = _load_legacy_text_model_config()
    cfg["source"] = "legacy_env_reflection"
    return cfg


def _resolve_registry_config(
    capability: str,
    node_name: str,
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    init_provider_registry()
    route = resolve_model_route(
        project_name=_extract_project_name(state),
        node_name=node_name,
        capability=capability,
    )
    if not route:
        return {}
    return _build_registry_config(route)


def load_text_model_config(
    state: Optional[Dict[str, Any]] = None,
    node_name: str = "n1_content_writer",
) -> Dict[str, Any]:
    """
    Load text generation model config with routing priority:
    node override > project default > registry default > legacy env fallback.
    """
    routed = _resolve_registry_config(capability="text", node_name=node_name, state=state)
    if routed.get("model"):
        return routed
    return _load_legacy_text_model_config()


def load_vision_model_config(
    state: Optional[Dict[str, Any]] = None,
    node_name: str = "n1b_ppt_vision_scriptwriter",
) -> Dict[str, Any]:
    """
    Load multimodal vision model config with the same routing strategy.
    """
    routed = _resolve_registry_config(capability="vision", node_name=node_name, state=state)
    if routed.get("model"):
        return routed
    return _load_legacy_vision_model_config()


def load_reflection_model_config(
    state: Optional[Dict[str, Any]] = None,
    node_name: str = "crew_reflection",
) -> Dict[str, Any]:
    """
    Load script reflection model config for CrewAI loops.
    """
    routed = _resolve_registry_config(capability="reflection", node_name=node_name, state=state)
    if routed.get("model"):
        return routed
    return _load_legacy_reflection_model_config()

