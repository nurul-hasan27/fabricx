"""Traceability matrix: requirement -> tests -> last result -> evidence, generated from tests/specs/*.yaml."""
from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml


def load_specs(d: Path = Path("tests/specs")) -> list[dict]:
    specs: list[dict] = []
    for p in sorted(d.glob("*.yaml")):
        specs += yaml.safe_load(p.read_text())
    return specs


def collected_ids() -> list[str]:
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"],
                       capture_output=True, text=True)
    return [ln for ln in r.stdout.splitlines() if "::" in ln]


def junit_results(pattern: str = "artifacts/junit*.xml") -> dict[str, str]:
    """nodeid -> pass|fail|skip merged from all JUnit XML files matching the pattern (empty if none)."""
    out: dict[str, str] = {}
    for path in sorted(Path(".").glob(pattern)):
        for tc in ET.parse(path).getroot().iter("testcase"):
            nid = tc.get("classname", "").replace(".", "/") + ".py::" + tc.get("name", "")
            out[nid] = ("fail" if tc.find("failure") is not None or tc.find("error") is not None
                        else "skip" if tc.find("skipped") is not None else "pass")
    return out


def build(specs: list[dict], ids: list[str], results: dict[str, str]) -> tuple[str, list[str]]:
    """Return (markdown, problems). Problems = spec test patterns that match no collected test."""
    problems: list[str] = []
    rows = ["| Requirement | Title | Tests (matching) | Last result | Evidence |", "|---|---|---|---|---|"]
    for s in specs:
        matched: list[str] = []
        for pat in s["tests"]:
            m = [i for i in ids if i == pat or i.startswith(pat + "[")]
            if not m:
                problems.append(f"{s['id']}: no test matches {pat}")
            matched += m
        res = [results.get(m) for m in matched if m in results]
        status = "not run" if not res else ("FAIL" if "fail" in res else f"pass ({len(res)}/{len(matched)})")
        rows.append(f"| {s['id']} | {s['title']} | {len(matched)} | {status} | {', '.join(s['evidence'])} |")
    return "\n".join(rows) + "\n", problems
