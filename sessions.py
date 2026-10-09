"""Connection layer (no GUI imports): one Session object per protocol.

Serial, Telnet and SSH all expose the same tiny interface so the UI never has
to care which one is active:

    s = SerialSession(...) / TelnetSession(...) / SshSession(...)
    s.start()          # connects in a worker thread
    s.send(b"...")     # -> (ok, error_text)
    s.resize(cols, rows)   # terminal size (SSH pty); no-op elsewhere
    s.stop()           # user disconnect

Callbacks (always invoked from the worker thread — the UI must marshal them):
    on_opened()                 session is up (first time only)
    on_line(text)               one received line (for the Log view)
    on_data(bytes)              raw received bytes (for the Terminal view)
    on_info(text, tag)          status message ("info"/"warn"/"error"/"success")
    on_closed(reason, error)    called exactly once when the session is over
"""
import platform
import re
import socket
import subprocess
import threading
import time

import serial

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[()][0-9A-Za-z]|\x1b[=>78]")
CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
IDLE_FLUSH_S = 0.5         # a line without newline (prompt) is shown after this much quiet


class LineBuffer:
    """Turn arbitrary byte chunks into complete lines (and flush idle prompts)."""

    def __init__(self, strip_ansi=True):
        self.buf = b""
        self.strip_ansi = strip_ansi

    def _decode(self, raw):
        text = raw.decode("utf-8", errors="replace").rstrip("\r")
        if "\r" in text:                       # progress bars: keep what is visible last
            text = text.rsplit("\r", 1)[-1]
        if self.strip_ansi:
            text = ANSI_RE.sub("", text)
        if "\b" in text:                       # apply backspaces (typing corrections)
            out = []
            for c in text:
                if c == "\b":
                    if out:
                        out.pop()
                else:
                    out.append(c)
            text = "".join(out)
        return CTRL_RE.sub("", text)           # other control characters are invisible

    def feed(self, data):
        self.buf += data
        *lines, self.buf = self.buf.split(b"\n")
        return [t for t in (self._decode(x) for x in lines) if t.strip()]

    def flush(self):
        """Pending partial line (e.g. a prompt without newline), or None."""
        raw, self.buf = self.buf, b""
        text = self._decode(raw) if raw else ""
        return text if text.strip() else None


# ── minimal Telnet option negotiation (what Tera Term does for us) ───────────
IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
OPT_ECHO, OPT_SGA = 1, 3


class TelnetFilter:
    """Strips Telnet commands from the stream and produces the replies:
    accept server ECHO + SUPPRESS-GO-AHEAD (character mode, server echoes),
    politely refuse everything else."""

    def __init__(self):
        self.state = 0
        self.cmd = 0
        self.answered = set()

    def feed(self, data):
        if self.state == 0 and IAC not in data:
            return data, b""
        out, reply = bytearray(), bytearray()
        for b in data:
            s = self.state
            if s == 0:
                if b == IAC:
                    self.state = 1
                else:
                    out.append(b)
            elif s == 1:                              # byte after IAC
                if b == IAC:
                    out.append(IAC)
                    self.state = 0
                elif b in (DO, DONT, WILL, WONT):
                    self.cmd, self.state = b, 2
                elif b == SB:
                    self.state = 3
                else:
                    self.state = 0                    # NOP, GA, …
            elif s == 2:                              # option byte
                key = (self.cmd, b)
                if key not in self.answered:
                    self.answered.add(key)
                    if self.cmd == WILL:
                        reply += bytes([IAC, DO if b in (OPT_ECHO, OPT_SGA) else DONT, b])
                    elif self.cmd == DO:
                        reply += bytes([IAC, WILL if b == OPT_SGA else WONT, b])
                self.state = 0
            elif s == 3:                              # inside sub-negotiation
                if b == IAC:
                    self.state = 4
            else:                                     # s == 4: IAC inside SB
                self.state = 0 if b == SE else 3
        return bytes(out), bytes(reply)


class Session:
    kind = "?"

    def __init__(self, on_line, on_info, on_opened, on_closed, on_data=None):
        self.on_line, self.on_info = on_line, on_info
        self.on_opened, self.on_closed = on_opened, on_closed
        self.on_data = on_data
        self.rx_hook = None         # when set (file transfer), received bytes go only here
        self.stop_evt = threading.Event()
        self._thread = None
        self._opened = False
        self._closed = False
        self._lock = threading.Lock()

    label = ""          # short text for the status pill

    # lifecycle ---------------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._guard, daemon=True)
        self._thread.start()

    def stop(self):
        self.stop_evt.set()
        self._close_io()

    def _guard(self):
        reason, error = "", False
        try:
            reason, error = self._run()
        except Exception as e:                      # never let a thread die silently
            reason, error = str(e), True
        finally:
            try:
                self._close_io()
            except Exception:
                pass
            if self.stop_evt.is_set():
                reason, error = "", False
            self._emit_closed(reason, error)

    def _emit_closed(self, reason, error):
        if not self._closed:
            self._closed = True
            self.on_closed(reason, error)

    def _mark_open(self):
        if not self._opened:
            self._opened = True
            self.on_opened()

    def _received(self, data, buf):
        """Fan raw bytes out to the terminal and complete lines to the log."""
        hook = self.rx_hook
        if hook is not None:
            hook(data)
            return
        if self.on_data:
            self.on_data(data)
        for line in buf.feed(data):
            self.on_line(line)

    # to be implemented -------------------------------------------------------
    def _run(self):
        raise NotImplementedError

    def _close_io(self):
        pass

    def send(self, data):
        return False, "not connected"

    def resize(self, cols, rows):
        pass


def list_ports():
    """[(device, description)] e.g. ("COM7", "USB-SERIAL CH340"), sorted by number."""
    import serial.tools.list_ports as lp
    out = []
    for p in lp.comports():
        desc = (p.description or "").strip()
        if desc.endswith(f"({p.device})"):
            desc = desc[: -len(p.device) - 2].strip()
        out.append((p.device, desc if desc and desc != "n/a" else ""))
    key = lambda d: (int(re.sub(r"\D", "", d[0]) or 0), d[0])
    return sorted(out, key=key)


# ══════════════════════════════════════════════════════════════
class SerialSession(Session):
    kind = "Serial"

    def __init__(self, port, baud, bytesize, parity, stopbits, auto_reconnect=False, **cb):
        super().__init__(**cb)
        self.port, self.baud = port, baud
        self.bytesize, self.parity, self.stopbits = bytesize, parity, stopbits
        self.auto_reconnect = auto_reconnect
        self.ser = None
        self.label = f"Serial  {port} @ {baud}"

    def _open(self):
        return serial.Serial(port=self.port, baudrate=self.baud, bytesize=self.bytesize,
                             parity=self.parity, stopbits=self.stopbits, timeout=0)

    def _wait_for_port(self):
        """USB-UART unplugged / board rebooting: retry until the port is back."""
        self.on_info(f"{self.port} lost — waiting for it to come back…", "warn")
        while not self.stop_evt.is_set():
            if any(d == self.port for d, _ in list_ports()):
                try:
                    self.ser = self._open()
                    self.on_info(f"Reconnected → {self.port} @ {self.baud}", "success")
                    return True
                except (serial.SerialException, OSError):
                    pass                       # driver not ready yet
            self.stop_evt.wait(1.0)
        return False

    def _run(self):
        try:
            self.ser = self._open()
        except (serial.SerialException, ValueError, OSError) as e:
            return str(e), True
        self._mark_open()
        buf, last = LineBuffer(), time.monotonic()
        while not self.stop_evt.is_set():
            ser = self.ser
            try:
                n = ser.in_waiting
                if n:
                    data = ser.read(n)
                    if self.stop_evt.is_set():
                        break
                    if data:
                        self._received(data, buf)
                        last = time.monotonic()
                else:
                    if buf.buf and time.monotonic() - last > IDLE_FLUSH_S:
                        pending = buf.flush()
                        if pending:
                            self.on_line(pending)
                    time.sleep(0.004)        # idle: don't spin the CPU
            except (serial.SerialException, OSError, AttributeError) as e:
                if self.stop_evt.is_set():
                    break
                self._close_io()
                if self.auto_reconnect and self._wait_for_port():
                    continue
                return f"Serial error — port disconnected ({e})", True
        return "", False

    def _close_io(self):
        ser, self.ser = self.ser, None
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    def send(self, data):
        ser = self.ser
        if ser is None:
            return False, "not connected"
        try:
            with self._lock:
                ser.write(data)
            return True, ""
        except (serial.SerialException, OSError) as e:
            return False, str(e)

    def send_break(self, duration=0.25):
        """Serial BREAK (Tera Term: Alt+B). Runs in a thread — it blocks."""
        ser = self.ser
        if ser is None:
            return False, "not connected"

        def go():
            try:
                with self._lock:
                    ser.send_break(duration)
            except Exception:
                pass
        threading.Thread(target=go, daemon=True).start()
        return True, ""


# ══════════════════════════════════════════════════════════════
class TelnetSession(Session):
    """Raw TCP / Telnet. Port 23 gets Telnet option negotiation (character mode
    with server echo, like Tera Term). Optional ping mode: wait for the host to
    answer ping, connect, and reconnect automatically whenever it comes back."""
    kind = "Telnet"

    def __init__(self, host, port, ping_mode=False, interval=2, **cb):
        super().__init__(**cb)
        self.host, self.port = host, port
        self.ping_mode, self.interval = ping_mode, interval
        self.sock = None
        self.label = f"Telnet  {host}:{port}"

    # -- helpers
    def _ping(self):
        windows = platform.system().lower() == "windows"
        cmd = (["ping", "-n", "1", "-w", "1000", self.host] if windows
               else ["ping", "-c", "1", "-W", "1", self.host])
        extra = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if windows else {}
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=3, **extra)
            if r.returncode != 0:
                return None
            m = re.search(r"time[=<]([\d.]+)\s*ms", r.stdout + r.stderr, re.I)
            return f"{m.group(1)} ms" if m else "?"
        except subprocess.TimeoutExpired:
            return None

    def _connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((self.host, self.port))
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # snappy key echo
        s.settimeout(IDLE_FLUSH_S)
        return s

    def _read(self, sock):
        """Blocking read loop for one socket. Returns the reason it ended."""
        buf = LineBuffer()
        tn = TelnetFilter() if self.port == 23 else None
        while not self.stop_evt.is_set() and self.sock is sock:
            try:
                data = sock.recv(4096)
                if not data:
                    return "TCP connection closed by remote"
                if tn is not None:
                    data, reply = tn.feed(data)
                    if reply:
                        with self._lock:
                            sock.sendall(reply)
                if data:
                    self._received(data, buf)
            except socket.timeout:
                pending = buf.flush()               # idle → show a bare prompt
                if pending:
                    self.on_line(pending)
            except OSError as e:
                return "" if (self.stop_evt.is_set() or self.sock is not sock) else f"TCP error: {e}"
        return ""

    def _drop(self, sock):
        if self.sock is sock:
            self.sock = None
        try:
            sock.close()
        except Exception:
            pass

    # -- main
    def _run(self):
        if not self.ping_mode:
            try:
                self.sock = self._connect()
            except OSError as e:
                return f"TCP connect failed → {self.host}:{self.port}  ({e})", True
            self._mark_open()
            sock = self.sock
            reason = self._read(sock)
            self._drop(sock)
            return reason, bool(reason)

        # ping mode: stay alive, (re)connect whenever the host answers
        was_up = None
        while not self.stop_evt.is_set():
            latency = self._ping()
            if latency is not None:
                if was_up is not True:
                    self.on_info(f"Ping Connected → {self.host}  ({latency})", "success")
                if self.sock is None:
                    try:
                        self.sock = self._connect()
                        sock = self.sock
                        self.on_info(f"TCP connected → {self.host}:{self.port}", "success")
                        self._mark_open()

                        def reader(s=sock):
                            reason = self._read(s)
                            self._drop(s)
                            if reason:
                                self.on_info(reason, "warn")
                        threading.Thread(target=reader, daemon=True).start()
                    except OSError as e:
                        self.sock = None
                        self.on_info(f"TCP connect failed → {self.host}:{self.port}  ({e})", "error")
                was_up = True
            else:
                if was_up is not False:
                    self.on_info(f"Ping Lost → {self.host}", "error")
                    if self.sock:
                        self._drop(self.sock)
                was_up = False
            self.stop_evt.wait(self.interval)
        return "", False

    def _close_io(self):
        s = self.sock
        if s is not None:
            self._drop(s)

    def send(self, data):
        s = self.sock
        if s is None:
            return False, "not connected"
        if self.port == 23 and IAC in data:
            data = data.replace(bytes([IAC]), bytes([IAC, IAC]))   # escape 0xFF
        try:
            with self._lock:
                s.sendall(data)
            return True, ""
        except OSError as e:
            return False, str(e)


# ══════════════════════════════════════════════════════════════
class SshSession(Session):
    kind = "SSH"

    def __init__(self, host, port, user, password, cols=80, rows=24, **cb):
        super().__init__(**cb)
        self.host, self.port, self.user, self.password = host, port, user, password
        self.cols, self.rows = cols, rows
        self.client = None
        self.chan = None
        self.label = f"SSH  {user}@{host}:{port}"

    def _run(self):
        try:
            import paramiko
        except ImportError:
            return "paramiko is not installed (pip install paramiko)", True
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client = client
            client.connect(self.host, port=self.port, username=self.user, password=self.password,
                           timeout=6, banner_timeout=8, look_for_keys=False, allow_agent=False)
            if self.stop_evt.is_set():
                return "", False
            self.chan = client.invoke_shell(term="xterm", width=self.cols, height=self.rows)
            self.chan.settimeout(0.5)
        except Exception as e:
            return f"SSH connect failed: {e}", True

        self._mark_open()
        buf = LineBuffer()
        chan, quiet_since, errors = self.chan, time.monotonic(), 0
        while not self.stop_evt.is_set():
            try:
                if chan.recv_ready():
                    data = chan.recv(8192)
                    errors = 0
                    quiet_since = time.monotonic()
                    if not data:
                        return "SSH connection closed by remote", True
                    self._received(data, buf)
                elif chan.closed or chan.exit_status_ready():
                    return "SSH session ended", True
                else:
                    time.sleep(0.008)
                    if buf.buf and time.monotonic() - quiet_since > IDLE_FLUSH_S:
                        pending = buf.flush()       # quiet → show bare prompt in the log
                        if pending:
                            self.on_line(pending)
            except Exception as e:
                if self.stop_evt.is_set():
                    break
                errors += 1
                if errors > 50:
                    return f"SSH read error — session lost ({e})", True
                time.sleep(0.1)
        return "", False

    def resize(self, cols, rows):
        self.cols, self.rows = cols, rows
        chan = self.chan
        if chan is not None:
            try:
                chan.resize_pty(width=cols, height=rows)
            except Exception:
                pass

    def _close_io(self):
        for name in ("chan", "client"):
            obj = getattr(self, name, None)
            setattr(self, name, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass

    def send(self, data):
        chan = self.chan
        if chan is None:
            return False, "not connected"
        try:
            with self._lock:
                chan.send(data)
            return True, ""
        except Exception as e:
            return False, str(e)
