from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def test_required_files():
    required = [
        "main.py", "engine.py", "i18n.py", "version.py", "LICENSE",
        "README.md", "README_RU.md", "THIRD_PARTY_NOTICES.md",
        "requirements.txt", "requirements-build.txt", "hook-tkinterdnd2.py",
        "prepare_ffmpeg.ps1", "build_release.bat", "version_info.txt",
        "assets/icon.ico", "assets/icon.png", "assets/flag_us.png", "assets/flag_ru.png",
        ".github/workflows/build-release.yml",
    ]
    missing = [p for p in required if not (ROOT / p).is_file()]
    assert not missing, f"Missing release files: {missing}"


def test_dependencies_are_pinned():
    runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    build = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")
    assert "tkinterdnd2==0.6.3" in runtime
    assert "Pillow==12.3.0" in runtime
    assert "PyInstaller==6.22.3" in build
    assert "-r requirements.txt" in build


def test_tkinterdnd2_hook_collects_native_files():
    hook = (ROOT / "hook-tkinterdnd2.py").read_text(encoding="utf-8")
    assert 'collect_all("tkinterdnd2")' in hook
    assert "datas, binaries, hiddenimports" in hook


def test_autonomous_build_contract():
    build = (ROOT / "build_release.bat").read_text(encoding="utf-8")
    assert "--onefile" in build
    assert "--noupx" in build
    assert "ffmpeg.exe;ffmpeg\\bin" in build
    assert "ffprobe.exe;ffmpeg\\bin" in build
    assert '--additional-hooks-dir "."' in build
    assert "--key" not in build.lower()


def test_workflow_contract():
    workflow = (ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8")
    assert 'python-version: "3.12.10"' in workflow
    assert "requirements-build.txt" in workflow
    assert "FFmpeg-9.0.2-source.zip" in workflow
    assert "TikTok Split Maker.exe" in workflow


def test_ffmpeg_is_pinned():
    prep = (ROOT / "prepare_ffmpeg.ps1").read_text(encoding="utf-8")
    assert "ffmpeg-9.0.2-essentials_build.zip" in prep
    assert "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba" in prep


def test_authorship_and_license():
    for name in ("README.md", "README_RU.md", "THIRD_PARTY_NOTICES.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "kiomi" in text
        assert "ChatGPT" in text and "OpenAI" in text
    assert "GNU GENERAL PUBLIC LICENSE" in (ROOT / "LICENSE").read_text(encoding="utf-8")


if __name__ == "__main__":
    for name, fn in sorted(globals().copy().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("release layout tests: OK")
