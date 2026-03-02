# Template System

## Available templates
- `tech_burst`
- `data_focus`
- `tutorial_clean`

## How to set template
Use CLI:

```powershell
python src/main.py --project my_first_demo --template-id tech_burst
```

Or set default in `.env`:

```env
PPT_TEMPLATE_ID=tech_burst
```

## Behavior
- `n2_slide_generator` and `n2b_hybrid_slide_generator` now read template from state/env.
- If template id is unknown, system falls back to `tech_burst`.
- Template affects Marp frontmatter style, typography, and color tokens.

