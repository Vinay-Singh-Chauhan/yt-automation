import subprocess
import textwrap
from pathlib import Path


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-2000:]}")


def audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Could not inspect narration audio: {result.stderr[-1000:]}")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("FFprobe returned an invalid audio duration") from exc


def _make_caption_segments(
    narration: str, duration: float, directory: Path
) -> list[tuple[Path, float, float]]:
    words = narration.split()
    if not words:
        raise ValueError("Narration must contain at least one word")
    groups = [words[index:index + 5] for index in range(0, len(words), 5)]
    segment_duration = duration / len(groups)
    segments: list[tuple[Path, float, float]] = []
    for index, group in enumerate(groups):
        path = directory / f"caption-{index:02}.txt"
        path.write_text(textwrap.fill(" ".join(group), width=27), encoding="utf-8")
        start = index * segment_duration
        end = duration if index == len(groups) - 1 else (index + 1) * segment_duration
        segments.append((path, start, end))
    return segments


def _escape_filter_path(path: Path) -> str:
    return path.as_posix().replace("\\", "\\\\").replace(":", "\\:")


def _build_video_filter(title_path: Path, caption_segments: list[tuple[Path, float, float]]) -> str:
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font_path = _escape_filter_path(Path(font))
    title_file = _escape_filter_path(title_path)
    duration = caption_segments[-1][2]
    filters = [
        "drawbox=x=0:y=0:w=iw:h=ih:color=0x10172A:t=fill",
        "drawbox=x=54:y=54:w=972:h=1812:color=0x34456F@0.85:t=6",
        "drawbox=x=0:y=0:w=iw:h=20:color=0x31D6B2:t=fill",
        "drawbox=x=100:y=112:w=14:h=96:color=0xEF6BA8:t=fill",
        "drawbox=x=130:y=112:w=330:h=96:color=0x1B2948:t=fill",
        (
            f"drawtext=fontfile='{font_path}':text='QUICK FACT':"
            "fontcolor=0x72F2D2:fontsize=34:x=160:y=142"
        ),
        "drawbox=x=100:y=260:w=880:h=400:color=0x17213B:t=fill",
        (
            f"drawtext=fontfile='{font_path}':textfile='{title_file}':expansion=none:"
            "fontcolor=white:fontsize=62:x=(w-text_w)/2:y=300:"
            "box=1:boxcolor=0x26345A@0.85:boxborderw=26"
        ),
        "drawbox=x=100:y=710:w=280:h=12:color=0xEF6BA8:t=fill",
        "drawbox=x=140:y=790:w=800:h=470:color=0x182849:t=fill",
        "drawbox=x=170:y=820:w=740:h=410:color=0x34456F@0.8:t=5",
        (
            f"drawtext=fontfile='{font_path}':text='THE BIG IDEA':"
            "fontcolor=0xB9C9F0:fontsize=30:x=210:y=850"
        ),
        "drawbox=x=220:y=1204:w=660:h=6:color=0xDCE6FF@0.85:t=fill",
    ]
    bars = [
        (220, 54, "0x31D6B2"),
        (360, 124, "0x77A7FF"),
        (500, 194, "0xEF6BA8"),
        (640, 154, "0xFFC36B"),
        (780, 244, "0x9E8CFF"),
    ]
    for index, (x, height, color) in enumerate(bars):
        y = 1204 - height
        reveal_at = duration * 0.35 * (index + 1) / len(bars)
        filters.extend(
            [
                f"drawbox=x={x}:y={y}:w=100:h={height}:color=0x26345A:t=fill",
                (
                    f"drawbox=x={x}:y={y}:w=100:h={height}:color={color}:t=fill:"
                    f"enable='gte(t,{reveal_at:.3f})'"
                ),
            ]
        )
    for caption_path, start, end in caption_segments:
        caption_file = _escape_filter_path(caption_path)
        filters.append(
            f"drawtext=fontfile='{font_path}':textfile='{caption_file}':expansion=none:"
            "fontcolor=white:fontsize=46:x=(w-text_w)/2:y=1400:"
            "box=1:boxcolor=0x080D1C@0.92:boxborderw=24:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
    filters.extend(
        [
            "drawbox=x=140:y=1720:w=800:h=5:color=0x34456F:t=fill",
            (
                f"drawtext=fontfile='{font_path}':text='WATCH  •  LEARN  •  SHARE':"
                "fontcolor=0x9EADD0:fontsize=24:x=(w-text_w)/2:y=1760"
            ),
        ]
    )
    return ",".join(filters)


def render_short(
    audio_path: Path,
    narration: str,
    title: str,
    output_path: Path,
    thumbnail_path: Path,
    min_seconds: int,
    max_seconds: int,
) -> float:
    duration = audio_duration(audio_path)
    if not min_seconds <= duration <= max_seconds:
        raise ValueError(
            f"Narration audio is {duration:.1f}s; expected {min_seconds}–{max_seconds}s. "
            "Adjust the generated narration or requested duration and retry."
        )

    title_path = output_path.with_suffix(".title.txt")
    title_path.write_text(textwrap.fill(title, width=22), encoding="utf-8")
    caption_segments = _make_caption_segments(narration, duration, output_path.parent)
    try:
        video_filter = _build_video_filter(title_path, caption_segments)
        _run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i",
                "color=c=0x10172a:s=1080x1920:r=30", "-i", str(audio_path),
                "-t", f"{duration:.3f}", "-vf", video_filter, "-shortest",
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                str(output_path),
            ]
        )
        _run(
            [
                "ffmpeg", "-y", "-ss", f"{min(duration * 0.6, duration - 0.1):.3f}", "-i",
                str(output_path), "-frames:v", "1", "-q:v", "2", str(thumbnail_path),
            ]
        )
    finally:
        title_path.unlink(missing_ok=True)
        for caption_path, _, _ in caption_segments:
            caption_path.unlink(missing_ok=True)
    return duration
