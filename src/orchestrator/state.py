from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class SpeakerSegment(BaseModel):
    """Segment-level speaker plan used for persona mixing."""

    persona_id: str = Field(
        default="host", description="Persona id to synthesize this segment."
    )
    text: str = Field(description="Narration segment text.")
    pause_ms: Optional[int] = Field(
        default=None,
        description="Optional pause duration after this segment in milliseconds.",
    )


class SlideContent(BaseModel):
    """Structured content for a single slide."""

    page_number: int = Field(description="Slide index, starting from 1.")
    title: str = Field(description="Slide title.")
    content_points: List[str] = Field(
        description="2-4 bullet points shown on the slide."
    )
    voiceover: str = Field(description="Narration text for this slide.")
    image_source: Optional[str] = Field(
        default=None,
        description="Path or URL to the specific user-provided image to use for this slide. If null, the system will generate a markdown slide.",
    )
    layout: Optional[str] = Field(
        default="text_only",
        description="Layout mode for this slide: 'text_only' (no image), 'image_right' (text left, image right), 'image_left' (image left, text right), 'image_bottom' (text top, image bottom), 'image_full' (image fullscreen, no text).",
    )
    capture_url: Optional[str] = Field(
        default=None,
        description="Optional webpage URL to capture as screenshot for this slide.",
    )
    capture_selector: Optional[str] = Field(
        default=None,
        description="Optional CSS selector. If present, capture only this element.",
    )
    capture_wait_ms: Optional[int] = Field(
        default=None,
        description="Optional extra wait time in milliseconds before taking screenshot.",
    )
    capture_full_page: Optional[bool] = Field(
        default=None,
        description="When capturing page-level screenshot, whether to capture full page.",
    )
    capture_viewport_width: Optional[int] = Field(
        default=None, description="Optional viewport width for browser capture."
    )
    capture_viewport_height: Optional[int] = Field(
        default=None, description="Optional viewport height for browser capture."
    )
    speaker_segments: Optional[List[SpeakerSegment]] = Field(
        default=None,
        description="Optional segment-level persona plan for role mixing.",
    )


class VideoGenerationState(TypedDict, total=False):
    """Shared workflow state for the LangGraph pipeline."""

    # Workflow Metadata
    project_name: str
    project_dir: str
    run_id: str
    run_dir: str

    # Input
    topic: str
    duration_mins: float
    target_audience: str
    template_id: str
    reference_image_path: str
    reference_image_url: str
    ppt_image_paths: List[str]
    script_image_markers: List[str]

    # Video Input (Douyin share URL flow)
    douyin_share_url: str
    video_path: str
    video_metadata: Dict[str, Any]  # {title, author, duration_sec, share_url, file_size_bytes}

    # Node 0a output (Keyframe extraction)
    keyframe_paths: List[str]
    keyframe_timestamps: List[float]
    scene_boundaries: List[Dict[str, Any]]

    # Node 0b output (Video understanding)
    video_understanding: Optional[Dict[str, Any]]

    # Node 1 output
    slides_data: List[SlideContent]
    script_reflection_report: Dict[str, Any]
    script_image_alignment_report: Dict[str, Any]

    # Node 3 output
    capture_warnings: List[str]

    # Node 2 output
    markdown_content: str
    image_paths: List[str]

    # Node 4 output
    audio_paths: List[str]
    audio_durations: List[float]
    audio_segment_report: List[Dict[str, Any]]
    audio_pacing_warnings: List[str]

    # Node 5 output
    final_video_path: str

    # Global error channel
    error_msg: Optional[str]
