"""
Video Understanding Schema

Defines structured output formats for AI-powered video content analysis.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class SceneDescription(BaseModel):
    """Description of a single scene/segment in the video."""

    scene_index: int = Field(description="Index of this scene, starting from 0")
    time_range: str = Field(
        description="Time range in format 'mm:ss - mm:ss'"
    )
    visual_content: str = Field(
        description="Description of visual elements: people, objects, actions, setting"
    )
    on_screen_text: Optional[str] = Field(
        default=None,
        description="Any text visible on screen (titles, captions, signs, etc.)",
    )
    mood_atmosphere: str = Field(
        description="Emotional tone: energetic, calm, dramatic, humorous, etc."
    )


class ContentElement(BaseModel):
    """A notable content element extracted from the video."""

    type: str = Field(
        description="Type of element: key_message, quote, statistic, product, person, action"
    )
    content: str = Field(
        description="The actual content or description"
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="Approximate timestamp when this appears (mm:ss format)",
    )
    importance: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Importance rating 1-10 (10 = critical to understanding)",
    )


class VideoUnderstanding(BaseModel):
    """
    Structured understanding of a video's content.

    This is the main output schema for the video understanding node.
    """

    # Basic metadata
    title_suggestion: str = Field(
        description="Suggested descriptive title for this video"
    )
    duration_category: str = Field(
        description="Duration category: short (<1min), medium (1-5min), long (>5min)"
    )

    # High-level summary
    one_sentence_summary: str = Field(
        description="One sentence summary capturing the core message"
    )
    detailed_summary: str = Field(
        description="2-3 paragraph detailed summary of the video content"
    )

    # Content structure
    main_topics: List[str] = Field(
        description="3-5 main topics or themes covered in the video"
    )
    key_points: List[str] = Field(
        description="5-10 key points or takeaways from the video"
    )

    # Scene-by-scene breakdown
    scenes: List[SceneDescription] = Field(
        description="Scene-by-scene visual and narrative breakdown"
    )

    # Extracted content elements
    content_elements: List[ContentElement] = Field(
        description="Notable quotes, messages, statistics, products, people, actions"
    )

    # Style and format analysis
    video_style: str = Field(
        description="Video style: tutorial, vlog, documentary, interview, performance, etc."
    )
    target_audience: str = Field(
        description="Inferred target audience based on content and presentation"
    )
    presentation_style: str = Field(
        description="Presentation style: formal, casual, energetic, educational, entertaining"
    )

    # Tags for searchability
    suggested_tags: List[str] = Field(
        description="10-15 searchable tags that describe this video"
    )

    # Potential use cases
    reusable_elements: List[str] = Field(
        default=[],
        description="Elements that could be reused or referenced in new content (clips, quotes, examples)",
    )

    # Quality notes
    production_quality: str = Field(
        default="unknown",
        description="Production quality assessment: low, medium, high, professional",
    )
    audio_quality: str = Field(
        default="unknown",
        description="Audio quality assessment: poor, acceptable, good, excellent",
    )
