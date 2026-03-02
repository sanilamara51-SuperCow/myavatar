# Persona Mixing and TTS Pacing

## What changed
- `n4_tts_synthesizer` now supports segment-level persona mixing.
- Script schema supports:
  - `speaker_segments[].persona_id`
  - `speaker_segments[].text`
  - `speaker_segments[].pause_ms`
- When `speaker_segments` is missing, narration falls back to sentence splitting.

## Persona registry
Personas are stored in `workspace/.myavatar/app.db` table `personas`.

CLI examples:
```powershell
python src/persona_registry_cli.py list
python src/persona_registry_cli.py upsert `
  --persona-id host `
  --name "Host" `
  --cosyvoice-mode zero_shot `
  --prompt-wav-path workspace\\voice_ref\\host.wav `
  --prompt-text "你好，欢迎来到频道"
```

Desktop:
- Use `python src/desktop_app.py`
- Open `Personas` tab to edit persona records visually.

## Pacing controls
Environment variables:
- `TTS_ENABLE_PACING=1`
- `TTS_TARGET_CPS_MIN=3.2`
- `TTS_TARGET_CPS_MAX=4.8`
- `TTS_AUTO_SPEEDUP=0`
- `TTS_DEFAULT_PAUSE_MS=260`
- `FFMPEG_BIN=` (optional explicit ffmpeg executable path)

Behavior:
- If CPS is above max, audio is slowed down (`atempo < 1`).
- If `TTS_AUTO_SPEEDUP=1` and CPS is below min, audio is sped up (`atempo > 1`).
- Extreme factors are handled with chained `atempo` filters.
- Segment pauses are inserted with silence clips and merged into slide-level wav.

## Runtime reporting
`n4_tts_synthesizer` returns:
- `audio_segment_report[]` with per-segment pacing metadata:
  - `pacing_applied`
  - `pacing_action`
  - `pacing_factor`
  - `warning`
- `audio_pacing_warnings[]` for deduplicated warnings (for logs/UI)

## Dependency notes
- If ffmpeg is unavailable, synthesis still runs and returns warning messages in pacing report fields.
