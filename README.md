# SuperTerm

Serial / Telnet / SSH terminal and log viewer for Windows, with quick commands
per protocol and an RTSP camera test window. One portable `SuperTerm.exe` â€”
nothing to install.

- **Log view** â€“ line log with filter and PASS / FAIL / warning colours
- **Terminal view** â€“ type directly like Tera Term (VT100/xterm, Ctrl+C, arrows,
  select = copy, right-click = paste, BREAK, scrollback)
- **Quick commands** â€“ tabs per protocol, import from the old SuperSerial
  `quick_commands.json`, export / import between PCs
- **Self-update** â€“ checks GitHub Releases and replaces itself

Settings live in `%APPDATA%\SuperTerm` (kept across updates).

## à¸ à¸²à¸©à¸²à¹„à¸—à¸¢ â€” à¹ƒà¸Šà¹‰à¸‡à¸²à¸™
1. à¸”à¸²à¸§à¸™à¹Œà¹‚à¸«à¸¥à¸” `SuperTerm.exe` à¸ˆà¸²à¸à¸«à¸™à¹‰à¸² **Releases** à¹à¸¥à¹‰à¸§à¸”à¸±à¸šà¹€à¸šà¸´à¸¥à¸„à¸¥à¸´à¸ (Windows 10/11 64-bit)
2. à¸–à¹‰à¸² Windows à¹€à¸•à¸·à¸­à¸™ à¹ƒà¸«à¹‰à¸à¸” *More info â†’ Run anyway* (à¹„à¸Ÿà¸¥à¹Œà¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¹„à¸”à¹‰à¹€à¸‹à¹‡à¸™à¸”à¸´à¸ˆà¸´à¸—à¸±à¸¥)
3. à¹€à¸§à¸­à¸£à¹Œà¸Šà¸±à¸™à¹ƒà¸«à¸¡à¹ˆ: à¹‚à¸›à¸£à¹à¸à¸£à¸¡à¹€à¸Šà¹‡à¸à¹€à¸­à¸‡à¸§à¸±à¸™à¸¥à¸° ~2 à¸„à¸£à¸±à¹‰à¸‡ à¸–à¹‰à¸²à¸¡à¸µà¸ˆà¸°à¸‚à¸¶à¹‰à¸™à¸›à¸¸à¹ˆà¸¡ **â¬† Update vX.Y.Z** à¸—à¸µà¹ˆà¸¡à¸¸à¸¡à¸šà¸™

## Build locally
```powershell
python -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File build.ps1      # -> dist\SuperTerm.exe
dist\SuperTerm.exe --selftest                           # result in %APPDATA%\SuperTerm\selftest.txt
```

## Release a new version (à¸­à¸­à¸à¹€à¸§à¸­à¸£à¹Œà¸Šà¸±à¸™à¹ƒà¸«à¸¡à¹ˆ)
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

## Self-update setup (à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§)
- In `updater.py` `GITHUB_REPO = "KNOT-ARIGATO/SuperTerm"` (already set) and release once.
- The repository's Releases must be **public** â€” an exe cannot keep a secret
  token, so private repositories cannot be used for self-update.
- IT roll-out without clicking: `SuperTerm.exe --apply-update NEW\SuperTerm.exe`

## Files
| File | Purpose |
|---|---|
| `app.py` | main window, log, quick commands, updates UI |
| `sessions.py` | Serial / Telnet / SSH connections (no GUI) |
| `terminal.py` | Tera Termâ€“style terminal widget |
| `quickstore.py` | quick-command storage, import / export |
| `updater.py` | GitHub Releases check, download, verify, swap |
| `nature.py` | theme icons |
| `build.ps1` | PyInstaller one-file build |

Third-party licences: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
