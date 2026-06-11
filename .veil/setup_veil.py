#!/usr/bin/env python3
"""Post-clone setup script for veilgit encryption filters."""

import subprocess
import sys
from pathlib import Path

CLEAN_CMD = "gzip -9 | age -r age1j0kxym6dph3s2s4etd7vvr336fllf9a9mqacfyef99g4hpfl0ukqj4al2w"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python setup_veil.py <path_to_private_key>")
        raise SystemExit(1)
    key_path = sys.argv[1]
    repo_root = Path(__file__).resolve().parent.parent
    smudge = f"age --decrypt -i {key_path} | gzip -d"
    commands = [
        ["git", "-C", str(repo_root), "config", "filter.veil.clean", CLEAN_CMD],
        ["git", "-C", str(repo_root), "config", "filter.veil.smudge", smudge],
        ["git", "-C", str(repo_root), "config", "filter.veil.required", "true"],
        ["git", "-C", str(repo_root), "config", "diff.veil.textconv", smudge],
    ]
    for cmd in commands:
        subprocess.run(cmd, check=True)
    print("veilgit filtry aktivovány.")


if __name__ == "__main__":
    main()
