#!/usr/bin/env python3
"""Statusline Installer - Deploy to Claude Code"""

import json
import shutil
import sys
from pathlib import Path

COMMAND = "~/.claude/statusline.py"
SCHEDULE_IDLE_HOOK_CMD = "echo idle > ~/.claude/.schedule_swap_state"


def _add_schedule_stop_hook(settings):
    """Add Stop hook for schedule idle guard (skip if already present)."""
    hooks = settings.setdefault('hooks', {})
    stop_hooks = hooks.setdefault('Stop', [])
    # Check if already installed
    for entry in stop_hooks:
        for h in entry.get('hooks', []):
            if SCHEDULE_IDLE_HOOK_CMD in h.get('command', ''):
                return
    stop_hooks.append({"hooks": [{"type": "command", "command": SCHEDULE_IDLE_HOOK_CMD}]})


def main():
    if shutil.which("ccsl"):
        print("ccsl is already on PATH (pip/brew installed).")
        print("Run: ccsl --setup")
        sys.exit(0)

    if sys.version_info < (3, 7):
        print("Error: Python 3.7+ required")
        sys.exit(1)

    source = Path("statusline.py")
    if not source.exists():
        print("Error: statusline.py not found in current directory")
        sys.exit(1)

    # Install
    claude_dir = Path.home() / ".claude"
    claude_dir.mkdir(exist_ok=True)
    target = claude_dir / "statusline.py"
    shutil.copy2(source, target)
    target.chmod(0o755)
    print(f"Installed to {target}")

    # Configure settings.json
    settings_path = claude_dir / "settings.json"
    statusline_config = {"type": "command", "command": COMMAND, "padding": 0, "refreshInterval": 5000}

    settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, encoding='utf-8') as f:
                settings = json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: invalid JSON in {settings_path}, creating backup")
            shutil.copy2(settings_path, settings_path.with_suffix('.json.backup'))
            settings = {}

    # Merge statusLine (preserve user customizations)
    existing_sl = settings.get('statusLine', {})
    if isinstance(existing_sl, dict):
        existing_sl.update(statusline_config)
        settings['statusLine'] = existing_sl
    else:
        settings['statusLine'] = statusline_config

    # Add Stop hook for schedule idle guard
    _add_schedule_stop_hook(settings)

    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    print(f"Settings updated: {settings_path}")

    # Auto-update opt-in/out
    no_update_file = claude_dir / ".statusline_no_update"
    try:
        answer = input("\nEnable auto-update? [Y/n]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        answer = ''
    if answer in ('n', 'no'):
        no_update_file.touch()
        print("Auto-update disabled. Re-enable: rm ~/.claude/.statusline_no_update")
    else:
        if no_update_file.exists():
            no_update_file.unlink()
        print("Auto-update enabled.")

    print("\nRestart Claude Code to see the status line.")
    print(f"Manual test: echo '{{\"session_id\":\"test\"}}' | {COMMAND}")
    print(f"Check updates: {COMMAND} --update")

if __name__ == "__main__":
    main()
