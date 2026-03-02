"""
Node 0a: Video Keyframe Extractor

Extracts keyframes from video files using scene detection and K-Means clustering.
"""

import os
from pathlib import Path
from typing import Any, Dict, List

from orchestrator.state import VideoGenerationState
from utils.video_keyframe_extractor import (
    KeyframeExtractionError,
    VideoKeyframeExtractor,
)


def video_keyframe_extractor_node(state: VideoGenerationState) -> Dict[str, Any]:
    """
    [Node 0a] Video keyframe extractor node.

    Takes video_path from state and extracts keyframes:
    - keyframe_paths: List of paths to extracted keyframe images
    - keyframe_timestamps: List of timestamps (seconds) for each keyframe
    - scene_boundaries: List of scene boundary information

    If video_path is not provided but douyin_share_url exists, this node
    may be skipped (video download happens in Node 0).
    """
    video_path = state.get("video_path")

    # If no video path provided, check if we have a Douyin URL (Node 0 should handle it)
    if not video_path:
        douyin_url = state.get("douyin_share_url")
        if douyin_url:
            # Node 0 should have downloaded the video - this is an error
            return {
                "error_msg": (
                    "douyin_share_url was provided but video_path is not set. "
                    "Node 0 (Douyin Downloader) should have run first."
                )
            }
        # No video input, skip silently
        print("[Node 0a: Keyframe Extractor] No video_path provided. Skipping.")
        return {}

    video_path = Path(video_path).resolve()
    if not video_path.exists():
        return {"error_msg": f"Video file not found: {video_path}"}

    run_dir = state.get("run_dir")
    if not run_dir:
        return {"error_msg": "Missing run_dir in state for keyframe extraction"}

    # Prepare output directory
    keyframes_dir = Path(run_dir) / "keyframes"
    keyframes_dir.mkdir(parents=True, exist_ok=True)

    # Get configuration from environment
    scene_threshold = float(
        os.getenv("VIDEO_KEYFRAME_SCENE_THRESHOLD", "30.0")
    )
    max_keyframes_per_scene = int(
        os.getenv("VIDEO_KEYFRAME_MAX_PER_SCENE", "3")
    )

    print(
        f"[Node 0a: Keyframe Extractor] Processing: {video_path.name}"
    )
    print(
        f"[Node 0a: Keyframe Extractor] scene_threshold={scene_threshold}, "
        f"max_keyframes_per_scene={max_keyframes_per_scene}"
    )

    try:
        extractor = VideoKeyframeExtractor(
            scene_threshold=scene_threshold,
            max_keyframes_per_scene=max_keyframes_per_scene,
        )

        result = extractor.extract_keyframes(
            video_path=str(video_path),
            output_dir=str(keyframes_dir),
        )

        stats = result.get("stats", {})
        print(
            f"[Node 0a: Keyframe Extractor] Extracted {stats.get('total_keyframes', 0)} keyframes "
            f"from {stats.get('total_scenes', 0)} scenes"
        )

        # Log keyframe paths for debugging
        for idx, kf_path in enumerate(result.get("keyframe_paths", [])[:5]):
            print(f"  - Keyframe {idx + 1}: {Path(kf_path).name}")
        if len(result.get("keyframe_paths", [])) > 5:
            print(f"  ... and {len(result['keyframe_paths']) - 5} more")

        return {
            "keyframe_paths": result.get("keyframe_paths", []),
            "keyframe_timestamps": result.get("keyframe_timestamps", []),
            "scene_boundaries": result.get("scene_boundaries", []),
        }

    except KeyframeExtractionError as e:
        error_msg = f"[Node 0a: Keyframe Extractor] Extraction error: {e}"
        print(error_msg)
        return {"error_msg": error_msg}

    except Exception as e:
        error_msg = f"[Node 0a: Keyframe Extractor] Unexpected error: {e}"
        print(error_msg)
        return {"error_msg": error_msg}
