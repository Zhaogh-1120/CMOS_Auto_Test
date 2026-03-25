from __future__ import annotations

import socket
import time
from pathlib import Path
from typing import Optional


class E5052BClient:
    def __init__(self, host: str, port: int = 5025, timeout_s: float = 15.0):
        self.host = host
        self.port = int(port)
        self.timeout_s = float(timeout_s)
        self.sock: Optional[socket.socket] = None

    def open(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout_s)
        self.sock.settimeout(self.timeout_s)

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def __enter__(self) -> "E5052BClient":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def write(self, cmd: str) -> None:
        if self.sock is None:
            raise RuntimeError("Instrument is not connected")
        self.sock.sendall((cmd + "\n").encode("ascii"))

    def _recv_exact(self, n: int) -> bytes:
        if self.sock is None:
            raise RuntimeError("Instrument is not connected")
        data = bytearray()
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise RuntimeError("Connection closed while reading instrument response")
            data.extend(chunk)
        return bytes(data)

    def read_text(self) -> str:
        if self.sock is None:
            raise RuntimeError("Instrument is not connected")
        chunks: list[bytes] = []
        while True:
            chunk = self.sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break
        return b"".join(chunks).decode("ascii", errors="replace").strip()

    def query_text(self, cmd: str) -> str:
        self.write(cmd)
        return self.read_text()

    def query_block(self, cmd: str) -> bytes:
        if self.sock is None:
            raise RuntimeError("Instrument is not connected")
        self.write(cmd)
        first = self._recv_exact(1)
        if first != b"#":
            rest = bytearray(first)
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                rest.extend(chunk)
                if b"\n" in chunk:
                    break
            return bytes(rest).strip()
        ndigits = int(self._recv_exact(1).decode("ascii"))
        length = int(self._recv_exact(ndigits).decode("ascii"))
        payload = self._recv_exact(length)
        try:
            self.sock.settimeout(0.2)
            _ = self.sock.recv(2)
        except Exception:
            pass
        finally:
            self.sock.settimeout(self.timeout_s)
        return payload

    def identify(self) -> str:
        return self.query_text("*IDN?")

    def ping(self) -> bool:
        try:
            _ = self.identify()
            return True
        except Exception:
            return False

    def set_ascii_format(self) -> None:
        self.write(":FORM:DATA ASC")

    def freeze_display(self) -> bool:
        ok = False
        for cmd in [":INIT:CONT OFF", ":ABOR", "*WAI"]:
            try:
                self.write(cmd)
                ok = True
            except Exception:
                pass
        time.sleep(0.08)
        return ok

    def resume_display(self) -> None:
        for cmd in [":INIT:CONT ON", ":INIT:IMM"]:
            try:
                self.write(cmd)
            except Exception:
                pass

    def request_screenshot_save(self, shot_id: str) -> str:
        remote_path = f'D:/e5052b_capture_{shot_id}.png'
        self.write(f':MMEM:STOR:IMAG "{remote_path}"')
        try:
            self.query_text("*OPC?")
        except Exception:
            time.sleep(0.35)
        return remote_path

    def fetch_remote_file(self, remote_path: str, local_path: Path) -> Optional[Path]:
        try:
            data = self.query_block(f':MMEM:DATA? "{remote_path}"')
            if not data:
                return None
            local_path.write_bytes(data)
            return local_path
        except Exception:
            return None
