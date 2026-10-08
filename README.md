# SuperTerm

Serial / Telnet / SSH terminal and log viewer for Windows, with quick commands
per protocol and an RTSP camera test window. One portable `SuperTerm.exe` —
nothing to install.

- **Log view** – line log with filter and PASS / FAIL / warning colours
- **Terminal view** – type directly like Tera Term (VT100/xterm, Ctrl+C, arrows,
  select = copy, right-click = paste, BREAK, scrollback)
- **Quick commands** – tabs per protocol, import from the old SuperSerial
  `quick_commands.json`, export / import between PCs
- **Self-update** – checks GitHub Releases and replaces itself

Settings live in `%APPDATA%\SuperTerm` (kept across updates).

## ภาษาไทย — ใช้งาน
1. ดาวน์โหลด `SuperTerm.exe` จากหน้า **Releases** แล้วดับเบิลคลิก (Windows 10/11 64-bit)
2. ถ้า Windows เตือน ให้กด *More info → Run anyway* (ไฟล์ยังไม่ได้เซ็นดิจิทัล)
3. เวอร์ชันใหม่: โปรแกรมเช็กเองวันละ ~2 ครั้ง ถ้ามีจะขึ้นปุ่ม **⬆ Update vX.Y.Z** ที่มุมบน

## Build locally
```powershell
python -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File build.ps1      # -> dist\SuperTerm.exe
dist\SuperTerm.exe --selftest                           # result in %APPDATA%\SuperTerm\selftest.txt
```

## Release a new version (ออกเวอร์ชันใหม่)
1. Change `APP_VERSION` in `app.py`, e.g. `"1.1.0"`
2. Commit and push, then tag:
   ```powershell
   git commit -am "SuperTerm 1.1.0"
   git tag v1.1.0
   git push --follow-tags
   ```
3. GitHub Actions (`.github/workflows/release.yml`) builds the exe, runs the
   self-test and publishes **SuperTerm.exe** + **SuperTerm.exe.sha256** as a Release.
   The tag must match `APP_VERSION`, otherwise the build stops.

## Self-update setup (ครั้งเดียว)
- In `updater.py` set `GITHUB_REPO = "your-account/SuperTerm"` and release once.
- The repository's Releases must be **public** — an exe cannot keep a secret
  token, so private repositories cannot be used for self-update.
- IT roll-out without clicking: `SuperTerm.exe --apply-update NEW\SuperTerm.exe`

## Files
| File | Purpose |
|---|---|
| `app.py` | main window, log, quick commands, updates UI |
| `sessions.py` | Serial / Telnet / SSH connections (no GUI) |
| `terminal.py` | Tera Term–style terminal widget |
| `quickstore.py` | quick-command storage, import / export |
| `updater.py` | GitHub Releases check, download, verify, swap |
| `nature.py` | theme icons |
| `build.ps1` | PyInstaller one-file build |

Third-party licences: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
