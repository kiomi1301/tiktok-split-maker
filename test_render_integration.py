from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from engine import RenderOptions, VideoEngine


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-4000:])


def main():
    root = Path(__file__).resolve().parent
    engine = VideoEngine(root)
    assert engine.binaries_ok(), "FFmpeg/ffprobe unavailable for integration test"

    with tempfile.TemporaryDirectory(prefix="tsm_integration_") as td:
        td = Path(td)
        main_video = td / "main.mp4"
        bottom_video = td / "bottom.mp4"
        single_out = td / "single.mp4"
        segment_out = td / "segment.mp4"

        run([
            engine.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=4.2",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4.2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(main_video),
        ])
        run([
            engine.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "smptebars=size=640x360:rate=30",
            "-t", "1.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(bottom_video),
        ])

        opts = RenderOptions(ratio="65/35", quality="Small file", encoder="CPU (x264)")
        progress = []
        ok, encoder_label, error = engine.render(
            str(main_video), str(bottom_video), str(single_out), opts,
            on_progress=lambda p: progress.append(p),
            on_status=lambda _s: None,
        )
        assert ok, error
        assert encoder_label == "CPU x264"
        assert single_out.exists() and single_out.stat().st_size > 0
        assert engine.get_duration(str(single_out)) > 4.0
        assert progress and progress[-1] >= 0.99

        metrics = []
        ok, error = engine.render_segment(
            main=str(main_video),
            bottom=str(bottom_video),
            output=str(segment_out),
            options=opts,
            use_nvenc=False,
            main_start=1.0,
            segment_duration=2.5,
            bottom_start=1.0,
            on_metrics=lambda p, speed: metrics.append((p, speed)),
        )
        assert ok, error
        assert segment_out.exists() and segment_out.stat().st_size > 0
        duration = engine.get_duration(str(segment_out))
        assert 2.35 <= duration <= 2.65, duration
        assert metrics and metrics[-1][0] >= 0.99

    print("render integration: OK")


if __name__ == "__main__":
    main()
