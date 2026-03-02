import asyncio
import os
import re
import shutil
import subprocess
import wave
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import soundfile as sf

from orchestrator.state import VideoGenerationState
from storage.persona_registry import get_persona, init_persona_registry
from utils.tts_client import (
    get_audio_duration,
    load_cosyvoice_config_from_env,
    synthesize_text_cosyvoice,
    synthesize_text_mock,
    validate_cosyvoice_config,
)
from utils.f5_tts_client import (
    load_f5tts_config_from_env,
    synthesize_text_f5tts,
    validate_f5tts_config,
)

SUPPORTED_AUDIO_EXTENSIONS = [".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"]
_FFMPEG_PROBED = False
_FFMPEG_BIN: Optional[str] = None


def _read_audio_source_mode() -> str:
    """Read audio source mode from env. Supported: mock | cosyvoice | f5tts | local_voice."""
    mode = (os.getenv("AUDIO_SOURCE_MODE") or "mock").strip().lower()
    if mode not in {"mock", "cosyvoice", "f5tts", "local_voice"}:
        return "mock"
    return mode


def _resolve_voice_input_dir(state: Optional[VideoGenerationState] = None) -> Path:
    """Resolve local voice input directory."""
    if state and state.get("project_dir"):
        project_inputs = Path(state["project_dir"]) / "inputs"
        voice_subdir = project_inputs / "voice_input"
        if voice_subdir.is_dir():
            return voice_subdir.resolve()
        project_inputs.mkdir(parents=True, exist_ok=True)
        return project_inputs.resolve()

    raw = (os.getenv("VOICE_INPUT_DIR") or "workspace/voice_input").strip()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _find_named_voice_file(input_dir: Path, index: int) -> Optional[Path]:
    stem = f"voice_{index:03d}"
    for ext in SUPPORTED_AUDIO_EXTENSIONS:
        candidate = input_dir / f"{stem}{ext}"
        if candidate.is_file():
            return candidate.resolve()
    return None


def _list_supported_audio_files(input_dir: Path) -> List[Path]:
    files: List[Path] = []
    for file in input_dir.glob("*"):
        if file.is_file() and file.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
            files.append(file.resolve())
    files.sort()
    return files


def _resolve_local_voice_files(slide_count: int, state: Optional[VideoGenerationState] = None) -> List[Path]:
    input_dir = _resolve_voice_input_dir(state)
    if not input_dir.is_dir():
        raise FileNotFoundError(
            f"Voice input directory does not exist: {input_dir}. "
            "Create it and put your recordings there."
        )

    strict_files: List[Optional[Path]] = [_find_named_voice_file(input_dir, i) for i in range(slide_count)]

    if all(path is not None for path in strict_files):
        return [path for path in strict_files if path is not None]

    if any(path is not None for path in strict_files):
        missing = [i for i, path in enumerate(strict_files) if path is None]
        missing_names = ", ".join([f"voice_{i:03d}" for i in missing])
        raise FileNotFoundError(
            "Partial strict naming detected in VOICE_INPUT_DIR. "
            f"Missing files for slide indexes: {missing_names}. "
            "Provide complete voice_000..voice_N set, or remove strict names and rely on sorted fallback."
        )

    fallback_files = _list_supported_audio_files(input_dir)
    if len(fallback_files) != slide_count:
        raise FileNotFoundError(
            "Local voice file count does not match slide count. "
            f"slides={slide_count}, audio_files={len(fallback_files)}, dir={input_dir}. "
            "Either rename files to voice_000/voice_001/... or provide exactly one audio per slide."
        )

    return fallback_files


def _detect_audio_duration_seconds(audio_file: Path) -> float:
    duration = get_audio_duration(str(audio_file))
    if duration > 0:
        return float(duration)
    raise ValueError(f"Unable to read audio duration for file: {audio_file}")


def _prepare_output_audio_dir(state: VideoGenerationState) -> Path:
    run_dir = state.get("run_dir")
    if run_dir:
        output_dir = Path(run_dir) / "audio"
    else:
        project_root = Path(__file__).resolve().parents[2]
        output_dir = project_root / "workspace" / "run_output" / "audio"
        if output_dir.exists():
            shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir.resolve()


def _get_slide_value(slide: Any, key: str) -> Any:
    if isinstance(slide, dict):
        return slide.get(key)
    return getattr(slide, key, None)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _split_voiceover(text: str) -> List[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    pieces = re.split(r"(?<=[。！？!?；;])\s*", raw)
    segments = [p.strip() for p in pieces if p and p.strip()]
    if segments:
        return segments
    return [raw]


def _extract_segments(slide: Any) -> List[Dict[str, Any]]:
    enable_mix = _as_bool(os.getenv("ENABLE_PERSONA_MIX"), True)
    default_persona = (os.getenv("DEFAULT_PERSONA_ID") or "host").strip() or "host"
    default_pause_ms = _as_int(os.getenv("TTS_DEFAULT_PAUSE_MS"), 260)

    if enable_mix:
        raw_segments = _get_slide_value(slide, "speaker_segments")
        if raw_segments:
            parsed: List[Dict[str, Any]] = []
            for item in raw_segments:
                if isinstance(item, dict):
                    persona_id = str(item.get("persona_id") or default_persona).strip() or default_persona
                    text = str(item.get("text") or "").strip()
                    pause_ms = _as_int(item.get("pause_ms"), default_pause_ms)
                else:
                    persona_id = str(getattr(item, "persona_id", default_persona) or default_persona).strip() or default_persona
                    text = str(getattr(item, "text", "") or "").strip()
                    pause_ms = _as_int(getattr(item, "pause_ms", None), default_pause_ms)

                if text:
                    parsed.append(
                        {
                            "persona_id": persona_id,
                            "text": text,
                            "pause_ms": max(0, pause_ms),
                        }
                    )
            if parsed:
                return parsed

    voiceover = str(_get_slide_value(slide, "voiceover") or "").strip()
    if not voiceover:
        voiceover = "This is a silent transition slide."
    return [
        {"persona_id": default_persona, "text": chunk, "pause_ms": default_pause_ms}
        for chunk in _split_voiceover(voiceover)
    ]


def _strip_for_cps(text: str) -> str:
    normalized = re.sub(r"\s+", "", text or "")
    normalized = re.sub(r"[，。！？；、,.!?;:：'\"“”‘’（）()【】\[\]<>《》\-_/]", "", normalized)
    return normalized


def _build_atempo_chain(factor: float) -> str:
    # ffmpeg atempo supports 0.5-2.0 per stage; chain if outside.
    if factor <= 0:
        return "atempo=1.0"

    remaining = max(0.1, min(8.0, float(factor)))
    stages: List[float] = []
    while remaining < 0.5:
        stages.append(0.5)
        remaining /= 0.5
    while remaining > 2.0:
        stages.append(2.0)
        remaining /= 2.0
    stages.append(remaining)
    return ",".join([f"atempo={max(0.5, min(2.0, s)):.6f}" for s in stages])


def _resolve_ffmpeg_bin() -> Optional[str]:
    global _FFMPEG_PROBED, _FFMPEG_BIN
    if _FFMPEG_PROBED:
        return _FFMPEG_BIN

    configured = (os.getenv("FFMPEG_BIN") or "").strip()
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.is_file():
            _FFMPEG_BIN = str(configured_path.resolve())
        else:
            _FFMPEG_BIN = None
    else:
        _FFMPEG_BIN = shutil.which("ffmpeg")

    _FFMPEG_PROBED = True
    return _FFMPEG_BIN


def _apply_atempo(input_path: Path, output_path: Path, factor: float, ffmpeg_bin: str) -> bool:
    filter_chain = _build_atempo_chain(factor)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-filter:a",
        filter_chain,
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except Exception:
        return False


def _apply_pacing_if_needed(audio_path: Path, text: str) -> Dict[str, Any]:
    base_result: Dict[str, Any] = {
        "audio_path": audio_path,
        "pacing_applied": False,
        "pacing_factor": 1.0,
        "pacing_action": "skipped",
        "warning": None,
    }

    if not _as_bool(os.getenv("TTS_ENABLE_PACING"), True):
        base_result["pacing_action"] = "disabled"
        return base_result

    min_cps = _as_float(os.getenv("TTS_TARGET_CPS_MIN"), 3.2)
    max_cps = _as_float(os.getenv("TTS_TARGET_CPS_MAX"), 4.8)
    allow_speedup = _as_bool(os.getenv("TTS_AUTO_SPEEDUP"), False)

    duration = get_audio_duration(str(audio_path))
    if duration <= 0:
        base_result["pacing_action"] = "invalid_duration"
        base_result["warning"] = f"Pacing skipped for '{audio_path.name}': invalid source duration."
        return base_result

    text_len = max(1, len(_strip_for_cps(text)))
    cps = text_len / max(duration, 1e-3)
    base_result["cps_before"] = float(cps)
    base_result["duration_before"] = float(duration)
    target_factor: Optional[float] = None

    if cps > max_cps:
        target_factor = max_cps / cps
        base_result["pacing_action"] = "slow_down"
    elif allow_speedup and cps < min_cps:
        target_factor = min_cps / cps
        base_result["pacing_action"] = "speed_up"
    else:
        base_result["pacing_action"] = "within_target"

    if target_factor is None or abs(target_factor - 1.0) < 0.03:
        return base_result

    ffmpeg_bin = _resolve_ffmpeg_bin()
    if not ffmpeg_bin:
        base_result["warning"] = (
            "Pacing skipped because ffmpeg was not found. "
            "Install ffmpeg or set FFMPEG_BIN to the executable path."
        )
        base_result["pacing_action"] = "ffmpeg_missing"
        return base_result

    target_factor = max(0.1, min(8.0, target_factor))
    base_result["pacing_factor"] = float(target_factor)

    adjusted_path = audio_path.with_name(f"{audio_path.stem}_paced{audio_path.suffix}")
    ok = _apply_atempo(audio_path, adjusted_path, target_factor, ffmpeg_bin=ffmpeg_bin)
    if not ok or not adjusted_path.exists():
        base_result["warning"] = f"Pacing failed for '{audio_path.name}' (factor={target_factor:.3f})."
        base_result["pacing_action"] = "ffmpeg_failed"
        return base_result

    try:
        audio_path.unlink(missing_ok=True)
    except Exception:
        pass
    paced_duration = get_audio_duration(str(adjusted_path))
    if paced_duration > 0:
        base_result["duration_after"] = float(paced_duration)
        base_result["cps_after"] = float(text_len / max(paced_duration, 1e-3))
    base_result["audio_path"] = adjusted_path
    base_result["pacing_applied"] = True
    return base_result


def _create_silence_wav(output_path: Path, duration_ms: int, sample_rate: int) -> None:
    duration_ms = max(0, duration_ms)
    n_frames = int(sample_rate * duration_ms / 1000.0)
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # pcm16
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)


def _concat_wavs(paths: List[Path], output_path: Path) -> None:
    if not paths:
        raise ValueError("No wav paths to concat.")
    chunks: List[np.ndarray] = []
    sample_rate: Optional[int] = None

    for path in paths:
        data, sr = sf.read(str(path), dtype="float32")
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        if sample_rate is None:
            sample_rate = int(sr)
        elif int(sr) != sample_rate:
            raise ValueError(f"Sample rate mismatch during concat: {path} has {sr}, expected {sample_rate}")
        chunks.append(data.astype(np.float32))

    merged = np.concatenate(chunks, axis=0) if chunks else np.zeros((1,), dtype=np.float32)
    sf.write(str(output_path), merged, sample_rate or 22050)


def _persona_for_id(persona_id: str) -> Optional[Dict[str, Any]]:
    init_persona_registry()
    persona = get_persona(persona_id)
    if persona and int(persona.get("enabled", 1)) == 1:
        return persona
    if persona_id != "host":
        fallback = get_persona("host")
        if fallback and int(fallback.get("enabled", 1)) == 1:
            return fallback
    return persona


def _build_persona_cosyvoice_config(base_config: Any, persona: Optional[Dict[str, Any]]) -> Any:
    if not persona:
        return base_config

    return replace(
        base_config,
        mode=str(persona.get("cosyvoice_mode") or base_config.mode).strip(),
        voice=str(persona.get("voice") or base_config.voice).strip(),
        prompt_text=str(persona.get("prompt_text") or base_config.prompt_text).strip(),
        prompt_wav_path=str(persona.get("prompt_wav_path") or base_config.prompt_wav_path).strip(),
        instruct_text=str(persona.get("instruct_text") or base_config.instruct_text).strip(),
        audio_format=str(persona.get("audio_format") or "wav").strip().lower(),
        sample_rate=int(persona.get("sample_rate") or base_config.sample_rate),
    )


def _generate_persona_voiceovers(
    slides_data: List[Any],
    output_dir: Path,
    mode: str,
    state: Optional[VideoGenerationState] = None,
) -> Dict[str, Any]:
    project_dir = state.get("project_dir") if state else None

    # Load config based on mode
    base_cosy_config = None
    base_f5tts_config = None
    if mode == "cosyvoice":
        base_cosy_config = load_cosyvoice_config_from_env()
        validate_cosyvoice_config(base_cosy_config, project_dir)
    elif mode == "f5tts":
        base_f5tts_config = load_f5tts_config_from_env()
        validate_f5tts_config(base_f5tts_config, project_dir)

    audio_paths: List[str] = []
    audio_durations: List[float] = []
    segment_report: List[Dict[str, Any]] = []
    pacing_warnings: List[str] = []

    for i, slide in enumerate(slides_data):
        segments = _extract_segments(slide)
        temp_files: List[Path] = []

        for j, segment in enumerate(segments):
            persona_id = str(segment.get("persona_id") or "host").strip() or "host"
            text = str(segment.get("text") or "").strip()
            if not text:
                continue

            segment_file = output_dir / f"voice_{i:03d}_seg_{j:03d}.wav"
            if mode == "cosyvoice":
                persona = _persona_for_id(persona_id)
                persona_config = _build_persona_cosyvoice_config(base_cosy_config, persona)
                # Keep wav output for deterministic concatenation.
                persona_config = replace(persona_config, audio_format="wav")
                duration = asyncio.run(
                    synthesize_text_cosyvoice(
                        text=text,
                        output_path=str(segment_file),
                        config=persona_config,
                        project_dir=project_dir,
                    )
                )
                used_mode = persona_config.mode
            elif mode == "f5tts":
                # F5-TTS uses single reference audio for all segments
                duration = asyncio.run(
                    synthesize_text_f5tts(
                        text=text,
                        output_path=str(segment_file),
                        config=base_f5tts_config,
                        project_dir=project_dir,
                    )
                )
                used_mode = "f5tts"
            else:
                duration = asyncio.run(synthesize_text_mock(text, str(segment_file)))
                used_mode = "mock"

            pacing_result = _apply_pacing_if_needed(segment_file, text)
            paced_file = pacing_result["audio_path"]
            paced_duration = get_audio_duration(str(paced_file)) or duration
            text_len = max(1, len(_strip_for_cps(text)))
            cps = text_len / max(paced_duration, 1e-3)
            temp_files.append(paced_file)
            warning_text = pacing_result.get("warning")
            if warning_text:
                pacing_warnings.append(str(warning_text))

            pause_ms = _as_int(segment.get("pause_ms"), 0)
            if pause_ms > 0 and j < len(segments) - 1:
                silence_file = output_dir / f"voice_{i:03d}_silence_{j:03d}.wav"
                # Determine sample rate based on mode
                if mode == "f5tts" and base_f5tts_config is not None:
                    sr = int(base_f5tts_config.sample_rate)
                elif base_cosy_config is not None:
                    sr = int(base_cosy_config.sample_rate)
                else:
                    sr = 22050
                _create_silence_wav(silence_file, pause_ms, sr)
                temp_files.append(silence_file)

            segment_report.append(
                {
                    "slide_index": i,
                    "segment_index": j,
                    "persona_id": persona_id,
                    "mode": used_mode,
                    "duration": float(paced_duration),
                    "cps": float(cps),
                    "pacing_applied": bool(pacing_result.get("pacing_applied")),
                    "pacing_action": pacing_result.get("pacing_action"),
                    "pacing_factor": float(pacing_result.get("pacing_factor") or 1.0),
                    "warning": warning_text,
                }
            )
            print(
                f"  - Slide {i + 1} Segment {j + 1}: persona='{persona_id}', "
                f"duration={paced_duration:.2f}s, cps={cps:.2f}"
            )

        if not temp_files:
            # Ensure every slide has an audio artifact.
            fallback = output_dir / f"voice_{i:03d}.wav"
            asyncio.run(synthesize_text_mock("silent", str(fallback)))
            final_duration = get_audio_duration(str(fallback))
            audio_paths.append(str(fallback))
            audio_durations.append(float(final_duration))
            continue

        final_file = output_dir / f"voice_{i:03d}.wav"
        _concat_wavs(temp_files, final_file)
        final_duration = get_audio_duration(str(final_file))

        for path in temp_files:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

        audio_paths.append(str(final_file))
        audio_durations.append(float(final_duration))

    return {
        "audio_paths": audio_paths,
        "audio_durations": audio_durations,
        "audio_segment_report": segment_report,
        "audio_pacing_warnings": sorted(set(pacing_warnings)),
    }


def _load_local_voiceovers(
    slides_data: List[Any],
    output_dir: Path,
    state: Optional[VideoGenerationState] = None,
) -> Dict[str, Any]:
    local_files = _resolve_local_voice_files(len(slides_data), state)

    audio_paths: List[str] = []
    audio_durations: List[float] = []

    for i, source_file in enumerate(local_files):
        ext = source_file.suffix.lower() or ".wav"
        target_file = output_dir / f"voice_{i:03d}{ext}"
        shutil.copy2(source_file, target_file)

        duration = _detect_audio_duration_seconds(target_file)
        print(
            f"Using local voice {i + 1}/{len(local_files)}: "
            f"{source_file.name} ({duration:.2f}s)"
        )

        audio_paths.append(str(target_file))
        audio_durations.append(float(duration))

    return {"audio_paths": audio_paths, "audio_durations": audio_durations}


def tts_synthesizer_node(state: VideoGenerationState) -> Dict[str, Any]:
    """
    [Node 4] Voiceover node.

    Modes:
    - mock: synthesize placeholder audio from text
    - cosyvoice: full-auto TTS from slide voiceover text
    - local_voice: load user-recorded files from VOICE_INPUT_DIR
    """
    slides_data = state.get("slides_data", [])
    if not slides_data:
        return {"error_msg": "Missing slides_data for audio generation."}

    mode = _read_audio_source_mode()
    print(
        f"[Node 4: TTS Synthesizer] Start processing {len(slides_data)} slides "
        f"with mode='{mode}'..."
    )

    try:
        output_dir = _prepare_output_audio_dir(state)
        if mode == "local_voice":
            result = _load_local_voiceovers(slides_data, output_dir, state)
        elif mode == "cosyvoice":
            result = _generate_persona_voiceovers(slides_data, output_dir, mode="cosyvoice", state=state)
        else:
            result = _generate_persona_voiceovers(slides_data, output_dir, mode="mock", state=state)

        print(
            "[Node 4: TTS Synthesizer] Audio ready. "
            f"segments={len(result['audio_paths'])}"
        )
        return result
    except Exception as exc:
        error_msg = f"Audio generation failed: {exc}"
        print(f"[Node 4 ERROR] {error_msg}")
        return {"error_msg": error_msg}
