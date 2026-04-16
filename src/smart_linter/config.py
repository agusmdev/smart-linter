"""Configuration loading from pyproject.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_EXCLUDE = [
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "build",
    "dist",
    ".eggs",
    "*.egg-info",
    ".smart_linter_cache",
]


@dataclass
class Config:
    select: list[str] = field(default_factory=lambda: ["all"])
    ignore: list[str] = field(default_factory=list)
    custom_rules: list[str] = field(default_factory=list)
    min_severity: str = "info"
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE))
    no_cache: bool = False
    workers: int = 0

    @classmethod
    def from_pyproject(cls, project_root: Path | None = None) -> Config:
        if project_root is None:
            project_root = Path.cwd()

        pyproject_path = project_root / "pyproject.toml"
        if not pyproject_path.exists():
            return cls()

        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            return cls()

        tool_config = data.get("tool", {}).get("smart-linter", {})

        return cls(
            select=tool_config.get("select", ["all"]),
            ignore=tool_config.get("ignore", []),
            custom_rules=tool_config.get("custom-rules", []),
            min_severity=tool_config.get("min-severity", "info"),
            exclude=tool_config.get("exclude", list(DEFAULT_EXCLUDE)),
            no_cache=tool_config.get("no-cache", False),
            workers=tool_config.get("workers", 0),
        )
