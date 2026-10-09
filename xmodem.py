"""XMODEM / XMODEM-1K / YMODEM file *sender* (no GUI imports).

Used to load firmware through a boot loader, e.g. U-Boot `loady` / `loadx`.
While a transfer runs, the session's received bytes are routed to this module
(session.rx_hook) instead of the terminal / log.
"""
import os
import threading
import time

SOH, STX, EOT, ACK, NAK, CAN, CRC_C = 0x01, 0x02, 0x04, 0x06, 0x15, 0x18, 0x43
PAD = 0x1A
PROTOCOLS = ("YMODEM", "XMODEM-1K", "XMODEM")


def crc16(data, crc=0):
    """CRC-16/XMODEM (poly 0x1021, init 0)."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


class TransferError(Exception):
    pass


class Sender:
    def __init__(self, session, path, protocol="YMODEM", progress=None, log=None):
        if protocol not in PROTOCOLS:
            raise ValueError(protocol)
        self.session, self.path, self.protocol = session, path, protocol
        self.progress = progress or (lambda done, total: None)
        self.log = log or (lambda text: None)
        self._buf = bytearray()
        self._cv = threading.Condition()
        self.cancelled = False

    # ── receive side (fed by the session's reader thread) ────────────────────
    def _rx(self, data):
        with self._cv:
            self._buf += data
            self._cv.notify_all()

    def _getc(self, timeout):
        end = time.monotonic() + timeout
        with self._cv:
            while not self._buf:
                if self.cancelled:
                    raise TransferError("Cancelled")
                left = end - time.monotonic()
                if left <= 0:
                    return None
                self._cv.wait(min(left, 0.2))
            c = self._buf[0]
            del self._buf[0]
            return c

    def _flush_rx(self):
        with self._cv:
            self._buf.clear()

    def _send(self, data):
        ok, err = self.session.send(bytes(data))
        if not ok:
            raise TransferError(f"Send failed: {err}")

    def cancel(self):
        self.cancelled = True
        with self._cv:
            self._cv.notify_all()

    # ── protocol ─────────────────────────────────────────────────────────────
    def _wait_start(self, timeout=60):
        """Receiver asks for CRC mode with 'C' (or checksum mode with NAK)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            c = self._getc(1.0)
            if c == CRC_C:
                return True
            if c == NAK:
                return False
            if c == CAN and self._getc(1.0) == CAN:
                raise TransferError("Receiver cancelled")
        raise TransferError("Receiver did not start (no 'C' / NAK) — did you run loady / loadx?")

    def _packet(self, blk, payload, size, use_crc):
        data = bytes(payload) + bytes([PAD if blk else 0]) * (size - len(payload))
        head = bytes([STX if size == 1024 else SOH, blk & 0xFF, 0xFF - (blk & 0xFF)])
        if use_crc:
            c = crc16(data)
            return head + data + bytes([c >> 8, c & 0xFF])
        return head + data + bytes([sum(data) & 0xFF])

    def _send_block(self, pkt, retries=10):
        for _ in range(retries):
            self._send(pkt)
            while True:
                c = self._getc(10.0)
                if c == ACK:
                    return
                if c == CAN:
                    if self._getc(1.0) == CAN:
                        raise TransferError("Receiver cancelled")
                    continue
                if c in (NAK, CRC_C, None):
                    break                         # resend
                # anything else: line noise, keep waiting for the answer
        raise TransferError("Too many retries — the receiver keeps rejecting blocks")

    def _send_eot(self):
        for _ in range(10):
            self._send([EOT])
            c = self._getc(5.0)
            if c == ACK:
                return
        raise TransferError("No ACK for end-of-transfer")

    def run(self):
        """Blocking. Returns a short success message or raises TransferError."""
        data = open(self.path, "rb").read()
        total = len(data)
        name = os.path.basename(self.path)
        hook_before = self.session.rx_hook
        self.session.rx_hook = self._rx
        try:
            self.log(f"{self.protocol}: waiting for the receiver…")
            use_crc = self._wait_start()
            ymodem = self.protocol == "YMODEM"
            size = 128 if self.protocol == "XMODEM" else 1024
            if ymodem:
                if not use_crc:
                    raise TransferError("YMODEM needs CRC mode")
                head = name.encode("utf-8", "replace") + b"\0" + \
                    f"{total} {int(os.path.getmtime(self.path)):o}".encode() + b"\0"
                if len(head) > 128:
                    head = head[:127] + b"\0"
                self._send_block(self._packet(0, head, 128, True))
                if self._wait_start(10) is not True:
                    raise TransferError("Receiver did not ask for data after the file header")
            blk, pos = 1, 0
            self.progress(0, total)
            while pos < total:
                chunk = data[pos:pos + size]
                bsize = size if (size == 128 or len(chunk) > 128) else 128   # short tail in 128-byte block
                self._send_block(self._packet(blk, chunk, bsize, use_crc))
                pos += len(chunk)
                blk += 1
                self.progress(min(pos, total), total)
            self._send_eot()
            if ymodem:                               # empty header = end of batch
                if self._wait_start(10) is True:
                    self._send_block(self._packet(0, b"", 128, True))
            return f"{self.protocol}: sent {name} ({total:,} bytes)"
        except TransferError:
            try:
                self._send(bytes([CAN] * 8))
            except TransferError:
                pass
            raise
        finally:
            self.session.rx_hook = hook_before
