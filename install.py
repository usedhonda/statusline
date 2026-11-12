#!/usr/bin/env python3
"""Statusline Installer - Deploy to Claude Code."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

if sys.version_info < (3, 9):
    raise SystemExit("Error: Python 3.9+ required")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from statusline import do_setup  # noqa: E402


def main():
    source = Path(__file__).resolve().with_name("statusline.py")
    if not source.is_file():
        raise SystemExit(f"Error: statusline.py not found beside {__file__}")

    claude_dir = Path.home() / ".claude"
    claude_dir.mkdir(exist_ok=True)
    target = claude_dir / "statusline.py"
    if target.is_symlink():
        raise SystemExit(f"Refusing to replace the development symlink: {target}")

    fd, temporary = tempfile.mkstemp(dir=str(claude_dir), suffix='.py.tmp')
    os.close(fd)
    try:
        shutil.copyfile(source, temporary)
        os.chmod(temporary, 0o755)
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    print(f"Installed to {target}")

    # Share settings merging, quoting, and hooks with the curl --setup path.
    if not do_setup(script_path=target):
        raise SystemExit(1)

    no_update_file = claude_dir / ".statusline_no_update"
    disabled = no_update_file.exists()
    default = 'n' if disabled else 'y'
    try:
        answer = input("\nEnable auto-update? " + ("[y/N]: " if disabled else "[Y/n]: ")).strip().lower()
    except (KeyboardInterrupt, EOFError):
        answer = ''
    answer = answer or default
    if answer in ('n', 'no'):
        no_update_file.touch()
        print("Auto-update disabled. Re-enable: rm ~/.claude/.statusline_no_update")
    elif answer in ('y', 'yes'):
        no_update_file.unlink(missing_ok=True)
        print("Auto-update enabled.")
    else:
        print("Auto-update preference unchanged.")


if __name__ == "__main__":
    main()
