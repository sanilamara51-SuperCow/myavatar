import argparse
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

from orchestrator.hybrid_graph import build_hybrid_graph
from storage.persona_registry import init_persona_registry
from storage.provider_registry import (
    init_provider_registry,
    upsert_node_model_override,
    upsert_project_model_route,
)

DEFAULT_TOPIC = (
    "今天我通过 vibecoding，只花了一天时间搭建了一个全自动生成口播稿和视频的智能体。"
    "现在的这段视频正是由 AI 自己跑通的！内容是“AI教你怎么做套娃视频”。"
    "附带了我提供的 5 张截图资产（0.png~4.png），分别对应：1是向大模型问可行性调研。"
    "2是生成的调研报告。3是丢给 Gemini 执行。4是多智能体开始写代码。"
    "5是它手把手教我跑起这套本地的 cosyvoice 开源库。请仔细看这 5 张截图。"
    "并用激昂的、适合抖音极速流量起号的科技区博主口语帮我编排这整一期的幻灯视频及其演说口播稿！"
)
DEFAULT_AUDIENCE = "抖音追求AI黑客增长的泛科技兴趣路人"

SCRIPT_IMAGE_MARKER_PATTERN = re.compile(
    r"\[(?:截图|image)\s*:\s*([^\]\r\n]+?)\s*\]",
    re.IGNORECASE,
)


def _parse_meta_file(meta_path: Path) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    if not meta_path.is_file():
        return meta

    for line in meta_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        meta[key.strip()] = value.strip()
    return meta


def _safe_float(value: Optional[str], default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _extract_script_image_markers(topic_text: str) -> list[str]:
    markers: list[str] = []
    for raw in SCRIPT_IMAGE_MARKER_PATTERN.findall(topic_text or ""):
        marker_name = Path(raw.strip()).name
        if marker_name:
            markers.append(marker_name)
    return markers


def _strip_script_image_markers(topic_text: str) -> str:
    cleaned = SCRIPT_IMAGE_MARKER_PATTERN.sub("", topic_text or "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _reorder_images_by_markers(image_paths: list[str], markers: list[str]) -> list[str]:
    if not image_paths or not markers:
        return image_paths

    used: set[str] = set()
    ordered: list[str] = []

    lower_name_to_paths: dict[str, list[str]] = {}
    for path in image_paths:
        lower_name_to_paths.setdefault(Path(path).name.lower(), []).append(path)

    for marker in markers:
        marker_key = Path(marker).name.lower()
        candidates = lower_name_to_paths.get(marker_key, [])
        for candidate in candidates:
            if candidate not in used:
                ordered.append(candidate)
                used.add(candidate)
                break

    for path in image_paths:
        if path not in used:
            ordered.append(path)

    return ordered


def _load_project_script_inputs(inputs_dir: Path) -> Dict[str, str]:
    script_path = inputs_dir / "script.txt"
    meta_path = inputs_dir / "meta.txt"

    topic = ""
    if script_path.is_file():
        topic = script_path.read_text(encoding="utf-8").strip()

    meta = _parse_meta_file(meta_path)
    result: Dict[str, str] = {}
    if topic:
        result["topic"] = topic
    if meta.get("duration_mins"):
        result["duration_mins"] = meta["duration_mins"]
    if meta.get("target_audience"):
        result["target_audience"] = meta["target_audience"]
    if meta.get("template_id"):
        result["template_id"] = meta["template_id"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Myavatar Video Generation CLI")
    parser.add_argument(
        "--project",
        type=str,
        default="demo_project",
        help="Name of the project workspace to use.",
    )
    parser.add_argument(
        "--douyin-url",
        type=str,
        default="",
        help="Douyin share URL to download and process (e.g., https://v.douyin.com/xxx/).",
    )
    parser.add_argument(
        "--text-model-id", type=str, default="", help="Project default text model id."
    )
    parser.add_argument(
        "--vision-model-id",
        type=str,
        default="",
        help="Project default vision model id.",
    )
    parser.add_argument(
        "--reflection-model-id",
        type=str,
        default="",
        help="Project default reflection model id.",
    )
    parser.add_argument(
        "--template-id",
        type=str,
        default="",
        help="Slide template id (e.g. tech_burst, data_focus, tutorial_clean).",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default="",
        help="Override topic/script text for this run.",
    )
    parser.add_argument(
        "--duration-mins",
        type=float,
        default=None,
        help="Override target duration (minutes) for this run.",
    )
    parser.add_argument(
        "--target-audience",
        type=str,
        default="",
        help="Override target audience for this run.",
    )
    parser.add_argument(
        "--node-model-override",
        action="append",
        default=[],
        help="Per-node model override in the format node_name=model_id. Can be repeated.",
    )
    args = parser.parse_args()

    project_name = args.project
    root_dir = Path(__file__).resolve().parents[1]
    env_path = root_dir / ".env"
    load_dotenv(dotenv_path=env_path)
    init_provider_registry()
    init_persona_registry()

    if args.text_model_id or args.vision_model_id or args.reflection_model_id:
        upsert_project_model_route(
            project_name=project_name,
            default_text_model_id=args.text_model_id,
            default_vision_model_id=args.vision_model_id,
            default_reflection_model_id=args.reflection_model_id,
        )
        print(
            f"[Provider Registry] Updated project defaults for '{project_name}': "
            f"text={args.text_model_id or '-'}, vision={args.vision_model_id or '-'}, "
            f"reflection={args.reflection_model_id or '-'}"
        )

    if args.node_model_override:
        for item in args.node_model_override:
            if "=" not in item:
                raise ValueError(
                    f"Invalid --node-model-override '{item}'. Use format node_name=model_id."
                )
            node_name, model_id = item.split("=", 1)
            upsert_node_model_override(
                project_name=project_name,
                node_name=node_name.strip(),
                model_id=model_id.strip(),
            )
            print(
                f"[Provider Registry] Updated node override for '{project_name}': "
                f"{node_name.strip()} -> {model_id.strip()}"
            )

    project_dir = root_dir / "workspace" / "projects" / project_name
    inputs_dir = project_dir / "inputs"
    runs_dir = project_dir / "runs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    reference_image_path = (os.getenv("REFERENCE_IMAGE_PATH") or "").strip()
    reference_image_url = (os.getenv("REFERENCE_IMAGE_URL") or "").strip()

    ppt_image_paths = []
    if inputs_dir.exists():
        for name in sorted(os.listdir(str(inputs_dir))):
            if name.lower().endswith((".png", ".jpg", ".jpeg")):
                ppt_image_paths.append(str(inputs_dir / name))

    project_inputs = _load_project_script_inputs(inputs_dir)
    cli_topic = (args.topic or "").strip()
    cli_target_audience = (args.target_audience or "").strip()

    topic = (
        cli_topic
        or project_inputs.get("topic")
        or (os.getenv("TOPIC") or "").strip()
        or DEFAULT_TOPIC
    )
    duration_mins = (
        float(args.duration_mins)
        if args.duration_mins is not None
        else _safe_float(
            project_inputs.get("duration_mins")
            or (os.getenv("DURATION_MINS") or "").strip()
            or None,
            1.5,
        )
    )
    target_audience = (
        cli_target_audience
        or project_inputs.get("target_audience")
        or (os.getenv("TARGET_AUDIENCE") or "").strip()
        or DEFAULT_AUDIENCE
    )
    template_id = (
        args.template_id
        or project_inputs.get("template_id")
        or (os.getenv("PPT_TEMPLATE_ID") or "").strip()
        or "tech_burst"
    )

    script_image_markers = _extract_script_image_markers(topic)
    if script_image_markers:
        available_image_names = {Path(path).name.lower() for path in ppt_image_paths}
        missing_markers = [
            marker
            for marker in script_image_markers
            if Path(marker).name.lower() not in available_image_names
        ]
        resolved_markers = [
            marker
            for marker in script_image_markers
            if Path(marker).name.lower() in available_image_names
        ]

        if missing_markers:
            print(
                "[Script Markers] Warning: marker images not found in inputs: "
                + ", ".join(missing_markers)
            )

        if resolved_markers:
            ppt_image_paths = _reorder_images_by_markers(
                ppt_image_paths, resolved_markers
            )
            print(
                "[Script Markers] Applied image order hints: "
                + " -> ".join(resolved_markers)
            )

        cleaned_topic = _strip_script_image_markers(topic)
        if cleaned_topic:
            topic = cleaned_topic
    else:
        resolved_markers = []

    print("=" * 60)
    print("Myavatar auto video pipeline start (Hybrid Graph)")
    print(f"Project: {project_name}")
    print(f"Inputs:  {inputs_dir} (assets: {len(ppt_image_paths)})")
    print(f"Run Dir: {run_dir}")
    print(f"Template: {template_id}")
    if args.douyin_url:
        print(f"Douyin URL: {args.douyin_url}")
    if cli_topic:
        topic_source = "cli(--topic)"
    elif project_inputs.get("topic"):
        topic_source = "script.txt"
    else:
        topic_source = "default/env"
    print(f"Topic source: {topic_source}")
    print("=" * 60)

    graph = build_hybrid_graph()
    initial_state = {
        "project_name": project_name,
        "project_dir": str(project_dir),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "topic": topic,
        "duration_mins": duration_mins,
        "target_audience": target_audience,
        "template_id": template_id,
        "ppt_image_paths": ppt_image_paths,
        "script_image_markers": resolved_markers,
    }
    if reference_image_path:
        initial_state["reference_image_path"] = reference_image_path
    if reference_image_url:
        initial_state["reference_image_url"] = reference_image_url
    if args.douyin_url:
        initial_state["douyin_share_url"] = args.douyin_url.strip()

    try:
        print("\n>>> Running workflow...\n")
        final_state = graph.invoke(initial_state)

        print("\n" + "=" * 60)
        if final_state.get("error_msg"):
            print("Pipeline failed:", final_state["error_msg"])
        else:
            print("Pipeline finished.")
            print("Final video path:", final_state.get("final_video_path"))
        print("=" * 60)
    except Exception as exc:
        print(f"Fatal runtime error: {exc}")


if __name__ == "__main__":
    main()
