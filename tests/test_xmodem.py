"""Sender against a small receiver that behaves like U-Boot loady / loadx."""
import os
import threading
import time

import pytest

import xmodem as X


class FakeLink:
    """session.send() goes to the receiver; the receiver answers through rx_hook."""

    def __init__(self):
        self.rx_hook = None
        self.to_rx = bytearray()
        self.cv = threading.Condition()

    def send(self, data):
        with self.cv:
            self.to_rx += data
            self.cv.notify_all()
        return True, ""

    def reply(self, b):
        self.rx_hook(bytes([b]))

    def read(self, n, timeout=5):
        end = time.time() + timeout
        with self.cv:
            while len(self.to_rx) < n:
                left = end - time.time()
                if left <= 0:
                    raise TimeoutError
                self.cv.wait(left)
            out = bytes(self.to_rx[:n])
            del self.to_rx[:n]
            return out


def receiver(link, mode, result):
    use_crc = mode != "checksum"
    while link.rx_hook is None:
        time.sleep(0.005)
    data, header_seen, corrupt_once = bytearray(), False, True
    link.reply(X.CRC_C if use_crc else X.NAK)
    while True:
        h = link.read(1)[0]
        if h == X.EOT:
            if mode == "ymodem" and not result.get("eot_naked"):
                result["eot_naked"] = True            # real receivers NAK the first EOT
                link.reply(X.NAK)
                continue
            link.reply(X.ACK)
            result.setdefault("files", []).append(bytes(data))
            data = bytearray()
            if mode != "ymodem":
                return
            header_seen = False
            link.reply(X.CRC_C)                       # ask for the next file header
            continue
        size = 1024 if h == X.STX else 128
        blk, inv = link.read(2)
        payload = link.read(size)
        chk = link.read(2 if use_crc else 1)
        if use_crc:
            ok = int.from_bytes(chk, "big") == X.crc16(payload)
        else:
            ok = chk[0] == sum(payload) & 0xFF
        ok = ok and blk + inv == 255
        if corrupt_once and blk == 1:                 # simulate one damaged block → NAK → resend
            corrupt_once, ok = False, False
        if not ok:
            link.reply(X.NAK)
            continue
        if mode == "ymodem" and blk == 0 and not header_seen:
            name = payload.split(b"\0")[0]
            link.reply(X.ACK)
            if not name:                              # empty header = end of batch
                return
            result["name"] = name.decode()
            result["size"] = int(payload.split(b"\0")[1].split(b" ")[0])
            header_seen = True
            link.reply(X.CRC_C)
            continue
        data += payload
        link.reply(X.ACK)


@pytest.mark.parametrize("proto,mode", [("YMODEM", "ymodem"), ("XMODEM-1K", "crc"), ("XMODEM", "checksum")])
def test_transfer(tmp_path, proto, mode):
    blob = os.urandom(5000)
    f = tmp_path / "u-boot.bin"
    f.write_bytes(blob)
    link, result = FakeLink(), {}
    th = threading.Thread(target=receiver, args=(link, mode, result), daemon=True)
    th.start()
    seen = []
    msg = X.Sender(link, str(f), proto, progress=lambda d, t: seen.append(d)).run()
    th.join(5)
    assert "sent" in msg and seen[-1] == len(blob)
    got = result["files"][0]
    if mode == "ymodem":
        assert result["name"] == "u-boot.bin" and result["size"] == len(blob)
        got = got[:result["size"]]
    else:
        got = got.rstrip(bytes([X.PAD]))
    assert got == blob
    assert link.rx_hook is None                        # terminal gets the data back afterwards


def test_receiver_not_ready_is_reported(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc")
    link = FakeLink()
    s = X.Sender(link, str(f), "YMODEM")
    s._wait_start = lambda timeout=60: (_ for _ in ()).throw(X.TransferError("Receiver did not start"))
    with pytest.raises(X.TransferError):
        s.run()


def test_crc16():
    assert X.crc16(b"123456789") == 0x31C3
