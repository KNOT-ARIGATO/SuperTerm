# SuperTerm

Serial / Telnet / SSH terminal and log viewer for Windows, built for board
bring-up and production testing. One portable `SuperTerm.exe` — nothing to install.

- **Terminal view** – type directly like Tera Term (VT100/xterm, Ctrl+C, arrows,
  select = copy, right-click = paste, BREAK, scrollback)
- **Log view** – line log with filter, PASS / FAIL / warning colours and your own highlight words;
  **every connection is saved to a time-stamped log file automatically**
- **Hex view** – raw bytes received (RX) and sent (TX)
- **Quick commands** – **group → tab → command**, per protocol; edit mode; import from the
  old SuperSerial `quick_commands.json`; export / import between PCs
- **Test sequences** – send → wait for expected text → PASS / FAIL, results appended to CSV
- **Serial** – friendly port names (e.g. `COM7 — USB-SERIAL CH340`), new-port detection,
  **auto-reconnect** after unplug / reboot, **XMODEM / YMODEM** file send (U-Boot `loady`)
- **Connection profiles**, several windows at once, **ไทย / English** switch (🌐 button)
- **Self-update** from GitHub Releases (Stable or Beta channel)

Settings: `%APPDATA%\SuperTerm` (kept across updates). Logs: `Documents\SuperTerm Logs`.

## ภาษาไทย — ใช้งาน
1. ดาวน์โหลด `SuperTerm.exe` จากหน้า **Releases** แล้วดับเบิลคลิก (Windows 10/11 64-bit)
2. ถ้า Windows เตือน ให้กด *More info → Run anyway* (ไฟล์ยังไม่ได้เซ็นดิจิทัล)
3. ปุ่ม **🌐** มุมขวาบนสลับภาษาไทย / อังกฤษได้ทันที
4. เวอร์ชันใหม่: โปรแกรมเช็กเองวันละ ~2 ครั้ง ถ้ามีจะขึ้นปุ่ม **⬆ Update vX.Y.Z** ที่มุมบน
   (หรือ ช่วยเหลือ → ตรวจหาอัปเดต)
5. พบปัญหา: ช่วยเหลือ → แจ้งปัญหา… (เปิดหน้า GitHub Issue พร้อมเวอร์ชันและ crash.log ให้)

## Build & test locally
```powershell
python -m pip install -r requirements-build.txt
python -m pytest -q tests                                # all tests (offscreen GUI)
powershell -ExecutionPolicy Bypass -File build.ps1      # -> dist\SuperTerm.exe
dist\SuperTerm.exe --selftest                           # result in %APPDATA%\SuperTerm\selftest.txt
```

## Release a new version (ออกเวอร์ชันใหม่)
1. Change `APP_VERSION` in `app.py`, e.g. `"1.2.0"` (beta: `"1.2.0-beta.1"`)
2. Commit and push, then tag:
   ```powershell
   git commit -am "SuperTerm 1.2.0"
   git tag v1.2.0
   git push --follow-tags
   ```
3. GitHub Actions (`.github/workflows/release.yml`) runs the tests, builds the exe, self-tests
   it and publishes **SuperTerm.exe** + **SuperTerm.exe.sha256** as a Release.
   Tags with a `-` (e.g. `v1.2.0-beta.1`) become **pre-releases**: only PCs set to the
   **Beta** channel (Settings → Updates) get them.
   The tag must match `APP_VERSION`, otherwise the build stops.

Every push to `main` also runs the tests (`.github/workflows/ci.yml`).

## Code signing (optional)
Unsigned exes trigger SmartScreen. To sign releases automatically, add two repository
secrets: `SIGN_PFX_BASE64` (base64 of a code-signing `.pfx`) and `SIGN_PFX_PASSWORD`.
The release workflow then signs `SuperTerm.exe` with `signtool` before publishing.
Free signing for open-source projects is available from e.g. SignPath Foundation.

## Self-update
- `updater.py` → `GITHUB_REPO = "KNOT-ARIGATO/SuperTerm"`.
- Releases must be **public** — an exe cannot keep a secret token.
- IT roll-out without clicking: `SuperTerm.exe --apply-update NEW\SuperTerm.exe`

## Files
| File | Purpose |
|---|---|
| `app.py` | main window, log / hex views, quick commands UI, updates UI |
| `sessions.py` | Serial / Telnet / SSH connections (no GUI) |
| `terminal.py` | Tera Term–style terminal widget |
| `quickstore.py` | quick commands: groups → tabs → commands, import / export |
| `testrunner.py` | test sequences engine + CSV |
| `xmodem.py` | XMODEM / XMODEM-1K / YMODEM sender |
| `logwriter.py` | automatic log files |
| `profiles.py` | saved connection profiles |
| `panels.py` | Settings, Test sequences and File transfer windows |
| `i18n.py` | Thai / English texts |
| `updater.py` | GitHub Releases check, download, verify, swap |
| `tests/` | pytest suite (runs in CI) |

Third-party licences: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
