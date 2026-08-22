from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import urllib.parse

GUIDE = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


WILDCARD_HOSTS = {"0.0.0.0", "::", "[::]", ""}


def split_bind(bind: str) -> tuple[str, int]:
    host, _, port = bind.rpartition(":")
    return (host or "0.0.0.0"), int(port)


def connect_host(host: str) -> str:
    """A listen address is not always a reachable one: 0.0.0.0 is dialed as loopback."""
    if host in WILDCARD_HOSTS:
        return "127.0.0.1"
    return host


def ws_url(bind: str, secret: str | None) -> str:
    host, port = split_bind(bind)
    host = connect_host(host)
    url = f"ws://{host}:{port}/ws"
    if secret:
        url += "?server-key=" + urllib.parse.quote(secret)
    return url


def ws_accept(key: str) -> str:
    digest = hashlib.sha1((key + GUIDE).encode()).digest()
    return base64.b64encode(digest).decode()


def ws_frame(opcode: int, data: bytes, *, client: bool) -> bytes:
    """RFC 6455 frame. Clients must mask; servers must not. Grok drops unmasked client frames."""
    header = bytearray([0x80 | (opcode & 0x0F)])
    ln = len(data)
    mask_bit = 0x80 if client else 0
    if ln < 126:
        header.append(mask_bit | ln)
    elif ln < 65536:
        header.append(mask_bit | 126)
        header.extend(struct.pack(">H", ln))
    else:
        header.append(mask_bit | 127)
        header.extend(struct.pack(">Q", ln))
    if client:
        mask = os.urandom(4)
        header.extend(mask)
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return bytes(header) + data


def ws_send(sock: socket.socket, text: str, *, client: bool) -> None:
    sock.sendall(ws_frame(0x1, text.encode("utf-8"), client=client))


def ws_close(sock: socket.socket, *, client: bool = True) -> None:
    try:
        sock.sendall(ws_frame(0x8, b"", client=client))
    except OSError:
        pass
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def _recvn(sock: socket.socket, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except TimeoutError:
            return None
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def ws_recv(sock: socket.socket, *, client: bool = False) -> str | None:
    hdr = _recvn(sock, 2)
    if hdr is None:
        return None
    opcode = hdr[0] & 0x0F
    masked = bool(hdr[1] & 0x80)
    ln = hdr[1] & 0x7F
    if ln == 126:
        ext = _recvn(sock, 2)
        if ext is None:
            return None
        ln = struct.unpack(">H", ext)[0]
    elif ln == 127:
        ext = _recvn(sock, 8)
        if ext is None:
            return None
        ln = struct.unpack(">Q", ext)[0]
    mask = _recvn(sock, 4) if masked else b""
    data = _recvn(sock, ln) if ln else b""
    if data is None:
        return None
    if masked:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    if opcode == 0x8:
        return None
    if opcode == 0x9:
        try:
            sock.sendall(ws_frame(0xA, data, client=client))
        except OSError:
            return None
        return ws_recv(sock, client=client)
    if opcode == 0x1:
        return data.decode("utf-8")
    return ""


def ws_connect(url: str, timeout: float = 8.0) -> socket.socket:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/ws"
    if parsed.query:
        path += "?" + parsed.query
    sock = socket.create_connection((host, port), timeout=timeout)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(req.encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise ConnectionError("websocket handshake closed")
        buf += chunk
    status = buf.split(b"\r\n", 1)[0]
    if b"101" not in status:
        sock.close()
        raise ConnectionError(status.decode("utf-8", "replace"))
    return sock


def dumps(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)
