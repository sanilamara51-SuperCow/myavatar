import asyncio
import base64
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
import soundfile as sf


@dataclass
class CosyVoiceConfig:
    api_url: str
    api_key: str
    api_style: str
    mode: str
    voice: str
    model: str
    prompt_text: str
    prompt_wav_path: str
    instruct_text: str
    audio_format: str
    sample_rate: int
    timeout_sec: int
    extra_body_json: str


def _normalize_api_style(raw: str) -> str:
    style = (raw or "").strip().lower()
    if style in {"official_fastapi", "official", "fastapi"}:
        return "official_fastapi"
    if style in {"generic", "generic_json"}:
        return "generic"
    return "official_fastapi"


def _normalize_mode(raw: str) -> str:
    mode = (raw or "").strip().lower()
    allowed = {"sft", "zero_shot", "cross_lingual", "instruct", "instruct2"}
    if mode in allowed:
        return mode
    return "sft"


def load_cosyvoice_config_from_env() -> CosyVoiceConfig:
    """
    Load CosyVoice config from env.

    `official_fastapi` style matches upstream CosyVoice runtime API.
    `generic` style is for custom gateways returning binary/base64/url payloads.
    """
    return CosyVoiceConfig(
        api_url=(os.getenv("COSYVOICE_API_URL") or "").strip(),
        api_key=(os.getenv("COSYVOICE_API_KEY") or "").strip(),
        api_style=_normalize_api_style(os.getenv("COSYVOICE_API_STYLE") or "official_fastapi"),
        mode=_normalize_mode(os.getenv("COSYVOICE_MODE") or "sft"),
        voice=(os.getenv("COSYVOICE_VOICE") or "").strip(),
        model=(os.getenv("COSYVOICE_MODEL") or "").strip(),
        prompt_text=(os.getenv("COSYVOICE_PROMPT_TEXT") or "").strip(),
        prompt_wav_path=(os.getenv("COSYVOICE_PROMPT_WAV_PATH") or "").strip(),
        instruct_text=(os.getenv("COSYVOICE_INSTRUCT_TEXT") or "").strip(),
        audio_format=(os.getenv("COSYVOICE_AUDIO_FORMAT") or "wav").strip().lower(),
        sample_rate=int((os.getenv("COSYVOICE_SAMPLE_RATE") or "22050").strip()),
        timeout_sec=int((os.getenv("COSYVOICE_TIMEOUT_SEC") or "120").strip()),
        extra_body_json=(os.getenv("COSYVOICE_EXTRA_BODY_JSON") or "").strip(),
    )


def is_official_fastapi_style(config: CosyVoiceConfig) -> bool:
    return config.api_style == "official_fastapi"


def _resolve_prompt_wav_path(raw: str, project_dir: Optional[str] = None) -> Path:
    value = (raw or "").strip()
    
    # 优先在具体的 Project 集装箱内进行寻找
    if project_dir:
        input_candidate = Path(project_dir) / "inputs" / value
        if input_candidate.is_file():
            return input_candidate.resolve()
        # 如果使用者配置的是个孤名，还可以直接硬搜 inputs 目录下
        filename_candidate = Path(project_dir) / "inputs" / Path(value).name
        if filename_candidate.is_file():
            return filename_candidate.resolve()

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"COSYVOICE_PROMPT_WAV_PATH not found: {resolved}")
    return resolved


def validate_cosyvoice_config(config: CosyVoiceConfig, project_dir: Optional[str] = None) -> None:
    missing = []
    if not config.api_url:
        missing.append("COSYVOICE_API_URL")

    if is_official_fastapi_style(config):
        if config.mode in {"sft", "instruct"} and not config.voice:
            missing.append("COSYVOICE_VOICE")
        if config.mode == "zero_shot" and not config.prompt_text:
            missing.append("COSYVOICE_PROMPT_TEXT")
        if config.mode in {"zero_shot", "cross_lingual", "instruct2"} and not config.prompt_wav_path:
            missing.append("COSYVOICE_PROMPT_WAV_PATH")
        if config.mode in {"instruct", "instruct2"} and not config.instruct_text:
            missing.append("COSYVOICE_INSTRUCT_TEXT")
    else:
        if not config.voice:
            missing.append("COSYVOICE_VOICE")

    if missing:
        raise ValueError("Missing required CosyVoice env vars: " + ", ".join(missing))

    if is_official_fastapi_style(config) and config.prompt_wav_path:
        _resolve_prompt_wav_path(config.prompt_wav_path, project_dir)


def _parse_extra_body(raw_json: str) -> Dict[str, Any]:
    if not raw_json:
        return {}
    parsed = json.loads(raw_json)
    if not isinstance(parsed, dict):
        raise ValueError("COSYVOICE_EXTRA_BODY_JSON must be a JSON object.")
    return parsed


def _extract_audio_base64(payload: Dict[str, Any]) -> Optional[str]:
    for key in ("audio_base64", "audio"):
        value = payload.get(key)
        if isinstance(value, str):
            return value

    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("audio_base64", "audio"):
            value = data.get(key)
            if isinstance(value, str):
                return value

    result = payload.get("result")
    if isinstance(result, dict):
        for key in ("audio_base64", "audio"):
            value = result.get(key)
            if isinstance(value, str):
                return value

    return None


def _extract_audio_url(payload: Dict[str, Any]) -> Optional[str]:
    for key in ("audio_url", "url"):
        value = payload.get(key)
        if isinstance(value, str):
            return value

    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("audio_url", "url"):
            value = data.get(key)
            if isinstance(value, str):
                return value

    result = payload.get("result")
    if isinstance(result, dict):
        for key in ("audio_url", "url"):
            value = result.get(key)
            if isinstance(value, str):
                return value

    return None


def _build_auth_headers(api_key: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _build_official_fastapi_url(base_url: str, mode: str) -> str:
    trimmed = base_url.rstrip("/")
    if "/inference_" in trimmed:
        return trimmed
    return f"{trimmed}/inference_{mode}"


async def _download_audio(url: str, output_path: Path, timeout_sec: int) -> None:
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            body = await response.read()
            if response.status >= 400:
                raise RuntimeError(
                    f"Failed to download audio from url. status={response.status}, body={body[:300]!r}"
                )
            output_path.write_bytes(body)


def _save_pcm16le_stream_as_wav(raw_pcm: bytes, output_path: Path, sample_rate: int) -> None:
    if not raw_pcm:
        raise RuntimeError("CosyVoice returned empty audio payload.")
    if len(raw_pcm) % 2 != 0:
        raw_pcm = raw_pcm[:-1]
    if not raw_pcm:
        raise RuntimeError("CosyVoice returned invalid PCM payload.")

    import wave

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(raw_pcm)


async def _synthesize_text_cosyvoice_official_fastapi(
    text: str,
    output_path: Path,
    config: CosyVoiceConfig,
    project_dir: Optional[str] = None
) -> None:
    url = _build_official_fastapi_url(config.api_url, config.mode)
    headers = _build_auth_headers(config.api_key)
    timeout = aiohttp.ClientTimeout(total=config.timeout_sec)

    form = aiohttp.FormData()
    form.add_field("tts_text", text)

    if config.mode == "sft":
        form.add_field("spk_id", config.voice)
    elif config.mode == "zero_shot":
        prompt_wav_path = _resolve_prompt_wav_path(config.prompt_wav_path, project_dir)
        content_type = mimetypes.guess_type(str(prompt_wav_path))[0] or "application/octet-stream"
        form.add_field("prompt_text", config.prompt_text)
        form.add_field(
            "prompt_wav",
            prompt_wav_path.read_bytes(),
            filename=prompt_wav_path.name,
            content_type=content_type,
        )
    elif config.mode == "cross_lingual":
        prompt_wav_path = _resolve_prompt_wav_path(config.prompt_wav_path, project_dir)
        content_type = mimetypes.guess_type(str(prompt_wav_path))[0] or "application/octet-stream"
        form.add_field(
            "prompt_wav",
            prompt_wav_path.read_bytes(),
            filename=prompt_wav_path.name,
            content_type=content_type,
        )
    elif config.mode == "instruct":
        form.add_field("spk_id", config.voice)
        form.add_field("instruct_text", config.instruct_text)
    elif config.mode == "instruct2":
        prompt_wav_path = _resolve_prompt_wav_path(config.prompt_wav_path, project_dir)
        content_type = mimetypes.guess_type(str(prompt_wav_path))[0] or "application/octet-stream"
        form.add_field("instruct_text", config.instruct_text)
        form.add_field(
            "prompt_wav",
            prompt_wav_path.read_bytes(),
            filename=prompt_wav_path.name,
            content_type=content_type,
        )

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, data=form, headers=headers) as response:
            body = await response.read()
            if response.status >= 400:
                raise RuntimeError(
                    f"CosyVoice FastAPI failed. status={response.status}, body={body[:500]!r}"
                )

            # Upstream fastapi usually streams raw PCM16LE bytes.
            # If service wrapper returns WAV directly, preserve it.
            if body[:4] == b"RIFF":
                output_path.write_bytes(body)
            else:
                _save_pcm16le_stream_as_wav(body, output_path, config.sample_rate)


async def _synthesize_text_cosyvoice_generic(
    text: str,
    output_path: Path,
    config: CosyVoiceConfig,
) -> None:
    payload_primary: Dict[str, Any] = {
        "text": text,
        "voice": config.voice,
        "format": config.audio_format,
        "sample_rate": config.sample_rate,
    }
    if config.model:
        payload_primary["model"] = config.model

    extra_body = _parse_extra_body(config.extra_body_json)
    payload_primary.update(extra_body)

    payload_openai: Dict[str, Any] = {
        "input": text,
        "voice": config.voice,
        "response_format": config.audio_format,
    }
    if config.model:
        payload_openai["model"] = config.model
    payload_openai.update(extra_body)

    headers = {"Content-Type": "application/json"}
    headers.update(_build_auth_headers(config.api_key))

    timeout = aiohttp.ClientTimeout(total=config.timeout_sec)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        payload_candidates = [payload_primary]
        if payload_openai != payload_primary:
            payload_candidates.append(payload_openai)

        last_error = None
        for payload in payload_candidates:
            async with session.post(config.api_url, json=payload, headers=headers) as response:
                body = await response.read()
                if response.status >= 400:
                    last_error = (
                        f"status={response.status}, body={body[:500]!r}, payload_keys={list(payload.keys())}"
                    )
                    continue

                content_type = (response.headers.get("Content-Type") or "").lower()
                if "application/json" in content_type or body[:1] in (b"{", b"["):
                    data = json.loads(body.decode("utf-8"))

                    audio_base64 = _extract_audio_base64(data)
                    if audio_base64:
                        output_path.write_bytes(base64.b64decode(audio_base64))
                    else:
                        audio_url = _extract_audio_url(data)
                        if not audio_url:
                            raise RuntimeError(
                                "CosyVoice response does not contain audio payload. "
                                "Expected binary audio, or JSON with audio_base64/audio_url."
                            )
                        await _download_audio(audio_url, output_path, config.timeout_sec)
                else:
                    output_path.write_bytes(body)
                break
        else:
            raise RuntimeError(f"CosyVoice API failed after payload retries: {last_error}")


async def synthesize_text_cosyvoice(text: str, output_path: str, config: CosyVoiceConfig, project_dir: Optional[str] = None) -> float:
    """
    Call CosyVoice API and save generated audio.
    """
    validate_cosyvoice_config(config, project_dir)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if is_official_fastapi_style(config):
        await _synthesize_text_cosyvoice_official_fastapi(text=text, output_path=out_path, config=config, project_dir=project_dir)
    else:
        # TODO: Generic API style might also need prompt_wav for some modes, but keeping it simpler for general text endpoints
        await _synthesize_text_cosyvoice_generic(text=text, output_path=out_path, config=config)

    duration = get_audio_duration(str(out_path))
    if duration <= 0:
        raise RuntimeError(f"Generated audio is invalid or duration unreadable: {out_path}")
    return float(duration)


async def synthesize_text_mock(text: str, output_path: str, voice: str = "default") -> float:
    """
    Mock TTS for pipeline testing.
    """
    estimated_duration = len(text) / 4.0
    if estimated_duration < 1.0:
        estimated_duration = 1.0

    import numpy as np

    sample_rate = 22050
    timeline = np.linspace(0, estimated_duration, int(sample_rate * estimated_duration), False)
    audio_data = np.random.normal(0, 0.01, size=timeline.shape)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sf.write(output_path, audio_data, sample_rate)

    return float(estimated_duration)


def get_audio_duration(file_path: str) -> float:
    """
    Get precise duration (seconds) via soundfile, then mutagen fallback.
    """
    try:
        with sf.SoundFile(file_path) as audio_file:
            return float(audio_file.frames / audio_file.samplerate)
    except Exception:
        pass

    try:
        from mutagen import File as MutagenFile

        info = MutagenFile(file_path)
        return float(getattr(getattr(info, "info", None), "length", 0.0))
    except Exception:
        return 0.0


if __name__ == "__main__":
    async def _run_demo() -> None:
        out_file = "c:/docker/Myavatar/workspace/task_test/test_voice.wav"
        test_text = "Welcome to Myavatar pipeline."
        duration = await synthesize_text_mock(test_text, out_file)
        print(f"Mock generated wav: {out_file}, duration_returned: {duration:.2f}s")
        real_duration = get_audio_duration(out_file)
        print(f"Real detected duration: {real_duration:.2f}s")

    asyncio.run(_run_demo())
