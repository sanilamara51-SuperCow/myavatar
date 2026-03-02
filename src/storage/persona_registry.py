import os
import sqlite3
from typing import Any, Dict, List, Optional

from storage.provider_registry import get_registry_db_path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_registry_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def init_persona_registry() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS personas (
                persona_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                cosyvoice_mode TEXT NOT NULL DEFAULT 'zero_shot',
                voice TEXT NOT NULL DEFAULT '',
                prompt_text TEXT NOT NULL DEFAULT '',
                prompt_wav_path TEXT NOT NULL DEFAULT '',
                instruct_text TEXT NOT NULL DEFAULT '',
                audio_format TEXT NOT NULL DEFAULT 'wav',
                sample_rate INTEGER NOT NULL DEFAULT 22050,
                base_speed REAL NOT NULL DEFAULT 1.0,
                default_pause_ms INTEGER NOT NULL DEFAULT 260,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        _seed_default_persona(conn)


def _seed_default_persona(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO personas
        (persona_id, name, cosyvoice_mode, voice, prompt_text, prompt_wav_path, instruct_text, audio_format, sample_rate, base_speed, default_pause_ms, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "host",
            "Host Default",
            (os.getenv("COSYVOICE_MODE") or "zero_shot").strip() or "zero_shot",
            (os.getenv("COSYVOICE_VOICE") or "").strip(),
            (os.getenv("COSYVOICE_PROMPT_TEXT") or "").strip(),
            (os.getenv("COSYVOICE_PROMPT_WAV_PATH") or "").strip(),
            (os.getenv("COSYVOICE_INSTRUCT_TEXT") or "").strip(),
            (os.getenv("COSYVOICE_AUDIO_FORMAT") or "wav").strip(),
            int((os.getenv("COSYVOICE_SAMPLE_RATE") or "22050").strip()),
            1.0,
            int((os.getenv("TTS_DEFAULT_PAUSE_MS") or "260").strip()),
            1,
        ),
    )
    conn.commit()


def list_personas(enabled_only: bool = False) -> List[Dict[str, Any]]:
    where = "WHERE enabled = 1" if enabled_only else ""
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT persona_id, name, cosyvoice_mode, voice, prompt_text, prompt_wav_path, instruct_text,
                   audio_format, sample_rate, base_speed, default_pause_ms, enabled
            FROM personas
            {where}
            ORDER BY persona_id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_persona(persona_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT persona_id, name, cosyvoice_mode, voice, prompt_text, prompt_wav_path, instruct_text,
                   audio_format, sample_rate, base_speed, default_pause_ms, enabled
            FROM personas
            WHERE persona_id = ?
            """,
            (persona_id.strip(),),
        ).fetchone()
    return dict(row) if row else None


def upsert_persona(payload: Dict[str, Any]) -> None:
    persona_id = str(payload["persona_id"]).strip()
    name = str(payload.get("name") or persona_id).strip()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO personas
            (persona_id, name, cosyvoice_mode, voice, prompt_text, prompt_wav_path, instruct_text,
             audio_format, sample_rate, base_speed, default_pause_ms, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(persona_id) DO UPDATE SET
                name = excluded.name,
                cosyvoice_mode = excluded.cosyvoice_mode,
                voice = excluded.voice,
                prompt_text = excluded.prompt_text,
                prompt_wav_path = excluded.prompt_wav_path,
                instruct_text = excluded.instruct_text,
                audio_format = excluded.audio_format,
                sample_rate = excluded.sample_rate,
                base_speed = excluded.base_speed,
                default_pause_ms = excluded.default_pause_ms,
                enabled = excluded.enabled
            """,
            (
                persona_id,
                name,
                str(payload.get("cosyvoice_mode") or "zero_shot").strip(),
                str(payload.get("voice") or "").strip(),
                str(payload.get("prompt_text") or "").strip(),
                str(payload.get("prompt_wav_path") or "").strip(),
                str(payload.get("instruct_text") or "").strip(),
                str(payload.get("audio_format") or "wav").strip(),
                int(payload.get("sample_rate") or 22050),
                float(payload.get("base_speed") or 1.0),
                int(payload.get("default_pause_ms") or 260),
                1 if bool(payload.get("enabled", True)) else 0,
            ),
        )
        conn.commit()

