import argparse
import json
from typing import Any, Dict

from storage.persona_registry import get_persona, init_persona_registry, list_personas, upsert_persona


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _cmd_list(args: argparse.Namespace) -> None:
    _print_json(list_personas(enabled_only=args.enabled_only))


def _cmd_get(args: argparse.Namespace) -> None:
    persona = get_persona(args.persona_id)
    if not persona:
        raise SystemExit(f"persona not found: {args.persona_id}")
    _print_json(persona)


def _cmd_upsert(args: argparse.Namespace) -> None:
    payload: Dict[str, Any] = {
        "persona_id": args.persona_id,
        "name": args.name or args.persona_id,
        "cosyvoice_mode": args.cosyvoice_mode,
        "voice": args.voice,
        "prompt_text": args.prompt_text,
        "prompt_wav_path": args.prompt_wav_path,
        "instruct_text": args.instruct_text,
        "audio_format": args.audio_format,
        "sample_rate": args.sample_rate,
        "base_speed": args.base_speed,
        "default_pause_ms": args.default_pause_ms,
        "enabled": not args.disabled,
    }
    upsert_persona(payload)
    print(f"persona upserted: {args.persona_id}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persona Registry management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List personas")
    list_parser.add_argument("--enabled-only", action="store_true")
    list_parser.set_defaults(func=_cmd_list)

    get_parser = subparsers.add_parser("get", help="Get one persona")
    get_parser.add_argument("--persona-id", required=True)
    get_parser.set_defaults(func=_cmd_get)

    upsert_parser = subparsers.add_parser("upsert", help="Create or update a persona")
    upsert_parser.add_argument("--persona-id", required=True)
    upsert_parser.add_argument("--name", default="")
    upsert_parser.add_argument("--cosyvoice-mode", default="zero_shot")
    upsert_parser.add_argument("--voice", default="")
    upsert_parser.add_argument("--prompt-text", default="")
    upsert_parser.add_argument("--prompt-wav-path", default="")
    upsert_parser.add_argument("--instruct-text", default="")
    upsert_parser.add_argument("--audio-format", default="wav")
    upsert_parser.add_argument("--sample-rate", type=int, default=22050)
    upsert_parser.add_argument("--base-speed", type=float, default=1.0)
    upsert_parser.add_argument("--default-pause-ms", type=int, default=260)
    upsert_parser.add_argument("--disabled", action="store_true")
    upsert_parser.set_defaults(func=_cmd_upsert)

    return parser


def main() -> None:
    init_persona_registry()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

