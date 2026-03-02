"""
Video Keyframe Extractor

Uses PySceneDetect for scene detection and K-Means clustering for keyframe selection.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from scenedetect import ContentDetector, detect, open_video
from sklearn.cluster import KMeans


class KeyframeExtractionError(Exception):
    """Exception raised when keyframe extraction fails."""

    pass


class VideoKeyframeExtractor:
    """Extract keyframes from video files using scene detection and clustering."""

    def __init__(
        self,
        scene_threshold: float = 30.0,
        max_keyframes_per_scene: int = 3,
        target_resolution: tuple = (320, 180),
    ):
        """
        Initialize the keyframe extractor.

        Args:
            scene_threshold: Threshold for scene change detection (higher = fewer scenes)
            max_keyframes_per_scene: Maximum keyframes to extract per scene
            target_resolution: Target resolution for keyframe images (width, height)
        """
        self.scene_threshold = scene_threshold
        self.max_keyframes_per_scene = max_keyframes_per_scene
        self.target_resolution = target_resolution

    def extract_keyframes(
        self,
        video_path: str,
        output_dir: str,
    ) -> Dict[str, Any]:
        """
        Extract keyframes from a video file.

        Args:
            video_path: Path to input video file
            output_dir: Directory to save extracted keyframes

        Returns:
            Dictionary containing:
            - keyframe_paths: List of paths to extracted keyframe images
            - keyframe_timestamps: List of timestamps (in seconds) for each keyframe
            - scene_boundaries: List of scene boundary info
            - stats: Extraction statistics

        Raises:
            KeyframeExtractionError: If extraction fails
        """
        video_path = Path(video_path).resolve()
        if not video_path.exists():
            raise KeyframeExtractionError(f"Video file not found: {video_path}")

        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Step 1: Detect scene boundaries
            print(f"[Keyframe Extractor] Detecting scenes in {video_path}...")
            scenes = self._detect_scenes(str(video_path))

            if not scenes:
                # No scenes detected, treat entire video as one scene
                print("[Keyframe Extractor] No scene changes detected, treating as single scene")
                scenes = [(0, self._get_video_duration(str(video_path)))]

            print(f"[Keyframe Extractor] Found {len(scenes)} scenes")

            # Step 2: Extract keyframes from each scene
            keyframe_paths: List[str] = []
            keyframe_timestamps: List[float] = []
            scene_boundaries: List[Dict[str, Any]] = []

            video = open_video(str(video_path))
            total_frames = video.duration.frame_num

            for scene_idx, (start_frame, end_frame) in enumerate(scenes):
                scene_result = self._extract_scene_keyframes(
                    video=video,
                    start_frame=start_frame,
                    end_frame=end_frame,
                    output_dir=output_dir,
                    scene_idx=scene_idx,
                )

                keyframe_paths.extend(scene_result["paths"])
                keyframe_timestamps.extend(scene_result["timestamps"])
                scene_boundaries.append(
                    {
                        "scene_index": scene_idx,
                        "start_frame": int(start_frame),
                        "end_frame": int(end_frame),
                        "start_time_sec": float(
                            start_frame * video.frame_rate_sec
                        ),
                        "end_time_sec": float(end_frame * video.frame_rate_sec),
                        "keyframes_extracted": len(scene_result["paths"]),
                    }
                )

            # Sort by timestamp
            if keyframe_paths:
                sorted_indices = np.argsort(keyframe_timestamps)
                keyframe_paths = [keyframe_paths[i] for i in sorted_indices]
                keyframe_timestamps = [keyframe_timestamps[i] for i in sorted_indices]

            stats = {
                "total_scenes": len(scenes),
                "total_keyframes": len(keyframe_paths),
                "video_duration_sec": float(total_frames * video.frame_rate_sec),
                "video_resolution": f"{video.frame_size[0]}x{video.frame_size[1]}",
            }

            print(
                f"[Keyframe Extractor] Extracted {len(keyframe_paths)} keyframes "
                f"from {len(scenes)} scenes"
            )

            return {
                "keyframe_paths": keyframe_paths,
                "keyframe_timestamps": keyframe_timestamps,
                "scene_boundaries": scene_boundaries,
                "stats": stats,
            }

        except Exception as e:
            raise KeyframeExtractionError(f"Keyframe extraction failed: {e}")

    def _detect_scenes(self, video_path: str) -> List[tuple]:
        """Detect scene boundaries using PySceneDetect."""
        try:
            # Use ContentDetector for scene change detection
            scene_list = detect(
                video_path,
                ContentDetector(
                    threshold=self.scene_threshold,
                    min_scene_len=15,  # Minimum scene length in frames
                ),
            )

            # Convert to list of (start_frame, end_frame) tuples
            scenes = []
            for i, scene in enumerate(scene_list):
                start_frame = scene[0].frame_num
                end_frame = scene[1].frame_num if i < len(scene_list) - 1 else None

                if end_frame is None:
                    # Last scene - need to get video duration
                    video = open_video(video_path)
                    end_frame = video.duration.frame_num

                scenes.append((start_frame, end_frame))

            return scenes

        except Exception as e:
            print(f"[Keyframe Extractor] Scene detection warning: {e}")
            return []

    def _get_video_duration(self, video_path: str) -> int:
        """Get video duration in frames."""
        try:
            video = open_video(video_path)
            return video.duration.frame_num
        except Exception:
            return 90000  # Default: assume 5 minutes at 30fps

    def _extract_scene_keyframes(
        self,
        video,
        start_frame: int,
        end_frame: int,
        output_dir: Path,
        scene_idx: int,
    ) -> Dict[str, Any]:
        """Extract keyframes from a single scene using K-Means clustering."""
        # Calculate number of frames to sample
        scene_length = end_frame - start_frame
        sample_size = min(30, scene_length // 10)  # Sample up to 30 frames

        if sample_size < 1:
            sample_size = 1

        # Get frame timestamps for sampling
        frame_indices = np.linspace(
            start_frame, end_frame - 1, num=sample_size, dtype=int
        )

        # Extract frames and compute features
        frames = []
        frame_times = []

        try:
            for frame_idx in frame_indices:
                frame = video.read(frame_idx)
                if frame is not None:
                    # Resize for feature extraction
                    frame_resized = self._resize_frame(frame)
                    frames.append(frame_resized)
                    frame_times.append(
                        float(frame_idx * video.frame_rate_sec)
                    )
        except Exception as e:
            print(f"[Keyframe Extractor] Warning: Could not read all frames: {e}")

        if not frames:
            return {"paths": [], "timestamps": []}

        # Determine number of keyframes for this scene
        n_keyframes = min(self.max_keyframes_per_scene, len(frames))

        if n_keyframes == 1 or len(frames) == 1:
            # Single keyframe: use the middle frame
            mid_idx = len(frames) // 2
            keyframe_path = self._save_keyframe(
                frames[mid_idx], output_dir, scene_idx, 0
            )
            return {
                "paths": [str(keyframe_path)],
                "timestamps": [frame_times[mid_idx]],
            }

        # K-Means clustering for keyframe selection
        features = self._extract_frame_features(frames)

        try:
            kmeans = KMeans(n_clusters=n_keyframes, random_state=42, n_init="auto")
            kmeans.fit(features)

            # For each cluster, select the frame closest to centroid
            keyframe_indices = []
            for cluster_id in range(n_keyframes):
                cluster_mask = kmeans.labels_ == cluster_id
                if not np.any(cluster_mask):
                    continue

                cluster_features = features[cluster_mask]
                cluster_frames = [frames[i] for i in range(len(frames)) if cluster_mask[i]]
                cluster_times = [frame_times[i] for i in range(len(frame_times)) if cluster_mask[i]]

                # Find frame closest to cluster centroid
                centroid = kmeans.cluster_centers_[cluster_id]
                distances = np.linalg.norm(cluster_features - centroid, axis=1)
                closest_idx = np.argmin(distances)

                keyframe_indices.append(
                    {
                        "frame": cluster_frames[closest_idx],
                        "timestamp": cluster_times[closest_idx],
                        "distance": distances[closest_idx],
                    }
                )

            # Sort by timestamp and save keyframes
            keyframe_indices.sort(key=lambda x: x["timestamp"])

            paths = []
            timestamps = []

            for kf_idx, kf_data in enumerate(keyframe_indices):
                keyframe_path = self._save_keyframe(
                    kf_data["frame"], output_dir, scene_idx, kf_idx
                )
                paths.append(str(keyframe_path))
                timestamps.append(kf_data["timestamp"])

            return {"paths": paths, "timestamps": timestamps}

        except Exception as e:
            print(f"[Keyframe Extractor] K-Means clustering failed: {e}")
            # Fallback: evenly spaced frames
            return self._fallback_keyframes(frames, frame_times, output_dir, scene_idx)

    def _resize_frame(self, frame: np.ndarray) -> np.ndarray:
        """Resize frame to target resolution."""
        import cv2

        return cv2.resize(
            frame,
            self.target_resolution,
            interpolation=cv2.INTER_AREA,
        )

    def _extract_frame_features(self, frames: List[np.ndarray]) -> np.ndarray:
        """Extract color histogram features from frames for clustering."""
        features = []
        for frame in frames:
            # Compute RGB histogram
            hist_r = np.histogram(frame[:, :, 0].flatten(), bins=16, range=(0, 256))[0]
            hist_g = np.histogram(frame[:, :, 1].flatten(), bins=16, range=(0, 256))[0]
            hist_b = np.histogram(frame[:, :, 2].flatten(), bins=16, range=(0, 256))[0]
            features.append(np.concatenate([hist_r, hist_g, hist_b]))

        features_array = np.array(features, dtype=np.float32)

        # Normalize features
        features_array = features_array / (features_array.sum(axis=1, keepdims=True) + 1e-8)

        return features_array

    def _save_keyframe(
        self,
        frame: np.ndarray,
        output_dir: Path,
        scene_idx: int,
        keyframe_idx: int,
    ) -> Path:
        """Save a keyframe to disk."""
        import cv2

        filename = f"scene_{scene_idx:03d}_keyframe_{keyframe_idx:02d}.jpg"
        output_path = output_dir / filename

        cv2.imwrite(str(output_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        return output_path

    def _fallback_keyframes(
        self,
        frames: List[np.ndarray],
        frame_times: List[float],
        output_dir: Path,
        scene_idx: int,
    ) -> Dict[str, Any]:
        """Fallback keyframe extraction: evenly spaced frames."""
        n_keyframes = min(self.max_keyframes_per_scene, len(frames))
        indices = np.linspace(0, len(frames) - 1, num=n_keyframes, dtype=int)

        paths = []
        timestamps = []

        for kf_idx, frame_idx in enumerate(indices):
            keyframe_path = self._save_keyframe(
                frames[frame_idx], output_dir, scene_idx, kf_idx
            )
            paths.append(str(keyframe_path))
            timestamps.append(frame_times[frame_idx])

        return {"paths": paths, "timestamps": timestamps}


def extract_keyframes(
    video_path: str,
    output_dir: str,
    scene_threshold: float = 30.0,
    max_keyframes_per_scene: int = 3,
) -> Dict[str, Any]:
    """
    Convenience function for keyframe extraction.

    Args:
        video_path: Path to input video
        output_dir: Directory for output keyframes
        scene_threshold: Scene detection threshold
        max_keyframes_per_scene: Max keyframes per scene

    Returns:
        Extraction result dictionary
    """
    extractor = VideoKeyframeExtractor(
        scene_threshold=scene_threshold,
        max_keyframes_per_scene=max_keyframes_per_scene,
    )
    return extractor.extract_keyframes(video_path, output_dir)
