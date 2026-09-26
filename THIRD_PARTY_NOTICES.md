# Third-party notices

TikTok Split Maker is authored by **kiomi** in collaboration with **ChatGPT, OpenAI**.
OpenAI is not the copyright owner of this project or of the third-party software listed below.

## FFmpeg

Release builds bundle the Windows **FFmpeg 9.0.2 Essentials** static build published by Gyan Doshi.

- FFmpeg project: https://ffmpeg.org/
- Windows build provider: https://www.gyan.dev/ffmpeg/builds/
- Download alias: `ffmpeg-release-essentials.zip`
- Resolved release: `ffmpeg-9.0.2-essentials_build.zip`
- Archive SHA-256: `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`
- Corresponding FFmpeg source commit: `946fcce07b6dcd0331c8cc609192aeff5e1924f8`
- Source: https://github.com/FFmpeg/FFmpeg/commit/946fcce07b6dcd0331c8cc609192aeff5e1924f8

Gyan's static Windows builds are distributed under **GNU GPL v3**. The GitHub release workflow publishes an FFmpeg source archive next to the application binary. FFmpeg and its bundled third-party components remain copyright of their respective authors.

## Python

The standalone Windows executable contains the CPython runtime. Python is distributed under the Python Software Foundation License Version 2 and other compatible historical licenses.

- https://www.python.org/
- https://docs.python.org/3/license.html

## Pillow

Pillow is used for preview/image processing and is distributed under the MIT-CMU license.

- https://python-pillow.github.io/
- https://github.com/python-pillow/Pillow/blob/main/LICENSE

## tkinterdnd2 / TkDND

`tkinterdnd2` and TkDND provide native drag-and-drop integration for Tkinter. Their original license notices remain available from their upstream projects.

- https://pypi.org/project/tkinterdnd2/
- https://github.com/pmgagne/tkinterdnd2
- https://github.com/petasis/tkdnd

## PyInstaller

The Windows release is packaged with PyInstaller. PyInstaller is GPL-2.0-or-later with a bootloader exception that permits distribution of the generated executable.

- https://pyinstaller.org/
- https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt

## Project license

TikTok Split Maker itself is distributed under **GNU GPL v3.0**. See `LICENSE`.
