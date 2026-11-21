"""fabricx-probe: sequence-numbered UDP probe to measure loss windows.

Standard library only, so the same file runs inside lab containers (bind-mounted)
and on the Mac for unit tests. Resolution is about +/- one send interval.

  receiver:  python3 probe.py recv --bind <ip> --port 9000 --duration 10 --out r.csv
  sender:    python3 probe.py send --src <ip> --dst <ip> --port 9000 --interval-ms 1 --duration 10
"""
from __future__ import annotations

import argparse
import socket
import struct
import time

HDR = struct.Struct("!QQ")  # seq, send_ts_ns


def analyze(rows: list[tuple[int, int, int]], sent: int | None = None) -> dict:
    """rows = [(seq, send_ts_ns, recv_ts_ns)] in arrival order.

    loss        : packets sent but never received (needs `sent`, else inferred from max seq)
    longest_gap : largest time between two consecutive arrivals, in ms (the outage estimate)
    reordered   : packets that arrived after a higher-numbered one
    """
    if not rows:
        return {"received": 0, "sent": sent or 0, "lost": sent or 0, "longest_gap_ms": None,
                "reordered": 0, "duplicates": 0}
    seqs = [r[0] for r in rows]
    uniq = set(seqs)
    total = sent if sent is not None else max(uniq) + 1
    reordered, hi = 0, -1
    for s in seqs:
        if s < hi:
            reordered += 1
        hi = max(hi, s)
    ordered = sorted(rows, key=lambda r: r[2])
    gap = max((b[2] - a[2] for a, b in zip(ordered, ordered[1:], strict=False)), default=0)
    return {"received": len(uniq), "sent": total, "lost": total - len(uniq),
            "longest_gap_ms": gap / 1e6, "reordered": reordered, "duplicates": len(seqs) - len(uniq)}


def send(src: str, dst: str, port: int, interval_ms: float, duration: float) -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((src, 0))
    step = int(interval_ms * 1e6)
    start = time.perf_counter_ns()
    n, end = 0, start + int(duration * 1e9)
    while True:
        due = start + n * step
        if due >= end:
            break
        while time.perf_counter_ns() < due:
            pass
        s.sendto(HDR.pack(n, time.time_ns()) + b"\0" * 32, (dst, port))
        n += 1
    return n


def recv(bind: str, port: int, duration: float) -> list[tuple[int, int, int]]:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((bind, port))
    s.settimeout(0.2)
    rows, end = [], time.time() + duration
    while time.time() < end:
        try:
            data, _ = s.recvfrom(2048)
        except TimeoutError:
            continue
        seq, ts = HDR.unpack(data[:HDR.size])
        rows.append((seq, ts, time.time_ns()))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("recv")
    r.add_argument("--bind", required=True)
    r.add_argument("--port", type=int, default=9000)
    r.add_argument("--duration", type=float, default=10)
    r.add_argument("--out", default="")
    r.add_argument("--sent", type=int, default=None)
    t = sub.add_parser("send")
    t.add_argument("--src", required=True)
    t.add_argument("--dst", required=True)
    t.add_argument("--port", type=int, default=9000)
    t.add_argument("--interval-ms", type=float, default=1.0)
    t.add_argument("--duration", type=float, default=10)
    sub.add_parser("now")
    a = ap.parse_args()
    if a.mode == "now":
        print(time.time_ns())
    elif a.mode == "send":
        print(send(a.src, a.dst, a.port, a.interval_ms, a.duration))
    else:
        rows = recv(a.bind, a.port, a.duration)
        if a.out:
            with open(a.out, "w") as fh:
                fh.write("seq,send_ts_ns,recv_ts_ns\n")
                fh.writelines(f"{x},{y},{z}\n" for x, y, z in rows)
        print(analyze(rows, a.sent))


if __name__ == "__main__":
    main()
