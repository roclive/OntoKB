# Bundled components

npocut source is MIT licensed (see LICENSE). The Windows distribution also includes:

- Electron and Chromium: licenses in LICENSE.electron.txt and LICENSES.chromium.html beside npocut.exe. Source: https://github.com/electron/electron (v44.5.1).
- CPython 3.13.12: Python Software Foundation license, included in runtime/python/LICENSE.txt. Source: https://www.python.org/downloads/release/python-31312/.
- faster-whisper 1.2.1 (MIT) and its dependencies: license files and metadata are included in runtime/python/Lib/site-packages. Source: https://github.com/SYSTRAN/faster-whisper/tree/v1.2.1.
- Microsoft Visual C++ runtime 14.44.35112, supplied by msvc-runtime: redistribution notice included in runtime/python/Lib/site-packages/msvc_runtime-14.44.35112.dist-info/licenses/LICENSE.
- ffmpeg-static 5.3.0 and ffprobe-static 3.1.0 supply the Windows FFmpeg/FFprobe executables, distributed under their respective FFmpeg build licenses (including GPL components). Notices are in runtime/licenses. Build and source information: https://github.com/eugeneware/ffmpeg-static and https://github.com/derhuerst/ffmpeg-static/releases and https://github.com/joshwnj/ffprobe-static. FFmpeg source: https://ffmpeg.org/download.html.

Whisper model weights are downloaded separately on first transcription into the user's application data directory; they are not part of the installer.

The bundled FFmpeg Windows binary is Gyan's 6.1.1 essentials GPL v3 build. Its exact upstream source revision and build configuration are recorded in runtime/licenses/ffmpeg.exe.README. The FFprobe binary is 4.0.2 (GPL v3); corresponding upstream source is https://github.com/FFmpeg/FFmpeg/tree/n4.0.2.
