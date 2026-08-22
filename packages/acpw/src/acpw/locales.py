"""CLI catalogs. English text is the msgid; en-US is identity."""

from __future__ import annotations

ZH_CN: dict[str, str] = {
    # UI chrome
    "Usage: ": "用法: ",
    "Options": "选项",
    "Commands": "命令",
    "Arguments": "参数",
    "Error": "错误",
    "Aborted.": "已中止。",
    "Description": "说明",
    "[OPTIONS]": "[选项]",
    "COMMAND [ARGS]...": "命令 [参数]...",
    "[ARGS]...": "[参数]...",
    "[default: {}]": "[默认: {}]",
    "[env var: {}]": "[环境变量: {}]",
    "[required]": "[必填]",
    "(deprecated) ": "(已弃用) ",
    "Show this message and exit.": "显示本帮助并退出。",
    "Install completion for the current shell.": "为当前 shell 安装补全。",
    "Show completion for the current shell, to copy it or customize the installation.": (
        "显示当前 shell 的补全脚本，便于复制或自定义安装。"
    ),
    "Install completion for the specified shell.": "为指定 shell 安装补全。",
    "Show completion for the specified shell, to copy it or customize the installation.": (
        "显示指定 shell 的补全脚本，便于复制或自定义安装。"
    ),
    "Try [blue]'{command_path} {help_option}'[/] for help.": (
        "试试 [blue]'{command_path} {help_option}'[/] 查看帮助。"
    ),
    "Try '{command_path} {help_option}' for help.\n": (
        "试试 '{command_path} {help_option}' 查看帮助。\n"
    ),
    "Missing argument {hint}.{extra}": "缺少参数 {hint}。{extra}",
    "Missing option {hint}.{extra}": "缺少选项 {hint}。{extra}",
    "Missing parameter {hint}.{extra}": "缺少参数 {hint}。{extra}",
    "Invalid value for {hint}: {message}": "选项 {hint} 的值无效: {message}",
    "Invalid value: {message}": "无效的值: {message}",
    "No such option: {name}": "没有这个选项: {name}",
    "No such option: {name} (Possible options: {options})": (
        "没有这个选项: {name}（候选: {options}）"
    ),
    "No such command {name}.": "没有这个命令 {name}。",
    "No such command {name}. Did you mean {suggestions}?": (
        "没有这个命令 {name}。是不是想输入 {suggestions}？"
    ),
    "Got unexpected extra argument(s) ({args})": "多余的参数（{args}）",
    "Could not open file {filename}: {message}": "无法打开文件 {filename}: {message}",
    "{value} is not a valid {name}.": "{value} 不是有效的 {name}。",
    "{shell} completion installed in {path}": "{shell} 补全已安装到 {path}",
    "Completion will take effect once you restart the terminal": "重新打开终端后补全才会生效",
    # app / commands
    "One WebSocket, many agents. Host plans; workers execute.": (
        "一条 WebSocket，多个 agent。Host 规划，worker 执行。"
    ),
    "Print the acpw version and exit.": "打印 acpw 版本并退出。",
    "CLI help language. Overrides ACPW_LANG and the saved config.": (
        "CLI 帮助语言。覆盖 ACPW_LANG 和已保存的配置。"
    ),
    "Write JSON instead of markdown.": "输出 JSON，而不是 markdown。",
    "Output format: markdown (default) or json. Overrides ACPW_OUTPUT and the saved config.": (
        "输出格式：markdown（默认）或 json。覆盖 ACPW_OUTPUT 和已保存的配置。"
    ),
    "Print the installed acpw version.": "打印已安装的 acpw 版本。",
    "List workers and the shared WebSocket.": "列出 worker 和共享 WebSocket。",
    "Check adapter binaries on PATH.": "检查 PATH 上的适配器二进制。",
    "Verify the installation end to end. Exits 1 if any check fails.": (
        "端到端核验安装。任一项失败则退出 1。"
    ),
    "Dispatch to a throwaway mock worker.": "向一次性 mock worker 派发探测。",
    "Register a worker or a manual websocket URL.": "登记一个 worker 或手动 websocket URL。",
    "Registry name for this worker.": "registry 里的 worker 名。",
    "ws://127.0.0.1:PORT/ws?server-key=...": "ws://127.0.0.1:PORT/ws?server-key=...",
    "host:port to listen on when this CLI starts the worker.": (
        "本 CLI 拉起该 worker 时监听的 host:port。"
    ),
    "grok, claude, codex, cursor, or mock.": "grok、claude、codex、cursor 或 mock。",
    "Unregister a worker.": "注销一个 worker。",
    "Registry name to unregister.": "要注销的 registry 名。",
    "Start the shared WebSocket, optionally pre-warming workers.": (
        "启动共享 WebSocket，可选预热 worker。"
    ),
    "Workers to pre-warm on the pool. Omit to start the socket only.": (
        "要在 pool 上预热的 worker。省略则只起 socket。"
    ),
    "Working directory for pre-warmed workers.": "预热 worker 的工作目录。",
    "Seconds to wait for the socket and children to come up.": (
        "等待 socket 和 child 就绪的秒数。"
    ),
    "Default: the shared WebSocket. --no-pool starts a standalone gateway/serve.": (
        "默认走共享 WebSocket。--no-pool 起独立 gateway / serve。"
    ),
    "Stop the shared WebSocket, or one child on it.": ("停止共享 WebSocket，或上面的一个 child。"),
    "One pooled child. Omit to stop the shared WebSocket.": (
        "一个 pool 里的 child。省略则停掉共享 WebSocket。"
    ),
    "Default: the shared WebSocket. --no-pool stops a standalone gateway/serve.": (
        "默认走共享 WebSocket。--no-pool 停独立 gateway / serve。"
    ),
    "ACP initialize against a live worker.": "对活着的 worker 做 ACP initialize。",
    "Worker to handshake with.": "要握手的 worker。",
    "Default: the shared WebSocket, for stdio workers.": (
        "默认走共享 WebSocket，适用于 stdio worker。"
    ),
    "Dispatch a prompt. Returns a session_id; pass --session-id to resume.": (
        "派发一条 prompt。返回 session_id；续会话加 --session-id。"
    ),
    "Worker to dispatch to.": "要派发的 worker。",
    "Prompt text. Mutually exclusive with --prompt-file.": ("prompt 文本。与 --prompt-file 互斥。"),
    "Read the prompt from this file.": "从该文件读取 prompt。",
    "Working directory for the session.": "会话的工作目录。",
    "Resume this session instead of opening a new one.": ("续这个 session，而不是新开一个。"),
    "Connect to this websocket and skip the pool.": "连这个 websocket 并绕开 pool。",
    "Seconds to wait for the agent to finish the turn.": ("等待 agent 完成本回合的秒数。"),
    "Register bash completion for this user.": "为当前用户注册 bash 补全。",
    "Remove bash completion. Does not uninstall the uv tool or skill.": (
        "移除 bash 补全。不会卸载 uv tool 或 skill。"
    ),
    "Also stop workers and delete registry and state.": (
        "同时停掉 worker 并删除 registry 和 state。"
    ),
    "Show or save the CLI language.": "查看或保存 CLI 语言。",
    "Print the current CLI language.": "打印当前 CLI 语言。",
    "Save the CLI language.": "保存 CLI 语言。",
    "Language to save: zh-CN, en-US, or zh-TW.": ("要保存的语言：zh-CN、en-US 或 zh-TW。"),
    "Show or save the CLI output format.": "查看或保存 CLI 输出格式。",
    "Print the current CLI output format.": "打印当前 CLI 输出格式。",
    "Save the CLI output format.": "保存 CLI 输出格式。",
    "Format to save: markdown or json.": "要保存的格式：markdown 或 json。",
    "One resident daemon, one port, many children.": ("一个常驻 daemon，一个端口，多个 child。"),
    "Start the pool daemon if it is not live.": "若 pool daemon 未在运行则启动它。",
    "Bind host:port for the pool daemon.": "pool daemon 的 bind host:port。",
    "Pre-warm these workers.": "预热这些 worker。",
    "Stop the pool daemon and every child it owns.": ("停止 pool daemon 及其名下每个 child。"),
    "Pool liveness, children, and session counts.": "pool 探活、child 和 session 计数。",
    "Internal multiplexing daemon. Started by `acpw up`.": ("内部多路 daemon。由 `acpw up` 启动。"),
    "Internal stdio-to-websocket bridge. Started by `acpw up --no-pool`.": (
        "内部 stdio 到 websocket 桥。由 `acpw up --no-pool` 启动。"
    ),
    "File that holds the server-key.": "写有 server-key 的文件。",
    "Listen address host:port.": "监听地址 host:port。",
    "Worker name for this child.": "这个 child 的 worker 名。",
    "JSON array of the stdio argv.": "stdio argv 的 JSON 数组。",
    "Working directory for the child.": "child 的工作目录。",
    # errors
    "--no-pool needs a worker name": "--no-pool 需要 worker 名",
    "empty prompt": "prompt 为空",
    "worker {name} has no stdio adapter and cannot be pooled; drop --pool": (
        "worker {name} 没有 stdio 适配器，不能进 pool；去掉 --pool"
    ),
    "unknown worker {name}": "未知 worker {name}",
    "unknown kind {kind}": "未知 kind {kind}",
    "{name} is disabled in registry": "{name} 在 registry 里被禁用",
    "manual url is not live": "手动 url 当前不可达",
    "grok not on PATH": "PATH 上找不到 grok",
    "{name} missing stdio_argv": "{name} 缺少 stdio_argv",
    "binary not on PATH: {head}": "PATH 上找不到二进制: {head}",
    "cannot start transport {transport}; use add --url": (
        "无法启动 transport {transport}；请用 add --url"
    ),
    "worker did not become reachable; inspect log": "worker 未能就绪；请查看日志",
    "no bind/url": "没有 bind/url",
    "worker not live": "worker 未在运行",
    "no websocket url": "没有 websocket url",
    "pool did not become reachable; inspect log": "pool 未能就绪；请查看日志",
    "pool not live": "pool 未在运行",
    (
        "pool on {bind} rejected our key: it was started with a different secret than"
        " {secret}. Run 'acpw pool down' and start it again, or point ACPW_STATE_DIR"
        " at the one it uses."
    ): (
        "bind {bind} 上的 pool 拒绝了我们的密钥：它用的 secret 不是 {secret}。"
        "请运行 acpw pool down 再启动，或把 ACPW_STATE_DIR 指到那份 daemon 使用的目录。"
    ),
    "session {session_id} is held by another client": ("session {session_id} 正被另一个客户端占用"),
    "worker {name} cannot resume sessions (loadSession not advertised)": (
        "worker {name} 不能续会话（未广告 loadSession）"
    ),
    "unknown session {session_id}": "未知 session {session_id}",
    "cannot resume session {session_id}: {message}": ("无法续 session {session_id}: {message}"),
    "unsupported language {value}; choose {supported}": ("不支持的语言 {value}；可选 {supported}"),
    "unsupported output format {value}; choose {supported}": (
        "不支持的输出格式 {value}；可选 {supported}"
    ),
    # install
    "acpw not on PATH; run: uv tool install --editable <this-repo>": (
        "PATH 上找不到 acpw；运行: uv tool install --editable <this-repo>"
    ),
    "appended {marker} to ~/.bashrc; open a new shell": (
        "已把 {marker} 追加到 ~/.bashrc；请开一个新 shell"
    ),
    "add {local_bin} to PATH": "把 {local_bin} 加进 PATH",
    "removed ~/.config/acp-workers and ~/.local/state/acp-workers": (
        "已删除 ~/.config/acp-workers 和 ~/.local/state/acp-workers"
    ),
    "CLI still on PATH until: uv tool uninstall acpw": (
        "CLI 仍在 PATH 上，卸载: uv tool uninstall acpw"
    ),
    "skill symlink: rm ~/.agents/skills/acp-workers  (or npx skills remove acp-workers -g)": (
        "skill 软链: rm ~/.agents/skills/acp-workers  （或 npx skills remove acp-workers -g）"
    ),
    # selfcheck
    "package metadata missing; acpw is imported from a source tree, not installed": (
        "缺少包元数据；acpw 是从源码树 import 的，没有真正安装"
    ),
    "acpw {version} at {location}": "acpw {version}，位于 {location}",
    "acpw not on PATH; add ~/.local/bin and reopen the shell": (
        "PATH 上找不到 acpw；把 ~/.local/bin 加进 PATH 并重新打开 shell"
    ),
    "uv not on PATH; updates will fail until it is installed": (
        "PATH 上找不到 uv；装好之前无法升级"
    ),
    "{path}: {detail}": "{path}: {detail}",
    "{path}: {count} workers": "{path}: {count} 个 worker",
    "{path} is writable": "{path} 可写",
    "bash completion not registered; run: acpw install": ("未注册 bash 补全；运行: acpw install"),
    "no agent binary found; install grok, npx, or cursor-agent": (
        "找不到任何 agent 二进制；请安装 grok、npx 或 cursor-agent"
    ),
    "present: {present}": "已找到: {present}",
    "present: {present}; missing: {missing}": "已找到: {present}；缺少: {missing}",
    "all workers bind loopback": "所有 worker 都绑在回环地址",
    (
        "reachable beyond loopback: {exposed}; workers run with always-approve and"
        " server-key travels in cleartext"
    ): ("可从回环以外到达: {exposed}；worker 跑 always-approve，且 server-key 明文过线"),
    "expected {expected!r}, got {got!r}": "期望 {expected!r}，实际 {got!r}",
    "pool session {session_id} answered, stop_reason={stop_reason}": (
        "pool session {session_id} 已应答，stop_reason={stop_reason}"
    ),
    "skipped (--no-live)": "已跳过（--no-live）",
}

ZH_TW: dict[str, str] = {
    "Usage: ": "用法: ",
    "Options": "選項",
    "Commands": "命令",
    "Arguments": "參數",
    "Error": "錯誤",
    "Aborted.": "已中止。",
    "Description": "說明",
    "[OPTIONS]": "[選項]",
    "COMMAND [ARGS]...": "命令 [參數]...",
    "[ARGS]...": "[參數]...",
    "[default: {}]": "[預設: {}]",
    "[env var: {}]": "[環境變數: {}]",
    "[required]": "[必填]",
    "(deprecated) ": "(已棄用) ",
    "Show this message and exit.": "顯示本說明並結束。",
    "Install completion for the current shell.": "為目前 shell 安裝補全。",
    "Show completion for the current shell, to copy it or customize the installation.": (
        "顯示目前 shell 的補全腳本，方便複製或自訂安裝。"
    ),
    "Install completion for the specified shell.": "為指定 shell 安裝補全。",
    "Show completion for the specified shell, to copy it or customize the installation.": (
        "顯示指定 shell 的補全腳本，方便複製或自訂安裝。"
    ),
    "Try [blue]'{command_path} {help_option}'[/] for help.": (
        "試試 [blue]'{command_path} {help_option}'[/] 查看說明。"
    ),
    "Try '{command_path} {help_option}' for help.\n": (
        "試試 '{command_path} {help_option}' 查看說明。\n"
    ),
    "Missing argument {hint}.{extra}": "缺少參數 {hint}。{extra}",
    "Missing option {hint}.{extra}": "缺少選項 {hint}。{extra}",
    "Missing parameter {hint}.{extra}": "缺少參數 {hint}。{extra}",
    "Invalid value for {hint}: {message}": "選項 {hint} 的值無效: {message}",
    "Invalid value: {message}": "無效的值: {message}",
    "No such option: {name}": "沒有這個選項: {name}",
    "No such option: {name} (Possible options: {options})": (
        "沒有這個選項: {name}（候選: {options}）"
    ),
    "No such command {name}.": "沒有這個命令 {name}。",
    "No such command {name}. Did you mean {suggestions}?": (
        "沒有這個命令 {name}。是不是想輸入 {suggestions}？"
    ),
    "Got unexpected extra argument(s) ({args})": "多餘的參數（{args}）",
    "Could not open file {filename}: {message}": "無法開啟檔案 {filename}: {message}",
    "{value} is not a valid {name}.": "{value} 不是有效的 {name}。",
    "{shell} completion installed in {path}": "{shell} 補全已安裝到 {path}",
    "Completion will take effect once you restart the terminal": "重新開啟終端機後補全才會生效",
    "One WebSocket, many agents. Host plans; workers execute.": (
        "一條 WebSocket，多個 agent。Host 規劃，worker 執行。"
    ),
    "Print the acpw version and exit.": "列印 acpw 版本並結束。",
    "CLI help language. Overrides ACPW_LANG and the saved config.": (
        "CLI 說明語言。覆蓋 ACPW_LANG 與已儲存的設定。"
    ),
    "Write JSON instead of markdown.": "輸出 JSON，而不是 markdown。",
    "Output format: markdown (default) or json. Overrides ACPW_OUTPUT and the saved config.": (
        "輸出格式：markdown（預設）或 json。覆蓋 ACPW_OUTPUT 與已儲存的設定。"
    ),
    "Print the installed acpw version.": "列印已安裝的 acpw 版本。",
    "List workers and the shared WebSocket.": "列出 worker 與共享 WebSocket。",
    "Check adapter binaries on PATH.": "檢查 PATH 上的轉接器二進位檔。",
    "Verify the installation end to end. Exits 1 if any check fails.": (
        "端到端核對安裝。任一項失敗則結束碼為 1。"
    ),
    "Dispatch to a throwaway mock worker.": "向一次性 mock worker 派發探測。",
    "Register a worker or a manual websocket URL.": "登記一個 worker 或手動 websocket URL。",
    "Registry name for this worker.": "registry 裡的 worker 名。",
    "ws://127.0.0.1:PORT/ws?server-key=...": "ws://127.0.0.1:PORT/ws?server-key=...",
    "host:port to listen on when this CLI starts the worker.": (
        "本 CLI 拉起該 worker 時監聽的 host:port。"
    ),
    "grok, claude, codex, cursor, or mock.": "grok、claude、codex、cursor 或 mock。",
    "Unregister a worker.": "註銷一個 worker。",
    "Registry name to unregister.": "要註銷的 registry 名。",
    "Start the shared WebSocket, optionally pre-warming workers.": (
        "啟動共享 WebSocket，可選擇預熱 worker。"
    ),
    "Workers to pre-warm on the pool. Omit to start the socket only.": (
        "要在 pool 上預熱的 worker。省略則只起 socket。"
    ),
    "Working directory for pre-warmed workers.": "預熱 worker 的工作目錄。",
    "Seconds to wait for the socket and children to come up.": (
        "等待 socket 與 child 就緒的秒數。"
    ),
    "Default: the shared WebSocket. --no-pool starts a standalone gateway/serve.": (
        "預設走共享 WebSocket。--no-pool 起獨立 gateway / serve。"
    ),
    "Stop the shared WebSocket, or one child on it.": ("停止共享 WebSocket，或上面的一個 child。"),
    "One pooled child. Omit to stop the shared WebSocket.": (
        "一個 pool 裡的 child。省略則停掉共享 WebSocket。"
    ),
    "Default: the shared WebSocket. --no-pool stops a standalone gateway/serve.": (
        "預設走共享 WebSocket。--no-pool 停獨立 gateway / serve。"
    ),
    "ACP initialize against a live worker.": "對執行中的 worker 做 ACP initialize。",
    "Worker to handshake with.": "要握手的 worker。",
    "Default: the shared WebSocket, for stdio workers.": (
        "預設走共享 WebSocket，適用於 stdio worker。"
    ),
    "Dispatch a prompt. Returns a session_id; pass --session-id to resume.": (
        "派發一條 prompt。回傳 session_id；續會話加 --session-id。"
    ),
    "Worker to dispatch to.": "要派發的 worker。",
    "Prompt text. Mutually exclusive with --prompt-file.": ("prompt 文字。與 --prompt-file 互斥。"),
    "Read the prompt from this file.": "從該檔案讀取 prompt。",
    "Working directory for the session.": "會話的工作目錄。",
    "Resume this session instead of opening a new one.": ("續這個 session，而不是新開一個。"),
    "Connect to this websocket and skip the pool.": "連這個 websocket 並繞過 pool。",
    "Seconds to wait for the agent to finish the turn.": ("等待 agent 完成本回合的秒數。"),
    "Register bash completion for this user.": "為目前使用者註冊 bash 補全。",
    "Remove bash completion. Does not uninstall the uv tool or skill.": (
        "移除 bash 補全。不會解除安裝 uv tool 或 skill。"
    ),
    "Also stop workers and delete registry and state.": (
        "同時停掉 worker 並刪除 registry 與 state。"
    ),
    "Show or save the CLI language.": "查看或儲存 CLI 語言。",
    "Print the current CLI language.": "列印目前 CLI 語言。",
    "Save the CLI language.": "儲存 CLI 語言。",
    "Language to save: zh-CN, en-US, or zh-TW.": ("要儲存的語言：zh-CN、en-US 或 zh-TW。"),
    "Show or save the CLI output format.": "查看或儲存 CLI 輸出格式。",
    "Print the current CLI output format.": "列印目前 CLI 輸出格式。",
    "Save the CLI output format.": "儲存 CLI 輸出格式。",
    "Format to save: markdown or json.": "要儲存的格式：markdown 或 json。",
    "One resident daemon, one port, many children.": ("一個常駐 daemon，一個埠，多個 child。"),
    "Start the pool daemon if it is not live.": "若 pool daemon 未在執行則啟動它。",
    "Bind host:port for the pool daemon.": "pool daemon 的 bind host:port。",
    "Pre-warm these workers.": "預熱這些 worker。",
    "Stop the pool daemon and every child it owns.": ("停止 pool daemon 及其名下每個 child。"),
    "Pool liveness, children, and session counts.": "pool 探活、child 與 session 計數。",
    "Internal multiplexing daemon. Started by `acpw up`.": ("內部多路 daemon。由 `acpw up` 啟動。"),
    "Internal stdio-to-websocket bridge. Started by `acpw up --no-pool`.": (
        "內部 stdio 到 websocket 橋。由 `acpw up --no-pool` 啟動。"
    ),
    "File that holds the server-key.": "寫有 server-key 的檔案。",
    "Listen address host:port.": "監聽位址 host:port。",
    "Worker name for this child.": "這個 child 的 worker 名。",
    "JSON array of the stdio argv.": "stdio argv 的 JSON 陣列。",
    "Working directory for the child.": "child 的工作目錄。",
    "--no-pool needs a worker name": "--no-pool 需要 worker 名",
    "empty prompt": "prompt 為空",
    "worker {name} has no stdio adapter and cannot be pooled; drop --pool": (
        "worker {name} 沒有 stdio 轉接器，不能進 pool；去掉 --pool"
    ),
    "unknown worker {name}": "未知 worker {name}",
    "unknown kind {kind}": "未知 kind {kind}",
    "{name} is disabled in registry": "{name} 在 registry 裡被停用",
    "manual url is not live": "手動 url 目前不可達",
    "grok not on PATH": "PATH 上找不到 grok",
    "{name} missing stdio_argv": "{name} 缺少 stdio_argv",
    "binary not on PATH: {head}": "PATH 上找不到二進位檔: {head}",
    "cannot start transport {transport}; use add --url": (
        "無法啟動 transport {transport}；請用 add --url"
    ),
    "worker did not become reachable; inspect log": "worker 未能就緒；請查看日誌",
    "no bind/url": "沒有 bind/url",
    "worker not live": "worker 未在執行",
    "no websocket url": "沒有 websocket url",
    "pool did not become reachable; inspect log": "pool 未能就緒；請查看日誌",
    "pool not live": "pool 未在執行",
    (
        "pool on {bind} rejected our key: it was started with a different secret than"
        " {secret}. Run 'acpw pool down' and start it again, or point ACPW_STATE_DIR"
        " at the one it uses."
    ): (
        "bind {bind} 上的 pool 拒絕了我們的金鑰：它用的 secret 不是 {secret}。"
        "請執行 acpw pool down 再啟動，或把 ACPW_STATE_DIR 指到那份 daemon 使用的目錄。"
    ),
    "session {session_id} is held by another client": ("session {session_id} 正被另一個用戶端佔用"),
    "worker {name} cannot resume sessions (loadSession not advertised)": (
        "worker {name} 不能續會話（未廣告 loadSession）"
    ),
    "unknown session {session_id}": "未知 session {session_id}",
    "cannot resume session {session_id}: {message}": ("無法續 session {session_id}: {message}"),
    "unsupported language {value}; choose {supported}": ("不支援的語言 {value}；可選 {supported}"),
    "unsupported output format {value}; choose {supported}": (
        "不支援的輸出格式 {value}；可選 {supported}"
    ),
    "acpw not on PATH; run: uv tool install --editable <this-repo>": (
        "PATH 上找不到 acpw；執行: uv tool install --editable <this-repo>"
    ),
    "appended {marker} to ~/.bashrc; open a new shell": (
        "已把 {marker} 追加到 ~/.bashrc；請開一個新 shell"
    ),
    "add {local_bin} to PATH": "把 {local_bin} 加進 PATH",
    "removed ~/.config/acp-workers and ~/.local/state/acp-workers": (
        "已刪除 ~/.config/acp-workers 與 ~/.local/state/acp-workers"
    ),
    "CLI still on PATH until: uv tool uninstall acpw": (
        "CLI 仍在 PATH 上，解除安裝: uv tool uninstall acpw"
    ),
    "skill symlink: rm ~/.agents/skills/acp-workers  (or npx skills remove acp-workers -g)": (
        "skill 軟連: rm ~/.agents/skills/acp-workers  （或 npx skills remove acp-workers -g）"
    ),
    "package metadata missing; acpw is imported from a source tree, not installed": (
        "缺少套件中繼資料；acpw 是從原始碼樹 import 的，沒有真正安裝"
    ),
    "acpw {version} at {location}": "acpw {version}，位於 {location}",
    "acpw not on PATH; add ~/.local/bin and reopen the shell": (
        "PATH 上找不到 acpw；把 ~/.local/bin 加進 PATH 並重新開啟 shell"
    ),
    "uv not on PATH; updates will fail until it is installed": (
        "PATH 上找不到 uv；裝好之前無法升級"
    ),
    "{path}: {detail}": "{path}: {detail}",
    "{path}: {count} workers": "{path}: {count} 個 worker",
    "{path} is writable": "{path} 可寫",
    "bash completion not registered; run: acpw install": ("未註冊 bash 補全；執行: acpw install"),
    "no agent binary found; install grok, npx, or cursor-agent": (
        "找不到任何 agent 二進位檔；請安裝 grok、npx 或 cursor-agent"
    ),
    "present: {present}": "已找到: {present}",
    "present: {present}; missing: {missing}": "已找到: {present}；缺少: {missing}",
    "all workers bind loopback": "所有 worker 都綁在回環位址",
    (
        "reachable beyond loopback: {exposed}; workers run with always-approve and"
        " server-key travels in cleartext"
    ): ("可從回環以外到達: {exposed}；worker 跑 always-approve，且 server-key 明文過線"),
    "expected {expected!r}, got {got!r}": "期望 {expected!r}，實際 {got!r}",
    "pool session {session_id} answered, stop_reason={stop_reason}": (
        "pool session {session_id} 已應答，stop_reason={stop_reason}"
    ),
    "skipped (--no-live)": "已跳過（--no-live）",
}

CATALOGS: dict[str, dict[str, str]] = {
    "en-US": {},
    "zh-CN": ZH_CN,
    "zh-TW": ZH_TW,
}
