import subprocess

import pytest

from fabricx import runner


def test_timeout_becomes_node_unreachable(monkeypatch):
    calls = []

    def fake_run(*a, **k):
        calls.append(1)
        raise subprocess.TimeoutExpired("x", 1)
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(runner.NodeUnreachable):
        runner.node_exec("lab", "n1", "true", timeout=1, retries=2)
    assert len(calls) == 3  # 1 try + 2 retries


def test_paused_container_is_unreachable(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 1, "", "Error response from daemon: Container abc is paused, unpause the container"))
    with pytest.raises(runner.NodeUnreachable):
        runner.node_exec("lab", "n1", "true")


def test_normal_failure_is_not_unreachable(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 2, "", "boom"))
    assert runner.node_exec("lab", "n1", "false").returncode == 2


def test_timeout_enforced_inside_the_prefixed_process(monkeypatch):
    seen = []

    def fake_run(argv, **k):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 124, "", "")   # `timeout` fired
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(runner.NodeUnreachable):
        runner.node_exec("lab", "n1", "sleep 99", timeout=5)
    assert seen[0][-6:-3] == ["timeout", "-k", "3"] or "timeout" in seen[0]
