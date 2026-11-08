#!/usr/bin/env python3
"""Create ZeroClaw skill links from tools.toml.

The skill files stay in the repository named by each tool. This script
creates a symlink under ~/.zeroclaw/shared/skills. It does not copy files.
"""

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "tools.toml"
SHARED = Path.home() / ".zeroclaw" / "shared" / "skills"


def main() -> int:
    with CATALOG.open("rb") as handle:
        catalog = tomllib.load(handle)
    SHARED.mkdir(parents=True, exist_ok=True)
    for tool in catalog.get("tool", []):
        name = tool["name"]
        skill = tool.get("skill")
        if not skill:
            continue
        source = (Path(tool["repo"]) / skill).resolve()
        if not source.is_dir():
            print(f"missing skill directory: {source}", file=sys.stderr)
            return 1
        link = SHARED / name
        if link.is_symlink() and link.resolve() == source:
            print(f"ok {link} -> {source}")
            continue
        if link.exists() or link.is_symlink():
            if link.is_symlink() or link.is_file():
                link.unlink()
            else:
                print(f"refusing to replace directory: {link}", file=sys.stderr)
                return 1
        link.symlink_to(source)
        print(f"linked {link} -> {source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
