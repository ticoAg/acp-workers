# Install / Uninstall

Skill 和 CLI 是两件东西。Skill 让各 agent 扫到 `SKILL.md`；CLI 提供 `acpw` 二进制。

装完 skill 之后，CLI 交给随 skill 一起下发的脚本：

```bash
bash scripts/ensure-acpw.sh              # 幂等；够新就报 already，偏旧自动升级
bash scripts/ensure-acpw.sh --update     # 主动重装到源里的最新版
bash scripts/ensure-acpw.sh --completion # 顺带注册 bash 补全（写 ~/.bashrc）
bash scripts/ensure-acpw.sh --force      # 无条件重装
```

脚本在 checkout 里会优先用同仓库的 `packages/acpw`，只装了 skill 时回落到 GitHub。stdout 恒为一行 JSON，进度在 stderr。下面是它替你做的事，手动装时照做。

## 版本

skill 和 CLI 同版本号发布。三处必须一致：`packages/acpw/pyproject.toml`、`skills/acp-workers/metadata.json`、`SKILL.md` frontmatter 里的 `metadata.version`；CI 会卡这一点。

```bash
acpw version   # {"ok":true,"version":"0.1.0","python":"3.12.14","location":"…"}
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

registry 不需要手写，`acpw add` / `acpw up` 会维护。示例文件只用于对照字段。

## Uninstall

顺序固定：先停 worker，再卸 CLI 与补全，最后卸 skill。

```bash
acpw down grok          # 每个 live worker 停一次
acpw uninstall          # 补全文件 + ~/.bashrc 标记
acpw uninstall --purge  # 上一项 + 停全部已登记 worker + 删 config 与 state 目录
uv tool uninstall acpw
npx skills remove acp-workers -g
rm ~/.agents/skills/acp-workers   # 若当初是软链
```

`acpw uninstall` 不会移除 `uv tool` 装的 `acpw` 二进制，最后一步的 `uv tool uninstall acpw` 不能省。
