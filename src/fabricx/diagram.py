"""Mermaid topology diagram generated from the model."""
from .model import Fabric


def mermaid(f: Fabric) -> str:
    lines = ["```mermaid", "graph TD"]
    for lk in f.fabric_links():
        lines.append(f'  {lk.spine} ---|"{lk.spine_ip}/{lk.prefixlen} - {lk.leaf_ip}/{lk.prefixlen}"| {lk.leaf}')
    for h in f.hosts:
        lines.append(f'  {h.leaf} --- {h.name}["{h.name} {h.ip}"]')
    lines.append("```")
    return "\n".join(lines) + "\n"
