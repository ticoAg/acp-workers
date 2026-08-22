# AGENTS.md

给在**本仓库上工作**的 AI 编码 agent 看的约定。若要*使用* skill，读 [skills/acp-workers/SKILL.md](skills/acp-workers/SKILL.md)。

## 仓库概览

同一棵树里两份产物：`acp-workers` skill（agent 加载的指令）和 `acpw` CLI（这些指令驱动的 Python 包）。它们分开发布——用户可以只装其中一份——所以任何一方都不得依赖另一方在磁盘上的位置。

## 布局

```
skills/{skill-name}/     # kebab-case；每个 skill 一个目录
  SKILL.md               # 必填
  AGENTS.md              # 跨 agent 入口，指向 SKILL.md
  README.md              # 给人看
  metadata.json          # version、organization、abstract、references
  scripts/               # 随 skill 下发的可执行文件
  references/            # 按需加载，相对 SKILL.md 只深一层
  assets/                # 示例数据
packages/{package}/      # 代码、测试、lockfile
docs/                    # 改代码的人看的契约，不是 skill 载荷
skills.sh.json           # skills.sh 分组清单
.github/workflows/       # CI
```

## Skill 约定

- SKILL.md frontmatter 里的 `name` 必须等于目录名。
- `SKILL.md` 控制在 500 行以内。少见或很长的内容放到 `references/`，用链接，不要内联。
- `description` 是路由器：先写动作，再写 `USE FOR:` 触发词，以及 `DO NOT USE FOR:` 排除项（点名真正负责那件事的兄弟 skill）。
- 新增 skill 也要写进 `skills.sh.json`。
- `npx skills add` 只复制 skill 目录——`SKILL.md`、`AGENTS.md`、`README.md`、`references/`、`scripts/`、`assets/`，可执行位原样保留。`metadata.json` 给安装器消费，不会落到磁盘，运行时不得依赖它。`skills/<name>/` 以外的任何东西都不会随 skill 下发。
- 安装器按 YAML 解析 frontmatter。标量里含 `: ` 必须加引号，否则 skill 会被静默跳过，报 "No skills found"。
- 脚本：`#!/bin/bash` 加 `set -euo pipefail`，可执行位打开，文件名 kebab-case。进度写 stderr，stdout 只打一行机器可读 JSON。必须幂等——agent 每次调用都可能再跑一遍。

## CLI 约定（`packages/acpw`）

- 类型放在 `src/acpw/types/`（Pydantic SSOT）。业务代码从 `acpw.types` 导入，不要走深路径。
- CLI 不输出说明文字。每条命令一个 `BaseModel`，用 `model_dump_json()` 序列化。
- Adapter 默认值（二进制、`stdio_argv`、默认 bind）放在 `src/acpw/adapters.py`。
- 包不得按仓库相对路径解析文件；`references/` 和 `assets/` 是 skill 载荷，不是运行时数据。
- 增删或改名一条命令，必须同步改 `SKILL.md` 里的命令表。
- 原生模式是一条 WebSocket：`acpw up` 起 pool daemon，`acpw up NAME…` 预热 children，`acpw down NAME` 停一个 child，`acpw down` 停 daemon。`acpw run` / `acpw ping` 在没有 live daemon 时会自己起一份。`--no-pool` 是独立 gateway / serve 逃生口；`--url` 同样绕开 pool。
- Pool daemon 遵守 [`docs/pool-protocol.md`](docs/pool-protocol.md)。改一处必须同一提交改另一处；host 只跟 daemon 说话，看不到自己打到了哪个 child。
- Id 互不串台：host id、child id、session id 是 daemon 翻译的三套空间。Children 自己选 session id，两个 child 可以选出同一字符串，所以任何表都不得拿 child 提供的 id 当键。
- 测试不得碰真实 registry。设置 `ACPW_CONFIG_DIR` 和 `ACPW_STATE_DIR`，端口用 `free_port()`，不要用默认端口。

## 发布

Skill 和 CLI 共用一个版本号。发版时下列文件一起 bump：

| 文件 | 字段 |
| --- | --- |
| `packages/acpw/pyproject.toml` | `version` |
| `skills/acp-workers/metadata.json` | `version` |
| `skills/acp-workers/SKILL.md` | frontmatter 里的 `metadata.version` |
| `CHANGELOG.md` | 把 `未发布` 条目移到新版本下 |

`__version__` 从已安装包的元数据读取，不必改。只有 skill 指令开始依赖更新的 CLI 时，才提高 `skills/acp-workers/scripts/ensure-acpw.sh` 里的 `required_version`；CI 会拒绝下限高于已发布版本。Tag 用 `vX.Y.Z`，这样 CHANGELOG 的链接才能解析。

## 推送前

```bash
cd packages/acpw && uv run ruff check . && uv run ruff format --check . && uv run pytest
```
