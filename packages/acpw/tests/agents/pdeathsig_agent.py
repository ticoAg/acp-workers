"""An agent that asks the kernel to SIGTERM it once its parent goes away, the way Grok does.

Linux ties `PR_SET_PDEATHSIG` to the parent *thread*, not the parent process, so this agent
dies the moment the thread that forked it exits. That makes it the only mock that can catch a
daemon which forks children on its short-lived per-request threads.
"""

from __future__ import annotations

import ctypes
import signal

from acpw.agents.echo import main

PR_SET_PDEATHSIG = 1

if __name__ == "__main__":
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0)
    main()
