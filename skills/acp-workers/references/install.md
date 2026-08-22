# 安装 / 卸载

Skill 和 CLI 是两件东西。Skill 让各 agent 扫到 `SKILL.md`；CLI 提供 `acpw` 二进制。

装完 skill 之后，CLI 交给随 skill 一起下发的脚本：

```bash
bash scripts/ensure-acpw.sh                 # 幂等；够新就报 already，偏旧自动升级，末尾自动自检
bash scripts/ensure-acpw.sh --update        # 主动重装到源里的最新版
bash scripts/ensure-acpw.sh --completion    # 顺带注册 bash 补全（写 ~/.bashrc）
bash scripts/ensure-acpw.sh --force         # 无条件重装
bash scripts/ensure-acpw.sh --no-selfcheck  # 跳过自检
```

脚本在 checkout 里会优先用同仓库的 `packages/acpw`，只装了 skill 时回落到 GitHub。stdout 恒为一行 JSON，进度在 stderr。下面是它替你做的事，手动装时照做。

## 自检

`ensure-acpw.sh` 装完会自动跑一次；也可以随时手动跑。

```bash
acpw selfcheck            # 九项，含 mock 往返；任一 fail 退出 1
acpw selfcheck --no-live  # 只查静态项，不起进程
```

| 检查 | fail 的含义 |
| --- | --- |
| `cli` | 包元数据缺失，acpw 是从源码树 import 的，没真正安装 |
| `path` | warn：`acpw` 不在 PATH |
| `uv` | warn：没有 uv，后续升级会失败 |
| `registry` | `registry.json` 读不了或解析不了 |
| `state` | state 目录不可写 |
| `completion` | warn：没注册补全，跑 `acpw install` |
| `adapters` | 一个 agent 二进制都没有；缺一部分只是 warn |
| `exposure` | 只会 warn，不会 fail：列出绑在非回环地址的 worker。默认就是 `0.0.0.0`，所以装完看到它是正常的 |
| `roundtrip` | 起共享 WebSocket、派一条 prompt 给临时 mock child、比对回包。这一项过了才说明链路真的通 |

`roundtrip` 用随机空闲端口，worker 名带进程号，跑完即停并从 registry 里删掉，不会碰你已有的 worker。

`exposure` 这一条值得当回事：worker 是 always-approve，`server-key` 明文过线。默认 `0.0.0.0` 图的是省事，别把这些端口放到不可信网络；要收回回环就给 worker 显式设 `bind`。

## 版本

skill 和 CLI 同版本号发布。三处必须一致：`packages/acpw/pyproject.toml`、`skills/acp-workers/metadata.json`、`SKILL.md` frontmatter 里的 `metadata.version`；CI 会卡这一点。

```bash
acpw version   # {"ok":true,"version":"0.6.0","python":"3.12.14","location":"…"}
acpw --version # 同上
```

脚本顶部的 `required_version` 是这份 skill 需要的 CLI 下限。低于它就自动升级；升完还不够（源太旧）会报 `version-too-old` 并退出 1。手动升级：

```bash
uv tool install --force "git+https://github.com/ticoAg/acp-workers#subdirectory=packages/acpw"
```

`uv tool upgrade acpw` 对 git 来源不会拉新提交，用上面的 `--force` 重装。变更记录见仓库根的 [CHANGELOG.md](https://github.com/ticoAg/acp-workers/blob/main/CHANGELOG.md)。

## Skill

```bash
# GitHub / skills.sh
npx skills add ticoAg/acp-workers --skill acp-workers -g -y

# 本机总库里已有一份时，软链过去即可
ln -sfn ~/.agents/skill-library/acp-workers/skills/acp-workers ~/.agents/skills/acp-workers
```

## CLI

CLI 是 `packages/acpw` 这个子目录里的 Python 包，和 skill 分开装。

```bash
# 从仓库 checkout
uv tool install --editable packages/acpw
# 从 GitHub
uv tool install "git+https://github.com/ticoAg/acp-workers#subdirectory=packages/acpw"

acpw install   # bash 补全 → ~/.local/share/bash-completion/completions/acpw，并写入 ~/.bashrc
```

`~/.local/bin` 要在 `PATH` 里。新开一个 shell 后用 `command -v acpw` 确认。

## Registry 与 state

| 路径 | 内容 | 覆盖变量 |
| --- | --- | --- |
| `~/.config/acp-workers/registry.json` | worker 配置，结构见 [../assets/registry.example.json](../assets/registry.example.json) | `ACPW_CONFIG_DIR` |
| `~/.local/state/acp-workers/<name>/` | secret、pid、日志 | `ACPW_STATE_DIR` |
| `~/.local/state/acp-workers/_pool/` | pool daemon 的 secret、pid、日志、bind、`sessions.json` | `ACPW_STATE_DIR`；bind 另可用 `ACPW_POOL_BIND` |

registry 不需要手写，`acpw add` / `acpw up` 会维护。示例文件只用于对照字段：`bind` 默认 `0.0.0.0`，写成 `127.0.0.1` 就只收本机；`stdio_argv` 用于二进制不在默认位置时覆盖。`_pool` 下划线开头，不会和 worker 名字撞。

## 卸载

顺序固定：先停 worker，再卸 CLI 与补全，最后卸 skill。

```bash
acpw down               # 停共享 WebSocket，连带收掉名下所有 child
acpw down grok --no-pool  # 若起过独立 gateway / serve，再逐个停
acpw uninstall          # 补全文件 + ~/.bashrc 标记
acpw uninstall --purge  # 上一项 + 停全部已登记 worker + 删 config 与 state 目录
uv tool uninstall acpw
npx skills remove acp-workers -g
rm ~/.agents/skills/acp-workers   # 若当初是软链
```

`acpw uninstall` 不会移除 `uv tool` 装的 `acpw` 二进制，最后一步的 `uv tool uninstall acpw` 不能省。
