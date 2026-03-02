# Script Reflection Workflow

## What it does
- `n1c_hybrid_content_writer` runs a reflection loop after initial draft.
- Reflection now supports two engines:
  - `crewai` (preferred): multi-agent reviewer/rewriter flow.
  - `model`: legacy direct review/rewrite loop.
- Both engines use Provider Registry route `crew_reflection`.

## Env controls
- `ENABLE_CREW_REFLECTION=1`
- `SCRIPT_REFLECTION_ENGINE=crewai`
- `SCRIPT_REFLECTION_FALLBACK_TO_MODEL=1`
- `SCRIPT_REFLECTION_MAX_ROUNDS=3`
- `SCRIPT_REFLECTION_TARGET_SCORE=85`
- `CREWAI_REFLECTION_VERBOSE=0`
- `CREWAI_DISABLE_TELEMETRY=true`
- `CREWAI_TRACING_ENABLED=false`
- `OTEL_SDK_DISABLED=true`

If CrewAI is unavailable or fails and fallback is enabled, the system automatically switches to the `model` engine.

## Routing
Reflection model uses Provider Registry:
- capability: `reflection`
- node: `crew_reflection`

Set project default reflection model:
```powershell
python src/provider_registry_cli.py set-project-defaults `
  --project my_first_demo `
  --reflection-model-id <reflection_model_id>
```

Set node override:
```powershell
python src/provider_registry_cli.py set-node-override `
  --project my_first_demo `
  --node-name crew_reflection `
  --model-id <reflection_model_id>
```

## Output
`n1c` returns:
- `slides_data` (possibly refined)
- `script_reflection_report`, including:
  - `engine_requested`
  - `engine_used`
  - `fallback_used`
  - `rounds`
  - `error`
