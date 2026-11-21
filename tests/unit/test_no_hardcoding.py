"""Rule: no IP, ASN or VNI literal may appear in code or templates. Only the inventory has them."""
import re
from pathlib import Path

IP = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
ALLOWED = {"127.0.0.1", "0.0.0.0"}


def test_no_ip_literals_in_code_or_templates():
    bad = []
    for p in list(Path("src").rglob("*.py")) + list(Path("templates").rglob("*.j2")):
        for n, line in enumerate(p.read_text().splitlines(), 1):
            for m in IP.findall(line):
                if m not in ALLOWED:
                    bad.append(f"{p}:{n}: {m}")
    assert not bad, bad
