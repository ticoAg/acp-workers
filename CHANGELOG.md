# 变更记录

版本号同时覆盖本仓库两份产物：`acp-workers` skill 和 `acpw` CLI。它们一起发布，所以 `packages/acpw/pyproject.toml`、`skills/acp-workers/metadata.json`，以及 `skills/acp-workers/SKILL.md` 里的 `metadata.version` 始终是同一个数字。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [未发布]

## [0.6.4] - 2026-08-23

### 变更

- CLI 默认输出 markdown（标题、表格、`key: value`），不再默认打一行 JSON。`--json`、`--format json`、`ACPW_OUTPUT=json`，或 `acpw output set json` 仍输出原来的 JSON 对象。字段名保持英文。`acpw run` 的 agent 正文写在元数据下面、以 `---` 分隔。

## [0.6.3] - 2026-08-22

### 新增

- CLI 语言：`acpw lang set zh-CN` 写入配置，`acpw lang` / `acpw lang get` 查看。一次调用用 `--lang` / `-L` 或 `ACPW_LANG`。支持 `en-US`、`zh-CN`、`zh-TW`。`--help`、Typer 提示和 JSON 里给人看的 `error` / `notes` / `detail` 随语言走；字段名、命令名、协议文案仍是英文。

## [0.6.2] - 2026-08-22

### 修复

- 并发冷启动时，没绑上端口的输家会覆盖 pid 文件；`read_pid` 认定那个 pid 已死就返回 None，`acpw down` 于是什么都不杀。`pool_down` 在 pid 文件不可用时改信 `/health` 报告的 pid；`pool_up` 在 health 起来后把正确 pid 写回文件（含 already 分支）。

## [0.6.1] - 2026-08-22

### 变更

- 将仓库内面向人与 agent 的文档改为中文；命令、协议字段、错误文案和链接保持原文。

### 修复

- Pool children 现在只在一条长命线程上 fork。Daemon 为每条请求起一条临时线程，而 Linux 把 `PR_SET_PDEATHSIG` 绑在父*线程*上，所以设了这个标志的 Grok 会在 `session/new` 刚转交出去、该线程退出的瞬间被内核 SIGTERM 杀掉。表现为 `acpw run grok` 稳定失败于 `child grok exited`，而 daemon 自己毫发无损、也从未调用 kill。
- Child 退出日志带上 `rc=`，child stderr 带上 worker 名前缀。此前两者都无法归属，`child grok exited` 分不清是 daemon 杀的、外部信号，还是 agent 自己退的。
- 内置 mock agent 的 `session/new` 现在每次铸一个新 session id。此前固定返回 `mock-session`，在 daemon 的 `(child, native)` 映射里会把并发开出的多个 session 折叠成同一个，扇出测试因此假失败于 `session … is held by another client`，也掩盖了真实的并发正确性。

## [0.6.0] - 2026-08-22

### 变更

- 原生模式是一条 WebSocket。`acpw up` 起 pool daemon；`acpw up grok claude` 预热这些 children；`acpw down NAME` 停一个 child；`acpw down` 停 daemon。`--no-pool` 是独立 gateway / `grok agent serve` 逃生口。
- `acpw ls` 报告一个 `pool` 对象，以及每个 worker 的 `via`（`pool` 或 `gateway`）。
- `acpw selfcheck` 往返走共享 WebSocket。

### 新增

- 在 live pool 上执行 `acpw down NAME` 会调用 `worker/down`，daemon 和 `sessions.json` 留下。

### 修复

- 客户端 WebSocket pong 和 close 帧现在带 mask。Grok `agent serve` 会丢掉未 mask 的客户端帧（`UnmaskedFrameFromClient`），随后报 `child grok exited`，导致 `acpw ping` / `acpw run grok --no-pool` 做不完一次 prompt。
- Pool daemon 及其 children 不再从 host Grok 进程继承 `GROK_AGENT` / `GROK_SESSION_ID`。

## [0.5.0] - 2026-08-22

### 变更

- Grok 进入 pool。判定条件是「有 stdio 命令」，不是 `transport == stdio_bridge`。`acpw run grok` 现在在 daemon 下起 `grok agent --always-approve --no-leader stdio`，与 acpx 拉 `grok-build` 的启动方式相同。`acpw up grok` 和 `--no-pool` 仍在 `48191` 起原生 `serve`。第二个 grok 进程是另一个 `kind: grok` 的 registry 名。

## [0.4.0] - 2026-08-22

### 变更

- Pool 成为 stdio worker 的默认路径。`acpw run NAME` 和 `acpw ping NAME` 在没有 live daemon 时会先起 daemon；`acpw pool up` 仍用于预热。`--no-pool` 走每个 worker 自己的 gateway；`--pool` 强制走 pool。原生 serve（grok）仍走自己的 gateway；显式 `--url` 也绕开 pool。
- `acpw pool up` 不带 `--bind` 时尊重 `ACPW_POOL_BIND` / 已记录的 bind 文件，不再总是用 `0.0.0.0:48190`。
- 公开 session id（`acpw-s` 加 16 位 hex）活过创建它的 WebSocket（L1）、agent child（L2：respawn 和 `session/load`），以及 daemon（L3：原子写入 `_pool/sessions.json`）。续会话仍取决于 agent 是否广告并执行 `loadSession`。

### 新增

- 一个 session 同一时刻只被一条活连接占用。另一客户端试图续它会得到 `session <id> is held by another client`；那条连接断开后，session 又可续。
- 在 `session/load` 之前，daemon 检查 `agentCapabilities.loadSession`。缺失或为 false 时返回 `worker <name> cannot resume sessions (loadSession not advertised)`，而不是开一个空白 session。

### 修复

- 经 pool 的 `acpw ping NAME` 现在会 spawn/initialize 指定 child，并报告该 child 的 `agentInfo` / `protocolVersion`。以前只和 daemon 握手。
- 对一份仍响应 `/health` 的 daemon 收到 401（用了另一份 state 目录起的）时，会点出 bind、secret 路径，以及修复办法：`acpw pool down`，或把 `ACPW_STATE_DIR` 指到那份 daemon 使用的目录。

## [0.3.0]

### 新增

- Pool：`48190` 上一个常驻 daemon，底下挂若干 stdio children，host 用一条 WebSocket 驱动多个 agent。`acpw pool up` / `down` / `ls`，以及 `acpw run` / `ping` 接受 `--pool` / `--no-pool`。
- `acpw run NAME` 在 daemon live 且 NAME 是 stdio worker 时优先走 pool。Grok 是原生 `serve` worker，从不进 pool；`--url` 也绕开它。
- 给用户的 `references/pool.md`，以及线路契约 `docs/pool-protocol.md`。

### 变更

- Worker 和 pool 默认绑 `0.0.0.0`，高位端口不变。客户端拨 `127.0.0.1`。仍写着已被取代的回环默认值的 registry 条目会在加载时迁移。
- `acpw selfcheck` 增加 `exposure` 检查：对每个可从回环以外到达的 worker 告警，因为 worker 跑 always-approve，且 server key 明文过线。

## [0.2.0]

### 新增

- `acpw selfcheck`：覆盖 CLI、PATH、uv、registry、state 目录、shell 补全、adapter 二进制，以及经一次性 mock worker 的 live 往返，共八项。任一失败退出 1；`--no-live` 只做静态检查。
- `scripts/ensure-acpw.sh` 装完后跑自检，结果写在 `selfcheck` 字段。失败则 `"ok":false`，完整报告打到 stderr，退出 1。`--no-selfcheck` 可跳过。

### 修复

- `ACPW_CONFIG_DIR` 和 `ACPW_STATE_DIR` 以前在 import 时读一次，之后再设无效，测试套件会写到调用者的真实 registry。路径改为每次调用再解析。

## [0.1.1]

### 修复

- `SKILL.md` frontmatter 无法按 YAML 解析：未加引号的 `description` 含 `USE FOR:`，YAML 会读成嵌套 mapping，于是 `npx skills add` 跳过该 skill 并报 "No skills found"。给该标量加了引号。CI 现在会解析每个 skill 的 frontmatter。

## [0.1.0]

### 新增

- `acpw` CLI：`ls`、`doctor`、`add`、`rm`、`up`、`down`、`ping`、`run`、`install`、`uninstall`、`version`。每条命令打印一行 JSON。
- 经 `grok agent serve` 的原生 Grok worker；Claude Code、Codex、Cursor 的 stdio ACP 桥，端口 48191–48194。
- `acp-workers` skill：派发流程、线路协议参考、安装参考、registry 示例。
- `scripts/ensure-acpw.sh`：幂等 CLI 引导，带版本下限、`--update`、`--force`、`--completion`。

[未发布]: https://github.com/ticoAg/acp-workers/compare/v0.6.4...HEAD
[0.6.4]: https://github.com/ticoAg/acp-workers/compare/v0.6.3...v0.6.4
[0.6.3]: https://github.com/ticoAg/acp-workers/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/ticoAg/acp-workers/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/ticoAg/acp-workers/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/ticoAg/acp-workers/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/ticoAg/acp-workers/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ticoAg/acp-workers/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ticoAg/acp-workers/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ticoAg/acp-workers/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/ticoAg/acp-workers/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/ticoAg/acp-workers/releases/tag/v0.1.0
