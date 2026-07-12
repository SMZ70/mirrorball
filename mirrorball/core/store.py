"""Saving and recalling shows.

A Show is one JSON document, so this is deliberately dull: write it, read it,
list them. That dullness is the point -- persistence that is just `json.dump`
cannot rot, cannot need a migration, and can be edited in a text editor when
something goes wrong at 1am.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from mirrorball.core.show import Show

SHOWS_DIR = Path("shows")


def _safe_name(name: str) -> str:
    """A show name comes from the UI, and ends up as a path. Keep it a file
    name and nothing else -- no traversal, no surprises."""
    keep = [c for c in name.strip() if c.isalnum() or c in " -_"]
    return ("".join(keep).strip() or "untitled")[:64]


def save(show: Show, directory: Path = SHOWS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_safe_name(show.name)}.json"

    # Write, then rename: a crash mid-write leaves the old show intact rather
    # than a half-written file that will not load.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(show.model_dump_json(indent=2) + "\n")
    tmp.replace(path)

    logger.info("saved show {!r}", show.name)
    return path


def load(name: str, directory: Path = SHOWS_DIR) -> Show:
    path = directory / f"{_safe_name(name)}.json"
    return Show.model_validate_json(path.read_text())


def names(directory: Path = SHOWS_DIR) -> list[str]:
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))


def delete(name: str, directory: Path = SHOWS_DIR) -> bool:
    path = directory / f"{_safe_name(name)}.json"
    if not path.exists():
        return False
    path.unlink()
    return True
