# statusline

[![CI](https://github.com/usedhonda/statusline/actions/workflows/ci.yml/badge.svg)](https://github.com/usedhonda/statusline/actions/workflows/ci.yml)

Enhanced status line for Claude Code showing token usage, session time, and burn rate.

## What it does

```
[Sonnet 4.6] | 🌿 main M2 +1 | 📁 statusline | 💬 254 | 💰 $0.031
Compact: ████████▒▒▒▒▒▒▒▒▒▒▒▒ [58%] 91.8K/200.0K ♻️  99% cached
Session: ███▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ [25%] 1h15m/5h 09:15 (08:00 to 13:00)
Burn:    ▁▁▂▃▄▅▆▇▇▆▅▄▃▂▁▁▁▁▁▁ 14.0M tokens
```

- **Line 1**: Model name, git status, directory, message count, cost
- **Line 2**: Conversation tokens vs context window with cache ratio
- **Line 3**: Session time within 5-hour usage window
- **Line 4**: Real-time burn rate sparkline

Supports **1M context** — the model bracket shows `[Sonnet 4.6(1M)]` when using extended context.

## Key Features

### 🟡🔴 Two-Level Warning System
- **70%+**: Yellow progress bar
- **90%+**: Red progress bar

### 🔥 Real-Time Burn Sparkline
- Each character represents a time segment
- Height shows actual token usage from real message timestamps
- Empty segments indicate periods with no activity

### 📐 Responsive Layout
Automatically adapts to terminal width:
- **Full** (≥68 cols): All details
- **Compact** (35–67 cols): Abbreviated labels
- **Tight** (<35 cols): Minimal display

## Installation

```bash
git clone https://github.com/usedhonda/statusline.git
cd statusline
python3 install.py
```

Restart Claude Code. Done.

## Requirements

- Python 3.9+
- Claude Code

## Configuration

### Display Options

Edit the top of `statusline.py`:
```python
SHOW_LINE1 = True   # [Sonnet 4.6] | 🌿 main | 📁 statusline | 💬 254
SHOW_LINE2 = True   # Compact: ████████▒▒▒▒ [58%] 91.8K/200.0K
SHOW_LINE3 = True   # Session: ███▒▒▒▒▒▒▒▒▒ [25%] 1h15m/5h
SHOW_LINE4 = True   # Burn:    ▁▂▃▄▅▆▇█▇▆▅▄
```

Or use `--show` at runtime:
```bash
~/.claude/statusline.py --show 1,2      # Lines 1 and 2 only
~/.claude/statusline.py --show simple   # Lines 2 and 3
~/.claude/statusline.py --show all      # All lines (default)
```

### Environment Variables

```bash
export STATUSLINE_NO_COLOR=1       # Disable colors
export CLAUDE_PROJECTS_DIR="/path" # Custom projects directory
```

Errors logged to `~/.claude/statusline-error.log`.
