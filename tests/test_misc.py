import hashlib
import http.server
import json
import os
import threading

import logwriter
import profiles
import updater as U


def test_versions_and_beta():
    assert U.parse_version("v1.2.0") > U.parse_version("v1.2.0-beta.3") > U.parse_version("1.2.0-beta.1")
    assert U.is_newer("v1.1.0", "1.0.2") and not U.is_newer("v1.0.2", "1.0.2")
    rel = U._pick_beta([{"tag_name": "v1.0.2"}, {"tag_name": "v1.1.0-beta.2"},
                        {"tag_name": "v1.1.0-beta.9", "draft": True}])
    assert rel["tag_name"] == "v1.1.0-beta.2"


def test_check_fetch_install_with_local_server(tmp_path, monkeypatch):
    blob = b"MZ" + os.urandom(1_100_000)
    sha = hashlib.sha256(blob).hexdigest()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            base = f"http://127.0.0.1:{srv.server_port}"
            body = {"/repos/o/r/releases/latest": json.dumps({"tag_name": "v9.0.0", "assets": [
                        {"name": "SuperTerm.exe", "browser_download_url": base + "/exe"},
                        {"name": "SuperTerm.exe.sha256", "browser_download_url": base + "/sha"}]}).encode(),
                    "/exe": blob, "/sha": f"{sha}  SuperTerm.exe".encode()}.get(self.path)
            self.send_response(200 if body else 404)
            self.end_headers()
            if body:
                self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(U, "API_BASE", f"http://127.0.0.1:{srv.server_port}")
    info = U.check_latest("o/r")
    path = U.fetch(info)
    target = tmp_path / "SuperTerm.exe"
    target.write_bytes(b"OLD")
    old = U.install(path, target=str(target), restart=False)
    assert target.read_bytes() == blob and open(old, "rb").read() == b"OLD"
    U.cleanup_old(str(target))
    assert not os.path.exists(old)
    srv.shutdown()


def test_logwriter(tmp_path):
    w = logwriter.LogWriter(str(tmp_path), "Serial COM7 @ 115200")
    w.write("boot ok")
    w.write("TX → mfg", True)
    w.close()
    text = open(w.path, encoding="utf-8").read()
    assert "Serial_COM7_@_115200" in os.path.basename(w.path)
    assert "] boot ok" in text and "] # TX → mfg" in text and text.count("\n") == 4


def test_profiles(tmp_path):
    s = profiles.ProfileStore(str(tmp_path / "p.json"))
    s.put("ssh", "board", {"host": "10.0.0.2", "port": "22", "user": "root", "password": "no!"})
    s2 = profiles.ProfileStore(str(tmp_path / "p.json"))
    assert s2.get("ssh", "board") == {"name": "board", "host": "10.0.0.2", "port": "22", "user": "root"}
    s2.delete("ssh", "board")
    assert profiles.ProfileStore(str(tmp_path / "p.json")).names("ssh") == []
