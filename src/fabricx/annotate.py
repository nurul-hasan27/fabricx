"""Grafana annotations for fault injection, so every dashboard dip lines up with its cause.

Active only when FABRICX_GRAFANA_URL is set (e.g. http://fabricx-lab.orb.local:3000). The local Grafana runs
with anonymous admin access (lab only), so no credentials are needed. A failure to post never breaks a test."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request


def post(text: str, tags: list[str]) -> bool:
    url = os.environ.get("FABRICX_GRAFANA_URL", "").rstrip("/")
    if not url:
        return False
    body = json.dumps({"time": int(time.time() * 1000), "tags": ["fabricx", *tags], "text": text}).encode()
    req = urllib.request.Request(f"{url}/api/annotations", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    # One retry: the first request to a freshly started Grafana was seen to take longer than 3 s, and the
    # inject marker of the first demo run was lost silently. Never silent again: a miss is printed.
    err = "non-2xx answer"
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                if 200 <= r.status < 300:
                    return True
        except OSError as e:
            err = str(e)
    print(f"[annotate] could not post '{text}' to {url}: {err}", file=sys.stderr)
    return False
