# Desktop Quickstart

## Install dependencies
```powershell
pip install -r requirements.txt
```

## Start desktop app
```powershell
python src/desktop_app.py
```

## Tabs
- `Overview`: current scope and roadmap summary.
- `Projects`: manage project assets, script/meta inputs, and run pipeline with live logs.
- `Providers`: manage provider profiles, model specs, project defaults, and per-node overrides.
- `Personas`: manage role-based voice presets for multi-speaker narration.

## Projects tab capabilities
- Create projects under `workspace/projects/<project_name>/`.
- Import image assets into `inputs/`.
- Edit and save:
  - `inputs/script.txt` (topic/script body)
  - `inputs/meta.txt` (`duration_mins`, `target_audience`, `template_id`)
- Start/stop pipeline and view live node logs/progress.
- Review run history under `runs/`.

## Provider tab capabilities
- View current provider/model registry tables.
- Upsert a provider profile.
- Upsert a model spec.
- Set project-level default text/vision/reflection routes.
- Set per-node model overrides (for example `n1c_hybrid_content_writer`).

## Persona tab capabilities
- View all personas from `workspace/.myavatar/app.db`.
- Upsert persona metadata:
  - `cosyvoice_mode`
  - `voice`
  - `prompt_wav_path`
  - `prompt_text`
  - `instruct_text`
  - `audio_format`
  - `sample_rate`
  - `base_speed`
  - `default_pause_ms`
  - `enabled`

## Notes
- GUI startup initializes provider/persona registries automatically.
- Registry database path: `workspace/.myavatar/app.db`.
- Desktop app and CLI (`provider_registry_cli.py`, `persona_registry_cli.py`) are fully interoperable.
- `src/main.py` now reads `inputs/script.txt` and `inputs/meta.txt` for project-level pipeline input.
