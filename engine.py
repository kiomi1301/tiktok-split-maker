from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".wmv", ".ts"}


def creation_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def find_binary(name: str, app_dir: Path) -> Optional[str]:
    exe = f"{name}.exe" if os.name == "nt" else name
    for candidate in (app_dir / exe, app_dir / "ffmpeg" / "bin" / exe):
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name) or shutil.which(exe)


def is_video_file(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def layout_heights(ratio: str) -> tuple[int, int]:
    try:
        top_percent = int(ratio.split("/", 1)[0])
    except Exception as exc:
        raise ValueError(f"Некорректное соотношение блоков: {ratio}") from exc
    top_h = round(1920 * top_percent / 100)
    top_h -= top_h % 2
    bottom_h = 1920 - top_h
    bottom_h -= bottom_h % 2
    top_h = 1920 - bottom_h
    return top_h, bottom_h


def parse_ffmpeg_time(value: str) -> float:
    """Parse HH:MM:SS.microseconds from ffmpeg -progress output."""
    m = re.fullmatch(r"(\d+):(\d+):(\d+(?:\.\d+)?)", value.strip())
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def parse_ffmpeg_speed(value: str) -> float:
    """Parse ffmpeg progress speed values such as '4.21x'."""
    value = value.strip().lower()
    if value.endswith("x"):
        value = value[:-1]
    try:
        speed = float(value)
        return speed if math.isfinite(speed) and speed >= 0 else 0.0
    except Exception:
        return 0.0


def segment_count(duration: float, segment_seconds: float) -> int:
    """Number of sequential clips needed to cover duration, including a remainder."""
    if duration <= 0 or segment_seconds <= 0:
        return 0
    # The epsilon prevents floating metadata such as 130.0000001 from creating
    # a useless one-frame extra clip.
    return max(1, int(math.ceil((duration - 1e-6) / segment_seconds)))


@dataclass
class RenderOptions:
    ratio: str = "70/30"
    quality: str = "High"
    encoder: str = "Auto (RTX/NVENC)"


class VideoEngine:
    def __init__(self, app_dir: Path):
        self.app_dir = app_dir
        self.ffmpeg = find_binary("ffmpeg", app_dir)
        self.ffprobe = find_binary("ffprobe", app_dir)
        self._nvenc_ok: Optional[bool] = None
        self._nvenc_error: str = ""
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def binaries_ok(self) -> bool:
        return bool(self.ffmpeg and self.ffprobe)

    def get_duration(self, path: str) -> float:
        if not self.ffprobe:
            return 0.0
        try:
            p = subprocess.run(
                [
                    self.ffprobe,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
                creationflags=creation_flags(),
            )
            if p.returncode == 0:
                return max(0.0, float((p.stdout or "0").strip()))
        except Exception:
            pass
        return 0.0

    def nvenc_works(self, force_recheck: bool = False) -> bool:
        if self._nvenc_ok is not None and not force_recheck:
            return self._nvenc_ok
        if not self.ffmpeg:
            self._nvenc_ok = False
            self._nvenc_error = "FFmpeg не найден"
            return False
        try:
            listed = subprocess.run(
                [self.ffmpeg, "-hide_banner", "-encoders"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                creationflags=creation_flags(),
            )
            if listed.returncode != 0 or "h264_nvenc" not in (listed.stdout or ""):
                self._nvenc_ok = False
                self._nvenc_error = "h264_nvenc отсутствует в этой сборке FFmpeg"
                return False

            # Same initialization test that was manually verified on the target
            # RTX 3050. Keep it stable: batch mode reuses this cached result.
            p = subprocess.run(
                [
                    self.ffmpeg,
                    "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30",
                    "-t", "0.20",
                    "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "18",
                    "-f", "null", "-",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                creationflags=creation_flags(),
            )
            self._nvenc_ok = p.returncode == 0
            self._nvenc_error = "" if self._nvenc_ok else (p.stderr or "NVENC initialization failed")[-2000:]
        except Exception as exc:
            self._nvenc_ok = False
            self._nvenc_error = str(exc)
        return self._nvenc_ok

    @property
    def nvenc_error(self) -> str:
        return self._nvenc_error

    @staticmethod
    def _x264_settings(quality: str) -> list[str]:
        if quality == "Very high":
            return ["-preset", "fast", "-crf", "16"]
        if quality == "Small file":
            return ["-preset", "medium", "-crf", "22"]
        return ["-preset", "fast", "-crf", "18"]

    @staticmethod
    def _nvenc_settings(quality: str) -> list[str]:
        cq = "16" if quality == "Very high" else ("21" if quality == "Small file" else "18")
        preset = "p6" if quality == "Very high" else ("p4" if quality == "Small file" else "p5")
        return ["-preset", preset, "-cq", cq]

    def resolve_encoder(self, options: RenderOptions) -> tuple[bool, str, str]:
        """Resolve the encoder once. Returns (use_nvenc, label, error)."""
        requested = options.encoder
        if requested == "CPU (x264)":
            return False, "CPU x264", ""

        nvenc_ok = self.nvenc_works()
        if requested == "NVIDIA NVENC" and not nvenc_ok:
            error = self._nvenc_error or "NVIDIA NVENC не смог инициализироваться."
            return False, "", error
        if requested == "NVIDIA NVENC" or (requested == "Auto (RTX/NVENC)" and nvenc_ok):
            return True, "NVIDIA NVENC", ""
        return False, "CPU x264", ""

    @staticmethod
    def _filter_complex(options: RenderOptions) -> str:
        top_h, bottom_h = layout_heights(options.ratio)
        return (
            f"[0:v]setpts=PTS-STARTPTS,"
            f"scale=1080:{top_h}:force_original_aspect_ratio=increase,"
            f"crop=1080:{top_h},setsar=1[top];"
            f"[1:v]setpts=PTS-STARTPTS,"
            f"scale=1080:{bottom_h}:force_original_aspect_ratio=increase,"
            f"crop=1080:{bottom_h},setsar=1[bottom];"
            f"[top][bottom]vstack=inputs=2:shortest=1,format=yuv420p[v]"
        )

    @staticmethod
    def _segment_filter_complex(options: RenderOptions, segment_duration: float) -> str:
        """Filter for batch clips with an exact tail->start bottom wrap.

        Input 1 is the finite tail beginning at bottom_start. Input 2 is the same
        bottom file looped forever from 0. concat therefore yields:
        [bottom_start..end] + [0..end] + [0..end] + ...
        The final trim limits it to the requested clip duration.
        """
        top_h, bottom_h = layout_heights(options.ratio)
        dur = max(0.001, float(segment_duration))
        return (
            f"[0:v]setpts=PTS-STARTPTS,"
            f"scale=1080:{top_h}:force_original_aspect_ratio=increase,"
            f"crop=1080:{top_h},setsar=1[top];"
            f"[1:v]setpts=PTS-STARTPTS[btail];"
            f"[2:v]setpts=PTS-STARTPTS[bloop];"
            f"[btail][bloop]concat=n=2:v=1:a=0,"
            f"trim=duration={dur:.6f},setpts=PTS-STARTPTS,"
            f"scale=1080:{bottom_h}:force_original_aspect_ratio=increase,"
            f"crop=1080:{bottom_h},setsar=1[bottom];"
            f"[top][bottom]vstack=inputs=2:shortest=1,format=yuv420p[v]"
        )

    def _append_encoder(self, cmd: list[str], options: RenderOptions, use_nvenc: bool) -> None:
        if use_nvenc:
            cmd += ["-c:v", "h264_nvenc", *self._nvenc_settings(options.quality)]
        else:
            cmd += ["-c:v", "libx264", *self._x264_settings(options.quality)]

    def build_command(
        self,
        main: str,
        bottom: str,
        output: str,
        options: RenderOptions,
        use_nvenc: bool,
    ) -> list[str]:
        """Original single-video command. Kept intentionally stable."""
        if not self.ffmpeg:
            raise RuntimeError("FFmpeg не найден")
        cmd = [
            self.ffmpeg,
            "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", main,
            "-stream_loop", "-1", "-i", bottom,
            "-filter_complex", self._filter_complex(options),
            "-map", "[v]", "-map", "0:a?",
        ]
        self._append_encoder(cmd, options, use_nvenc)
        cmd += [
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-shortest",
            "-progress", "pipe:1", "-nostats",
            output,
        ]
        return cmd

    def build_segment_command(
        self,
        main: str,
        bottom: str,
        output: str,
        options: RenderOptions,
        use_nvenc: bool,
        main_start: float,
        segment_duration: float,
        bottom_start: float,
    ) -> list[str]:
        """Build one batch clip while preserving the continuous bottom timeline.

        The bottom input is infinitely looped and seeked to (main_start % bottom_duration).
        If the requested clip crosses the physical end of the bottom file, FFmpeg
        continues from its beginning without restarting the output segment.
        """
        if not self.ffmpeg:
            raise RuntimeError("FFmpeg не найден")
        if segment_duration <= 0:
            raise ValueError("Длительность сегмента должна быть больше нуля")

        cmd = [
            self.ffmpeg,
            "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-ss", f"{max(0.0, main_start):.6f}", "-i", main,
            # Finite tail from the exact global bottom position.
            "-ss", f"{max(0.0, bottom_start):.6f}", "-i", bottom,
            # Infinite full-file loop used after the tail reaches EOF.
            "-stream_loop", "-1", "-i", bottom,
            "-filter_complex", self._segment_filter_complex(options, segment_duration),
            "-map", "[v]", "-map", "0:a?",
        ]
        self._append_encoder(cmd, options, use_nvenc)
        cmd += [
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-t", f"{segment_duration:.6f}",
            "-shortest",
            "-progress", "pipe:1", "-nostats",
            output,
        ]
        return cmd

    def cancel(self) -> None:
        with self._lock:
            proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    def _run_process(
        self,
        cmd: list[str],
        output: str,
        duration: float,
        on_metrics: Callable[[float, float], None],
    ) -> tuple[bool, str]:
        stderr = ""
        code = -1
        last_progress = 0.0
        last_speed = 0.0
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags(),
            )
            with self._lock:
                self._proc = proc

            if proc.stdout:
                for raw_line in proc.stdout:
                    line = raw_line.strip()
                    if line.startswith("out_time=") and duration > 0:
                        current = parse_ffmpeg_time(line.split("=", 1)[1])
                        last_progress = min(0.995, max(0.0, current / duration))
                        on_metrics(last_progress, last_speed)
                    elif line.startswith("speed="):
                        last_speed = parse_ffmpeg_speed(line.split("=", 1)[1])
                        on_metrics(last_progress, last_speed)
                    elif line == "progress=end":
                        last_progress = 1.0
                        on_metrics(1.0, last_speed)
            stderr = proc.stderr.read() if proc.stderr else ""
            code = proc.wait()
        except Exception as exc:
            stderr = str(exc)
            code = -1
        finally:
            with self._lock:
                self._proc = None

        ok = code == 0 and Path(output).is_file() and Path(output).stat().st_size > 0
        if ok:
            on_metrics(1.0, last_speed)
            return True, ""

        try:
            if Path(output).exists():
                Path(output).unlink()
        except Exception:
            pass
        return False, (stderr[-5000:] if stderr else "FFmpeg завершился с ошибкой.")

    def render(
        self,
        main: str,
        bottom: str,
        output: str,
        options: RenderOptions,
        on_progress: Callable[[float], None],
        on_status: Callable[[str], None],
    ) -> tuple[bool, str, str]:
        """Single-video mode. Returns (ok, encoder_label, error_text)."""
        if not self.ffmpeg:
            return False, "", "FFmpeg не найден."

        duration = self.get_duration(main)
        requested = options.encoder
        use_nvenc, encoder_label, resolve_error = self.resolve_encoder(options)
        if resolve_error:
            return False, "", resolve_error

        attempts = [use_nvenc]
        # Preserve v4.4 behavior: Auto may fall back to CPU for this one file.
        if requested == "Auto (RTX/NVENC)" and use_nvenc:
            attempts.append(False)

        first_error = ""
        for attempt_index, nvenc in enumerate(attempts):
            label = "NVIDIA NVENC" if nvenc else "CPU x264"
            if attempt_index:
                on_status("NVENC не запустился на этом файле. Повторяем через CPU…")
                on_progress(0.0)
            else:
                on_status(f"Рендер: {label}")

            cmd = self.build_command(main, bottom, output, options, nvenc)
            ok, error = self._run_process(
                cmd,
                output,
                duration,
                on_metrics=lambda progress, _speed: on_progress(progress),
            )
            if ok:
                return True, label, ""
            if not first_error:
                first_error = error

        return False, "", first_error or "FFmpeg завершился с ошибкой."

    def render_segment(
        self,
        main: str,
        bottom: str,
        output: str,
        options: RenderOptions,
        use_nvenc: bool,
        main_start: float,
        segment_duration: float,
        bottom_start: float,
        on_metrics: Callable[[float, float], None],
    ) -> tuple[bool, str]:
        """Render one batch segment with an encoder already resolved for the queue."""
        cmd = self.build_segment_command(
            main=main,
            bottom=bottom,
            output=output,
            options=options,
            use_nvenc=use_nvenc,
            main_start=main_start,
            segment_duration=segment_duration,
            bottom_start=bottom_start,
        )
        return self._run_process(cmd, output, segment_duration, on_metrics)

    def make_preview_png(self, video_path: str, output_png: str, width: int, height: int) -> bool:
        if not self.ffmpeg or not Path(video_path).is_file():
            return False
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )
        try:
            p = subprocess.run(
                [
                    self.ffmpeg,
                    "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-ss", "0.2", "-i", video_path,
                    "-frames:v", "1", "-vf", vf,
                    output_png,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=20,
                creationflags=creation_flags(),
            )
            return p.returncode == 0 and Path(output_png).is_file()
        except Exception:
            return False
