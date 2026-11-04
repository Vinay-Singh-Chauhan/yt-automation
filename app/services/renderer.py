import math
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
    # Target ~2.5 s per caption group so each phrase reads naturally.
    # words_per_group adapts to both short (10 s) and long (30 s) videos.
    target_secs_per_group = 2.5
    num_groups = max(1, round(duration / target_secs_per_group))
    words_per_group = max(3, math.ceil(len(words) / num_groups))
    groups = [words[i:i + words_per_group] for i in range(0, len(words), words_per_group)]
    segment_duration = duration / len(groups)
    segments: list[tuple[Path, float, float]] = []
    for index, group in enumerate(groups):
        path = directory / f"caption-{index:02}.txt"
        path.write_text(textwrap.fill(" ".join(group), width=22), encoding="utf-8")
        start = index * segment_duration
        end = duration if index == len(groups) - 1 else (index + 1) * segment_duration
        segments.append((path, start, end))
    return segments


def _escape_filter_path(path: Path) -> str:
    return path.as_posix().replace("\\", "\\\\").replace(":", "\\:")


def _strip_prep_filters(video_filter: str) -> str:
    """Remove the leading scale/crop/eq filters from a video filter chain.

    ``_build_video_filter`` always prepends ``scale,crop,eq`` so the frame is
    correctly sized and darkened.  When those steps are already handled by the
    filter_complex prep stage (slideshow path), we must not apply them a second
    time — this helper strips them so only the drawbox/drawtext overlay remains.
    """
    # The prep block is exactly the first three comma-separated tokens.
    parts = video_filter.split(",")
    stripped = [
        p for p in parts
        if not (
            p.startswith("scale=")
            or p.startswith("crop=")
            or p.startswith("eq=")
        )
    ]
    return ",".join(stripped)


def _build_video_filter(
    title_path: Path,
    caption_segments: list[tuple[Path, float, float]],
    badge_label: str = "QUICK FACT",
    channel_handle: str = "WATCH  •  LEARN  •  SHARE",
) -> str:
    """Build the full FFmpeg -vf filter chain for a YouTube Short.

    Layout (1080 × 1920):
      y=  0–10   Teal accent bar
      y= 80–152  Category badge (badge_label)
      y=180–660  Title panel
      y=658–666  Pink accent underline
      y=1250     Caption text (dynamic, centre-aligned)
      y=1870–1878 Animated progress bar
      y=1890     Footer divider
      y=1910     Channel handle / footer text
    """
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font_path = _escape_filter_path(Path(font))
    title_file = _escape_filter_path(title_path)
    duration = caption_segments[-1][2]

    # Escape badge_label and channel_handle for FFmpeg drawtext (no special chars expected
    # but guard against accidental colons or single-quotes).
    safe_badge = badge_label.replace("'", "").replace(":", "")
    safe_handle = channel_handle.replace("'", "").replace(":", "")

    filters = []

    # ── Background prep ────────────────────────────────────────────────────────
    filters.extend(
        [
            "scale=1080:1920:force_original_aspect_ratio=increase",
            "crop=1080:1920",
            "eq=brightness=-0.2:saturation=0.8",
        ]
    )

    # ── Global dark overlay (makes text legible over any background image) ─────
    filters.append("drawbox=x=0:y=0:w=iw:h=ih:color=0x10172A@0.38:t=fill")

    # ── Top accent bar ─────────────────────────────────────────────────────────
    # Thicker than before (10 px) for better visibility on small screens.
    filters.append("drawbox=x=0:y=0:w=iw:h=10:color=0x31D6B2:t=fill")

    # ── Category badge ─────────────────────────────────────────────────────────
    # Pink strip on the left + dark pill behind the label.
    filters.extend(
        [
            "drawbox=x=100:y=80:w=14:h=72:color=0xEF6BA8:t=fill",
            "drawbox=x=120:y=80:w=330:h=72:color=0x1B2948:t=fill",
            (
                f"drawtext=fontfile='{font_path}':text='{safe_badge}':"
                "fontcolor=0x72F2D2:fontsize=28:x=148:y=104"
            ),
        ]
    )

    # ── Title panel ────────────────────────────────────────────────────────────
    # Taller panel + smaller font (52 → was 62) so longer titles don't overflow.
    filters.extend(
        [
            "drawbox=x=80:y=180:w=920:h=480:color=0x17213B@0.82:t=fill",
            (
                f"drawtext=fontfile='{font_path}':textfile='{title_file}':expansion=none:"
                "fontcolor=white:fontsize=52:x=(w-text_w)/2:y=210:"
                "box=1:boxcolor=0x26345A@0.85:boxborderw=22"
            ),
            # Thin pink accent underline below the title panel.
            "drawbox=x=80:y=666:w=240:h=8:color=0xEF6BA8:t=fill",
        ]
    )

    # ── Caption text ───────────────────────────────────────────────────────────
    # Moved from y=1400 to y=1250 to fill the previously empty middle zone.
    # Box colour now matches the dark-blue card palette instead of plain black.
    for caption_path, start, end in caption_segments:
        caption_file = _escape_filter_path(caption_path)
        filters.append(
            f"drawtext=fontfile='{font_path}':textfile='{caption_file}':expansion=none:"
            "fontcolor=white:fontsize=50:x=(w-text_w)/2:y=1250:"
            "box=1:boxcolor=0x17213B@0.90:boxborderw=28:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )

    # ── Animated progress bar ──────────────────────────────────────────────────
    # Track (dark) + filled portion (teal, grows with time).
    # drawbox evaluates w dynamically per frame using 't'.
    filters.extend(
        [
            "drawbox=x=0:y=1870:w=iw:h=8:color=0x1B2948:t=fill",
            f"drawbox=x=0:y=1870:w='iw*t/{duration:.3f}':h=8:color=0x31D6B2:t=fill",
        ]
    )

    # ── Footer ─────────────────────────────────────────────────────────────────
    filters.extend(
        [
            "drawbox=x=80:y=1890:w=920:h=3:color=0x34456F:t=fill",
            (
                f"drawtext=fontfile='{font_path}':text='{safe_handle}':"
                "fontcolor=0x9EADD0:fontsize=24:x=(w-text_w)/2:y=1910"
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
    background_path: Path | None = None,
    background_paths: list[Path] | None = None,
    badge_label: str = "QUICK FACT",
    channel_handle: str = "WATCH  •  LEARN  •  SHARE",
) -> float:
    """Render a YouTube Short.

    Supply ``background_paths`` (a list of 2+ Vertex AI images) to get a
    smooth crossfade slideshow background.  Pass ``background_path`` for the
    legacy single-image path.  If neither is given an animated gradient is
    used as a fallback.
    """
    # Normalise: if the caller passes background_paths with one entry treat it
    # as the single-image path so the simpler code-path is used.
    if background_paths and len(background_paths) == 1:
        background_path = background_paths[0]
        background_paths = None
    duration = audio_duration(audio_path)
    if not min_seconds <= duration <= max_seconds:
        raise ValueError(
            f"Narration audio is {duration:.1f}s; expected {min_seconds}–{max_seconds}s. "
            "Adjust the generated narration or requested duration and retry."
        )

    title_path = output_path.with_suffix(".title.txt")
    # width=20 matches the smaller fontsize=52 in the title panel.
    title_path.write_text(textwrap.fill(title, width=20), encoding="utf-8")
    caption_segments = _make_caption_segments(narration, duration, output_path.parent)
    try:
        video_filter = _build_video_filter(
            title_path, caption_segments,
            badge_label=badge_label,
            channel_handle=channel_handle,
        )

        if background_paths:
            # --- Slideshow path: N Vertex AI images crossfaded over the video duration ---
            #
            # Strategy:
            #   1. Each image is looped for (duration / N) seconds.
            #   2. Images are chained with the `xfade` filter using a 1-second dissolve
            #      so the transition is smooth rather than abrupt.
            #   3. The UI overlay (video_filter) is applied on top of the final merged
            #      stream via filter_complex, keeping a single output stream.
            #
            n = len(background_paths)
            # Time each image occupies (seconds); ensure xfade offset stays positive.
            segment = duration / n
            xfade_duration = min(1.0, segment * 0.4)

            # Build the -i inputs: one looped still per image + the audio.
            slideshow_inputs: list[str] = []
            for bp in background_paths:
                slideshow_inputs += ["-loop", "1", "-framerate", "30", "-i", str(bp)]
            slideshow_inputs += ["-i", str(audio_path)]

            # Build the filter_complex string:
            #   [0]prep[s0]; [1]prep[s1]; …
            #   [s0][s1]xfade=…[x01]; [x01][s2]xfade=…[x012]; …
            #   [xFinal]<video_filter>[vout]
            prep = (
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,"
                "eq=brightness=-0.2:saturation=0.8"
            )
            fc_parts: list[str] = []
            # Prep each input stream.
            for i in range(n):
                fc_parts.append(f"[{i}]{prep}[s{i}]")
            # Chain xfade between consecutive streams.
            prev_label = "s0"
            for i in range(1, n):
                offset = round(segment * i - xfade_duration / 2, 3)
                out_label = f"x{i}"
                fc_parts.append(
                    f"[{prev_label}][s{i}]xfade=transition=dissolve:"
                    f"duration={xfade_duration:.3f}:offset={offset:.3f}[{out_label}]"
                )
                prev_label = out_label
            # Apply the UI overlay filter on top (strip the leading scale/crop/eq since
            # that's already done in the prep step, then apply the drawbox/drawtext chain).
            ui_only = _strip_prep_filters(video_filter)
            fc_parts.append(f"[{prev_label}]{ui_only}[vout]")

            filter_complex = ";".join(fc_parts)

            _run(
                [
                    "ffmpeg", "-y",
                    *slideshow_inputs,
                    "-t", f"{duration:.3f}",
                    "-filter_complex", filter_complex,
                    "-map", "[vout]",
                    "-map", f"{n}:a",
                    "-shortest",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(output_path),
                ]
            )
        else:
            # --- Single image or gradient fallback path ---
            gradient_lavfi = (
                "geq="
                r"r='clip(16+12*sin(2*3.14159*t/8)+8*sin(2*3.14159*t/13)+4*(W/2-X)/W,0,255)':"
                r"g='clip(18+8*sin(2*3.14159*t/11)+5*sin(2*3.14159*t/7)+3*(H/2-Y)/H,0,255)':"
                r"b='clip(55+35*sin(2*3.14159*t/9)+20*sin(2*3.14159*t/5)+8*(W/2-X)/W,0,255)':"
                "s=1080x1920:r=30"
            )
            if background_path is not None:
                inputs = [
                    "-loop", "1",
                    "-framerate", "30",
                    "-i", str(background_path),
                    "-i", str(audio_path),
                ]
            else:
                inputs = [
                    "-f", "lavfi",
                    "-i", gradient_lavfi,
                    "-i", str(audio_path),
                ]
            _run(
                [
                    "ffmpeg", "-y",
                    *inputs,
                    "-t", f"{duration:.3f}",
                    "-vf", video_filter,
                    "-shortest",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(output_path),
                ]
            )

        # Thumbnail: grab the first clean frame (0.5 s) which always shows the
        # fully rendered title card — better click-through than a mid-caption frame.
        _run(
            [
                "ffmpeg", "-y",
                "-ss", "0.5",
                "-i", str(output_path),
                "-frames:v", "1",
                "-q:v", "2",
                str(thumbnail_path),
            ]
        )
    finally:
        title_path.unlink(missing_ok=True)
        for caption_path, _, _ in caption_segments:
            caption_path.unlink(missing_ok=True)
    return duration
