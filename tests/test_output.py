"""Tests for smart_linter.output formatters."""

from __future__ import annotations

import json

import pytest

from smart_linter.models import FixSuggestion, Location, Severity, Violation
from smart_linter.output import format_json, format_sarif, format_text


def _make_violation(
    *,
    rule_id: str = "ASYNC001",
    message: str = "Blocking sync call in async context.",
    filename: str = "src/api.py",
    row: int = 10,
    col: int = 4,
    severity: Severity = Severity.WARNING,
    fix: FixSuggestion | None = None,
    end_location: Location | None = None,
) -> Violation:
    return Violation(
        rule_id=rule_id,
        message=message,
        location=Location(row=row, column=col),
        end_location=end_location,
        severity=severity,
        fix=fix,
        filename=filename,
    )


# ---------------------------------------------------------------------------
# format_text
# ---------------------------------------------------------------------------


class TestFormatText:
    def test_empty_violations(self):
        assert format_text([]) == "No issues found."

    def test_single_violation_without_fix(self):
        v = _make_violation()
        result = format_text([v])
        assert "src/api.py:10:4:" in result
        assert "WARNING ASYNC001" in result
        assert "Blocking sync call in async context." in result
        assert "💡" not in result

    def test_single_violation_with_fix(self):
        fix = FixSuggestion(
            title="Use async alternative",
            replacement="await client.get()",
            explanation="Blocking calls should be async.",
        )
        v = _make_violation(fix=fix)
        result = format_text([v])
        assert "💡 Use async alternative" in result
        assert "Suggestion: await client.get()" in result

    def test_fix_without_replacement(self):
        fix = FixSuggestion(title="Consider refactoring")
        v = _make_violation(fix=fix)
        result = format_text([v])
        assert "💡 Consider refactoring" in result
        assert "Suggestion:" not in result

    def test_multiple_violations(self):
        v1 = _make_violation(rule_id="ASYNC001", row=10)
        v2 = _make_violation(rule_id="ERR001", row=20, filename="src/err.py")
        result = format_text([v1, v2])
        lines = result.split("\n")
        assert len(lines) == 2
        assert "ASYNC001" in lines[0]
        assert "ERR001" in lines[1]

    def test_severity_displayed_uppercase(self):
        v = _make_violation(severity=Severity.ERROR)
        result = format_text([v])
        assert "ERROR ASYNC001" in result

    def test_info_severity_displayed(self):
        v = _make_violation(severity=Severity.INFO)
        result = format_text([v])
        assert "INFO ASYNC001" in result


# ---------------------------------------------------------------------------
# format_json
# ---------------------------------------------------------------------------


class TestFormatJson:
    def test_empty_violations(self):
        result = format_json([])
        assert json.loads(result) == []

    def test_single_violation_without_fix(self):
        v = _make_violation()
        result = format_json([v])
        data = json.loads(result)
        assert len(data) == 1
        entry = data[0]
        assert entry["code"] == "ASYNC001"
        assert entry["filename"] == "src/api.py"
        assert entry["location"] == {"row": 10, "column": 4}
        assert entry["severity"] == "warning"
        assert entry["message"] == "Blocking sync call in async context."
        assert entry["fix"] is None

    def test_single_violation_with_fix(self):
        fix = FixSuggestion(
            title="Use async alternative",
            replacement="await client.get()",
        )
        v = _make_violation(fix=fix)
        result = format_json([v])
        data = json.loads(result)
        entry = data[0]
        assert entry["fix"] is not None
        assert entry["fix"]["message"] == "Use async alternative"
        assert entry["fix"]["applicability"] == "unsafe"
        assert len(entry["fix"]["edits"]) == 1
        assert entry["fix"]["edits"][0]["content"] == "await client.get()"

    def test_violation_with_end_location(self):
        v = _make_violation(
            end_location=Location(row=12, column=20),
        )
        result = format_json([v])
        data = json.loads(result)
        assert data[0]["end_location"] == {"row": 12, "column": 20}

    def test_violation_without_end_location(self):
        v = _make_violation()
        result = format_json([v])
        data = json.loads(result)
        assert data[0]["end_location"] is None

    def test_multiple_violations(self):
        v1 = _make_violation(rule_id="ASYNC001")
        v2 = _make_violation(rule_id="ERR001")
        result = format_json([v1, v2])
        data = json.loads(result)
        assert len(data) == 2
        assert data[0]["code"] == "ASYNC001"
        assert data[1]["code"] == "ERR001"

    def test_ruff_compatible_fields(self):
        v = _make_violation()
        result = format_json([v])
        data = json.loads(result)
        entry = data[0]
        assert "cell" in entry
        assert "url" in entry
        assert "noqa_row" in entry
        assert entry["cell"] is None
        assert entry["url"] is None
        assert entry["noqa_row"] is None

    def test_fix_with_no_replacement_yields_empty_edits(self):
        fix = FixSuggestion(title="Refactor needed")
        v = _make_violation(fix=fix)
        result = format_json([v])
        data = json.loads(result)
        assert data[0]["fix"]["edits"] == []


# ---------------------------------------------------------------------------
# format_sarif
# ---------------------------------------------------------------------------


class TestFormatSarif:
    def test_empty_violations(self):
        result = format_sarif([])
        sarif = json.loads(result)
        assert sarif["$schema"] == "https://json.schemastore.org/sarif-2.1.0.json"
        assert sarif["version"] == "2.1.0"
        assert sarif["runs"][0]["results"] == []
        assert sarif["runs"][0]["tool"]["driver"]["name"] == "smart-linter"

    def test_single_violation(self):
        v = _make_violation()
        result = format_sarif([v])
        sarif = json.loads(result)
        run = sarif["runs"][0]
        assert len(run["results"]) == 1
        r = run["results"][0]
        assert r["ruleId"] == "ASYNC001"
        assert r["level"] == "warning"
        assert r["message"]["text"] == "Blocking sync call in async context."
        loc = r["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == "src/api.py"
        assert loc["region"]["startLine"] == 10
        assert loc["region"]["startColumn"] == 4

    def test_sarif_schema_and_version(self):
        result = format_sarif([_make_violation()])
        sarif = json.loads(result)
        assert sarif["$schema"] == "https://json.schemastore.org/sarif-2.1.0.json"
        assert sarif["version"] == "2.1.0"

    def test_tool_driver_metadata(self):
        result = format_sarif([_make_violation()])
        sarif = json.loads(result)
        driver = sarif["runs"][0]["tool"]["driver"]
        assert driver["name"] == "smart-linter"
        assert driver["version"] == "0.1.0"
        assert len(driver["rules"]) == 1
        assert driver["rules"][0]["id"] == "ASYNC001"

    def test_custom_tool_version(self):
        result = format_sarif([_make_violation()], tool_version="2.3.0")
        sarif = json.loads(result)
        assert sarif["runs"][0]["tool"]["driver"]["version"] == "2.3.0"

    def test_error_severity_maps_to_error(self):
        v = _make_violation(severity=Severity.ERROR)
        result = format_sarif([v])
        sarif = json.loads(result)
        assert sarif["runs"][0]["results"][0]["level"] == "error"

    def test_info_severity_maps_to_note(self):
        v = _make_violation(severity=Severity.INFO)
        result = format_sarif([v])
        sarif = json.loads(result)
        assert sarif["runs"][0]["results"][0]["level"] == "note"

    def test_warning_severity_maps_to_warning(self):
        v = _make_violation(severity=Severity.WARNING)
        result = format_sarif([v])
        sarif = json.loads(result)
        assert sarif["runs"][0]["results"][0]["level"] == "warning"

    def test_violation_with_end_location(self):
        v = _make_violation(end_location=Location(row=15, column=30))
        result = format_sarif([v])
        sarif = json.loads(result)
        region = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
        assert region["endLine"] == 15
        assert region["endColumn"] == 30

    def test_violation_without_end_location_no_end_fields(self):
        v = _make_violation()
        result = format_sarif([v])
        sarif = json.loads(result)
        region = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
        assert "endLine" not in region
        assert "endColumn" not in region

    def test_fix_with_replacement_included(self):
        fix = FixSuggestion(
            title="Use async alternative",
            replacement="await client.get()",
        )
        v = _make_violation(fix=fix)
        result = format_sarif([v])
        sarif = json.loads(result)
        r = sarif["runs"][0]["results"][0]
        assert "fixes" in r
        assert len(r["fixes"]) == 1
        assert r["fixes"][0]["description"]["text"] == "Use async alternative"
        replacement = r["fixes"][0]["artifactChanges"][0]["replacements"][0]
        assert replacement["insertedContent"]["text"] == "await client.get()"

    def test_fix_without_replacement_excluded(self):
        fix = FixSuggestion(title="Refactor needed")
        v = _make_violation(fix=fix)
        result = format_sarif([v])
        sarif = json.loads(result)
        r = sarif["runs"][0]["results"][0]
        assert "fixes" not in r

    def test_no_fix_excluded(self):
        v = _make_violation()
        result = format_sarif([v])
        sarif = json.loads(result)
        r = sarif["runs"][0]["results"][0]
        assert "fixes" not in r

    def test_rules_map_deduplicates(self):
        v1 = _make_violation(rule_id="ASYNC001", row=10)
        v2 = _make_violation(rule_id="ASYNC001", row=20)
        result = format_sarif([v1, v2])
        sarif = json.loads(result)
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) == 1
        assert rules[0]["id"] == "ASYNC001"

    def test_multiple_rules_in_rules_map(self):
        v1 = _make_violation(rule_id="ASYNC001")
        v2 = _make_violation(rule_id="ERR001")
        result = format_sarif([v1, v2])
        sarif = json.loads(result)
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        rule_ids = {r["id"] for r in rules}
        assert rule_ids == {"ASYNC001", "ERR001"}

    def test_short_description_from_message(self):
        v = _make_violation(message="Blocking sync call. Use async instead.")
        result = format_sarif([v])
        sarif = json.loads(result)
        desc = sarif["runs"][0]["tool"]["driver"]["rules"][0]["shortDescription"]["text"]
        assert desc == "Blocking sync call"
