import os
from typing import Dict, List, Tuple

from orchestrator.state import VideoGenerationState


_THEMES: Dict[str, Dict[str, str]] = {
    "tech_burst": {
        "name": "Tech Burst",
        "style": "\n".join(
            [
                "section {",
                "  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;",
                "  background: linear-gradient(135deg, #0b1220 0%, #16263a 100%);",
                "  color: #e8f1ff;",
                "  padding: 56px 72px;",
                "}",
                "h1 {",
                "  color: #5eead4;",
                "  font-size: 54px;",
                "  letter-spacing: 0.5px;",
                "  margin-bottom: 22px;",
                "}",
                "ul { margin-top: 14px; }",
                "li {",
                "  font-size: 30px;",
                "  line-height: 1.45;",
                "  margin-bottom: 14px;",
                "}",
                "strong { color: #a7f3d0; }",
            ]
        ),
    },
    "data_focus": {
        "name": "Data Focus",
        "style": "\n".join(
            [
                "section {",
                "  font-family: 'Aptos', 'Segoe UI', 'Microsoft YaHei', sans-serif;",
                "  background: linear-gradient(180deg, #f7fafc 0%, #ecf4f7 100%);",
                "  color: #0f172a;",
                "  padding: 56px 72px;",
                "}",
                "h1 {",
                "  color: #0f766e;",
                "  font-size: 52px;",
                "  margin-bottom: 20px;",
                "}",
                "li {",
                "  font-size: 29px;",
                "  line-height: 1.48;",
                "  margin-bottom: 12px;",
                "}",
                "code {",
                "  background: rgba(15, 118, 110, 0.12);",
                "  color: #115e59;",
                "  padding: 2px 6px;",
                "  border-radius: 6px;",
                "}",
            ]
        ),
    },
    "tutorial_clean": {
        "name": "Tutorial Clean",
        "style": "\n".join(
            [
                "section {",
                "  font-family: 'Source Han Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;",
                "  background: linear-gradient(160deg, #ffffff 0%, #f1f5f9 100%);",
                "  color: #0b1220;",
                "  padding: 56px 72px;",
                "}",
                "h1 {",
                "  color: #1d4ed8;",
                "  font-size: 52px;",
                "  margin-bottom: 18px;",
                "}",
                "li {",
                "  font-size: 30px;",
                "  line-height: 1.5;",
                "  margin-bottom: 12px;",
                "}",
                "blockquote {",
                "  border-left: 5px solid #1d4ed8;",
                "  padding-left: 12px;",
                "}",
            ]
        ),
    },
}

_DEFAULT_THEME_ID = "tech_burst"


def list_template_ids() -> List[str]:
    return sorted(_THEMES.keys())


def resolve_template_id(state: VideoGenerationState) -> str:
    requested = (state.get("template_id") or os.getenv("PPT_TEMPLATE_ID") or _DEFAULT_THEME_ID).strip()
    if requested in _THEMES:
        return requested
    return _DEFAULT_THEME_ID


def resolve_template_profile(state: VideoGenerationState) -> Tuple[str, Dict[str, str]]:
    template_id = resolve_template_id(state)
    return template_id, _THEMES[template_id]


def build_marp_frontmatter(state: VideoGenerationState, paginate: bool) -> List[str]:
    template_id, profile = resolve_template_profile(state)
    style_lines = profile["style"].splitlines()
    frontmatter = [
        "---",
        "marp: true",
        "theme: default",
        "size: 16:9",
        f"# template_id: {template_id}",
    ]
    if paginate:
        frontmatter.append("paginate: true")
    frontmatter.append("style: |")
    frontmatter.extend([f"  {line}" for line in style_lines])
    frontmatter.extend(["---", ""])
    return frontmatter

