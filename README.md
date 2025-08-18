# statusline

Enhanced status line for Claude Code showing token usage, session time, and burn rate.

## What it does

```
[Sonnet 4] | 🌿 main M1 +1 | 📁 statusline | 💬 170 | 💰 $0.044
🚨  Compact: █████████████████▒▒▒ [89%] ⚠️ 142.6K/160.0K ♻️  99% cached
⏱️  Session: ███████▒▒▒▒▒▒▒▒▒▒▒▒▒ [37%] 1h51m/5h 14:51 (13:00 to 18:00)
🔥 Burn:    ▁▁█▂▁▁▅▄▁▁▁▁▁▁▁▁▁▁▁▁ 8,387,710 token(w/cache), Rate: 75,515 t/m
```

- **Line 1**: Model, git status, directory, message count, cost
- **Line 2**: Conversation tokens vs compaction limit (160K) with 85%+ warning
- **Line 3**: Session time within 5-hour usage window  
- **Line 4**: Real-time burn rate with 15-minute segment sparkline

## Key Features

### 🚨 85% Warning System
When conversation tokens reach 85% of the compaction threshold (136K/160K):
- Icon changes from 🪙 to 🚨
- Red background warning appears
- Percentage display includes ⚠️ symbol

### 🔥 Real-Time Burn Sparkline
- Each character represents a 15-minute time segment
- Height shows actual token usage during that period
- Based on real message timestamps from transcript files
- Empty segments (▁) indicate periods with no activity

### ⏱️ UTC Time Handling
- All internal calculations use UTC for consistency
- Display times automatically convert to local timezone
- Prevents timezone-related calculation errors

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
SHOW_LINE1 = True   # [Sonnet 4] | 🌿 main M2 +1 | 📁 statusline | 💬 254 | 💰 $0.031
SHOW_LINE2 = True   # 🪙  Compact: ████████▒▒▒▒▒▒▒ [58%] 91.8K/160.0K ♻️  99% cached
SHOW_LINE3 = True   # ⏱️  Session: ███▒▒▒▒▒▒▒▒▒▒▒▒ [25%] 1h15m/5h 09:15 (08:00 to 13:00)
SHOW_LINE4 = True   # 🔥 Burn:    ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁ 0 token(w/cache), Rate: 0 t/m
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