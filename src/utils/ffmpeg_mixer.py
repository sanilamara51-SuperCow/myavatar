import os
import shutil
import subprocess
from typing import List


def _get_ffmpeg_bin() -> str:
    """Get ffmpeg binary path from env or PATH."""
    # 1. Check FFMPEG_BIN env var
    env_path = os.getenv("FFMPEG_BIN", "").strip()
    if env_path and os.path.isfile(env_path):
        return env_path

    # 2. Try to find in PATH
    ffmpeg_in_path = shutil.which("ffmpeg")
    if ffmpeg_in_path:
        return ffmpeg_in_path

    # 3. Fallback to hardcoded path for backward compatibility
    fallback = r"C:\Users\liuzh\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
    if os.path.isfile(fallback):
        return fallback

    raise RuntimeError(
        "FFmpeg not found. Please set FFMPEG_BIN environment variable "
        "or ensure ffmpeg is in your PATH."
    )


def assemble_video(
    image_list: List[str],
    audio_list: List[str],
    durations: List[float],
    output_video_path: str,
):
    """
    终极绕过方案：
    抛弃 FFmpeg 读取图片的功能（Windows Winget 版本可能有未知 Bug）。
    1. OpenCV 物理将静态图片渲染成纯净无声 mp4
    2. 使用 FFmpeg 将纯净 mp4 与对应的音频流合并为独立 MP4 切片
    3. 最后拼接所有的 MP4 切片
    """
    import cv2
    import numpy as np

    print(f"Bypassing complex FFmpeg concat. Using OpenCV frame generation...")

    ffmpeg_bin = _get_ffmpeg_bin()
    print(f"[FFmpeg] Using binary: {ffmpeg_bin}")
    work_dir = os.path.dirname(os.path.abspath(output_video_path))
    segments = []

    fps = 25

    # Step 1: 为每个场景生成无声纯视频并与对应的音频合并
    for i, (img, aud, dur) in enumerate(zip(image_list, audio_list, durations)):
        silent_vid_path = os.path.join(work_dir, f"silent_{i:03d}.mp4")
        segment_path = os.path.join(work_dir, f"segment_{i:03d}.mp4")
        segments.append(segment_path)

        # 加载图片计算要生成的帧数
        frame = cv2.imread(img)
        if frame is None:
            raise FileNotFoundError(f"OpenCV failed to read image: {img}")

        height, width, layers = frame.shape
        num_frames = int(dur * fps)

        print(
            f"Generating OpenCV silent video {i + 1}/{len(image_list)} ({num_frames} frames)..."
        )
        # 写入物理视频流
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore
        video = cv2.VideoWriter(silent_vid_path, fourcc, fps, (width, height))

        for _ in range(num_frames):
            video.write(frame)
        video.release()

        # 将静态物理生成的视频和对应音频合并成一个独立片段
        print(f"Multiplexing audio into {os.path.basename(segment_path)}...")
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            silent_vid_path,
            "-i",
            os.path.abspath(aud),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            segment_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            # 可选：立马回收无声音轨废料
            os.remove(silent_vid_path)
        except subprocess.CalledProcessError as e:
            print(f"Error mixing audio to segment {i}: {e.stderr}")
            raise

    # Step 2: 编写 concat 文本文件拼接所有 MP4
    concat_txt_path = os.path.join(work_dir, "segments_list.txt")
    with open(concat_txt_path, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"file '{os.path.basename(seg)}'\n")

    # Step 3: 无损拼接所有视频切片
    print(f"Concatenating all segments into {os.path.basename(output_video_path)}...")
    concat_cmd = [
        ffmpeg_bin,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        "segments_list.txt",
        "-c",
        "copy",
        os.path.abspath(output_video_path),
    ]

    try:
        subprocess.run(
            concat_cmd, cwd=work_dir, check=True, capture_output=True, text=True
        )
        print("Assemble done successfully! OpenCV Bypass Pipeline UNBLOCKED.")
    except subprocess.CalledProcessError as e:
        print(f"Error concatenating final segments: {e.stderr}")
        raise

    for seg in segments:
        try:
            os.remove(seg)
        except:
            pass
    try:
        os.remove(concat_txt_path)
    except:
        pass


if __name__ == "__main__":
    print("Running OpenCV standalone test...")
    img_list = [
        "c:/docker/Myavatar/workspace/task_test/marp_output/slide_%03d.001.png",
        "c:/docker/Myavatar/workspace/task_test/marp_output/slide_%03d.002.png",
    ]
    audio_list = [
        "c:/docker/Myavatar/workspace/task_test/test_voice.wav",
        "c:/docker/Myavatar/workspace/task_test/test_voice.wav",
    ]
    durations = [3.0, 3.0]
    out_video = "c:/docker/Myavatar/workspace/task_test/final_output.mp4"

    assemble_video(img_list, audio_list, durations, out_video)
