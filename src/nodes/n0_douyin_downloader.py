"""
Node 0: Douyin Downloader

Downloads watermark-free videos from Douyin share URLs.
"""

import os
from pathlib import Path
from typing import Any, Dict

from orchestrator.state import VideoGenerationState
from utils.douyin_api_client import DouyinAPIClient, DouyinAPIError


def douyin_downloader_node(state: VideoGenerationState) -> Dict[str, Any]:
    """
    [Node 0] Douyin downloader node.

    Takes a douyin_share_url from state, downloads the video, and outputs:
    - video_path: Local path to downloaded video
    - video_metadata: {title, author, duration_sec, share_url, file_size_bytes}

    If no douyin_share_url is provided, passes through without error.
    """
    douyin_url = state.get("douyin_share_url")

    # If no Douyin URL provided, pass through without error
    if not douyin_url:
        print("[Node 0: Douyin Downloader] No douyin_share_url provided. Skipping.")
        return {}

    run_dir = state.get("run_dir")
    if not run_dir:
        return {"error_msg": "Missing run_dir in state for video download"}

    # Prepare output directory
    video_input_dir = Path(run_dir) / "video_input"
    video_input_dir.mkdir(parents=True, exist_ok=True)

    # Generate output filename
    # Use a sanitized filename based on the URL or a default name
    video_filename = "douyin_video.mp4"
    output_path = video_input_dir / video_filename

    print(f"[Node 0: Douyin Downloader] Downloading from: {douyin_url}")
    print(f"[Node 0: Douyin Downloader] Output path: {output_path}")

    # Get API base URL from config
    api_base = os.getenv("DOUYIN_PARSE_API_PRIMARY")

    try:
        client = DouyinAPIClient(api_base=api_base)
        result = client.download_video(
            share_url=douyin_url,
            output_path=str(output_path),
            timeout=120,  # 2 minutes timeout for large videos
        )

        print(
            f"[Node 0: Douyin Downloader] Download complete: "
            f"title='{result['title'][:50]}...', "
            f"author='{result['author']}', "
            f"duration={result.get('duration_sec', 'N/A')}s, "
            f"size={result.get('file_size_bytes', 0) / 1024 / 1024:.2f}MB"
        )

        return {
            "video_path": result["video_path"],
            "video_metadata": {
                "title": result["title"],
                "author": result["author"],
                "duration_sec": result.get("duration_sec"),
                "share_url": result["share_url"],
                "file_size_bytes": result.get("file_size_bytes"),
            },
        }

    except DouyinAPIError as e:
        error_msg = f"[Node 0: Douyin Downloader] API error: {e}"
        print(error_msg)
        return {"error_msg": error_msg}

    except Exception as e:
        error_msg = f"[Node 0: Douyin Downloader] Unexpected error: {e}"
        print(error_msg)
        return {"error_msg": error_msg}
