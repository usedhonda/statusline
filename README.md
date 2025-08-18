# statusline

Enhanced status line for Claude Code showing token usage, session time, and burn rate.

## What it does

```
[Sonnet 4] | 🌿 main M1 +1 | 📁 statusline | 💬 170
🪙  Compact: 140.5K/160.0K █████████████▒▒ 88% ♻️  99% cached 💰 Cost: $0.049
⏱️  Session: 3h33m/5h     ██████████▒▒▒▒▒ 71% 19:33 (16:00 to 21:00)
🔥 Burn:    55,823,011 (Rate: 261,309 t/m) ▁▁▁▁▁▁▁▁▁▁▄▂▁▇█▂▁█▂▇█▅██▆▆▅█▅█
```

- **Line 1**: Model, git status, directory, message count
- **Line 2**: Conversation tokens vs compaction limit (160K)
- **Line 3**: Session time within 5-hour billing window  
- **Line 4**: Session tokens and real-time burn rate

## Installation

```bash
git clone https://github.com/usedhonda/statusline.git
cd statusline
python3 install.py
```

Restart Claude Code. Done.

## Commands

```bash
statusline daily              # Today's usage
statusline daily --date 2025-01-15
statusline graph              # Visual charts  
statusline burn               # Live monitoring
```

## Requirements

- Python 3.7+
- Claude Code

## Configuration

Errors logged to `~/.claude/statusline-error.log`

Optional environment variables:
```bash
export CLAUDE_PROJECTS_DIR="/custom/path"
export STATUSLINE_NO_COLOR=1  # Disable colors
```