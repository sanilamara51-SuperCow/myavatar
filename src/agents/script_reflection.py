import json
import os
import re
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple

from openai import OpenAI
from pydantic import BaseModel, Field

from orchestrator.state import SlideContent, VideoGenerationState
from utils.llm_config import load_reflection_model_config

try:
    from crewai import Agent, Crew, LLM as CrewLLM, Process, Task

    _HAS_CREWAI = True
except Exception:
    Agent = None  # type: ignore[assignment]
    Crew = None  # type: ignore[assignment]
    CrewLLM = None  # type: ignore[assignment]
    Process = None  # type: ignore[assignment]
    Task = None  # type: ignore[assignment]
    _HAS_CREWAI = False


class ReviewResult(BaseModel):
    score: int = Field(ge=0, le=100)
    rewrite_required: bool
    issues: List[str] = Field(default_factory=list)
    rewrite_instructions: List[str] = Field(default_factory=list)


class SlidesEnvelope(BaseModel):
    slides: List[SlideContent]


def _as_int(value: Optional[str], default: int) -> int:
    try:
        return int(value) if value is not None else default
    except Exception:
        return default


def _as_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _is_enabled() -> bool:
    return _as_bool(os.getenv("ENABLE_CREW_REFLECTION"), True)


def _read_engine_preference() -> str:
    raw = (os.getenv("SCRIPT_REFLECTION_ENGINE") or "crewai").strip().lower()
    if raw in {"crewai", "model"}:
        return raw
    return "crewai"


def _allow_model_fallback() -> bool:
    return _as_bool(os.getenv("SCRIPT_REFLECTION_FALLBACK_TO_MODEL"), True)


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join([p for p in parts if p]).strip()
    return ""


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    text = raw_text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("Model output does not contain a valid JSON object.")
    return json.loads(text[start : end + 1])


def _slides_to_json(slides: List[SlideContent]) -> str:
    return json.dumps(
        {"slides": [slide.model_dump() for slide in slides]},
        ensure_ascii=False,
        indent=2,
    )


def _call_json_chat(
    client: OpenAI,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float,
) -> Dict[str, Any]:
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    if not response.choices:
        raise RuntimeError("Model response has no choices.")
    raw_text = _extract_text_content(response.choices[0].message.content)
    if not raw_text:
        raise RuntimeError("Model response is empty.")
    return _extract_json_object(raw_text)


def _review_once_model(
    client: OpenAI,
    model: str,
    topic: str,
    slides: List[SlideContent],
    target_score: int,
) -> ReviewResult:
    system_prompt = (
        "You are a strict video script reviewer.\n"
        "Evaluate slide script quality for short-video narration.\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "score": 0,\n'
        '  "rewrite_required": true,\n'
        '  "issues": ["..."],\n'
        '  "rewrite_instructions": ["..."]\n'
        "}\n"
        "Scoring dimensions:\n"
        "- Clarity and coherence\n"
        "- Natural spoken rhythm\n"
        "- Information density control\n"
        "- Audience fit and hook strength\n"
        "Rules:\n"
        f"- If score >= {target_score}, rewrite_required should usually be false.\n"
        "- Keep issues and instructions concise and actionable.\n"
    )
    user_prompt = f"Topic: {topic}\n\nCurrent slides JSON:\n{_slides_to_json(slides)}\n"

    parsed = _call_json_chat(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return ReviewResult.model_validate(parsed)


def _rewrite_once_model(
    client: OpenAI,
    model: str,
    topic: str,
    slides: List[SlideContent],
    review: ReviewResult,
) -> List[SlideContent]:
    system_prompt = (
        "You are a senior script editor.\n"
        "Rewrite the slides according to reviewer instructions.\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "slides": [\n'
        "    {\n"
        '      "page_number": 1,\n'
        '      "title": "string",\n'
        '      "content_points": ["string", "string"],\n'
        '      "voiceover": "string",\n'
        '      "image_source": null,\n'
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
        "}\n"
        "Rules:\n"
        "- Preserve slide count and page_number continuity.\n"
        "- Keep language in Simplified Chinese.\n"
        "- Keep capture/image fields if still valid, only change when necessary.\n"
        "- Keep speaker_segments aligned with voiceover. If missing, create it.\n"
        "- Improve spoken rhythm and avoid over-dense wording.\n"
    )
    user_prompt = (
        f"Topic: {topic}\n\n"
        f"Current slides JSON:\n{_slides_to_json(slides)}\n\n"
        "Reviewer result:\n"
        f"{json.dumps(review.model_dump(), ensure_ascii=False, indent=2)}\n"
    )

    parsed = _call_json_chat(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.35,
    )
    rewritten = SlidesEnvelope.model_validate(parsed)
    if not rewritten.slides:
        raise RuntimeError("Rewrite produced empty slides.")
    return rewritten.slides


@contextmanager
def _temporary_env(overrides: Dict[str, str]) -> Iterable[None]:
    old_values: Dict[str, Optional[str]] = {}
    try:
        for key, value in overrides.items():
            old_values[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key, old in old_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _instantiate_flex(factory: Any, payload: Dict[str, Any]) -> Any:
    current = dict(payload)
    while True:
        try:
            return factory(**current)
        except TypeError as exc:
            msg = str(exc)
            match = re.search(r"unexpected keyword argument ['\"]([^'\"]+)['\"]", msg)
            if match:
                bad_key = match.group(1)
                if bad_key in current:
                    current.pop(bad_key)
                    continue
            raise


def _extract_crewai_text(result: Any) -> str:
    if isinstance(result, str):
        return result

    for attr in ("raw", "output", "result", "final_output"):
        value = getattr(result, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    task_outputs = getattr(result, "tasks_output", None)
    if isinstance(task_outputs, list) and task_outputs:
        for item in reversed(task_outputs):
            raw = getattr(item, "raw", None)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()

    return str(result)


def _build_crewai_llm(config: Dict[str, Any]) -> Any:
    if CrewLLM is None:
        return None

    base_url = str(config.get("base_url") or "").strip()
    api_key = str(config.get("api_key") or "").strip()
    model = str(config.get("model") or "").strip()
    if not model:
        return None

    candidates = [
        {"model": model, "base_url": base_url, "api_key": api_key},
        {"model": f"openai/{model}", "base_url": base_url, "api_key": api_key},
    ]
    for payload in candidates:
        try:
            return _instantiate_flex(CrewLLM, payload)
        except Exception:
            continue
    return None


def _build_crewai_agent(
    role: str,
    goal: str,
    backstory: str,
    config: Dict[str, Any],
) -> Any:
    if Agent is None:
        raise RuntimeError("CrewAI Agent is unavailable.")

    verbose = _as_bool(os.getenv("CREWAI_REFLECTION_VERBOSE"), False)
    llm_candidates: List[Any] = []
    llm_obj = _build_crewai_llm(config)
    if llm_obj is not None:
        llm_candidates.append(llm_obj)
    model_name = str(config.get("model") or "").strip()
    if model_name:
        llm_candidates.append(f"openai/{model_name}")
        llm_candidates.append(model_name)
    llm_candidates.append(None)

    last_error: Optional[Exception] = None
    for llm in llm_candidates:
        payload: Dict[str, Any] = {
            "role": role,
            "goal": goal,
            "backstory": backstory,
            "allow_delegation": False,
            "verbose": verbose,
        }
        if llm is not None:
            payload["llm"] = llm
        try:
            return _instantiate_flex(Agent, payload)
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Failed to build CrewAI agent: {last_error}")


def _run_crewai_single_task(
    *,
    config: Dict[str, Any],
    role: str,
    goal: str,
    backstory: str,
    description: str,
    expected_output: str,
) -> str:
    if not _HAS_CREWAI or Crew is None or Task is None:
        raise RuntimeError("CrewAI package is not installed.")

    agent = _build_crewai_agent(
        role=role,
        goal=goal,
        backstory=backstory,
        config=config,
    )

    task = _instantiate_flex(
        Task,
        {
            "description": description,
            "expected_output": expected_output,
            "agent": agent,
        },
    )

    crew_payload: Dict[str, Any] = {
        "agents": [agent],
        "tasks": [task],
        "verbose": _as_bool(os.getenv("CREWAI_REFLECTION_VERBOSE"), False),
    }
    if Process is not None:
        try:
            crew_payload["process"] = Process.sequential
        except Exception:
            pass

    crew = _instantiate_flex(Crew, crew_payload)

    env_overrides = {
        "OPENAI_API_KEY": str(config.get("api_key") or "").strip(),
        "OPENAI_BASE_URL": str(config.get("base_url") or "").strip(),
        "OPENAI_API_BASE": str(config.get("base_url") or "").strip(),
        "OPENAI_MODEL_NAME": str(config.get("model") or "").strip(),
        "CREWAI_DISABLE_TELEMETRY": (
            os.getenv("CREWAI_DISABLE_TELEMETRY") or "true"
        ).strip(),
        "CREWAI_TRACING_ENABLED": (
            os.getenv("CREWAI_TRACING_ENABLED") or "false"
        ).strip(),
        "OTEL_SDK_DISABLED": (os.getenv("OTEL_SDK_DISABLED") or "true").strip(),
    }
    with _temporary_env(env_overrides):
        result = crew.kickoff()
    return _extract_crewai_text(result)


def _review_once_crewai(
    config: Dict[str, Any],
    topic: str,
    slides: List[SlideContent],
    target_score: int,
) -> ReviewResult:
    description = (
        "你是短视频脚本审稿人。请对下面 slides JSON 打分并给出可执行修改建议。\n"
        "输出必须是严格 JSON 对象，不要 Markdown，不要解释。\n"
        "格式:\n"
        "{\n"
        '  "score": 0,\n'
        '  "rewrite_required": true,\n'
        '  "issues": ["..."],\n'
        '  "rewrite_instructions": ["..."]\n'
        "}\n"
        f"当 score >= {target_score} 时，rewrite_required 通常应为 false。\n"
        f"Topic: {topic}\n\n"
        f"Slides JSON:\n{_slides_to_json(slides)}\n"
    )
    expected_output = (
        "A strict JSON object with score/rewrite_required/issues/rewrite_instructions."
    )

    raw = _run_crewai_single_task(
        config=config,
        role="Script Reviewer",
        goal="Identify quality issues and score short-video slide scripts.",
        backstory="You audit script clarity, rhythm, density, and audience fit.",
        description=description,
        expected_output=expected_output,
    )
    parsed = _extract_json_object(raw)
    return ReviewResult.model_validate(parsed)


def _rewrite_once_crewai(
    config: Dict[str, Any],
    topic: str,
    slides: List[SlideContent],
    review: ReviewResult,
) -> List[SlideContent]:
    description = (
        "你是短视频脚本改稿编辑。请根据评审意见重写 slides。\n"
        "输出必须是严格 JSON 对象，不要 Markdown，不要解释。\n"
        "格式:\n"
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
        "}\n"
        "规则:\n"
        "- 保持页数与 page_number 连续。\n"
        "- 保持简体中文口语风格。\n"
        "- speaker_segments 要与 voiceover 对齐。\n"
        "- image/capture/layout 字段尽量保留，确需调整再改。\n"
        "- layout 选项: text_only(纯文字), image_right(图文左右), image_left(右左), image_bottom(上中下), image_full(全屏图)。\n\n"
        f"Topic: {topic}\n\n"
        f"Current slides JSON:\n{_slides_to_json(slides)}\n\n"
        "Review JSON:\n"
        f"{json.dumps(review.model_dump(), ensure_ascii=False, indent=2)}\n"
    )
    expected_output = "A strict JSON object with key 'slides'."

    raw = _run_crewai_single_task(
        config=config,
        role="Script Rewriter",
        goal="Rewrite slides into tighter, more natural short-video narration.",
        backstory="You transform rough scripts into polished creator-ready narration.",
        description=description,
        expected_output=expected_output,
    )
    parsed = _extract_json_object(raw)
    rewritten = SlidesEnvelope.model_validate(parsed)
    if not rewritten.slides:
        raise RuntimeError("CrewAI rewrite produced empty slides.")
    return rewritten.slides


def _run_model_reflection_loop(
    *,
    config: Dict[str, Any],
    topic: str,
    slides: List[SlideContent],
    max_rounds: int,
    target_score: int,
) -> Tuple[List[SlideContent], List[Dict[str, Any]], str]:
    client = OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        default_headers=config.get("extra_headers") or None,
    )

    current_slides = slides
    rounds: List[Dict[str, Any]] = []
    final_error = ""

    for idx in range(max_rounds):
        round_no = idx + 1
        try:
            review = _review_once_model(
                client=client,
                model=config["model"],
                topic=topic,
                slides=current_slides,
                target_score=target_score,
            )
            rounds.append(
                {
                    "round": round_no,
                    "score": review.score,
                    "rewrite_required": review.rewrite_required,
                    "issues": review.issues,
                    "engine": "model",
                }
            )
            print(
                "[Script Reflection:model] "
                f"round={round_no}, score={review.score}, rewrite_required={review.rewrite_required}"
            )

            if review.score >= target_score or not review.rewrite_required:
                break

            current_slides = _rewrite_once_model(
                client=client,
                model=config["model"],
                topic=topic,
                slides=current_slides,
                review=review,
            )
        except Exception as exc:
            final_error = str(exc)
            rounds.append({"round": round_no, "error": final_error, "engine": "model"})
            print(f"[Script Reflection:model] round={round_no} failed: {exc}")
            break

    return current_slides, rounds, final_error


def _run_crewai_reflection_loop(
    *,
    config: Dict[str, Any],
    topic: str,
    slides: List[SlideContent],
    max_rounds: int,
    target_score: int,
) -> Tuple[List[SlideContent], List[Dict[str, Any]], str]:
    current_slides = slides
    rounds: List[Dict[str, Any]] = []
    final_error = ""

    for idx in range(max_rounds):
        round_no = idx + 1
        try:
            review = _review_once_crewai(
                config=config,
                topic=topic,
                slides=current_slides,
                target_score=target_score,
            )
            rounds.append(
                {
                    "round": round_no,
                    "score": review.score,
                    "rewrite_required": review.rewrite_required,
                    "issues": review.issues,
                    "engine": "crewai",
                }
            )
            print(
                "[Script Reflection:crewai] "
                f"round={round_no}, score={review.score}, rewrite_required={review.rewrite_required}"
            )

            if review.score >= target_score or not review.rewrite_required:
                break

            current_slides = _rewrite_once_crewai(
                config=config,
                topic=topic,
                slides=current_slides,
                review=review,
            )
        except Exception as exc:
            final_error = str(exc)
            rounds.append({"round": round_no, "error": final_error, "engine": "crewai"})
            print(f"[Script Reflection:crewai] round={round_no} failed: {exc}")
            break

    return current_slides, rounds, final_error


def refine_slides_with_reflection(
    slides: List[SlideContent],
    topic: str,
    state: VideoGenerationState,
) -> Dict[str, Any]:
    """
    Reflection loop used by Node 1C.

    Engines:
    - crewai: multi-agent reflection (preferred)
    - model: legacy model-driven review/rewrite loop
    """
    if not slides:
        return {
            "slides": slides,
            "report": {"enabled": False, "reason": "empty_slides"},
        }
    if not _is_enabled():
        return {
            "slides": slides,
            "report": {"enabled": False, "reason": "disabled_by_env"},
        }

    max_rounds = max(1, _as_int(os.getenv("SCRIPT_REFLECTION_MAX_ROUNDS"), 3))
    target_score = _as_int(os.getenv("SCRIPT_REFLECTION_TARGET_SCORE"), 85)
    engine_requested = _read_engine_preference()
    fallback_to_model = _allow_model_fallback()

    config = load_reflection_model_config(state=state, node_name="crew_reflection")
    if not config.get("api_key"):
        return {
            "slides": slides,
            "report": {
                "enabled": False,
                "reason": "missing_api_key",
                "api_key_env": config.get("api_key_env"),
                "engine_requested": engine_requested,
                "crewai_available": _HAS_CREWAI,
            },
        }

    current_slides = slides
    rounds: List[Dict[str, Any]] = []
    final_error = ""
    engine_used = engine_requested
    fallback_used = False

    try:
        if engine_requested == "crewai":
            if not _HAS_CREWAI:
                raise RuntimeError("CrewAI package is not installed.")
            current_slides, rounds, final_error = _run_crewai_reflection_loop(
                config=config,
                topic=topic,
                slides=current_slides,
                max_rounds=max_rounds,
                target_score=target_score,
            )
        else:
            current_slides, rounds, final_error = _run_model_reflection_loop(
                config=config,
                topic=topic,
                slides=current_slides,
                max_rounds=max_rounds,
                target_score=target_score,
            )
    except Exception as exc:
        final_error = str(exc)
        rounds.append({"round": 0, "error": final_error, "engine": engine_requested})

    if engine_requested == "crewai" and (final_error or not rounds):
        if fallback_to_model:
            fallback_used = True
            engine_used = "model"
            warn_msg = (
                "CrewAI reflection failed; switched to model loop. "
                f"reason={final_error or 'unknown'}"
            )
            rounds.append({"round": 0, "warning": warn_msg, "engine": "model_fallback"})
            current_slides, model_rounds, model_error = _run_model_reflection_loop(
                config=config,
                topic=topic,
                slides=slides,
                max_rounds=max_rounds,
                target_score=target_score,
            )
            rounds.extend(model_rounds)
            final_error = model_error

    return {
        "slides": current_slides,
        "report": {
            "enabled": True,
            "provider": config.get("provider"),
            "provider_id": config.get("provider_id"),
            "model": config.get("model"),
            "max_rounds": max_rounds,
            "target_score": target_score,
            "engine_requested": engine_requested,
            "engine_used": engine_used,
            "fallback_to_model": fallback_to_model,
            "fallback_used": fallback_used,
            "crewai_available": _HAS_CREWAI,
            "rounds": rounds,
            "error": final_error,
        },
    }
