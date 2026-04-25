import json
import random
import shutil
import subprocess
from pathlib import Path


DEFAULT_VIDEO_PROCESSING_CONFIG = {
    "autoProcess": True,
    "trimEnabled": True,
    "trimHeadMin": 0.3,
    "trimHeadMax": 1.2,
    "trimTailMin": 0.3,
    "trimTailMax": 1.2,
    "speedEnabled": True,
    "speedMin": 0.97,
    "speedMax": 1.03,
    "cropEnabled": True,
    "cropPercentMin": 1.0,
    "cropPercentMax": 3.0,
    "pinkFilterEnabled": True,
    "pinkFilterStrength": 0.12,
    "lightSweep": True,
    "frameDropEnabled": True,
    "frameDropStrength": 0.02,
    "edgeGuardEnabled": True,
    "edgeGuardPixels": 8,
    "maxConcurrent": 4,
    "hardwareMode": "cpu",
}


def coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "on", "yes"}:
            return True
        if normalized in {"0", "false", "off", "no"}:
            return False
    if value is None:
        return default
    return bool(value)


def clamp_number(value, default, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def clamp_int(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def normalize_video_processing_config(payload=None):
    payload = payload or {}
    defaults = DEFAULT_VIDEO_PROCESSING_CONFIG
    config = {
        "autoProcess": coerce_bool(payload.get("autoProcess"), defaults["autoProcess"]),
        "trimEnabled": coerce_bool(payload.get("trimEnabled"), defaults["trimEnabled"]),
        "trimHeadMin": clamp_number(payload.get("trimHeadMin"), defaults["trimHeadMin"], 0, 10),
        "trimHeadMax": clamp_number(payload.get("trimHeadMax"), defaults["trimHeadMax"], 0, 10),
        "trimTailMin": clamp_number(payload.get("trimTailMin"), defaults["trimTailMin"], 0, 10),
        "trimTailMax": clamp_number(payload.get("trimTailMax"), defaults["trimTailMax"], 0, 10),
        "speedEnabled": coerce_bool(payload.get("speedEnabled"), defaults["speedEnabled"]),
        "speedMin": clamp_number(payload.get("speedMin"), defaults["speedMin"], 0.5, 2),
        "speedMax": clamp_number(payload.get("speedMax"), defaults["speedMax"], 0.5, 2),
        "cropEnabled": coerce_bool(payload.get("cropEnabled"), defaults["cropEnabled"]),
        "cropPercentMin": clamp_number(payload.get("cropPercentMin"), defaults["cropPercentMin"], 0, 10),
        "cropPercentMax": clamp_number(payload.get("cropPercentMax"), defaults["cropPercentMax"], 0, 10),
        "pinkFilterEnabled": coerce_bool(payload.get("pinkFilterEnabled"), defaults["pinkFilterEnabled"]),
        "pinkFilterStrength": clamp_number(
            payload.get("pinkFilterStrength"), defaults["pinkFilterStrength"], 0, 1
        ),
        "lightSweep": coerce_bool(payload.get("lightSweep"), defaults["lightSweep"]),
        "frameDropEnabled": coerce_bool(payload.get("frameDropEnabled"), defaults["frameDropEnabled"]),
        "frameDropStrength": clamp_number(
            payload.get("frameDropStrength"), defaults["frameDropStrength"], 0, 0.2
        ),
        "edgeGuardEnabled": coerce_bool(payload.get("edgeGuardEnabled"), defaults["edgeGuardEnabled"]),
        "edgeGuardPixels": clamp_int(payload.get("edgeGuardPixels"), defaults["edgeGuardPixels"], 0, 32),
        "maxConcurrent": clamp_int(payload.get("maxConcurrent"), defaults["maxConcurrent"], 1, 8),
        "hardwareMode": payload.get("hardwareMode") if payload.get("hardwareMode") in {"cpu", "gpu"} else "cpu",
    }

    for lower_key, upper_key in [
        ("trimHeadMin", "trimHeadMax"),
        ("trimTailMin", "trimTailMax"),
        ("speedMin", "speedMax"),
        ("cropPercentMin", "cropPercentMax"),
    ]:
        if config[lower_key] > config[upper_key]:
            config[lower_key], config[upper_key] = config[upper_key], config[lower_key]

    return config


def load_video_processing_config(raw_value):
    if not raw_value:
        return dict(DEFAULT_VIDEO_PROCESSING_CONFIG)
    try:
        payload = json.loads(raw_value)
    except (TypeError, ValueError):
        payload = {}
    return normalize_video_processing_config(payload)


def probe_video(video_path: Path):
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        raise RuntimeError("ffprobe is required for video processing")

    command = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,width,height:format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"ffprobe failed: {stderr[:400]}")

    try:
        payload = json.loads(result.stdout or "{}")
        duration = float(payload.get("format", {}).get("duration") or 0)
        streams = payload.get("streams") or []
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
        has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
        width = int(video_stream.get("width") or 0)
        height = int(video_stream.get("height") or 0)
    except (TypeError, ValueError, IndexError):
        duration, width, height, has_audio = 0, 0, 0, False

    if duration <= 0:
        raise RuntimeError("Unable to read video duration")
    return {"duration": duration, "width": width, "height": height, "has_audio": has_audio}


def build_video_filter(config, rng, width=None, height=None):
    crop_percent = rng.uniform(config["cropPercentMin"], config["cropPercentMax"]) / 100
    speed = rng.uniform(config["speedMin"], config["speedMax"]) if config.get("speedEnabled", True) else 1
    pink = config["pinkFilterStrength"] if config.get("pinkFilterEnabled", True) else 0
    output_width = width if width and width % 2 == 0 else "trunc(iw/2)*2"
    output_height = height if height and height % 2 == 0 else "trunc(ih/2)*2"
    edge_guard = int(config.get("edgeGuardPixels") or 0) if config.get("edgeGuardEnabled", True) else 0
    filters = []
    if config.get("cropEnabled", True):
        filters.extend([
            f"crop=trunc(iw*{1 - crop_percent * 2:.6f}/2)*2:trunc(ih*{1 - crop_percent * 2:.6f}/2)*2:(iw-ow)/2:(ih-oh)/2",
            f"scale={output_width}:{output_height}:flags=bicubic",
        ])
    if edge_guard > 0:
        filters.extend([
            f"crop=iw-{edge_guard * 2}:ih:{edge_guard}:0",
            f"scale={output_width}:{output_height}:flags=bicubic",
        ])
    if config.get("speedEnabled", True):
        filters.append(f"setpts={1 / speed:.6f}*PTS")
    if pink > 0:
        filters.append(
            "colorchannelmixer="
            f"rr={1 + pink * 0.22:.4f}:"
            f"gg={max(0, 1 - pink * 0.08):.4f}:"
            f"bb={1 + pink * 0.12:.4f}:"
            f"rg={pink * 0.04:.4f}:"
            f"br={pink * 0.03:.4f}"
        )
    if config["lightSweep"]:
        filters.append(
            "drawbox=x='mod(t*180,w+240)-240':y=0:w=120:h=ih:color=white@0.08:t=fill"
        )
    if config.get("frameDropEnabled", True) and config["frameDropStrength"] > 0:
        filters.append("fps=fps=30")
    if not filters:
        filters.append("format=yuv420p")
    return ",".join(filters), speed


def output_has_video(output_path: Path) -> bool:
    try:
        metadata = probe_video(output_path)
    except Exception:
        return False
    return metadata["width"] > 0 and metadata["height"] > 0


def process_video(input_path: Path, output_path: Path, config, seed=None, progress_callback=None):
    if not input_path.exists():
        raise FileNotFoundError(f"video file not found: {input_path}")

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg is required for video processing")

    normalized_config = normalize_video_processing_config(config)
    rng = random.Random(seed)
    metadata = probe_video(input_path)
    if normalized_config.get("trimEnabled", True):
        head_trim = rng.uniform(normalized_config["trimHeadMin"], normalized_config["trimHeadMax"])
        tail_trim = rng.uniform(normalized_config["trimTailMin"], normalized_config["trimTailMax"])
    else:
        head_trim = 0
        tail_trim = 0
    max_total_trim = max(0, metadata["duration"] - 1)
    total_trim = min(head_trim + tail_trim, max_total_trim)
    if total_trim < head_trim + tail_trim and head_trim + tail_trim > 0:
        ratio = total_trim / (head_trim + tail_trim)
        head_trim *= ratio
        tail_trim *= ratio
    output_duration = max(0.1, metadata["duration"] - head_trim - tail_trim)
    video_filter, speed = build_video_filter(
        normalized_config,
        rng,
        metadata.get("width"),
        metadata.get("height"),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    encoder = "h264_nvenc" if normalized_config["hardwareMode"] == "gpu" and shutil.which("nvidia-smi") else "libx264"
    command = [
        ffmpeg_bin,
        "-y",
        "-ss",
        f"{head_trim:.3f}",
        "-t",
        f"{output_duration:.3f}",
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-vf",
        video_filter,
        "-c:v",
        encoder,
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
    ]
    if metadata["has_audio"]:
        if normalized_config.get("speedEnabled", True) and abs(speed - 1) > 0.001:
            command.extend(["-filter:a", f"atempo={speed:.6f}"])
        command.extend(["-c:a", "aac"])
    command.append(str(output_path))
    if progress_callback:
        progress_callback(35, "Running ffmpeg")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not output_path.exists():
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"ffmpeg video processing failed: {stderr[:400]}")
    if not output_has_video(output_path):
        try:
            output_path.unlink()
        except OSError:
            pass
        raise RuntimeError("ffmpeg video processing produced an output without a video stream")
    if progress_callback:
        progress_callback(100, "Processing completed")
    return {
        "output_path": output_path,
        "config": normalized_config,
        "profile": "default-basic",
        "operations": {
            "headTrim": round(head_trim, 3),
            "tailTrim": round(tail_trim, 3),
            "speed": round(speed, 4),
            "encoder": encoder,
        },
        "command": command,
    }
