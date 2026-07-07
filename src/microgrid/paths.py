"""Project-root-relative path resolution.

Keeps all filesystem layout knowledge in one place so no module hardcodes
directory strings. Paths in yaml configs are interpreted relative to the
project root (the directory containing ``pyproject.toml``).
"""

from __future__ import annotations

from pathlib import Path


def project_root(start: Path | None = None) -> Path:
    """Walk upwards until a directory containing pyproject.toml is found."""
    p = (start or Path(__file__)).resolve()
    for parent in [p, *p.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    raise FileNotFoundError("pyproject.toml not found above " + str(p))


def resolve(path_str: str) -> Path:
    """Resolve a (possibly relative) config path against the project root."""
    p = Path(path_str)
    return p if p.is_absolute() else project_root() / p
