"""Deterministic E11 number-station script generator.

Generates scripts in the text format consumed by ``ZapdoZ/numberstations/main.py``::

    E11
    <3-digit station ID>
    <group count>
    <space-separated 5-digit groups>

Each line is terminated with ``\\n`` (including the last), giving exactly
four lines.

Quick start
-----------
>>> from computational_qr.numberstation.e11_script import generate
>>> script = generate("my-secret-seed", group_count=5)
>>> print(script.to_text())
E11
...

CLI
---
::

    python -m computational_qr.numberstation.e11_script \\
        --seed "my-secret-seed" --groups 20 --out transmission.txt
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_from_string(seed: str) -> int:
    """Derive a stable integer seed from *seed* via SHA-256 (UTF-8).

    The first 8 bytes of the digest are interpreted as a big-endian
    unsigned integer.  This is deterministic across platforms and Python
    versions.
    """
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class E11Script:
    """An E11 number-station transmission script.

    Parameters
    ----------
    station_id:
        3-digit primary station identifier (0–999).
    group_count:
        Number of 5-digit groups in the transmission.
    groups:
        The actual 5-digit code groups (each in 0–99999).
    """

    station_id: int
    group_count: int
    groups: list[int] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_text(self) -> str:
        """Return the script as a four-line string with trailing newlines.

        Line layout (matches ZapdoZ/numberstations input format):

        1. ``E11\\n``
        2. ``<3-digit station ID>\\n``
        3. ``<group count>\\n``
        4. ``<space-separated 5-digit groups>\\n``
        """
        id_str = f"{self.station_id:03d}"
        groups_str = " ".join(f"{g:05d}" for g in self.groups)
        return f"E11\n{id_str}\n{self.group_count}\n{groups_str}\n"

    def write(self, path: Union[str, Path]) -> None:
        """Write the script text to *path* (UTF-8, overwriting if exists)."""
        Path(path).write_text(self.to_text(), encoding="utf-8")


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def generate(
    seed: Union[int, str],
    group_count: int = 20,
    *,
    station_id: Union[int, None] = None,
) -> E11Script:
    """Generate a deterministic :class:`E11Script`.

    Parameters
    ----------
    seed:
        Either an :class:`int` used directly as the PRNG seed, or a
        :class:`str` from which a stable integer seed is derived via
        SHA-256 (UTF-8).
    group_count:
        How many 5-digit groups to generate.
    station_id:
        Optional fixed station ID (0–999).  When *None* (default), the ID
        is derived from *seed* so it is also deterministic.

    Returns
    -------
    E11Script
        Fully populated script ready for :py:meth:`E11Script.to_text` or
        :py:meth:`E11Script.write`.
    """
    if isinstance(seed, str):
        seed = _seed_from_string(seed)

    rng = random.Random(seed)

    if station_id is None:
        station_id = rng.randint(0, 999)

    groups = [rng.randint(0, 99999) for _ in range(group_count)]
    return E11Script(station_id=station_id, group_count=group_count, groups=groups)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m computational_qr.numberstation.e11_script",
        description="Generate a deterministic E11 number-station script.",
    )
    parser.add_argument(
        "--seed",
        required=True,
        help="String seed (human-readable) or integer seed.",
    )
    parser.add_argument(
        "--groups",
        type=int,
        default=20,
        metavar="N",
        help="Number of 5-digit groups (default: 20).",
    )
    parser.add_argument(
        "--station-id",
        type=int,
        default=None,
        metavar="ID",
        help="Fixed 3-digit station ID (0-999).  Derived from seed when omitted.",
    )
    parser.add_argument(
        "--out",
        default=None,
        metavar="FILE",
        help="Output file path.  Writes to stdout when omitted.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Accept numeric seeds passed as strings on the CLI.
    seed: Union[int, str] = args.seed
    try:
        seed = int(args.seed)
    except ValueError:
        pass  # Keep as string – will be hashed.

    script = generate(seed, group_count=args.groups, station_id=args.station_id)
    text = script.to_text()

    if args.out:
        script.write(args.out)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":  # pragma: no cover
    main()
