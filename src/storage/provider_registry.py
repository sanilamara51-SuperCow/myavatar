import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.provider import ModelSpec, ProviderProfile, ResolvedModelRoute

_CAPABILITIES = ("text", "vision", "reflection")
_NODE_NAMES = (
    "n1_content_writer",
    "n1c_hybrid_content_writer",
    "n1b_ppt_vision_scriptwriter",
    "n0b_video_understanding",
    "crew_reflection",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_registry_db_path() -> Path:
    db_path = _repo_root() / "workspace" / ".myavatar" / "app.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_registry_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_provider_registry() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS provider_profiles (
                provider_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                base_url TEXT NOT NULL,
                api_key_env TEXT NOT NULL,
                extra_headers_json TEXT NOT NULL DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS provider_models (
                model_id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                capability TEXT NOT NULL,
                context_window INTEGER NOT NULL DEFAULT 0,
                supports_vision INTEGER NOT NULL DEFAULT 0,
                supports_json_mode INTEGER NOT NULL DEFAULT 1,
                enabled INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (provider_id) REFERENCES provider_profiles(provider_id)
            );

            CREATE TABLE IF NOT EXISTS project_model_routes (
                project_name TEXT PRIMARY KEY,
                default_text_model_id TEXT,
                default_vision_model_id TEXT,
                default_reflection_model_id TEXT
            );

            CREATE TABLE IF NOT EXISTS node_model_overrides (
                project_name TEXT NOT NULL,
                node_name TEXT NOT NULL,
                model_id TEXT NOT NULL,
                PRIMARY KEY (project_name, node_name)
            );
            """
        )
        _seed_legacy_defaults(conn)


def _seed_legacy_defaults(conn: sqlite3.Connection) -> None:
    ark_base = (os.getenv("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3").strip()
    ark_model = (os.getenv("ARK_API_MODEL") or "doubao-seed-2-0-pro-260215").strip()

    openai_base = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip()
    openai_model = (os.getenv("OPENAI_API_MODEL") or "gpt-4o-mini").strip()

    vision_base = (
        os.getenv("OPENAI_VISION_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).strip()
    vision_model = (os.getenv("VISION_API_MODEL") or "gpt-4o").strip()

    # Qwen2.5-VL for video understanding (local or cloud)
    qwen_vision_base = (
        os.getenv("CLOUD_VISION_BASE_URL")
        or os.getenv("LOCAL_VISION_MODEL_BASE_URL")
        or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ).strip()
    qwen_vision_model = (
        os.getenv("CLOUD_VISION_MODEL_NAME")
        or os.getenv("LOCAL_VISION_MODEL_NAME")
        or "qwen-vl-max-latest"
    ).strip()

    providers = [
        ProviderProfile(
            provider_id="legacy_ark",
            name="Legacy ARK",
            kind="openai_compatible",
            base_url=ark_base,
            api_key_env="ARK_API_KEY",
        ),
        ProviderProfile(
            provider_id="legacy_openai",
            name="Legacy OpenAI-Compatible",
            kind="openai_compatible",
            base_url=openai_base,
            api_key_env="OPENAI_API_KEY",
        ),
        ProviderProfile(
            provider_id="legacy_vision",
            name="Legacy Vision",
            kind="openai_compatible",
            base_url=vision_base,
            api_key_env="OPENAI_VISION_API_KEY",
        ),
        ProviderProfile(
            provider_id="qwen_vision",
            name="Qwen2.5-VL (Video Understanding)",
            kind="openai_compatible",
            base_url=qwen_vision_base,
            api_key_env="DASHSCOPE_API_KEY",
        ),
    ]

    for provider in providers:
        conn.execute(
            """
            INSERT OR IGNORE INTO provider_profiles
            (provider_id, name, kind, base_url, api_key_env, extra_headers_json, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider.provider_id,
                provider.name,
                provider.kind,
                provider.base_url,
                provider.api_key_env,
                provider.extra_headers_json,
                1 if provider.enabled else 0,
            ),
        )

    models = [
        ModelSpec(
            model_id=f"legacy_ark_text::{ark_model}",
            provider_id="legacy_ark",
            model_name=ark_model,
            capability="text",
            supports_json_mode=True,
        ),
        ModelSpec(
            model_id=f"legacy_ark_reflection::{ark_model}",
            provider_id="legacy_ark",
            model_name=ark_model,
            capability="reflection",
            supports_json_mode=True,
        ),
        ModelSpec(
            model_id=f"legacy_openai_text::{openai_model}",
            provider_id="legacy_openai",
            model_name=openai_model,
            capability="text",
            supports_json_mode=True,
        ),
        ModelSpec(
            model_id=f"legacy_openai_reflection::{openai_model}",
            provider_id="legacy_openai",
            model_name=openai_model,
            capability="reflection",
            supports_json_mode=True,
        ),
        ModelSpec(
            model_id=f"legacy_vision::{vision_model}",
            provider_id="legacy_vision",
            model_name=vision_model,
            capability="vision",
            supports_vision=True,
            supports_json_mode=True,
        ),
        ModelSpec(
            model_id=f"qwen_vision::{qwen_vision_model}",
            provider_id="qwen_vision",
            model_name=qwen_vision_model,
            capability="vision",
            supports_vision=True,
            supports_json_mode=True,
        ),
    ]

    for model in models:
        conn.execute(
            """
            INSERT OR IGNORE INTO provider_models
            (model_id, provider_id, model_name, capability, context_window, supports_vision, supports_json_mode, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                model.model_id,
                model.provider_id,
                model.model_name,
                model.capability,
                model.context_window,
                1 if model.supports_vision else 0,
                1 if model.supports_json_mode else 0,
                1 if model.enabled else 0,
            ),
        )

    conn.commit()


def _row_to_resolved(row: sqlite3.Row) -> ResolvedModelRoute:
    return ResolvedModelRoute(
        provider_id=row["provider_id"],
        provider_kind=row["kind"],
        base_url=row["base_url"],
        api_key_env=row["api_key_env"],
        extra_headers_json=row["extra_headers_json"],
        model_id=row["model_id"],
        model_name=row["model_name"],
        capability=row["capability"],
    )


def _fetch_route_by_model_id(conn: sqlite3.Connection, model_id: str) -> Optional[ResolvedModelRoute]:
    row = conn.execute(
        """
        SELECT
            m.model_id,
            m.model_name,
            m.capability,
            p.provider_id,
            p.kind,
            p.base_url,
            p.api_key_env,
            p.extra_headers_json
        FROM provider_models m
        JOIN provider_profiles p ON p.provider_id = m.provider_id
        WHERE m.model_id = ?
          AND m.enabled = 1
          AND p.enabled = 1
        """,
        (model_id,),
    ).fetchone()
    if not row:
        return None
    return _row_to_resolved(row)


def _project_default_model_id(
    conn: sqlite3.Connection,
    project_name: Optional[str],
    capability: str,
) -> Optional[str]:
    if not project_name:
        return None
    row = conn.execute(
        """
        SELECT default_text_model_id, default_vision_model_id, default_reflection_model_id
        FROM project_model_routes
        WHERE project_name = ?
        """,
        (project_name,),
    ).fetchone()
    if not row:
        return None

    if capability == "text":
        return row["default_text_model_id"]
    if capability == "vision":
        return row["default_vision_model_id"]
    if capability == "reflection":
        return row["default_reflection_model_id"] or row["default_text_model_id"]
    return None


def resolve_model_route(
    project_name: Optional[str],
    node_name: Optional[str],
    capability: str,
) -> Optional[Dict[str, str]]:
    if capability not in _CAPABILITIES:
        raise ValueError(f"Unsupported capability: {capability}")

    with _connect() as conn:
        if project_name and node_name:
            row = conn.execute(
                """
                SELECT model_id
                FROM node_model_overrides
                WHERE project_name = ? AND node_name = ?
                """,
                (project_name, node_name),
            ).fetchone()
            if row:
                resolved = _fetch_route_by_model_id(conn, row["model_id"])
                if resolved:
                    return resolved.to_dict()

        project_default_model_id = _project_default_model_id(conn, project_name, capability)
        if project_default_model_id:
            resolved = _fetch_route_by_model_id(conn, project_default_model_id)
            if resolved:
                return resolved.to_dict()

        capability_candidates = (capability,) if capability != "reflection" else ("reflection", "text")
        placeholders = ",".join(["?"] * len(capability_candidates))
        row = conn.execute(
            f"""
            SELECT
                m.model_id,
                m.model_name,
                m.capability,
                p.provider_id,
                p.kind,
                p.base_url,
                p.api_key_env,
                p.extra_headers_json
            FROM provider_models m
            JOIN provider_profiles p ON p.provider_id = m.provider_id
            WHERE m.enabled = 1
              AND p.enabled = 1
              AND m.capability IN ({placeholders})
            ORDER BY m.model_id ASC
            LIMIT 1
            """,
            capability_candidates,
        ).fetchone()
        if not row:
            return None
        return _row_to_resolved(row).to_dict()


def upsert_provider_profile(profile: Dict[str, Any]) -> None:
    provider = ProviderProfile(
        provider_id=str(profile["provider_id"]).strip(),
        name=str(profile["name"]).strip(),
        kind=str(profile["kind"]).strip(),  # type: ignore[arg-type]
        base_url=str(profile["base_url"]).strip(),
        api_key_env=str(profile["api_key_env"]).strip(),
        extra_headers_json=str(profile.get("extra_headers_json") or "{}").strip(),
        enabled=bool(profile.get("enabled", True)),
    )

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO provider_profiles
            (provider_id, name, kind, base_url, api_key_env, extra_headers_json, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_id) DO UPDATE SET
                name = excluded.name,
                kind = excluded.kind,
                base_url = excluded.base_url,
                api_key_env = excluded.api_key_env,
                extra_headers_json = excluded.extra_headers_json,
                enabled = excluded.enabled
            """,
            (
                provider.provider_id,
                provider.name,
                provider.kind,
                provider.base_url,
                provider.api_key_env,
                provider.extra_headers_json,
                1 if provider.enabled else 0,
            ),
        )
        conn.commit()


def upsert_model_spec(spec: Dict[str, Any]) -> None:
    model = ModelSpec(
        model_id=str(spec["model_id"]).strip(),
        provider_id=str(spec["provider_id"]).strip(),
        model_name=str(spec["model_name"]).strip(),
        capability=str(spec["capability"]).strip(),  # type: ignore[arg-type]
        context_window=int(spec.get("context_window") or 0),
        supports_vision=bool(spec.get("supports_vision", False)),
        supports_json_mode=bool(spec.get("supports_json_mode", True)),
        enabled=bool(spec.get("enabled", True)),
    )
    if model.capability not in _CAPABILITIES:
        raise ValueError(f"Unsupported capability: {model.capability}")

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO provider_models
            (model_id, provider_id, model_name, capability, context_window, supports_vision, supports_json_mode, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_id) DO UPDATE SET
                provider_id = excluded.provider_id,
                model_name = excluded.model_name,
                capability = excluded.capability,
                context_window = excluded.context_window,
                supports_vision = excluded.supports_vision,
                supports_json_mode = excluded.supports_json_mode,
                enabled = excluded.enabled
            """,
            (
                model.model_id,
                model.provider_id,
                model.model_name,
                model.capability,
                model.context_window,
                1 if model.supports_vision else 0,
                1 if model.supports_json_mode else 0,
                1 if model.enabled else 0,
            ),
        )
        conn.commit()


def upsert_project_model_route(
    project_name: str,
    default_text_model_id: Optional[str] = None,
    default_vision_model_id: Optional[str] = None,
    default_reflection_model_id: Optional[str] = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO project_model_routes
            (project_name, default_text_model_id, default_vision_model_id, default_reflection_model_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_name) DO UPDATE SET
                default_text_model_id = excluded.default_text_model_id,
                default_vision_model_id = excluded.default_vision_model_id,
                default_reflection_model_id = excluded.default_reflection_model_id
            """,
            (
                project_name.strip(),
                (default_text_model_id or "").strip() or None,
                (default_vision_model_id or "").strip() or None,
                (default_reflection_model_id or "").strip() or None,
            ),
        )
        conn.commit()


def upsert_node_model_override(project_name: str, node_name: str, model_id: str) -> None:
    normalized_node_name = node_name.strip()
    if normalized_node_name not in _NODE_NAMES:
        raise ValueError(f"Unsupported node_name '{normalized_node_name}'.")

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO node_model_overrides (project_name, node_name, model_id)
            VALUES (?, ?, ?)
            ON CONFLICT(project_name, node_name) DO UPDATE SET
                model_id = excluded.model_id
            """,
            (project_name.strip(), normalized_node_name, model_id.strip()),
        )
        conn.commit()


def list_provider_profiles() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT provider_id, name, kind, base_url, api_key_env, extra_headers_json, enabled
            FROM provider_profiles
            ORDER BY provider_id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_models(capability: Optional[str] = None) -> List[Dict[str, Any]]:
    params: List[Any] = []
    where_sql = ""
    if capability:
        where_sql = "WHERE capability = ?"
        params.append(capability)
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT model_id, provider_id, model_name, capability, context_window, supports_vision, supports_json_mode, enabled
            FROM provider_models
            {where_sql}
            ORDER BY model_id ASC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def list_project_model_routes() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                project_name,
                default_text_model_id,
                default_vision_model_id,
                default_reflection_model_id
            FROM project_model_routes
            ORDER BY project_name ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_node_model_overrides(project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    params: List[Any] = []
    where_sql = ""
    if project_name:
        where_sql = "WHERE project_name = ?"
        params.append(project_name.strip())

    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT project_name, node_name, model_id
            FROM node_model_overrides
            {where_sql}
            ORDER BY project_name ASC, node_name ASC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def supported_capabilities() -> List[str]:
    return list(_CAPABILITIES)


def supported_node_names() -> List[str]:
    return list(_NODE_NAMES)
