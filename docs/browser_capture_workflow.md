# Browser Capture Workflow

## What it does
- `n3_browser_capture` scans `slides_data` for `capture_url`.
- If present, it opens the page with Playwright and captures a screenshot.
- Captured image path is written back to the slide as `image_source`.
- Downstream `n2b_hybrid_slide_generator` uses that screenshot directly.

## Slide fields
Each slide can include:
- `capture_url`
- `capture_selector` (optional CSS selector)
- `capture_wait_ms` (optional extra wait before screenshot)
- `capture_full_page` (optional, default `true`)
- `capture_viewport_width` (optional, default `1920`)
- `capture_viewport_height` (optional, default `1080`)

## Runtime env
- `BROWSER_CAPTURE_WAIT_MS=1200`
- `BROWSER_CAPTURE_TIMEOUT_MS=20000`
- `BROWSER_CAPTURE_MAX_FAILURES=3`
- `BROWSER_CAPTURE_VIEWPORT_WIDTH=1920`
- `BROWSER_CAPTURE_VIEWPORT_HEIGHT=1080`

## Dependencies
Install:
```powershell
pip install playwright
playwright install chromium
```

## Failure behavior
- No `capture_url` on all slides: node skips.
- Single slide capture failure: warning is recorded, pipeline continues.
- Failures reaching `BROWSER_CAPTURE_MAX_FAILURES`: node returns `error_msg` and pipeline stops.

