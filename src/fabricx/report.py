"""Write JSON (machine) + Markdown (human) reports with environment metadata."""
from __future__ import annotations

import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .validators import ALL, Finding


def env_meta() -> dict:
    def sh(c: str) -> str:
        try:
            return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:  # noqa: BLE001
            return "unknown"
    return {"time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "host": platform.platform(),
            "frr": "quay.io/frrouting/frr:10.2.1",
            "containerlab": sh("orb -m fabricx-lab sudo containerlab version 2>/dev/null | grep version")}


def write(out: Path, findings: list[Finding], state: dict) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    checks = [c.__name__.replace("check_", "") for c in ALL]
    meta = env_meta()
    (out / "report.json").write_text(json.dumps(
        {"meta": meta, "checks": checks, "passed": not findings,
         "findings": [f.to_dict() for f in findings], "state": state}, indent=1, default=str))
    md = ["# FabricX validation report", "", f"- Time (UTC): {meta['time_utc']}",
          f"- Checks run: {', '.join(checks)}",
          f"- Result: **{'PASS' if not findings else f'FAIL ({len(findings)} findings)'}**", ""]
    if findings:
        md += ["| Check | Node | Message |", "|---|---|---|"]
        md += [f"| {f.check} | {f.node} | {f.message} |" for f in findings]
    (out / "report.md").write_text("\n".join(md) + "\n")
    return out / "report.md"
