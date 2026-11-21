"""Render templates from the fabric model into generated/."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .model import Fabric

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined,
                       trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)


def render_all(f: Fabric, routing: bool = True) -> dict[str, str]:
    """Return {relative_path: file_text}. Pure function, easy to unit test."""
    env, files = _env(), {}
    files[f"{f.name}.clab.yml"] = env.get_template("clab.yml.j2").render(f=f)
    for sw in f.spines + f.leaves:
        d = f"configs/{sw.name}"
        files[f"{d}/frr.conf"] = env.get_template("frr.conf.j2").render(
            f=f, sw=sw, ifaces=f.iface_ips(sw.name),
            nbrs=f.neighbors(sw.name), routing=routing, u=f.underlay,
            is_leaf=sw in f.leaves, isis_net=f.isis_net(sw.name),
            vlans=f.leaf_vlans(sw.name), vrfs=f.leaf_vrfs(sw.name))
        files[f"{d}/daemons"] = env.get_template("daemons.j2").render(routing=routing, u=f.underlay)
        if sw in f.leaves:
            files[f"{d}/setup.sh"] = env.get_template("leaf-setup.sh.j2").render(
                f=f, sw=sw, vlans=f.leaf_vlans(sw.name), vrfs=f.leaf_vrfs(sw.name),
                ports=[hl for hl in f.host_links() if hl.leaf == sw.name])
            files[f"{d}/ports.sh"] = env.get_template("leaf-ports.sh.j2").render(
                f=f, sw=sw, ports=[hl for hl in f.host_links() if hl.leaf == sw.name])
        files[f"{d}/vtysh.conf"] = env.get_template("vtysh.conf.j2").render()
    return files


def write_all(f: Fabric, out: Path, routing: bool = True) -> list[Path]:
    written = []
    for rel, text in render_all(f, routing).items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        written.append(p)
    return written
