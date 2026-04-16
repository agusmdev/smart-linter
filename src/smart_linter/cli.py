"""CLI entry point for smart-linter."""

from __future__ import annotations

from pathlib import Path

import click

from smart_linter import __version__
from smart_linter.config import Config
from smart_linter.engine import run
from smart_linter.output import format_json, format_sarif, format_text


@click.group()
@click.version_option(version=__version__, prog_name="smart-linter")
def main() -> None:
    pass


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "sarif"]),
    default="text",
)
@click.option("--config", "config_file", type=click.Path(exists=True), default=None)
@click.option("--select", multiple=True, help="Enable specific rules")
@click.option("--ignore", multiple=True, help="Ignore specific rules")
@click.option(
    "--fix",
    "apply_fix",
    is_flag=True,
    help="Print fix suggestions in AI-parseable format",
)
@click.option("--diff", "show_diff", is_flag=True, help="Show what would change (for AI agents)")
@click.option("--no-cache", is_flag=True, help="Disable result caching")
@click.option(
    "--workers",
    type=int,
    default=0,
    show_default=True,
    help="Number of parallel workers (0 = auto)",
)
def check(
    paths: tuple[str, ...],
    output_format: str,
    config_file: str | None,
    select: tuple[str, ...],
    ignore: tuple[str, ...],
    apply_fix: bool,
    show_diff: bool,
    no_cache: bool,
    workers: int,
) -> None:
    target_paths = [Path(p) for p in paths]

    config = Config.from_pyproject()

    if config_file:
        override = Config.from_pyproject(Path(config_file).parent)
        config = override

    if select:
        config.select = list(select)
    if ignore:
        config.ignore = list(ignore)

    if no_cache:
        config.no_cache = True
    if workers:
        config.workers = workers

    violations = run(target_paths, config)

    if apply_fix or show_diff:
        _print_fixes(violations, show_diff=show_diff)
    elif output_format == "json":
        click.echo(format_json(violations))
    elif output_format == "sarif":
        click.echo(format_sarif(violations, __version__))
    else:
        click.echo(format_text(violations))

    if violations:
        raise SystemExit(1)


def _print_fixes(violations: list, show_diff: bool = False) -> None:
    import json

    fixes = []
    for v in violations:
        if v.fix:
            fix_data = {
                "file": v.filename,
                "line": v.location.row,
                "column": v.location.column,
                "rule": v.rule_id,
                "message": v.message,
                "fix_title": v.fix.title,
                "fix_replacement": v.fix.replacement,
                "fix_explanation": v.fix.explanation,
            }
            fixes.append(fix_data)

            if show_diff and v.fix.replacement:
                click.echo(f"--- {v.filename}:{v.location.row}")
                click.echo(f"+++ Suggested fix ({v.rule_id})")
                click.echo(f"- # original line {v.location.row}")
                click.echo(f"+ {v.fix.replacement}")
                click.echo()

    click.echo(json.dumps(fixes, indent=2))


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
def list_rules(paths: tuple[str, ...]) -> None:
    from smart_linter.registry import get_all_rules

    rules = get_all_rules()
    if not rules:
        click.echo("No rules available.")
        return

    click.echo("Available rules:\n")
    for rule_id, rule_cls in sorted(rules.items()):
        click.echo(f"  {rule_id}: {rule_cls.description}")


if __name__ == "__main__":
    main()
