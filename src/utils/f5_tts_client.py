"""
F5-TTS API Client for voice cloning.

F5-TTS is a state-of-the-art zero-shot TTS model with Flow-based Diffusion + Transformer architecture.
GitHub: https://github.com/SWivid/F5-TTS

Features:
- Zero-shot voice cloning with 3-5 seconds reference audio
- Cross-lingual support (Chinese, English, Japanese, Korean, etc.)
- Natural prosody and emotion
- Fast inference (~2-3x real-time)

Requirements:
- F5-TTS FastAPI server running locally
- Reference audio (wav format, 16kHz or 22050Hz recommended)
"""

import asyncio
import base64
import json
import os
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import numpy as np
import soundfile as sf


@dataclass
class F5TTSConfig:
    """F5-TTS configuration loaded from environment variables."""
    api_url: str = ""
    api_key: str = ""
    model_name: str = "F5-TTS"
    ref_audio_path: str = ""
    ref_text: str = ""
    audio_format: str = "wav"
    sample_rate: int = 22050
    timeout_sec: int = 120
    extra_body_json: str = ""

    # Inference parameters
    gen_text: str = ""
    gen_file: str = ""
    remove_silence: bool = True
    cross_fade_duration: float = 0.15
    speed: float = 1.0


def load_f5tts_config_from_env() -> F5TTSConfig:
    """
    Load F5-TTS config from environment variables.

    Environment variables:
    - F5TTS_API_URL: FastAPI server URL (default: http://127.0.0.1:7865)
    - F5TTS_API_KEY: Optional API key
    - F5TTS_MODEL_NAME: Model name (default: F5-TTS)
    - F5TTS_REF_AUDIO_PATH: Path to reference audio file
    - F5TTS_REF_TEXT: Text content of reference audio
    - F5TTS_SAMPLE_RATE: Output sample rate (default: 22050)
    - F5TTS_TIMEOUT_SEC: Request timeout (default: 120)
    - F5TTS_SPEED: Speech speed multiplier (default: 1.0)
    """
    return F5TTSConfig(
        api_url=(os.getenv("F5TTS_API_URL") or "http://127.0.0.1:7865").strip(),
        api_key=(os.getenv("F5TTS_API_KEY") or "").strip(),
        model_name=(os.getenv("F5TTS_MODEL_NAME") or "F5-TTS").strip(),
        ref_audio_path=(os.getenv("F5TTS_REF_AUDIO_PATH") or "").strip(),
        ref_text=(os.getenv("F5TTS_REF_TEXT") or "").strip(),
        audio_format=(os.getenv("F5TTS_AUDIO_FORMAT") or "wav").strip().lower(),
        sample_rate=int((os.getenv("F5TTS_SAMPLE_RATE") or "22050").strip()),
        timeout_sec=int((os.getenv("F5TTS_TIMEOUT_SEC") or "120").strip()),
        extra_body_json=(os.getenv("F5TTS_EXTRA_BODY_JSON") or "").strip(),
        speed=float((os.getenv("F5TTS_SPEED") or "1.0").strip()),
    )


def validate_f5tts_config(config: F5TTSConfig, project_dir: Optional[str] = None) -> None:
    """
    Validate F5-TTS configuration before use.

    Raises:
        ValueError: If required configuration is missing
        FileNotFoundError: If reference audio file doesn't exist
    """
    missing = []
    if not config.api_url:
        missing.append("F5TTS_API_URL")
    if not config.ref_audio_path:
        missing.append("F5TTS_REF_AUDIO_PATH")
    if not config.ref_text:
        missing.append("F5TTS_REF_TEXT")

    if missing:
        raise ValueError("Missing required F5-TTS env vars: " + ", ".join(missing))

    # Validate reference audio file exists
    ref_path = _resolve_ref_audio_path(config.ref_audio_path, project_dir)
    if not ref_path.is_file():
        raise FileNotFoundError(f"F5-TTS reference audio not found: {ref_path}")


def _resolve_ref_audio_path(raw: str, project_dir: Optional[str] = None) -> Path:
    """
    Resolve reference audio path with project directory support.

    Priority:
    1. Project inputs directory (if project_dir provided)
    2. Absolute path
    3. Relative path from current working directory
    """
    value = (raw or "").strip()

    if project_dir:
        # First try in project inputs directory
        input_candidate = Path(project_dir) / "inputs" / value
        if input_candidate.is_file():
            return input_candidate.resolve()

        # Try if it's already an absolute path
        abs_candidate = Path(value).expanduser()
        if abs_candidate.is_absolute() and abs_candidate.is_file():
            return abs_candidate.resolve()

    # Fallback to absolute/relative path resolution
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"F5-TTS reference audio not found: {resolved}")
    return resolved


def _build_auth_headers(api_key: str) -> Dict[str, str]:
    """Build authorization headers for API request."""
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _prepare_reference_audio(ref_audio_path: str, project_dir: Optional[str] = None) -> Tuple[str, str]:
    """
    Prepare reference audio for API request.

    Returns:
        Tuple of (base64_encoded_audio, audio_format)
    """
    resolved_path = _resolve_ref_audio_path(ref_audio_path, project_dir)

    # Read audio file
    audio_data, sample_rate = sf.read(str(resolved_path), dtype="float32")

    # Convert to mono if stereo
    if audio_data.ndim > 1:
        audio_data = np.mean(audio_data, axis=1)

    # Resample to target sample rate if needed
    target_sr = 22050  # F5-TTS preferred sample rate
    if sample_rate != target_sr:
        from scipy import signal
        audio_data = signal.resample(
            audio_data,
            int(len(audio_data) * target_sr / sample_rate)
        ).astype(np.float32)

    # Encode to base64
    # Convert to int16 for WAV encoding
    audio_int16 = (audio_data * 32767).astype(np.int16)

    # Create WAV in memory
    import io
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(target_sr)
        wav_file.writeframes(audio_int16.tobytes())

    audio_base64 = base64.b64encode(wav_buffer.getvalue()).decode("utf-8")
    return audio_base64, "wav"


async def synthesize_text_f5tts(
    text: str,
    output_path: str,
    config: F5TTSConfig,
    project_dir: Optional[str] = None,
    ref_audio_base64: Optional[str] = None,
) -> float:
    """
    Synthesize speech using F5-TTS API.

    Args:
        text: Text to synthesize
        output_path: Path to save output audio
        config: F5-TTS configuration
        project_dir: Project directory for relative path resolution
        ref_audio_base64: Optional pre-encoded reference audio (for batch optimization)

    Returns:
        Audio duration in seconds

    Raises:
        RuntimeError: If API request fails
    """
    validate_f5tts_config(config, project_dir)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Prepare request payload
    payload: Dict[str, Any] = {
        "gen_text": text,
        "ref_text": config.ref_text,
        "remove_silence": config.remove_silence,
        "cross_fade_duration": config.cross_fade_duration,
        "speed": config.speed,
    }

    # Add extra parameters from JSON
    if config.extra_body_json:
        try:
            extra = json.loads(config.extra_body_json)
            payload.update(extra)
        except json.JSONDecodeError:
            pass

    # Handle reference audio
    if ref_audio_base64:
        payload["ref_audio_base64"] = ref_audio_base64
    else:
        ref_audio_b64, audio_fmt = _prepare_reference_audio(config.ref_audio_path, project_dir)
        payload["ref_audio_base64"] = ref_audio_b64

    # Make API request
    headers = _build_auth_headers(config.api_key)
    timeout = aiohttp.ClientTimeout(total=config.timeout_sec)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            f"{config.api_url}/api/generate",
            json=payload,
            headers=headers
        ) as response:
            body = await response.read()

            if response.status >= 400:
                raise RuntimeError(
                    f"F5-TTS API failed. status={response.status}, body={body[:500]!r}"
                )

            # Check if response is JSON with base64 audio or direct binary audio
            content_type = (response.headers.get("Content-Type") or "").lower()

            if "application/json" in content_type or body[:1] in (b"{", b"["):
                data = json.loads(body.decode("utf-8"))

                # Extract audio from response
                audio_base64 = data.get("audio_base64") or data.get("audio") or data.get("data", {}).get("audio")

                if not audio_base64:
                    raise RuntimeError(
                        "F5-TTS response does not contain audio payload. "
                        f"Response: {data}"
                    )

                # Decode and save
                audio_bytes = base64.b64decode(audio_base64)
                out_path.write_bytes(audio_bytes)
            else:
                # Direct binary audio response
                out_path.write_bytes(body)

    # Get duration
    duration = _get_audio_duration(str(out_path))
    if duration <= 0:
        raise RuntimeError(f"Generated audio is invalid or duration unreadable: {out_path}")

    return float(duration)


async def synthesize_batch_f5tts(
    texts: List[str],
    output_dir: str,
    config: F5TTSConfig,
    project_dir: Optional[str] = None,
) -> List[float]:
    """
    Synthesize multiple audio files using F5-TTS with optimized single reference audio encoding.

    Args:
        texts: List of texts to synthesize
        output_dir: Directory to save output audio files
        config: F5-TTS configuration
        project_dir: Project directory for relative path resolution

    Returns:
        List of audio durations in seconds
    """
    import os
    os.makedirs(output_dir, exist_ok=True)

    # Encode reference audio once for all requests
    ref_audio_b64, _ = _prepare_reference_audio(config.ref_audio_path, project_dir)

    durations = []
    for i, text in enumerate(texts):
        output_path = Path(output_dir) / f"f5tts_{i:03d}.wav"
        duration = await synthesize_text_f5tts(
            text=text,
            output_path=str(output_path),
            config=config,
            project_dir=project_dir,
            ref_audio_base64=ref_audio_b64,
        )
        durations.append(duration)
        print(f"  F5-TTS [{i+1}/{len(texts)}]: {text[:50]}... duration={duration:.2f}s")

    return durations


def _get_audio_duration(file_path: str) -> float:
    """Get precise audio duration using soundfile with mutagen fallback."""
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


async def test_f5tts_connection(config: F5TTSConfig) -> bool:
    """
    Test connection to F5-TTS API server.

    Returns:
        True if connection successful, False otherwise
    """
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{config.api_url}/health") as response:
                return response.status == 200
    except Exception:
        return False


if __name__ == "__main__":
    async def _run_demo() -> None:
        """Demo F5-TTS synthesis."""
        config = load_f5tts_config_from_env()

        if not config.api_url:
            print("F5TTS_API_URL not set, using default: http://127.0.0.1:7865")
            config.api_url = "http://127.0.0.1:7865"

        # Test connection
        connected = await test_f5tts_connection(config)
        if not connected:
            print("F5-TTS server not reachable. Please start the server first.")
            return

        # Demo synthesis
        test_text = "Welcome to F5-TTS synthesis test."
        out_file = "test_f5tts_output.wav"

        try:
            duration = await synthesize_text_f5tts(
                text=test_text,
                output_path=out_file,
                config=config,
            )
            print(f"F5-TTS generated: {out_file}, duration: {duration:.2f}s")
        except Exception as e:
            print(f"F5-TTS synthesis failed: {e}")

    asyncio.run(_run_demo())
