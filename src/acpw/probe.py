from __future__ import annotations

import json
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from acpw.adapters import ADAPTERS, PROCESS_NEEDLES
from acpw.types import ListeningHit, ProbeResult, ProbeVia
from acpw.ws import split_bind, ws_connect, ws_url


def http_get(url: str, timeout: float = 1.5) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except OSError:
        return 0, ""


def probe(bind: str, secret: str | None = None) -> ProbeResult:
    host, port = split_bind(bind)
    sock = socket.socket()
    sock.settimeout(0.4)
    try:
        sock.connect((host, port))
    except OSError:
        return ProbeResult(live=False, bind=bind)
    finally:
        sock.close()
    code, body = http_get(f"http://{host}:{port}/health")
    if code == 200:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"raw": body[:200]}
        return ProbeResult(live=True, bind=bind, via=ProbeVia.health, health=payload)
    code_ws, _body_ws = http_get(f"http://{host}:{port}/ws")
    if code_ws == 401:
        return ProbeResult(live=True, bind=bind, via=ProbeVia.ws_401)
    if secret:
        try:
            conn = ws_connect(ws_url(bind, secret), timeout=3)
            conn.close()
            return ProbeResult(live=True, bind=bind, via=ProbeVia.ws_auth)
        except OSError:
            pass
    return ProbeResult(live=True, bind=bind, via=ProbeVia.tcp, http_ws=code_ws)


def scan_listening() -> list[ListeningHit]:
    found: list[ListeningHit] = []
    try:
        out = subprocess.check_output(["ss", "-lntp"], text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return found
    for line in out.splitlines():
        if "127.0.0.1:" not in line and "[::1]:" not in line:
            continue
        for kind, spec in ADAPTERS.items():
            if spec.hidden:
                continue
            _, port = split_bind(spec.default_bind)
            if f":{port}" in line:
                found.append(ListeningHit(kind=kind, bind=spec.default_bind, ss=line.strip()[:200]))
    return found


def argv_running(needle: str) -> list[int]:
    pids: list[int] = []
    proc = Path("/proc")
    if not proc.exists():
        return pids
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if needle in cmdline and "acpw" not in cmdline.split()[0:1]:
            if " -m acpw" in f" {cmdline}" and "gateway" in cmdline:
                continue
            pids.append(int(entry.name))
    return pids


def cmdline_has(pid: int, fragment: str) -> bool:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        return False
    return fragment in raw


def process_map() -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for kind, needle in PROCESS_NEEDLES.items():
        pids = argv_running(needle)
        if kind == "cursor":
            pids = [pid for pid in pids if cmdline_has(pid, " acp")]
        out[kind] = pids
    return out
