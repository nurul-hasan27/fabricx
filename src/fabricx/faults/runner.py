"""Run one fault end to end and keep an evidence bundle (blueprint 10.2):
baseline green -> probe + inject -> observe -> diagnose (blind) -> restore -> baseline green again."""
from __future__ import annotations

import gzip
import json
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import annotate, collectors, diagnose, model, validators
from ..runner import PREFIX, node_exec
from .catalogue import Fault

ACTIVE = Path("artifacts/active_fault.json")


def now() -> float:
    return time.time()


def wait_healthy(f: model.Fabric, timeout: int = 240) -> float:
    """Wait until validate is clean. Returns seconds waited."""
    t0 = now()
    while now() - t0 < timeout:
        if not validators.validate(f, collectors.Collector(f).snapshot()):
            return now() - t0
        time.sleep(4)
    raise RuntimeError("fabric did not return to healthy")


def traffic_classes(f: model.Fabric) -> dict[str, bool]:
    return diagnose._dataplane(f)  # noqa: SLF001  (same four ping checks the diagnoser uses)


def inject(f: model.Fabric, fault: Fault) -> dict:
    ts = now()
    state = fault.inject(f)
    annotate.post(f"inject {fault.id}: {fault.name}", ["inject", fault.id])
    ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE.write_text(json.dumps({"id": fault.id, "state": state, "ts": ts}))
    return state


def restore(f: model.Fabric, fault: Fault, state: dict | None = None) -> None:
    if state is None and ACTIVE.exists():
        state = json.loads(ACTIVE.read_text()).get("state", {})
    fault.restore(f, state or {})
    annotate.post(f"restore {fault.id}: {fault.name}", ["restore", fault.id])
    ACTIVE.unlink(missing_ok=True)


def run_fault(f: model.Fabric, fault: Fault, out_root: Path = Path("artifacts/runs"),
              probe_seconds: int = 0) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    d = out_root / f"{stamp}_{fault.id}"
    for sub in ("baseline", "during", "after", "probe"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    tl: dict = {"fault": fault.id}
    tl["baseline_wait_s"] = wait_healthy(f)
    collectors.Collector(f, d / "baseline").snapshot()
    (d / "baseline" / "classes.json").write_text(json.dumps(traffic_classes(f)))

    probe = None
    if probe_seconds:
        h = f.hosts_by_name()
        probe = subprocess.Popen(shlex.split(PREFIX) + shlex.split(
            f"docker exec clab-{f.name}-h4 python3 /opt/probe.py recv --bind {h['h4'].ip} --port 9000 "
            f"--duration {probe_seconds + 3} --out /tmp/r.csv"), stdout=subprocess.PIPE, text=True)
        time.sleep(1)
        subprocess.Popen(shlex.split(PREFIX) + shlex.split(
            f"docker exec clab-{f.name}-h1 python3 /opt/probe.py send --src {h['h1'].ip} --dst {h['h4'].ip} "
            f"--port 9000 --interval-ms 1 --duration {probe_seconds}"), stdout=subprocess.PIPE, text=True)
        time.sleep(2)

    tl["inject_ts"] = now()
    state = inject(f, fault)
    time.sleep(2)
    during_t2 = collectors.Collector(f, d / "during" / "t+2s").snapshot()
    time.sleep(max(0, fault.settle_s - 2))
    tl["observed_ts"] = now()
    # blind diagnosis: only live state + inventory are used
    diag, deep = diagnose.diagnose(f)
    (d / "during" / "diagnosis.json").write_text(json.dumps(diag.to_dict(), indent=1))
    (d / "during" / "deep_state.json").write_text(json.dumps(deep, indent=1, default=str))
    (d / "during" / "diagnosis.txt").write_text(diagnose.render(diag))
    findings = validators.validate(f, during_t2)
    (d / "during" / "validate_findings.json").write_text(json.dumps([x.to_dict() for x in findings], indent=1))
    classes = diag.symptoms
    tl["diagnosed_ts"] = now()

    restore(f, fault, state)
    tl["restore_ts"] = now()
    tl["recovery_s"] = wait_healthy(f)
    after_state = collectors.Collector(f, d / "after").snapshot()
    tl["healthy_again_ts"] = now()
    after_findings = validators.validate(f, after_state)

    if probe:
        probe.communicate(timeout=60)
        csv = node_exec(f.name, "h4", "cat /tmp/r.csv", 60).stdout
        with gzip.open(d / "probe" / "h1-h4.csv.gz", "wt") as fh:
            fh.write(csv)

    got = {x.cause_key for x in diag.primary}
    observed_failing = sorted(k for k, ok in classes.items() if not ok and k != "c4")
    isolation_breach = bool(classes.get("c4"))
    result = {
        "fault": fault.id, "name": fault.name, "expected_cause": fault.cause_key, "layer": fault.layer,
        "diagnosed_causes": sorted(got), "localised": fault.cause_key in got and diag.primary[0].layer == fault.layer
        if diag.primary else False,
        "primary_layer": diag.primary[0].layer if diag.primary else None,
        "expected_failing": fault.expected_failing, "observed_failing": observed_failing,
        "symptoms_match_hypothesis": sorted(fault.expected_failing) == observed_failing,
        "isolation_breach": isolation_breach, "healthy_after_restore": not after_findings, "timeline": tl,
    }
    (d / "timeline.json").write_text(json.dumps(tl, indent=1))
    (d / "manifest.json").write_text(json.dumps(
        {"fault": fault.id, "how": fault.how, "run_dir": str(d), "operator": "fabricx run-fault",
         "versions": "see versions.lock.md", "topology": "ebgp-underlay / evpn", "result": result}, indent=1))
    md = [f"# {fault.id} — {fault.name}", "", f"- Layer: {fault.layer}", f"- Injected by: {fault.how}",
          f"- Customer symptom (hypothesis): {fault.symptom}",
          f"- Traffic classes failing: expected {fault.expected_failing or 'none'}, observed {observed_failing or 'none'}",
          f"- Diagnosis localised the fault: **{result['localised']}** (expected `{fault.cause_key}`, got {sorted(got)})",
          f"- First evidence command: `{fault.first_evidence}`",
          f"- Healthy again after restore: **{result['healthy_after_restore']}** (recovery {tl['recovery_s']:.0f} s)",
          "", "## Diagnosis output", "", "```", diagnose.render(diag), "```"]
    (d / "report.md").write_text("\n".join(md) + "\n")
    result["run_dir"] = str(d)
    return result
