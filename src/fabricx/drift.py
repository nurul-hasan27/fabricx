"""Config drift: is the running FRR config what the inventory would generate?

Both sides are reduced to a set of 'context path' lines (e.g. 'router bgp 65001 > address-family ipv4
unicast > maximum-paths 2') so a line moved to a different block counts as drift. Lines FRR adds or
omits by itself (banner, version, 'exit', default-valued settings) are ignored; the list is small and explicit.
"""
from __future__ import annotations

import re

# FRR 10.2.1 housekeeping/default lines that appear on one side only. Keep this list short and explicit.
IGNORE = {
    "Building configuration...", "Current configuration:", "end", "line vty",
    "no ipv6 forwarding", "no bgp ebgp-requires-policy",
    "detect-multiplier 3", "receive-interval 300", "transmit-interval 300",
}
IGNORE_RE = re.compile(r"^(frr version .*|exit.*)$")
# Lines the SONiC-VS image's own zebra config adds (FPM to fpmsyncd, next-hop handling). Seen on CI with
# 202505 build 1238524. They belong to the image, not to our inventory, so they are not drift.
SONIC_IGNORE = {
    "fpm address 127.0.0.1", "no fpm use-next-hop-groups", "ip nht resolve-via-default",
    "ipv6 nht resolve-via-default", "no zebra nexthop kernel enable", "zebra nexthop-group keep 1",
}


def normalize(text: str, extra_ignore: frozenset[str] = frozenset()) -> set[str]:
    out: set[str] = set()
    stack: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.strip() == "!" or raw.lstrip().startswith("! "):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if line in IGNORE or line in extra_ignore or IGNORE_RE.match(line):
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        out.add(" > ".join([p for _, p in stack] + [line]))
        stack.append((indent, line))
    return out


def diff(generated: str, running: str, nos: str = "frr") -> tuple[list[str], list[str]]:
    """(missing_from_running, extra_in_running). Parent lines that only exist as context are not reported twice."""
    extra = frozenset(SONIC_IGNORE) if nos == "sonic-vs" else frozenset()
    g, r = normalize(generated, extra), normalize(running, extra)

    def leaves(s: set[str]) -> set[str]:
        return {x for x in s if not any(y.startswith(x + " > ") for y in s)}
    return sorted(leaves(g) - leaves(r)), sorted(leaves(r) - leaves(g))
