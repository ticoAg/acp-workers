# Pool protocol v1

Contract between `acpw daemon` (server) and `MuxClient` (client). Both sides are implemented against this file; if the code and this file disagree, this file is the bug report.

## Why

Today one worker means one `acpw gateway` process, one port, one secret, and one in-flight request (`conn_lock` plus `child.lock` serialize everything). The pool replaces that with a single resident daemon on one port that owns several stdio children, so one host connection can drive several agents concurrently.

## Endpoint

```
ws://127.0.0.1:48190/ws?server-key=<secret>
GET /health
```

- Secret lives at `~/.local/state/acp-workers/_pool/secret`, pid at `.../pid`, log at `.../server.log`, and the bind the daemon was started on at `.../bind`.
- Bind discovery, in order: `ACPW_POOL_BIND` in the environment, then the `bind` state file, then `DEFAULT_POOL_BIND`. `pool_up()` writes the file; everything else reads it, so a pool started on a non-default port stays reachable.
- Wrong or missing `server-key` on `/ws` → HTTP 401, same as the per-worker gateway.
- `GET /health` → `{"ok":true,"kind":"pool","pid":N,"workers":[{"name","kind","alive","pid","sessions"}],"sessions":N}`
- Many connections are allowed at once. There is no `conn_lock`.

## Messages the daemon answers itself

The daemon is the ACP agent from the host's point of view. Children are initialized by the daemon at spawn time; the host never sees a child's `initialize`.

| Method | Result |
| --- | --- |
| `initialize` | `{"protocolVersion":1,"agentCapabilities":{"loadSession":false,"promptCapabilities":{"image":false,"audio":false,"embeddedContext":true}},"authMethods":[],"agentInfo":{"name":"acpw-pool","version":"<acpw version>"}}` |
| `authenticate` | `{}` |
| `worker/list` | `{"workers":[{"name","kind","alive","pid","sessions"}]}` |
| `worker/up` | params `{"name":str,"cwd":str?}` → `{"name","alive":true,"pid":N,"already":bool}`. Spawns the child and runs `initialize` (plus `authenticate` when the child reports auth methods) before returning. |
| `worker/down` | params `{"name":str}` → `{"name","stopped":bool}`. Kills the child; its sessions are dropped. |

## Routing

1. `session/new` and `session/load` **must** carry `params._meta.worker` naming a registry worker. Missing or unknown → error `-32602` with message `missing _meta.worker` / `unknown worker <name>`.
2. The daemon spawns that worker's child on demand (same as `worker/up`), forwards the request, and on success mints a public `sessionId` of the form `acpw-s<n>` bound to `(worker, child, connection)`. The child's own id never reaches the host.
3. Every other request carrying `params.sessionId` routes to that session's child. Unknown session, a session owned by another connection, or a dead child → error `-32001`, message `unknown session <id>`.
4. A request that is neither control nor session-bound → error `-32602`, message `no route: <method>`.
5. Notifications from a child carrying `params.sessionId` go to the connection that owns the session. A notification for an unknown session is dropped and logged to the daemon log.

## Identifier remapping

Two independent id spaces meet at the daemon. Never leak one into the other.

- **Host → child.** The daemon allocates a fresh integer id per child (`1, 2, 3, …`, counter per child) and remembers `child.pending[child_id] = handler`. When the child answers with that id, the daemon replies to the owning connection using the host's **original** id, verbatim (it may be an int or a string).
- **Child → host.** When a child sends a request (`session/request_permission`, `fs/read_text_file`, `fs/write_text_file`, `terminal/*`), the daemon allocates a **string** id of the form `"acpw:<n>"` from a global counter, stores `conn.inbound[acpw_id] = (child, child_side_id)`, and forwards it to the connection that owns the session. When the host answers `"acpw:<n>"`, the daemon writes the answer back to the child under the child's original id.
  String ids are deliberate: hosts allocate integers, so `"acpw:*"` can never collide with an id the host chose.
- **Session ids.** A third space, and the reason it exists: children pick their own session ids and two children may well pick the same string, so a flat table keyed by the child's id routes later requests to the wrong agent — silently. The daemon keys sessions by `acpw-s<n>` and translates `params.sessionId` in both directions: child's id → public on the way up (`session/new` and `session/load` results, child notifications and requests), public → child's id on the way down. A child restart gets a new generation token, so a recycled id cannot inherit a dead session.
- Responses must preserve `jsonrpc`, `id`, and exactly one of `result` / `error`.

## Concurrency

- Each child has one reader thread draining stdout forever and dispatching by id; there is no read-until-my-id anywhere.
- Each child has a write lock; each connection has a write lock. A WebSocket frame and a stdio line are each written atomically.
- Multiple requests may be in flight per child. Whether the agent behind it truly parallelizes is the agent's business; the daemon does not serialize on its behalf.
- Child stderr is drained to the daemon log, never to a WebSocket.

## Lifecycle

- A connection dropping releases its sessions. Children stay warm.
- In-flight requests belonging to a dead connection are abandoned when their answer arrives.
- A child exiting marks its sessions dead; further requests to them get `-32001`.
- The daemon exits on SIGTERM and kills every child.

## Errors

| Code | When |
| --- | --- |
| `-32602` | missing `_meta.worker`, unknown worker, unroutable method |
| `-32001` | unknown or dead session |
| `-32000` | child write failed or child exited mid-request |

## Module contract

Shared constants already live in `acpw.paths`: `DEFAULT_POOL_BIND = "0.0.0.0:48190"` and `POOL_STATE_NAME = "_pool"`. Response models already live in `acpw.types`: `PoolWorker`, `PoolStatus`, `PoolStartResponse`, `PoolStopResponse`.

`acpw/daemon.py` exposes exactly:

```python
def run_daemon(bind: str, secret_file: str) -> None: ...   # blocks until SIGTERM
```

`acpw/pool.py` exposes exactly:

```python
def pool_secret() -> str: ...                    # read or create the pool secret
def pool_url(secret: str | None = None) -> str: ...
def pool_live(timeout: float = 1.0) -> bool: ...  # GET /health
def pool_up(bind: str = DEFAULT_POOL_BIND, workers: list[str] | None = None,
            cwd: str | None = None, timeout: float = 45) -> PoolStartResponse: ...
def pool_down() -> PoolStopResponse: ...
def pool_status() -> PoolStatus: ...
def pool_ping(name: str) -> PingResponse: ...
def pool_run(params: ExecParams) -> ExecResponse: ...
```

`acpw/client.py` gains, without touching `AcpClient`:

```python
class MuxClient:
    def __init__(self, sock: socket.socket) -> None: ...
    def start(self) -> None: ...                  # spawn the reader thread
    def close(self) -> None: ...
    def rpc(self, method: str, params: dict | None = None, timeout: float = 60.0) -> dict: ...
    def updates(self, session_id: str) -> list[dict]: ...   # session/update params seen so far
```

## Client obligations (`MuxClient`)

- One background reader thread; requests return via futures keyed by host id.
- Answer `session/request_permission` with `{"outcome":{"outcome":"selected","optionId":"allow-once"}}`.
- Answer `fs/*` and `terminal/*` with error `-32601` (`client fs not offered`), matching today's `AcpClient`.
- Collect `session/update` notifications per `sessionId`.
- Never block the reader thread on user code.
