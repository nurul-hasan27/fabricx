"""Run commands inside lab containers.

The prefix is configurable so the same code works from the Mac (through the OrbStack VM) and on a
CI runner (FABRICX_EXEC='sudo'). Commands have timeouts and retries; a container that is stopped,
paused or hung raises NodeUnreachable instead of hanging the whole run.
"""
from __future__ import annotations

import os
import shlex
import subprocess

PREFIX = os.environ.get("FABRICX_EXEC", "orb -m fabricx-lab sudo")
_DEAD = ("No such container", "is not running", "is paused", "container not found")


class NodeUnreachable(Exception):
    def __init__(self, node: str, reason: str):
        super().__init__(f"{node}: {reason}")
        self.node = node
        self.reason = reason


def sh(cmd: str, timeout: int = 60, retries: int = 0) -> subprocess.CompletedProcess[str]:
    """Run a command (prefix + cmd). Retries on timeout; raises subprocess.TimeoutExpired when exhausted.

    The time limit is enforced by `timeout -k` running INSIDE the prefixed (sudo) process: an ordinary
    user cannot kill a root-owned child, and Python would then wait forever on its pipes (seen on CI).
    The Python-side limit is only a backstop."""
    argv = shlex.split(PREFIX) + ["timeout", "-k", "3", str(timeout)] + shlex.split(cmd)
    last: subprocess.TimeoutExpired | None = None
    for _ in range(retries + 1):
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout + 15)
        except subprocess.TimeoutExpired as e:
            last = e
            continue
        if r.returncode in (124, 137):   # killed by `timeout` (TERM / KILL after grace)
            last = subprocess.TimeoutExpired(cmd, timeout)
            continue
        return r
    assert last is not None
    raise last


def node_exec(lab: str, node: str, cmd: str, timeout: int = 60, retries: int = 0) -> subprocess.CompletedProcess[str]:
    """docker exec into clab-<lab>-<node>. Raises NodeUnreachable for dead/paused/hung containers."""
    try:
        r = sh(f"docker exec clab-{lab}-{node} {cmd}", timeout, retries)
    except subprocess.TimeoutExpired as e:
        raise NodeUnreachable(node, f"no answer after {timeout}s x {retries + 1}") from e
    if r.returncode != 0 and any(m in r.stderr for m in _DEAD):
        raise NodeUnreachable(node, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "dead")
    return r
