# Release checklist

1. Push the project to `kiomi1301/tiktok-split-maker`.
2. Confirm the Windows build workflow passes.
3. Download the workflow artifact and test `TikTok Split Maker.exe` on a Windows machine without Python or FFmpeg in PATH.
4. Verify Single mode, Multi mode, drag & drop, EN/RU switching, CPU x264 fallback and NVIDIA NVENC when available.
5. Scan the exact release EXE with Microsoft Defender and VirusTotal. Generic heuristic detections can still occur on unsigned one-file applications; do not claim 0/70 unless the exact release binary actually gets that result.
6. Create/push tag `v1.0.0`. The workflow publishes the EXE, SHA-256, license/notices and FFmpeg source archive.
7. Keep the repository source at the same tag as the release binary.

A code-signing certificate is the reliable next step if Windows SmartScreen/reputation becomes important.
