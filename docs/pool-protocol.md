# Pool protocol v2

Contract between `acpw daemon` (server) and `MuxClient` (client). Both sides are implemented against this file; if the code and this file disagree, this file is the bug report.

## Why

This is the native mode of the project: one resident daemon on one port that owns several stdio children, so one host connection can drive several agents concurrently and resume them by public session id. The standalone `acpw gateway` (one worker, one port, one secret, one in-flight request) remains as `--no-pool`.

## Endpoint

```
ws://127.0.0.1:48190/ws?server-key=<secret>
GET /health
```

- Secret lives at `~/.local/state/acp-workers/_pool/secret`, pid at `.../pid`, log at `.../server.log`, the bind the daemon was started on at `.../bind`, and the durable session map at `.../sessions.json`.
- Bind discovery, in order: `ACPW_POOL_BIND` in the environment, then the `bind` state file, then `DEFAULT_POOL_BIND`. `pool_up()` writes the file; everything else reads it, so a pool started on a non-default port stays reachable.
- Wrong or missing `server-key` on `/ws` → HTTP 401, same as the per-worker gateway.
- `GET /health` → `{"ok":true,"kind":"pool","pid":N,"workers":[{"name","kind","alive","pid","sessions"}],"sessions":N}`. Both session counts are live bindings, not durable records, so they drop to zero when a child dies even though those sessions can still be resumed.
- `/health` requires no key. A daemon started against a different state directory therefore looks alive until `/ws` answers 401; clients should say so plainly rather than reporting the pool as down.
- Many connections are allowed at once. There is no `conn_lock`.

## Messages the daemon answers itself

The daemon is the ACP agent from the host's point of view. Children are initialized by the daemon at spawn time; the host never sees a child's `initialize`.

| Method | Result |
| --- | --- |
| `initialize` | `{"protocolVersion":1,"agentCapabilities":{"loadSession":true,"promptCapabilities":{"image":false,"audio":false,"embeddedContext":true}},"authMethods":[],"agentInfo":{"name":"acpw-pool","version":"<acpw version>"}}` |
| `authenticate` | `{}` |
| `worker/list` | `{"workers":[{"name","kind","alive","pid","sessions"}]}` |
| `worker/up` | params `{"name":str,"cwd":str?}` → `{"name","alive":true,"pid":N,"already":bool,"protocolVersion","agentInfo","agentVersion"}`. Spawns the child and runs `initialize` (plus `authenticate` when the child reports auth methods) before returning. The last three fields echo the child's own handshake, so a caller can tell which agent it reached rather than only hearing from the daemon; they are null if the child answered without them. |
| `worker/down` | params `{"name":str}` → `{"name","stopped":bool}`. Kills the child and clears its in-memory bindings. The durable records survive, so those sessions are still resumable under L2. |

## Routing

1. `session/new` and `session/load` **must** carry `params._meta.worker` naming a registry worker. Missing or unknown → error `-32602` with message `missing _meta.worker` / `unknown worker <name>`.
2. The daemon spawns that worker's child on demand (same as `worker/up`), forwards the request, and on success mints a public `sessionId` of the form `acpw-s<16 hex>` bound to `(worker, child, connection)`. The child's own id never reaches the host. The id is random, not sequential: a session outlives its connection, so knowing the id is the capability to resume the conversation.
3. Every other request carrying `params.sessionId` routes to that session's child, resuming it first if necessary (see Session durability). Unknown session or unresumable session → error `-32001`, message `unknown session <id>`. A session currently attached to a different **open** connection → error `-32001`, message `session <id> is held by another client`.
4. A request that is neither control nor session-bound → error `-32602`, message `no route: <method>`.
5. Notifications from a child carrying `params.sessionId` go to the connection currently attached to the session. A notification for an unknown or detached session is dropped and logged to the daemon log.

## Session durability

A session is a conversation, not a socket. It survives the connection that opened it and is resumed by presenting its id again. Three tiers, tried in order:

| Tier | State | What the daemon does |
| --- | --- | --- |
| L1 | Child alive, session in memory | Re-attach it to the requesting connection. No agent involvement. |
| L2 | Child gone, mapping known | Respawn the worker, `session/load` the child-native id, re-bind under the same public id. |
| L3 | Daemon restarted | Same as L2, with the mapping read back from `sessions.json`. |

- `sessions.json` maps public id → `{"worker":str,"native":str,"cwd":str|null}`. Written on every bind, atomically (temp file plus rename). A record outlives its child on purpose: that is what makes L2 and L3 work.
- L2 and L3 require the child to advertise `agentCapabilities.loadSession`. When it does not, the resume fails with `-32001` and message `worker <name> cannot resume sessions (loadSession not advertised)`. The daemon must check the capability it cached at spawn **before** sending `session/load`, so an agent that cannot resume says so instead of returning an opaque error.
- If `session/load` returns a different `sessionId` than the one sent, the new value becomes the session's native id and the record is rewritten. The public id never changes.
- Only one connection drives a session at a time. Attaching is allowed when the holder is absent or its socket has closed; stealing from a live holder is not.
- Sessions die with their worker only in the sense that L1 stops applying. `worker/down` and child exit clear the in-memory binding but keep the durable record.

## Identifier remapping

Two independent id spaces meet at the daemon. Never leak one into the other.

- **Host → child.** The daemon allocates a fresh integer id per child (`1, 2, 3, …`, counter per child) and remembers `child.pending[child_id] = handler`. When the child answers with that id, the daemon replies to the owning connection using the host's **original** id, verbatim (it may be an int or a string).
- **Child → host.** When a child sends a request (`session/request_permission`, `fs/read_text_file`, `fs/write_text_file`, `terminal/*`), the daemon allocates a **string** id of the form `"acpw:<n>"` from a global counter, stores `conn.inbound[acpw_id] = (child, child_side_id)`, and forwards it to the connection that owns the session. When the host answers `"acpw:<n>"`, the daemon writes the answer back to the child under the child's original id.
  String ids are deliberate: hosts allocate integers, so `"acpw:*"` can never collide with an id the host chose.
- **Session ids.** A third space, and the reason it exists: children pick their own session ids and two children may well pick the same string, so a flat table keyed by the child's id routes later requests to the wrong agent — silently. The daemon keys sessions by `acpw-s<16 hex>` and translates `params.sessionId` in both directions: child's id → public on the way up (`session/new` and `session/load` results, child notifications and requests), public → child's id on the way down. A child restart gets a new generation token, so a recycled id cannot inherit a dead session.
- Responses must preserve `jsonrpc`, `id`, and exactly one of `result` / `error`.

## Concurrency

- Each child has one reader thread draining stdout forever and dispatching by id; there is no read-until-my-id anywhere.
- Each child has a write lock; each connection has a write lock. A WebSocket frame and a stdio line are each written atomically.
- Multiple requests may be in flight per child. Whether the agent behind it truly parallelizes is the agent's business; the daemon does not serialize on its behalf.
- Child stderr is drained to the daemon log, never to a WebSocket.

## Lifecycle

- A connection dropping **detaches** its sessions; it does not end them. Children stay warm and the durable record stays on disk.
- In-flight requests belonging to a dead connection are abandoned when their answer arrives.
- A child exiting clears the in-memory binding of its sessions. A later request for one of them takes the L2 path.
- The daemon exits on SIGTERM and kills every child. Sessions come back through L3.

## Errors

| Code | When |
| --- | --- |
| `-32602` | missing `_meta.worker`, unknown worker, unroutable method |
| `-32001` | unknown session, session held by another client, or a worker that cannot resume |
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
def pool_up(bind: str | None = None, workers: list[str] | None = None,
            cwd: str | None = None, timeout: float = 45) -> PoolStartResponse: ...
def pool_down() -> PoolStopResponse: ...
def pool_status() -> PoolStatus: ...
def pool_ping(name: str) -> PingResponse: ...
def pool_run(params: ExecParams) -> ExecResponse: ...
```

`pool_up` with no bind resolves one the same way everything else does; starting a daemon on an address the rest of the code does not look at just produces a pool nobody can find.

`pool_ping` must reach the named worker, not the daemon in front of it: send `worker/up` and report the child's `agentInfo` and `protocolVersion`. Handshaking with the pool alone proves nothing about the agent the caller asked for, and would report a broken agent binary as healthy.

`pool_run` resume rule: when `params.session_id` is set, send `session/prompt` with that id directly. Do **not** call `session/new`, and do **not** call `session/load` — the daemon owns resuming. A `-32001` is surfaced to the caller as a failure; silently opening a fresh session would drop the conversation without telling anyone.

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
