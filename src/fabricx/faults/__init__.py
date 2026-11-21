"""Fault catalogue. Every fault is confined to lab containers (it only runs `docker exec` into clab-* nodes)."""
from __future__ import annotations

from .catalogue import CATALOGUE, Fault, get

__all__ = ["CATALOGUE", "Fault", "get"]
