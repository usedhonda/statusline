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


## Requirements

- Python 3.7+
- Claude Code

## Configuration

### Display Options

You can customize which lines to display in two ways:

#### 1. File Configuration (Default Settings)
Edit the top of `statusline.py`:
```python
# Set which lines to display (True = show, False = hide)
SHOW_LINE1 = True   # [Sonnet 4] | 🌿 main M2 +1 | 📁 statusline | 💬 254
SHOW_LINE2 = True   # 🪙  Compact: 91.8K/160.0K ████████▒▒▒▒▒▒▒ 58% ♻️  99% cached 💰 Cost: $0.031
SHOW_LINE3 = True   # ⏱️  Session: 1h15m/5h    ███▒▒▒▒▒▒▒▒▒▒▒▒ 25% 09:15 (08:00 to 13:00)
SHOW_LINE4 = True   # 🔥 Burn:    0 (Rate: 0 t/m) ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
```

#### 2. Claude Code Settings (Runtime Override)
```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline.py"
  }
}
```

Available command options:
```json
// Show specific lines
"command": "~/.claude/statusline.py --show 1,2"
"command": "~/.claude/statusline.py --show 2,3,4"

// Quick presets  
"command": "~/.claude/statusline.py --show simple"  // Lines 2,3 only
"command": "~/.claude/statusline.py --show all"     // All lines (default)

// Help (command line only)
~/.claude/statusline.py --help
```

**Priority**: Command line options override file settings when specified.

### Other Configuration

Errors logged to `~/.claude/statusline-error.log`

Optional environment variables:
```bash
export CLAUDE_PROJECTS_DIR="/custom/path"
export STATUSLINE_NO_COLOR=1  # Disable colors
```