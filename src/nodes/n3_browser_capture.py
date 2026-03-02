import os
from pathlib import Path
from typing import Any, Dict, List

from orchestrator.state import VideoGenerationState


def _get_slide_value(slide: Any, key: str) -> Any:
    if isinstance(slide, dict):
        return slide.get(key)
    return getattr(slide, key, None)


def _set_slide_value(slide: Any, key: str, value: Any) -> None:
    if isinstance(slide, dict):
        slide[key] = value
    else:
        setattr(slide, key, value)


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
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


def _prepare_capture_output_dir(state: VideoGenerationState) -> Path:
    run_dir = state.get("run_dir")
    if run_dir:
        out_dir = Path(run_dir) / "captures"
    else:
        project_root = Path(__file__).resolve().parents[2]
        out_dir = project_root / "workspace" / "run_output" / "captures"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir.resolve()


def browser_capture_node(state: VideoGenerationState) -> Dict[str, Any]:
    """
    [Node 3] Browser capture node.

    It scans slides_data for capture_url and captures page/element screenshots.
    For successful captures, image_source is filled with the local screenshot path.
    """
    slides_data = state.get("slides_data", [])
    if not slides_data:
        return {"error_msg": "Missing slides_data for browser capture."}

    default_wait_ms = _as_int(os.getenv("BROWSER_CAPTURE_WAIT_MS"), 1200)
    timeout_ms = _as_int(os.getenv("BROWSER_CAPTURE_TIMEOUT_MS"), 20000)
    max_failures = _as_int(os.getenv("BROWSER_CAPTURE_MAX_FAILURES"), 3)
    default_viewport_width = _as_int(os.getenv("BROWSER_CAPTURE_VIEWPORT_WIDTH"), 1920)
    default_viewport_height = _as_int(os.getenv("BROWSER_CAPTURE_VIEWPORT_HEIGHT"), 1080)

    requested_count = 0
    captured_count = 0
    failed_count = 0
    warnings: List[str] = []

    for slide in slides_data:
        capture_url = _as_str(_get_slide_value(slide, "capture_url"))
        if capture_url:
            requested_count += 1

    if requested_count == 0:
        print("[Node 3: Browser Capture] No capture_url found. Skipping.")
        return {"slides_data": slides_data, "capture_warnings": warnings}

    output_dir = _prepare_capture_output_dir(state)
    print(
        "[Node 3: Browser Capture] "
        f"Requested={requested_count}, timeout_ms={timeout_ms}, output_dir='{output_dir}'"
    )

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        msg = (
            "Playwright is not available. Install with `pip install playwright` and "
            "`playwright install chromium`."
        )
        warnings.append(f"{msg} Raw error: {exc}")
        if requested_count >= max_failures:
            return {"error_msg": msg}
        return {"slides_data": slides_data, "capture_warnings": warnings}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for idx, slide in enumerate(slides_data):
                page_index = idx + 1
                capture_url = _as_str(_get_slide_value(slide, "capture_url"))
                if not capture_url:
                    continue

                if not (capture_url.startswith("http://") or capture_url.startswith("https://")):
                    failed_count += 1
                    warnings.append(
                        f"Slide {page_index}: invalid capture_url '{capture_url}', only http/https is supported."
                    )
                    continue

                capture_selector = _as_str(_get_slide_value(slide, "capture_selector"))
                wait_ms = _as_int(_get_slide_value(slide, "capture_wait_ms"), default_wait_ms)
                full_page = _as_bool(_get_slide_value(slide, "capture_full_page"), True)
                viewport_width = _as_int(
                    _get_slide_value(slide, "capture_viewport_width"),
                    default_viewport_width,
                )
                viewport_height = _as_int(
                    _get_slide_value(slide, "capture_viewport_height"),
                    default_viewport_height,
                )

                screenshot_path = output_dir / f"slide_{page_index:03d}_capture.png"
                context = browser.new_context(
                    viewport={"width": viewport_width, "height": viewport_height}
                )
                page = context.new_page()
                try:
                    page.goto(capture_url, wait_until="networkidle", timeout=timeout_ms)
                    if wait_ms > 0:
                        page.wait_for_timeout(wait_ms)

                    if capture_selector:
                        locator = page.locator(capture_selector).first
                        locator.wait_for(state="visible", timeout=timeout_ms)
                        locator.screenshot(path=str(screenshot_path))
                    else:
                        page.screenshot(path=str(screenshot_path), full_page=full_page)

                    _set_slide_value(slide, "image_source", str(screenshot_path))
                    captured_count += 1
                    print(
                        f"  - Slide {page_index}: captured from '{capture_url}' "
                        f"(selector='{capture_selector or 'page'}')"
                    )
                except Exception as exc:
                    failed_count += 1
                    warnings.append(
                        f"Slide {page_index}: capture failed for '{capture_url}'. Error: {exc}"
                    )
                finally:
                    context.close()
        finally:
            browser.close()

    print(
        "[Node 3: Browser Capture] "
        f"done. captured={captured_count}, failed={failed_count}, requested={requested_count}"
    )

    if failed_count >= max_failures:
        return {
            "error_msg": (
                f"Browser capture failed too many times: {failed_count} "
                f"(max_failures={max_failures})."
            ),
            "capture_warnings": warnings,
            "slides_data": slides_data,
        }

    return {"slides_data": slides_data, "capture_warnings": warnings}
