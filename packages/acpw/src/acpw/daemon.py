"""The multiplexing pool daemon: one port, many stdio children.

Implements docs/pool-protocol.md. The daemon is the ACP agent from a host's point of view;
children are initialized here at spawn time and never expose their own `initialize` upstream.
"""

from __future__ import annotations

import itertools
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acpw import __version__
from acpw.adapters import ADAPTERS, resolve_stdio_argv
from acpw.paths import POOL_STATE_NAME, worker_state_dir
from acpw.registry import AcpwError, load_registry, resolve_worker
from acpw.service import expand_stdio
from acpw.types import PoolWorker
from acpw.ws import dumps, split_bind, ws_accept, ws_recv, ws_send

ERR_ROUTE = -32602
ERR_SESSION = -32001
ERR_CHILD = -32000

INIT_TIMEOUT = 30.0
HANDSHAKE_TIMEOUT = 15.0

Handler = Callable[[dict[str, Any]], None]

# Children are forked here, never on a request thread. Linux ties PR_SET_PDEATHSIG to the
# parent *thread*: an agent that sets it (grok does) gets SIGTERM the moment the thread that
# forked it exits. The daemon serves each request on a throwaway thread, so forking there
# killed every child as soon as its `session/new` was handed off. One long-lived worker
# thread outlives every request; at interpreter exit it drains and children get the signal
# then, which is the shutdown behaviour we want anyway.
_SPAWNER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="acpw-spawn")


class RouteError(Exception):
    """A JSON-RPC error the daemon answers itself."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def log(message: str) -> None:
    sys.stderr.write(f"[acpw-pool] {message}\n")
    sys.stderr.flush()


def _result(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _answer_of(obj: dict[str, Any]) -> dict[str, Any]:
    """Carry exactly one of result/error across an id remap, verbatim."""
    if "error" in obj:
        return {"error": obj["error"]}
    if "result" in obj:
        return {"result": obj["result"]}
    return {"error": {"code": ERR_CHILD, "message": "malformed response from child"}}


def initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": 1,
        "agentCapabilities": {
            "loadSession": True,
            "promptCapabilities": {"image": False, "audio": False, "embeddedContext": True},
        },
        "authMethods": [],
        "agentInfo": {"name": "acpw-pool", "version": __version__},
    }


def child_initialize_params() -> dict[str, Any]:
    # fs/terminal are declared off: those child requests are relayed to the host, and the host
    # side (MuxClient/AcpClient) answers them with -32601.
    return {
        "protocolVersion": 1,
        "clientInfo": {"name": "acpw-pool", "version": __version__},
        "clientCapabilities": {
            "fs": {"readTextFile": False, "writeTextFile": False},
            "terminal": False,
        },
    }


_child_tokens = itertools.count(1)


def _sessions_path() -> Path:
    return worker_state_dir(POOL_STATE_NAME) / "sessions.json"


def _durable_record(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    worker = raw.get("worker")
    native = raw.get("native")
    if not isinstance(worker, str) or not worker or not isinstance(native, str) or not native:
        return None
    cwd = raw.get("cwd")
    return {"worker": worker, "native": native, "cwd": cwd if isinstance(cwd, str) else None}


def _read_durable_map() -> dict[str, dict[str, Any]]:
    path = _sessions_path()
    if not path.exists():
        log("sessions.json absent; starting with empty map")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        log(f"sessions.json unreadable ({exc}); starting with empty map")
        return {}
    if not isinstance(data, dict):
        log("sessions.json is not an object; starting with empty map")
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        record = _durable_record(value) if isinstance(key, str) else None
        if record is None:
            log(f"sessions.json: skipping malformed entry {key!r}")
            continue
        out[key] = record
    if out:
        log(f"loaded {len(out)} durable session(s) from {path}")
    return out


def _child_supports_load(child: PooledChild) -> bool:
    init = child.init_result or {}
    caps = init.get("agentCapabilities")
    return isinstance(caps, dict) and bool(caps.get("loadSession"))


class PooledChild:
    """One stdio agent subprocess with a single reader thread dispatching by JSON-RPC id."""

    def __init__(self, name: str, kind: str, argv: list[str], cwd: str, pool: Pool):
        self.name = name
        self.kind = kind
        self.pool = pool
        # Distinguishes two generations of the same worker, so a restart cannot inherit
        # the session ids of the process it replaced.
        self.token = next(_child_tokens)
        env = os.environ.copy()
        # Host grok exports these so nested `acpw run grok` would otherwise inherit
        # the parent's session and exit (`child grok exited`).
        for key in ("GROK_AGENT", "GROK_SESSION_ID"):
            env.pop(key, None)
        self.proc = _SPAWNER.submit(
            subprocess.Popen,
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            bufsize=0,
        ).result()
        assert self.proc.stdin and self.proc.stdout and self.proc.stderr
        self.write_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.pending: dict[int, Handler] = {}
        self.init_result: dict[str, Any] | None = None
        self._next_id = 0
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def alive(self) -> bool:
        return self.proc.poll() is None

    def send(self, obj: dict[str, Any]) -> None:
        assert self.proc.stdin
        line = (dumps(obj) + "\n").encode()
        with self.write_lock:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()

    def request(self, method: str, params: Any, handler: Handler) -> int:
        """Allocate this child's next integer id, remember the handler, write one line."""
        if not self.alive():
            raise RouteError(ERR_CHILD, f"child {self.name} exited")
        with self.state_lock:
            self._next_id += 1
            child_id = self._next_id
            self.pending[child_id] = handler
        try:
            self.send({"jsonrpc": "2.0", "id": child_id, "method": method, "params": params})
        except OSError as exc:
            with self.state_lock:
                self.pending.pop(child_id, None)
            raise RouteError(ERR_CHILD, f"child write failed: {exc}") from exc
        return child_id

    def call(self, method: str, params: Any, timeout: float = INIT_TIMEOUT) -> dict[str, Any]:
        """A daemon-internal request. Never called from the reader thread."""
        done = threading.Event()
        box: dict[str, Any] = {}

        def handler(obj: dict[str, Any]) -> None:
            box.update(obj)
            done.set()

        self.request(method, params, handler)
        if not done.wait(timeout):
            raise RouteError(ERR_CHILD, f"child {self.name} timed out on {method}")
        if "error" in box:
            raise RouteError(ERR_CHILD, f"child {self.name} {method}: {dumps(box['error'])}")
        result = box.get("result")
        return result if isinstance(result, dict) else {}

    def kill(self) -> None:
        with self.write_lock:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
            except OSError:
                pass
        if self.proc.poll() is not None:
            return
        try:
            self.proc.terminate()
        except OSError:
            return
        try:
            self.proc.wait(timeout=0.4)
        except subprocess.TimeoutExpired:
            try:
                self.proc.kill()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass

    def _read_stdout(self) -> None:
        assert self.proc.stdout
        while True:
            raw = self.proc.stdout.readline()
            if not raw:
                break
            text = raw.decode("utf-8", "replace").strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                log(f"{self.name}: non-JSON stdout line dropped: {text[:200]}")
                continue
            if isinstance(obj, dict):
                self._dispatch(obj)
        self._on_exit()

    def _read_stderr(self) -> None:
        assert self.proc.stderr
        for line in self.proc.stderr:
            text = line.decode("utf-8", "replace").rstrip()
            if not text:
                continue
            # Attributed, not raw: a bare line in the log cannot be traced to a worker.
            log(f"{self.name}/stderr: {text}")

    def _dispatch(self, obj: dict[str, Any]) -> None:
        msg_id = obj.get("id")
        method = obj.get("method")
        if method is None:
            if not isinstance(msg_id, int):
                log(f"{self.name}: response with unusable id {msg_id!r} dropped")
                return
            with self.state_lock:
                handler = self.pending.pop(msg_id, None)
            if handler is None:
                log(f"{self.name}: response for unknown id {msg_id} dropped")
                return
            try:
                handler(obj)
            except Exception as exc:  # noqa: BLE001 - reader thread must keep draining
                log(f"{self.name}: pending handler failed: {exc}")
            return
        if msg_id is None:
            self.pool.on_child_notification(self, obj)
            return
        self.pool.on_child_request(self, obj)

    def _on_exit(self) -> None:
        with self.state_lock:
            pending = list(self.pending.values())
            self.pending.clear()
        for handler in pending:
            try:
                handler(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": ERR_CHILD, "message": f"child {self.name} exited"},
                    }
                )
            except Exception as exc:  # noqa: BLE001 - remaining handlers still need to run
                log(f"{self.name}: pending handler failed on exit: {exc}")
        self.pool.on_child_exit(self)


class Conn:
    """One host WebSocket. Its write lock keeps frames atomic; nothing else is shared."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.write_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.inbound: dict[str, tuple[PooledChild, Any]] = {}
        self.open = True
        # Guarded by Pool.lock together with `sessions`, so bind vs drop is atomic.
        self.released = False

    def send(self, obj: dict[str, Any]) -> None:
        with self.write_lock:
            if not self.open:
                return
            try:
                ws_send(self.sock, dumps(obj), client=False)
            except OSError:
                self.open = False

    def close(self) -> None:
        with self.write_lock:
            self.open = False
        try:
            self.sock.close()
        except OSError:
            pass


@dataclass
class Session:
    worker: str
    child: PooledChild
    # The connection currently driving it, or None while nobody is attached. A session
    # outlives the connection that opened it. The in-memory binding dies with the child;
    # the durable record stays so a later request can take the L2 path.
    conn: Conn | None
    # What the child calls this session. Children pick their own ids and two of them may
    # well pick the same string, so it is never used as a key on the daemon side.
    native: str
    cwd: str | None


class Pool:
    """Children, sessions, and the two id spaces that meet between them."""

    def __init__(self) -> None:
        self.children: dict[str, PooledChild] = {}
        # Keyed by the public id the daemon hands the host, never by the child's own.
        self.sessions: dict[str, Session] = {}
        self.public_ids: dict[tuple[int, str], str] = {}
        self.lock = threading.Lock()
        self.spawn_locks: dict[str, threading.Lock] = {}
        # Per public session id: two in-flight resumes of the same conversation must not
        # each spawn a child and each send session/load.
        self.resume_locks: dict[str, threading.Lock] = {}
        self.inbound_lock = threading.Lock()
        self.inbound_n = 0
        self.disk_lock = threading.Lock()
        self.durable: dict[str, dict[str, Any]] = _read_durable_map()

    # ---- inventory -------------------------------------------------------------------

    def worker_rows(self) -> list[dict[str, Any]]:
        with self.lock:
            children = list(self.children.items())
            counts: dict[str, int] = {}
            for session in self.sessions.values():
                counts[session.worker] = counts.get(session.worker, 0) + 1
        return [
            PoolWorker(
                name=name,
                kind=child.kind,
                alive=child.alive(),
                pid=child.proc.pid,
                sessions=counts.get(name, 0),
            ).model_dump()
            for name, child in children
        ]

    def session_count(self) -> int:
        with self.lock:
            return len(self.sessions)

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "kind": "pool",
            "pid": os.getpid(),
            "workers": self.worker_rows(),
            "sessions": self.session_count(),
        }

    # ---- children --------------------------------------------------------------------

    def ensure_child(self, name: str, cwd: str | None) -> tuple[PooledChild, bool]:
        with self.lock:
            child = self.children.get(name)
            if child is not None and child.alive():
                return child, False
            lock = self.spawn_locks.setdefault(name, threading.Lock())
        # Per worker, not global: two different workers still spawn and initialize in parallel.
        with lock:
            with self.lock:
                child = self.children.get(name)
                if child is not None and child.alive():
                    return child, False
            child = self._spawn(name, cwd)
            with self.lock:
                self.children[name] = child
            return child, True

    def _spawn(self, name: str, cwd: str | None) -> PooledChild:
        registry = load_registry()
        if name not in registry.workers:
            raise RouteError(ERR_ROUTE, f"unknown worker {name}")
        try:
            entry, spec = resolve_worker(name)
        except AcpwError as exc:
            raise RouteError(ERR_ROUTE, f"unknown worker {name}") from exc
        if not entry.enabled:
            raise RouteError(ERR_ROUTE, f"worker {name} is disabled in registry")
        kind = entry.kind or name
        adapter = ADAPTERS.get(kind, spec)
        argv = expand_stdio(resolve_stdio_argv(entry.stdio_argv, adapter))
        if not argv:
            raise RouteError(ERR_ROUTE, f"worker {name} is not a stdio worker")
        workdir = cwd or os.getcwd()
        try:
            child = PooledChild(name, kind, argv, workdir, self)
        except OSError as exc:
            raise RouteError(ERR_CHILD, f"cannot spawn {name}: {exc}") from exc
        try:
            init = child.call("initialize", child_initialize_params())
            child.init_result = init
            method_id = _auth_method_id(init)
            if method_id:
                child.call("authenticate", {"methodId": method_id})
        except RouteError:
            child.kill()
            raise
        log(f"{name}: child up pid={child.proc.pid}")
        return child

    def _drop_sessions(self, keep: Callable[[Session], bool]) -> list[str]:
        """Caller holds self.lock."""
        dropped = [sid for sid, session in self.sessions.items() if not keep(session)]
        for sid in dropped:
            session = self.sessions.pop(sid)
            self.public_ids.pop((session.child.token, session.native), None)
        return dropped

    def stop_child(self, name: str) -> bool:
        with self.lock:
            child = self.children.pop(name, None)
            dropped = self._drop_sessions(lambda session: session.worker != name)
        if child is None:
            return False
        child.kill()
        log(
            f"{name}: child killed, {len(dropped)} in-memory session(s) cleared; "
            "durable records kept"
        )
        return True

    def on_child_exit(self, child: PooledChild) -> None:
        with self.lock:
            if self.children.get(child.name) is child:
                del self.children[child.name]
            dropped = self._drop_sessions(lambda session: session.child is not child)
        log(
            f"{child.name}: child exited rc={child.proc.poll()}, "
            f"{len(dropped)} in-memory session(s) cleared; durable records kept"
        )

    def shutdown(self) -> None:
        with self.lock:
            children = list(self.children.values())
            self.children.clear()
            self.sessions.clear()
            self.public_ids.clear()
        for child in children:
            child.kill()

    # ---- child -> host ---------------------------------------------------------------

    def next_inbound_id(self) -> str:
        with self.inbound_lock:
            self.inbound_n += 1
            return f"acpw:{self.inbound_n}"

    def upstream(self, child: PooledChild, params: Any) -> tuple[Conn, dict[str, Any]] | None:
        """Resolve a child-side sessionId to its owning connection and the host-side params."""
        native = params.get("sessionId") if isinstance(params, dict) else None
        if not isinstance(native, str):
            return None
        with self.lock:
            public = self.public_ids.get((child.token, native))
            session = self.sessions.get(public) if public else None
            conn = session.conn if session is not None else None
        if session is None or public is None or conn is None or not conn.open:
            return None
        return conn, {**params, "sessionId": public}

    def on_child_notification(self, child: PooledChild, obj: dict[str, Any]) -> None:
        route = self.upstream(child, obj.get("params"))
        if route is None:
            log(f"{child.name}: {obj.get('method')} for unknown or detached session dropped")
            return
        conn, params = route
        conn.send(
            {
                "jsonrpc": obj.get("jsonrpc", "2.0"),
                "method": obj.get("method"),
                "params": params,
            }
        )

    def on_child_request(self, child: PooledChild, obj: dict[str, Any]) -> None:
        route = self.upstream(child, obj.get("params"))
        child_id = obj.get("id")
        if route is None:
            # Nothing to forward to; answering keeps the child from waiting forever.
            log(f"{child.name}: {obj.get('method')} for unknown or detached session refused")
            self.reply_to_child(
                child,
                child_id,
                {"error": {"code": ERR_SESSION, "message": "unknown session"}},
            )
            return
        conn, params = route
        acpw_id = self.next_inbound_id()
        with conn.state_lock:
            conn.inbound[acpw_id] = (child, child_id)
        conn.send(
            {
                "jsonrpc": "2.0",
                "id": acpw_id,
                "method": obj.get("method"),
                "params": params,
            }
        )

    def reply_to_child(self, child: PooledChild, child_id: Any, answer: dict[str, Any]) -> None:
        try:
            child.send({"jsonrpc": "2.0", "id": child_id, **answer})
        except OSError as exc:
            log(f"{child.name}: cannot deliver answer for id {child_id!r}: {exc}")

    def answer_from_host(self, conn: Conn, msg: dict[str, Any]) -> None:
        """Host answered an `acpw:<n>` request: write it back under the child's own id."""
        msg_id = msg.get("id")
        if not isinstance(msg_id, str):
            log(f"response with unexpected id {msg_id!r} dropped")
            return
        with conn.state_lock:
            route = conn.inbound.pop(msg_id, None)
        if route is None:
            log(f"response for unknown inbound id {msg_id} dropped")
            return
        child, child_id = route
        self.reply_to_child(child, child_id, _answer_of(msg))

    # ---- host -> child ---------------------------------------------------------------

    def forward(
        self, conn: Conn, msg_id: Any, child: PooledChild, method: str, params: Any
    ) -> None:
        """Host id -> fresh child id; the answer goes back under the host's original id."""

        def handler(obj: dict[str, Any]) -> None:
            conn.send({"jsonrpc": "2.0", "id": msg_id, **_answer_of(obj)})

        child.request(method, params, handler)

    def open_session(self, conn: Conn, msg_id: Any, method: str, params: Any) -> None:
        meta = params.get("_meta") if isinstance(params, dict) else None
        worker = meta.get("worker") if isinstance(meta, dict) else None
        if not isinstance(worker, str) or not worker:
            raise RouteError(ERR_ROUTE, "missing _meta.worker")
        cwd = params.get("cwd") if isinstance(params, dict) else None
        workdir = cwd if isinstance(cwd, str) else None
        child, _ = self.ensure_child(worker, workdir)
        if method == "session/load" and isinstance(params, dict):
            # Only translatable if this connection opened it; otherwise the host is naming
            # a child-native id and the child gets to decide whether it knows it.
            params = self.downstream(child, params)

        def handler(obj: dict[str, Any]) -> None:
            result = obj.get("result")
            if isinstance(result, dict):
                native = result.get("sessionId")
                if isinstance(native, str):
                    public = self.bind_session(worker, child, conn, native, cwd=workdir)
                    obj = {**obj, "result": {**result, "sessionId": public}}
            conn.send({"jsonrpc": "2.0", "id": msg_id, **_answer_of(obj)})

        # `_meta` is forwarded verbatim; the contract does not ask for it to be stripped.
        child.request(method, params, handler)

    def bind_session(
        self,
        worker: str,
        child: PooledChild,
        conn: Conn,
        native: str,
        *,
        cwd: str | None = None,
        public: str | None = None,
    ) -> str:
        """Mint or reuse the id the host will use. Child ids are not unique across children.

        The id is random rather than sequential because a session outlives the connection
        that opened it: knowing the id is what entitles a later connection to resume the
        conversation, the same way knowing the server key entitles you to the socket.
        """
        with self.lock:
            existing = self.public_ids.get((child.token, native))
            if public is None and existing is not None and existing in self.sessions:
                session = self.sessions[existing]
                session.conn = conn
                if cwd is not None:
                    session.cwd = cwd
                self.durable[existing] = {
                    "worker": worker,
                    "native": native,
                    "cwd": session.cwd,
                }
                public = existing
            else:
                if public is None:
                    public = f"acpw-s{secrets.token_hex(8)}"
                old = self.sessions.get(public)
                if old is not None:
                    self.public_ids.pop((old.child.token, old.native), None)
                if existing is not None and existing != public:
                    leftover = self.sessions.pop(existing, None)
                    if leftover is not None:
                        self.public_ids.pop((leftover.child.token, leftover.native), None)
                    self.durable.pop(existing, None)
                self.sessions[public] = Session(
                    worker=worker, child=child, conn=conn, native=native, cwd=cwd
                )
                self.public_ids[(child.token, native)] = public
                self.durable[public] = {"worker": worker, "native": native, "cwd": cwd}
        self._persist_durable()
        return public

    def _persist_durable(self) -> None:
        """Write sessions.json without holding Pool.lock across the I/O."""
        with self.disk_lock:
            with self.lock:
                snapshot = {key: dict(value) for key, value in self.durable.items()}
            path = _sessions_path()
            fd = -1
            tmp_name = ""
            try:
                fd, tmp_name = tempfile.mkstemp(
                    prefix=".sessions.", suffix=".tmp", dir=str(path.parent)
                )
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fd = -1
                    json.dump(snapshot, fh)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_name, path)
                tmp_name = ""
            except (OSError, TypeError, ValueError) as exc:
                log(f"sessions.json write failed: {exc}")
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                if tmp_name:
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass

    def downstream(self, child: PooledChild, params: dict[str, Any]) -> dict[str, Any]:
        """Public sessionId -> the one the child issued."""
        public = params.get("sessionId")
        if not isinstance(public, str):
            return params
        with self.lock:
            session = self.sessions.get(public)
        if session is None or session.child is not child:
            return params
        return {**params, "sessionId": session.native}

    def _attach(self, conn: Conn, session: Session, session_id: str) -> Session:
        """Caller holds self.lock."""
        holder = session.conn
        if holder is conn:
            return session
        if holder is not None and holder.open:
            # Two hosts prompting one agent would interleave; the first one keeps it.
            raise RouteError(ERR_SESSION, f"session {session_id} is held by another client")
        session.conn = conn
        return session

    def session_for(self, conn: Conn, session_id: Any) -> Session:
        """L1 only: attach if the session is in memory and its child is alive."""
        with self.lock:
            session = self.sessions.get(session_id) if isinstance(session_id, str) else None
            if session is None or not session.child.alive():
                raise RouteError(ERR_SESSION, f"unknown session {session_id}")
            return self._attach(conn, session, session_id)

    def resume_session(self, conn: Conn, session_id: str) -> Session:
        """L2/L3: respawn the worker, session/load the native id, rebind the same public id.

        Runs on the serve_request thread. Must not be called from a child reader.
        """
        with self.lock:
            if session_id not in self.durable:
                raise RouteError(ERR_SESSION, f"unknown session {session_id}")
            lock = self.resume_locks.setdefault(session_id, threading.Lock())
        with lock:
            with self.lock:
                session = self.sessions.get(session_id)
                if session is not None and session.child.alive():
                    return self._attach(conn, session, session_id)
                raw = self.durable.get(session_id)
                record = dict(raw) if raw is not None else None
            if record is None:
                raise RouteError(ERR_SESSION, f"unknown session {session_id}")
            worker = str(record["worker"])
            native = str(record["native"])
            cwd = record.get("cwd")
            cwd_str = cwd if isinstance(cwd, str) else None
            child, _ = self.ensure_child(worker, cwd_str)
            if not _child_supports_load(child):
                raise RouteError(
                    ERR_SESSION,
                    f"worker {worker} cannot resume sessions (loadSession not advertised)",
                )
            load_params: dict[str, Any] = {"sessionId": native, "mcpServers": []}
            if cwd_str is not None:
                load_params["cwd"] = cwd_str
            try:
                result = child.call("session/load", load_params)
            except RouteError:
                raise RouteError(ERR_SESSION, f"unknown session {session_id}") from None
            loaded = result.get("sessionId")
            if isinstance(loaded, str) and loaded:
                native = loaded
            self.bind_session(worker, child, conn, native, cwd=cwd_str, public=session_id)
            log(f"session {session_id}: resumed on {worker} native={native}")
            with self.lock:
                session = self.sessions.get(session_id)
                if session is None:
                    raise RouteError(ERR_SESSION, f"unknown session {session_id}")
                return self._attach(conn, session, session_id)

    def resolve_session(self, conn: Conn, session_id: str) -> Session:
        """L1 attach, else L2/L3 resume. Held-by-another is never turned into a resume."""
        try:
            return self.session_for(conn, session_id)
        except RouteError as exc:
            if exc.code != ERR_SESSION or exc.message.endswith("held by another client"):
                raise
            return self.resume_session(conn, session_id)

    def serve_request(self, conn: Conn, msg: dict[str, Any]) -> None:
        msg_id = msg.get("id")
        method = msg.get("method") or ""
        params = msg.get("params")
        if params is None:
            params = {}
        try:
            self._route(conn, msg_id, method, params)
        except RouteError as exc:
            conn.send(_error(msg_id, exc.code, exc.message))
        except Exception as exc:  # noqa: BLE001 - one bad request must not close the connection
            log(f"{method}: {type(exc).__name__}: {exc}")
            conn.send(_error(msg_id, ERR_CHILD, f"{type(exc).__name__}: {exc}"))

    def _route(self, conn: Conn, msg_id: Any, method: str, params: Any) -> None:
        if method == "initialize":
            conn.send(_result(msg_id, initialize_result()))
            return
        if method == "authenticate":
            conn.send(_result(msg_id, {}))
            return
        if method == "worker/list":
            conn.send(_result(msg_id, {"workers": self.worker_rows()}))
            return
        if method == "worker/up":
            name = params.get("name") if isinstance(params, dict) else None
            if not isinstance(name, str) or not name:
                raise RouteError(ERR_ROUTE, "missing name")
            cwd = params.get("cwd")
            child, spawned = self.ensure_child(name, cwd if isinstance(cwd, str) else None)
            init = child.init_result or {}
            conn.send(
                _result(
                    msg_id,
                    {
                        "name": name,
                        "alive": child.alive(),
                        "pid": child.proc.pid,
                        "already": not spawned,
                        # The child's own handshake, so a caller can tell which agent it
                        # actually reached instead of only hearing from the daemon.
                        "protocolVersion": init.get("protocolVersion"),
                        "agentInfo": init.get("agentInfo") or init.get("serverInfo"),
                        "agentVersion": (init.get("_meta") or {}).get("agentVersion"),
                    },
                )
            )
            return
        if method == "worker/down":
            name = params.get("name") if isinstance(params, dict) else None
            if not isinstance(name, str) or not name:
                raise RouteError(ERR_ROUTE, "missing name")
            conn.send(_result(msg_id, {"name": name, "stopped": self.stop_child(name)}))
            return
        if method in {"session/new", "session/load"}:
            self.open_session(conn, msg_id, method, params)
            return
        session_id = params.get("sessionId") if isinstance(params, dict) else None
        if isinstance(session_id, str):
            session = self.resolve_session(conn, session_id)
            self.forward(
                conn, msg_id, session.child, method, self.downstream(session.child, params)
            )
            return
        raise RouteError(ERR_ROUTE, f"no route: {method}")

    def serve_notification(self, conn: Conn, msg: dict[str, Any]) -> None:
        method = msg.get("method") or ""
        params = msg.get("params")
        session_id = params.get("sessionId") if isinstance(params, dict) else None
        try:
            session = self.session_for(conn, session_id)
        except RouteError:
            log(f"host notification {method} for unknown session {session_id!r} dropped")
            return
        child = session.child
        params = self.downstream(child, params) if isinstance(params, dict) else params
        try:
            child.send(
                {
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params if params is not None else {},
                }
            )
        except OSError as exc:
            log(f"{child.name}: cannot forward notification {method}: {exc}")

    # ---- connection lifetime ---------------------------------------------------------

    def serve_conn(self, conn: Conn) -> None:
        try:
            while True:
                raw = ws_recv(conn.sock)
                if raw is None:
                    break
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    log(f"non-JSON frame dropped: {raw[:200]}")
                    continue
                if not isinstance(msg, dict):
                    continue
                if "method" not in msg:
                    self.answer_from_host(conn, msg)
                    continue
                if msg.get("id") is None:
                    self.serve_notification(conn, msg)
                    continue
                # Off the reader thread: spawning a child blocks, and requests must not queue
                # behind each other.
                threading.Thread(target=self.serve_request, args=(conn, msg), daemon=True).start()
        except OSError:
            pass
        finally:
            self.close_conn(conn)

    def close_conn(self, conn: Conn) -> None:
        conn.close()
        with self.lock:
            conn.released = True
            # Sessions outlive their connection. They are detached, not dropped, so the
            # next `acpw run --session-id` finds the conversation still there.
            detached = 0
            for session in self.sessions.values():
                if session.conn is conn:
                    session.conn = None
                    detached += 1
        with conn.state_lock:
            inbound = list(conn.inbound.items())
            conn.inbound.clear()
        for _acpw_id, (child, child_id) in inbound:
            self.reply_to_child(
                child,
                child_id,
                {"error": {"code": ERR_CHILD, "message": "host connection closed"}},
            )
        if detached:
            log(f"connection closed, {detached} session(s) detached; children stay warm")


def _auth_method_id(init: dict[str, Any]) -> str | None:
    methods = init.get("authMethods") or []
    default = (init.get("_meta") or {}).get("defaultAuthMethodId")
    if default:
        return str(default)
    if methods and isinstance(methods[0], dict) and methods[0].get("id"):
        return str(methods[0]["id"])
    return None


def _read_http(sock: socket.socket) -> bytes:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
        if len(buf) > 65536:
            break
    head, _, _rest = buf.partition(b"\r\n\r\n")
    return head


def _send_json(sock: socket.socket, payload: dict[str, Any]) -> None:
    body = dumps(payload).encode()
    sock.sendall(
        b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )


def _send_401(sock: socket.socket) -> None:
    msg = b"Invalid or missing authorization token"
    sock.sendall(
        b"HTTP/1.1 401 Unauthorized\r\ncontent-type: text/plain\r\ncontent-length: "
        + str(len(msg)).encode()
        + b"\r\n\r\n"
        + msg
    )


def _serve_socket(pool: Pool, sock: socket.socket, secret: str) -> None:
    keep = False
    try:
        sock.settimeout(HANDSHAKE_TIMEOUT)
        head = _read_http(sock)
        if not head:
            return
        first = head.split(b"\r\n", 1)[0].decode("utf-8", "replace")
        headers: dict[str, str] = {}
        for line in head.split(b"\r\n")[1:]:
            if b":" in line:
                key, value = line.split(b":", 1)
                headers[key.decode().lower()] = value.decode().strip()
        if first.startswith("GET /health"):
            _send_json(sock, pool.health())
            return
        if not first.startswith("GET /ws"):
            sock.sendall(b"HTTP/1.1 404 Not Found\r\ncontent-length: 0\r\n\r\n")
            return
        path = first.split(" ")[1]
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
        key = (qs.get("server-key") or qs.get("secret") or [None])[0]
        if key != secret:
            _send_401(sock)
            return
        ws_key = headers.get("sec-websocket-key")
        if not ws_key:
            sock.sendall(b"HTTP/1.1 400 Bad Request\r\ncontent-length: 0\r\n\r\n")
            return
        sock.sendall(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {ws_accept(ws_key)}\r\n"
                "\r\n"
            ).encode()
        )
        # A pooled connection is resident: no read deadline, and no conn_lock either.
        sock.settimeout(None)
        keep = True
        pool.serve_conn(Conn(sock))
    except OSError:
        pass
    finally:
        if not keep:
            try:
                sock.close()
            except OSError:
                pass


def run_daemon(bind: str, secret_file: str) -> None:
    """Serve the pool protocol on `bind` until SIGTERM."""
    secret = Path(secret_file).read_text().strip()
    host, port = split_bind(bind)
    pool = Pool()
    (worker_state_dir(POOL_STATE_NAME) / "pid").write_text(str(os.getpid()) + "\n")
    stop = threading.Event()

    def on_term(_signum: int, _frame: Any) -> None:
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, on_term)
        except ValueError:
            pass

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(64)
    log(f"listening on {host}:{port} pid={os.getpid()}")
    try:
        while not stop.is_set():
            try:
                srv.settimeout(1.0)
                sock, _addr = srv.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(target=_serve_socket, args=(pool, sock, secret), daemon=True).start()
    finally:
        pool.shutdown()
        try:
            srv.close()
        except OSError:
            pass
