"""Self-update from GitHub Releases (no GUI imports).

How it works
  1. GET https://api.github.com/repos/<GITHUB_REPO>/releases/latest
  2. newer tag than APP_VERSION?  → download the release asset SuperTerm.exe
     (+ SuperTerm.exe.sha256, written by the GitHub Actions workflow) and verify it
  3. rename the running exe to SuperTerm.exe.old (Windows allows renaming a
     running program), move the new exe into its place, start it, quit.
     The .old file is deleted on the next start.

Set GITHUB_REPO below (e.g. "my-account/SuperTerm") to switch updates on.
The repository (or at least its Releases) must be public: an exe cannot keep a
secret token, so private repositories are not supported for self-update.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

GITHUB_REPO = "KNOT-ARIGATO/SuperTerm"     # "owner/repo" — empty = update check disabled
ASSET_NAME = "SuperTerm.exe"
API_BASE = os.environ.get("SUPERTERM_UPDATE_API", "https://api.github.com")   # override for tests


class UpdateError(Exception):
    pass


def configured():
    return bool(GITHUB_REPO.strip())


def parse_version(text):
    nums = [int(n) for n in re.findall(r"\d+", text or "")[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(latest, current):
    return parse_version(latest) > parse_version(current)


def _open(url, timeout):
    req = urllib.request.Request(url, headers={
        "User-Agent": "SuperTerm-updater",
        "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)    # uses the Windows proxy settings


def check_latest(repo=None, timeout=8):
    """Latest release info: dict(version, name, notes, exe_url, sha_url, page)."""
    repo = (repo or GITHUB_REPO).strip()
    if not repo:
        raise UpdateError("The update source (GitHub repository) is not configured yet.")
    try:
        with _open(f"{API_BASE}/repos/{repo}/releases/latest", timeout) as r:
            rel = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError("No release found — or the repository is private.")
        if e.code == 403:
            raise UpdateError("GitHub refused the request (rate limit) — try again later.")
        raise UpdateError(f"GitHub answered HTTP {e.code}.")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise UpdateError(f"Cannot reach GitHub: {getattr(e, 'reason', e)}")
    assets = {a.get("name"): a.get("browser_download_url") for a in rel.get("assets", [])}
    return {
        "version": rel.get("tag_name", ""),
        "name": rel.get("name") or rel.get("tag_name", ""),
        "notes": rel.get("body") or "",
        "exe_url": assets.get(ASSET_NAME),
        "sha_url": assets.get(ASSET_NAME + ".sha256"),
        "page": rel.get("html_url", ""),
    }


def _download(url, dest, progress=None, cancelled=None, timeout=30):
    try:
        with _open(url, timeout) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancelled and cancelled():
                    raise UpdateError("Cancelled.")
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(f"Download failed: {getattr(e, 'reason', e)}")
    return dest


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(info, progress=None, cancelled=None):
    """Download + verify the new exe. Returns the path of the downloaded file."""
    if not info.get("exe_url"):
        raise UpdateError(f"The release has no {ASSET_NAME} attached.")
    folder = tempfile.mkdtemp(prefix="superterm_update_")
    dest = _download(info["exe_url"], os.path.join(folder, ASSET_NAME), progress, cancelled)
    with open(dest, "rb") as f:
        if f.read(2) != b"MZ" or os.path.getsize(dest) < 1_000_000:
            raise UpdateError("The downloaded file is not a valid SuperTerm.exe.")
    if info.get("sha_url"):
        sha_file = _download(info["sha_url"], dest + ".sha256")
        with open(sha_file, "r", encoding="ascii", errors="ignore") as f:
            m = re.search(r"\b([0-9a-fA-F]{64})\b", f.read())
        if not m or m.group(1).lower() != sha256_of(dest):
            raise UpdateError("The downloaded file is damaged (checksum mismatch). Nothing was changed.")
    return dest


def running_exe():
    """Path of the running SuperTerm.exe, or None when running from source."""
    return sys.executable if getattr(sys, "frozen", False) else None


def install(new_exe, target=None, restart=True):
    """Put new_exe in place of the running exe (keeps it as .old) and restart."""
    target = target or running_exe()
    if not target:
        raise UpdateError("Self-update works only in the built SuperTerm.exe.")
    old = target + ".old"
    try:
        if os.path.exists(old):
            os.remove(old)
    except OSError:
        old = f"{target}.{int(time.time())}.old"
    try:
        os.replace(target, old)                 # renaming a running exe is allowed on Windows
    except OSError as e:
        raise UpdateError(f"Cannot replace {target} — is the folder read-only? ({e})")
    try:
        shutil.move(new_exe, target)
    except OSError as e:
        os.replace(old, target)                  # roll back: the old program stays untouched
        raise UpdateError(f"Could not put the new version in place: {e}")
    if restart:
        env = dict(os.environ)
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"   # start as an independent PyInstaller app
        env.pop("_MEIPASS2", None)
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([target], env=env, close_fds=True, creationflags=flags,
                         cwd=os.path.dirname(target) or None)
    return old


def cleanup_old(target=None):
    """Delete the .old copies left by a previous update (silently)."""
    target = target or running_exe()
    if not target:
        return
    folder, base = os.path.split(target)
    try:
        for name in os.listdir(folder or "."):
            if name.startswith(base + ".") and name.endswith(".old"):
                try:
                    os.remove(os.path.join(folder, name))
                except OSError:
                    pass                          # still running? try again next time
    except OSError:
        pass
