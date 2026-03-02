"""
Douyin API Client for parsing share URLs and downloading watermark-free videos.

Supports:
- Douyin share link parsing (e.g., https://v.douyin.com/xxx/)
- Video download to local file
- Metadata extraction (title, author, duration, cover)
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
import requests


class DouyinAPIError(Exception):
    """Exception raised when Douyin API call fails."""

    pass


class DouyinAPIClient:
    """Client for interacting with Douyin video parsing APIs."""

    # Primary API: devtool.top (free, no auth required for basic usage)
    DEFAULT_API_BASE = "https://www.devtool.top/api/douyin/parse"

    # Alternative:自建 API (Evil0ctal/Douyin_TikTok_Download_API)
    # self_hosted_api_base = "http://localhost:8080/api/douyin/parse"

    def __init__(self, api_base: Optional[str] = None):
        """
        Initialize the Douyin API client.

        Args:
            api_base: Base URL for the parsing API. Defaults to devtool.top.
        """
        self.api_base = (api_base or os.getenv("DOUYIN_PARSE_API_PRIMARY") or self.DEFAULT_API_BASE).rstrip(
            "/"
        )

    def parse_share_url(self, share_url: str) -> Dict[str, Any]:
        """
        Parse a Douyin share URL and extract video metadata.

        Args:
            share_url: Douyin share link (e.g., https://v.douyin.com/abc123/)

        Returns:
            Dictionary containing:
            - video_url: Direct URL to watermark-free video
            - title: Video title/description
            - author: Author name
            - cover: Cover image URL
            - duration: Video duration in seconds (if available)

        Raises:
            DouyinAPIError: If API call fails or returns invalid response
        """
        share_url = share_url.strip()

        # Validate Douyin URL pattern
        if not self._is_valid_douyin_url(share_url):
            raise DouyinAPIError(f"Invalid Douyin share URL: {share_url}")

        try:
            response = requests.get(self.api_base, params={"url": share_url}, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Parse API response (adapt to actual API schema)
            result = self._parse_api_response(data)

            if not result.get("video_url"):
                raise DouyinAPIError("API returned empty video_url")

            return result

        except requests.RequestException as e:
            raise DouyinAPIError(f"API request failed: {e}")
        except (KeyError, ValueError, TypeError) as e:
            raise DouyinAPIError(f"Failed to parse API response: {e}")

    def download_video(
        self,
        share_url: str,
        output_path: str,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """
        Download a watermark-free video from a Douyin share URL.

        Args:
            share_url: Douyin share link
            output_path: Local file path to save the video
            timeout: Download timeout in seconds

        Returns:
            Dictionary containing:
            - video_path: Path to downloaded video
            - title: Video title
            - author: Author name
            - duration_sec: Video duration
            - share_url: Original share URL
            - file_size_bytes: Downloaded file size in bytes

        Raises:
            DouyinAPIError: If parsing or download fails
        """
        # Step 1: Parse the URL to get video URL and metadata
        parse_result = self.parse_share_url(share_url)
        video_url = parse_result["video_url"]

        # Step 2: Download the video
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.douyin.com/",
            }

            response = requests.get(video_url, headers=headers, stream=True, timeout=timeout)
            response.raise_for_status()

            # Ensure output directory exists
            output_path = Path(output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Download in chunks
            total_size = 0
            chunk_size = 8192

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)

            if total_size == 0:
                raise DouyinAPIError("Downloaded file is empty")

            return {
                "video_path": str(output_path),
                "title": parse_result.get("title", "Unknown"),
                "author": parse_result.get("author", "Unknown"),
                "duration_sec": parse_result.get("duration"),
                "share_url": share_url,
                "file_size_bytes": total_size,
            }

        except requests.RequestException as e:
            raise DouyinAPIError(f"Video download failed: {e}")

    def _is_valid_douyin_url(self, url: str) -> bool:
        """Validate if the URL is a Douyin share link."""
        # Common Douyin URL patterns
        patterns = [
            r"https?://(?:www\.)?douyin\.com/.*",
            r"https?://v\.douyin\.com/.*",
            r"https?://ies\.douyin\.com/.*",
            r"https?://share\.douyin\.com/.*",
        ]
        return any(re.match(pattern, url, re.IGNORECASE) for pattern in patterns)

    def _parse_api_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse the API response into a standardized format.

        Different APIs may return different schemas. This method normalizes them.
        """
        # devtool.top API response schema:
        # {
        #     "code": 0,
        #     "msg": "success",
        #     "data": {
        #         "aweme_id": "...",
        #         "title": "...",
        #         "author": {...},
        #         "video": {
        #             "play_addr": {"url_list": ["..."]},
        #             "cover": {"url_list": ["..."]},
        #             "duration": 12345
        #         }
        #     }
        # }

        if not isinstance(data, dict):
            raise ValueError("API response is not a dictionary")

        # Check for error codes
        code = data.get("code")
        if code != 0:
            msg = data.get("msg") or data.get("message") or "Unknown error"
            raise DouyinAPIError(f"API returned error code {code}: {msg}")

        result_data = data.get("data", {})
        if not result_data:
            # Try flat structure (some APIs return data directly)
            result_data = data

        # Extract video URL
        video_data = result_data.get("video", {})
        play_addr = video_data.get("play_addr", {})
        url_list = play_addr.get("url_list", [])
        video_url = url_list[0] if url_list else ""

        # Extract author info
        author_data = result_data.get("author", {})
        author_name = author_data.get("nickname", "") or author_data.get("name", "")

        # Extract cover
        cover_data = video_data.get("cover", {})
        cover_url_list = cover_data.get("url_list", [])
        cover_url = cover_url_list[0] if cover_url_list else ""

        # Extract duration (in milliseconds for some APIs, convert to seconds)
        duration_ms = video_data.get("duration", 0)
        duration_sec = duration_ms / 1000.0 if duration_ms else None

        return {
            "video_url": video_url,
            "title": result_data.get("title", "") or result_data.get("desc", ""),
            "author": author_name,
            "cover": cover_url,
            "duration": duration_sec,
            "aweme_id": result_data.get("aweme_id", ""),
        }


async def download_video_async(
    share_url: str,
    output_path: str,
    api_base: Optional[str] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    Async version of video download.

    Args:
        share_url: Douyin share link
        output_path: Local file path to save the video
        api_base: Optional custom API base URL
        timeout: Download timeout in seconds

    Returns:
        Dictionary with download result metadata
    """
    client = DouyinAPIClient(api_base=api_base)
    return client.download_video(share_url=share_url, output_path=output_path, timeout=timeout)
