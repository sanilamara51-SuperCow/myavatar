# Myavatar

Myavatar is a Python-based `video-as-code` pipeline for generating short knowledge videos from structured script + slide + voice workflows.

## Current Capabilities
- Hybrid script generation with optional image understanding.
- Script reflection loop for iterative quality improvement.
- Browser capture node (Playwright) for webpage screenshots in slide flow.
- Slide generation with switchable template profiles.
- TTS with persona mixing (multi-role segments) and pacing control.
- Provider registry for multi-vendor model routing.
- Desktop control panel (PySide6) for projects/provider/persona operations.

## Project Layout
- `src/main.py`: CLI pipeline entrypoint.
- `src/desktop_app.py`: desktop app entrypoint.
- `src/orchestrator/hybrid_graph.py`: main graph (`n1c -> n3 -> n2b -> n4 -> n5`).
- `src/storage/provider_registry.py`: provider/model/routing DB layer.
- `src/storage/persona_registry.py`: persona DB layer.
- `workspace/.myavatar/app.db`: SQLite registry database.
- `docs/`: implementation and feature docs.

## Quick Start

Install:
```powershell
pip install -r requirements.txt
```

Run CLI pipeline:
```powershell
python src/main.py --project demo_project --template-id tech_burst
```

Override content input for one run:
```powershell
python src/main.py `
  --project demo_project `
  --topic "你的自定义选题" `
  --duration-mins 2.0 `
  --target-audience "你的目标受众" `
  --template-id data_focus
```

Run desktop app:
```powershell
python src/desktop_app.py
```

Desktop `Projects` tab writes project inputs to:
- `workspace/projects/<project_name>/inputs/script.txt`
- `workspace/projects/<project_name>/inputs/meta.txt`

`src/main.py` reads these files during pipeline startup.

## Configuration
Copy and edit env:
```powershell
copy .env.example .env
```

Important env groups:
- Reflection: `ENABLE_CREW_REFLECTION`, `SCRIPT_REFLECTION_ENGINE`, `SCRIPT_REFLECTION_FALLBACK_TO_MODEL`, `SCRIPT_REFLECTION_MAX_ROUNDS`, `SCRIPT_REFLECTION_TARGET_SCORE`
- Browser capture: `BROWSER_CAPTURE_*`
- Templates: `PPT_TEMPLATE_ID`
- Persona mixing: `ENABLE_PERSONA_MIX`, `DEFAULT_PERSONA_ID`
- Pacing: `TTS_ENABLE_PACING`, `TTS_TARGET_CPS_MIN`, `TTS_TARGET_CPS_MAX`, `TTS_AUTO_SPEEDUP`, `FFMPEG_BIN`

## Model Provider Routing
Use CLI:
```powershell
python src/provider_registry_cli.py list providers
python src/provider_registry_cli.py list models
python src/provider_registry_cli.py list project-routes
python src/provider_registry_cli.py list node-overrides
```

Set project defaults:
```powershell
python src/provider_registry_cli.py set-project-defaults `
  --project demo_project `
  --text-model-id my_text_model `
  --vision-model-id my_vision_model `
  --reflection-model-id my_reflect_model
```

## Persona Mixing
Use CLI:
```powershell
python src/persona_registry_cli.py list
python src/persona_registry_cli.py upsert --persona-id host --name Host
```

Narration can define per-slide segments:
```json
{
  "speaker_segments": [
    { "persona_id": "host", "text": "Opening line", "pause_ms": 200 },
    { "persona_id": "guest", "text": "Counterpoint", "pause_ms": 300 }
  ]
}
```

## Docs Index
- `docs/implementation_master_plan.md`
- `docs/desktop_quickstart.md`
- `docs/provider_registry.md`
- `docs/persona_mixing_and_pacing.md`
- `docs/template_system.md`
- `docs/script_reflection_workflow.md`
- `docs/browser_capture_workflow.md`
