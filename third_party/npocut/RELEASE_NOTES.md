# npocut 0.2.0 — Windows Electron

- Windows 10/11 x64 desktop app with an NSIS installer and a portable ZIP.
- Bundled Python 3.13, FFmpeg/FFprobe, and faster-whisper; no separate Node.js or Python installation required.
- Load video/subtitle files from any folder, including paths containing Chinese characters or spaces.
- Run cutting, subtitle burning, and transcription inside the app with task logs and cancellation.
- Outputs and subtitle edits are saved to Documents\npocut. Original imported media is kept intact.
- First automatic transcription requires internet access to download Whisper model weights. Later uses reuse the cached model.

Download `npocut-0.2.0-windows-x64-setup.exe` to install, or extract the ZIP completely and run `npocut.exe`.

This release is not code-signed; Windows SmartScreen may show an unknown-publisher prompt. SHA256SUMS.txt contains download checksums.
