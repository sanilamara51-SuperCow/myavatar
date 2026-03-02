import os
import traceback
from typing import Dict, Any

from orchestrator.state import VideoGenerationState
from utils.ffmpeg_mixer import assemble_video


def ffmpeg_assembler_node(state: VideoGenerationState) -> Dict[str, Any]:
    """
    [Node 5] 终极封包节点
    作用：提取先前节点生成的图片物理路径和对应讲稿的音频文件及时长，最后交由底层混音程序压制出最终的 mp4 视频文件。
    """
    image_paths = state.get("image_paths") or state.get("ppt_image_paths") or []
    audio_paths = state.get("audio_paths", [])
    audio_durations = state.get("audio_durations", [])

    # 详细的前置校验
    if not image_paths:
        return {
            "error_msg": "[N5] Missing image assets (image_paths is empty). Check upstream nodes (n2b/n3)."
        }

    if not audio_paths:
        return {
            "error_msg": "[N5] Missing audio assets (audio_paths is empty). Check TTS node (n4)."
        }

    if not audio_durations:
        return {
            "error_msg": "[N5] Missing audio duration metadata. Check TTS node (n4) output."
        }

    if len(image_paths) != len(audio_paths):
        return {
            "error_msg": (
                f"[N5] Asset count mismatch: {len(image_paths)} images vs {len(audio_paths)} audio files. "
                "Check that every slide has a corresponding voiceover."
            )
        }

    if len(audio_paths) != len(audio_durations):
        return {
            "error_msg": (
                f"[N5] Duration metadata mismatch: {len(audio_paths)} audio files but {len(audio_durations)} durations. "
                "Check TTS node (n4) audio_segment_report generation."
            )
        }

    print(
        f"[Node 5: FFmpeg Assembler] Start processing {len(image_paths)} segment pairs..."
    )

    # 验证文件存在性
    missing_files = []
    for i, img in enumerate(image_paths):
        if not os.path.isfile(img):
            missing_files.append(f"Image {i}: {img}")
    for i, aud in enumerate(audio_paths):
        if not os.path.isfile(aud):
            missing_files.append(f"Audio {i}: {aud}")

    if missing_files:
        return {
            "error_msg": (
                f"[N5] {len(missing_files)} asset files not found:\n"
                + "\n".join(f"  - {m}" for m in missing_files[:5])
                + ("\n  ... and more" if len(missing_files) > 5 else "")
            )
        }

    # 构建安全隔离的输出目录以存放本批次最终资产
    run_dir = state.get("run_dir")
    if run_dir:
        output_dir = run_dir
    else:
        output_dir = os.path.join(os.getcwd(), "workspace", "run_output", "final")
    os.makedirs(output_dir, exist_ok=True)

    out_video = os.path.join(output_dir, "output.mp4")

    # 检查 ffmpeg 可用性
    ffmpeg_bin = os.getenv("FFMPEG_BIN", "").strip()
    if ffmpeg_bin and not os.path.isfile(ffmpeg_bin):
        print(f"[Node 5 WARNING] FFMPEG_BIN is set but file not found: {ffmpeg_bin}")

    try:
        # 调用最底层的引擎
        assemble_video(image_paths, audio_paths, audio_durations, out_video)
        print(f"[Node 5: FFmpeg Assembler] Success! Video saved at: {out_video}")
        return {"final_video_path": out_video}

    except FileNotFoundError as e:
        error_msg = f"[N5] File not found during assembly: {e}"
        print(f"[Node 5 ERROR] {error_msg}")
        return {"error_msg": error_msg}

    except RuntimeError as e:
        error_msg = f"[N5] FFmpeg runtime error: {e}"
        print(f"[Node 5 ERROR] {error_msg}")
        return {"error_msg": error_msg}

    except Exception as e:
        error_msg = f"[N5] Final Assembly failed: {str(e)}"
        detail = traceback.format_exc()
        print(f"[Node 5 ERROR] {error_msg}\n{detail}")
        return {"error_msg": error_msg, "error_detail": detail}
