# Provider Registry

## Goal
Provider Registry centralizes model vendor routing. It supports:
- provider-level profiles
- model-level capabilities (`text`, `vision`, `reflection`)
- project default routes
- node-level overrides

Storage location:
- `workspace/.myavatar/app.db`

Routing priority:
1. Node override
2. Project defaults
3. First enabled registry model by capability
4. Legacy `.env` fallback (inside `utils/llm_config.py`)

## CLI commands

List data:
```powershell
python src/provider_registry_cli.py list providers
python src/provider_registry_cli.py list models
python src/provider_registry_cli.py list models --capability vision
python src/provider_registry_cli.py list project-routes
python src/provider_registry_cli.py list node-overrides
python src/provider_registry_cli.py list node-overrides --project demo_project
```

Add or update provider:
```powershell
python src/provider_registry_cli.py add-provider `
  --provider-id my_gateway `
  --name "My Gateway" `
  --kind openai_compatible `
  --base-url "https://my-gateway.example.com/v1" `
  --api-key-env MY_GATEWAY_API_KEY
```

Add or update model:
```powershell
python src/provider_registry_cli.py add-model `
  --model-id my_gateway_text_v1 `
  --provider-id my_gateway `
  --model-name gpt-4o-mini `
  --capability text
```

Set project defaults:
```powershell
python src/provider_registry_cli.py set-project-defaults `
  --project my_project `
  --text-model-id my_gateway_text_v1 `
  --vision-model-id my_gateway_vision_v1 `
  --reflection-model-id my_gateway_reflect_v1
```

Set node override:
```powershell
python src/provider_registry_cli.py set-node-override `
  --project my_project `
  --node-name n1c_hybrid_content_writer `
  --model-id my_gateway_vision_v1
```

Supported node names:
- `n1_content_writer`
- `n1c_hybrid_content_writer`
- `n1b_ppt_vision_scriptwriter`
- `crew_reflection`

## Notes
- API key values are never stored in DB; only the env var name is stored.
- Desktop Provider tab writes to the same tables as CLI.
