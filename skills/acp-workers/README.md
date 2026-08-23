# acp-workers

通过一条常驻 WebSocket 派发编码任务，底下挂多个 agent 进程；验收留在 host agent。

`acpw up` 起这条 socket。`acpw run NAME` 开或续一段会话，返回 `session_id`。Grok、Claude、Codex、Cursor 都是同一 daemon 下的 children。`--no-pool` 是独立 gateway / `grok agent serve` 逃生口。

[![skills.sh](https://skills.sh/b/ticoAg/acp-workers)](https://skills.sh/ticoAg/acp-workers)

## 安装

只装这份 skill：

```bash
npx skills add ticoAg/acp-workers --skill acp-workers
```

Skill 驱动的 `acpw` CLI 是另一次安装。引导脚本随 skill 下发，且幂等：

```bash
bash scripts/ensure-acpw.sh --completion
```

等价的手动步骤：

```bash
uv tool install "git+https://github.com/ticoAg/acp-workers#subdirectory=packages/acpw"
acpw install
```

## 更新

```bash
npx skills update acp-workers
bash scripts/ensure-acpw.sh --update
```

Skill 和 CLI 共用同一版本号。`acpw version` 打印已装版本；引导脚本持有下限，skill 需要更新的 CLI 时会自行升级。

## 要求

- Python 3.12+ 和 uv；`~/.local/bin` 在 `PATH` 里
- 至少一个 agent 二进制：`grok`、`npx`（Claude Code / Codex adapter）、`cursor-agent`
- 共享 WebSocket 需要端口 `48190` 空闲，或自定义 `ACPW_POOL_BIND`

## 使用

```bash
acpw selfcheck            # 端到端核验安装，含 mock 往返
acpw doctor && acpw ls
acpw up grok --cwd "$PWD"
acpw run grok -f /tmp/task.txt
acpw run grok -f /tmp/next.txt --session-id <session_id>
acpw down
```

`acpw run` / `acpw ping` 在需要时会自己起 socket。Zed / acp-devtools 走 `acpw stdio grok`（标准 ACP stdin/stdout）。第二个 grok 进程用 `acpw add grok-b --kind grok`。只派 `acpw ls` 里 `allowed` 且 `enabled` 的 worker：`acpw allow set grok cursor` 写入本机允许的 kind。

`--no-pool` 走该 worker 自己的 gateway；`--url` 指名某个 socket，同样绕开 pool。

`ok` 表示 ACP 回合结束，不表示任务做对。接受任何结果之前先看 diff、跑测试。

Worker 绑 `0.0.0.0`，跑 always-approve，`server-key` 明文过线。别把这些端口放到不可信网络；`acpw selfcheck` 会报 `exposure` 告警作为提醒。

## 文件

| 路径 | 作用 |
| --- | --- |
| [SKILL.md](./SKILL.md) | agent 加载的流程 |
| [scripts/ensure-acpw.sh](./scripts/ensure-acpw.sh) | 幂等 CLI 引导；stdout 一行 JSON |
| [references/install.md](./references/install.md) | 安装、registry/state 路径、卸载顺序 |
| [references/protocol.md](./references/protocol.md) | URL 方案、ACP 握手、stdio 桥、Grok 继承什么 |
| [references/pool.md](./references/pool.md) | 原生 WebSocket、session 耐久、所有权、错误码 |
| [assets/registry.example.json](./assets/registry.example.json) | registry 文件形状 |

## 许可证

MIT
