"""Core data models for smart-linter: Rule, Violation, Severity, FixSuggestion."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import AbstractSet, ClassVar


class Severity(enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Location:
    row: int
    column: int


@dataclass(frozen=True)
class Range:
    start: Location
    end: Location


@dataclass(frozen=True)
class FixSuggestion:
    title: str
    replacement: str | None = None
    explanation: str | None = None


@dataclass(frozen=True)
class Violation:
    rule_id: str
    message: str
    location: Location
    end_location: Location | None = None
    severity: Severity = Severity.WARNING
    fix: FixSuggestion | None = None
    filename: str = ""

    def to_ruff_json(self) -> dict:
        return {
            "cell": None,
            "code": self.rule_id,
            "message": self.message,
            "severity": self.severity.value,
            "location": {"row": self.location.row, "column": self.location.column},
            "end_location": (
                {"row": self.end_location.row, "column": self.end_location.column}
                if self.end_location
                else None
            ),
            "filename": self.filename,
            "fix": (
                {
                    "applicability": "unsafe",
                    "message": self.fix.title,
                    "edits": (
                        [
                            {
                                "content": self.fix.replacement,
                                "location": {
                                    "row": self.location.row,
                                    "column": self.location.column,
                                },
                                "end_location": (
                                    {
                                        "row": self.end_location.row,
                                        "column": self.end_location.column,
                                    }
                                    if self.end_location
                                    else {
                                        "row": self.location.row,
                                        "column": self.location.column,
                                    }
                                ),
                            }
                        ]
                        if self.fix.replacement is not None
                        else []
                    ),
                }
                if self.fix
                else None
            ),
            "url": None,
            "noqa_row": None,
        }


class Rule:
    id: ClassVar[str]
    description: ClassVar[str]
    severity: ClassVar[Severity] = Severity.WARNING
    tags: ClassVar[tuple[str, ...]] = ()

    def check(self, tree, filename: str) -> list[Violation]:
        raise NotImplementedError
