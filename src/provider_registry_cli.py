import argparse
import json
from typing import Any, Dict

from storage.provider_registry import (
    init_provider_registry,
    list_models,
    list_node_model_overrides,
    list_project_model_routes,
    list_provider_profiles,
    upsert_model_spec,
    upsert_node_model_override,
    upsert_project_model_route,
    upsert_provider_profile,
)


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _cmd_list(args: argparse.Namespace) -> None:
    if args.target == "providers":
        _print_json(list_provider_profiles())
        return
    if args.target == "models":
        _print_json(list_models(capability=args.capability))
        return
    if args.target == "project-routes":
        _print_json(list_project_model_routes())
        return
    if args.target == "node-overrides":
        _print_json(list_node_model_overrides(project_name=args.project))
        return
    raise ValueError(f"Unsupported list target: {args.target}")


def _cmd_add_provider(args: argparse.Namespace) -> None:
    payload: Dict[str, Any] = {
        "provider_id": args.provider_id,
        "name": args.name,
        "kind": args.kind,
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "extra_headers_json": args.extra_headers_json or "{}",
        "enabled": not args.disabled,
    }
    upsert_provider_profile(payload)
    print(f"provider upserted: {args.provider_id}")


def _cmd_add_model(args: argparse.Namespace) -> None:
    payload: Dict[str, Any] = {
        "model_id": args.model_id,
        "provider_id": args.provider_id,
        "model_name": args.model_name,
        "capability": args.capability,
        "context_window": args.context_window,
        "supports_vision": args.supports_vision,
        "supports_json_mode": not args.no_json_mode,
        "enabled": not args.disabled,
    }
    upsert_model_spec(payload)
    print(f"model upserted: {args.model_id}")


def _cmd_set_project_defaults(args: argparse.Namespace) -> None:
    upsert_project_model_route(
        project_name=args.project,
        default_text_model_id=args.text_model_id,
        default_vision_model_id=args.vision_model_id,
        default_reflection_model_id=args.reflection_model_id,
    )
    print(f"project defaults set: {args.project}")


def _cmd_set_node_override(args: argparse.Namespace) -> None:
    upsert_node_model_override(
        project_name=args.project,
        node_name=args.node_name,
        model_id=args.model_id,
    )
    print(f"node override set: {args.project} / {args.node_name} -> {args.model_id}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provider Registry management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser(
        "list",
        help="List providers, models, project routes, or node overrides",
    )
    list_parser.add_argument(
        "target",
        choices=["providers", "models", "project-routes", "node-overrides"],
    )
    list_parser.add_argument("--capability", choices=["text", "vision", "reflection"], default=None)
    list_parser.add_argument("--project", default=None)
    list_parser.set_defaults(func=_cmd_list)

    add_provider = subparsers.add_parser("add-provider", help="Create or update a provider profile")
    add_provider.add_argument("--provider-id", required=True)
    add_provider.add_argument("--name", required=True)
    add_provider.add_argument(
        "--kind",
        required=True,
        choices=[
            "openai_compatible",
            "anthropic_compatible",
            "gemini_compatible",
            "local_ollama",
            "custom_http",
        ],
    )
    add_provider.add_argument("--base-url", required=True)
    add_provider.add_argument("--api-key-env", required=True)
    add_provider.add_argument("--extra-headers-json", default="{}")
    add_provider.add_argument("--disabled", action="store_true")
    add_provider.set_defaults(func=_cmd_add_provider)

    add_model = subparsers.add_parser("add-model", help="Create or update a model spec")
    add_model.add_argument("--model-id", required=True)
    add_model.add_argument("--provider-id", required=True)
    add_model.add_argument("--model-name", required=True)
    add_model.add_argument("--capability", required=True, choices=["text", "vision", "reflection"])
    add_model.add_argument("--context-window", type=int, default=0)
    add_model.add_argument("--supports-vision", action="store_true")
    add_model.add_argument("--no-json-mode", action="store_true")
    add_model.add_argument("--disabled", action="store_true")
    add_model.set_defaults(func=_cmd_add_model)

    project_defaults = subparsers.add_parser(
        "set-project-defaults",
        help="Set project-level default model routes",
    )
    project_defaults.add_argument("--project", required=True)
    project_defaults.add_argument("--text-model-id")
    project_defaults.add_argument("--vision-model-id")
    project_defaults.add_argument("--reflection-model-id")
    project_defaults.set_defaults(func=_cmd_set_project_defaults)

    node_override = subparsers.add_parser("set-node-override", help="Set per-node model override")
    node_override.add_argument("--project", required=True)
    node_override.add_argument(
        "--node-name",
        required=True,
        choices=[
            "n1_content_writer",
            "n1c_hybrid_content_writer",
            "n1b_ppt_vision_scriptwriter",
            "crew_reflection",
        ],
    )
    node_override.add_argument("--model-id", required=True)
    node_override.set_defaults(func=_cmd_set_node_override)

    return parser


def main() -> None:
    init_provider_registry()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
