# statusline

[![CI](https://github.com/usedhonda/statusline/actions/workflows/ci.yml/badge.svg)](https://github.com/usedhonda/statusline/actions/workflows/ci.yml)

Enhanced status line for Claude Code showing context usage, session time, and weekly budget.

## What it does

![screenshot](assets/screenshot.png)

```
[Opus 4.6] | 🌿 main | 📁 statusline | 💬 249 | +24/-45 | 💰 $7.36
Context:    ████████▒▒▒▒▒▒▒▒▒▒▒▒ [49%] 98.4K/200.0K
Session:    ▅█▃▁▂▄▁▁▁▁▁▁▁▁▁▁▁▁▁▁ [7%] 67.7M token (5am-10am)
Weekly:     ▅▃▁▇▂▇▁▁▄▁▆█▁▁▁▁▁▁▁▁ [42%] 3d0h24m, Extra: 7% $3.59/$50
```

- **Line 1**: Model, git branch, directory, message count, lines changed, cost
- **Line 2**: Context window token usage with progress bar and cache ratio
- **Line 3**: Session sparkline with 5-hour utilization, token count, and time range
- **Line 4**: Weekly sparkline with 7-day token distribution, remaining time, extra usage

Supports **1M context** — the model bracket shows `(1M)` when using extended context.

## Key Features

### Context Window Monitoring
- Progress bar for token usage vs context window size (200K or 1M)
- Fractional segments shown in dim color for partial fill
- Color-coded warnings: yellow at 80%, red at 90%

### 5-Hour Session Blocks
- Sparkline showing token consumption across 5-hour window (20 segments, 15min each)
- API-derived time range (e.g., `5am-10am`)
- Total tokens consumed in the current block

### Weekly Usage Tracking
- Sparkline showing 7-day token distribution (20 segments, ~8.4h each)
- Remaining time until weekly reset
- Extra usage percentage and cost vs budget display

### Responsive Layout
Automatically adapts to terminal width:
- **Full** (≥55 cols): All details with full labels, graph width scales smoothly with terminal width
- **Compact** (35–54 cols): Abbreviated labels
- **Tight** (<35 cols): Ultra-minimal display

Also adapts to terminal height — switches to single-line minimal mode for short terminals.

### Agent Teams Support
When running as a Claude Code team agent, displays a single-line format with agent name, model, and usage. Includes dead agent warnings (`⚠️ DEAD: agent-name`) on the main terminal.

### Schedule Integration
Line 1 can swap with a calendar event display showing upcoming events with time-based urgency coloring.

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

Use `--show` to control which lines are displayed:
```bash
~/.claude/statusline.py --show all      # All 4 lines (default)
~/.claude/statusline.py --show simple   # Lines 2 and 3 only
~/.claude/statusline.py --show 1,2      # Specific lines
```

Or edit the top of `statusline.py`:
```python
SHOW_LINE1 = True   # Model / git / directory / cost
SHOW_LINE2 = True   # Context window usage
SHOW_LINE3 = True   # Session sparkline / tokens / time range
SHOW_LINE4 = True   # Weekly sparkline / remaining time / budget
```

### Environment Variables

```bash
export STATUSLINE_DISPLAY_MODE=full   # Force display mode (full/compact/tight)
export STATUSLINE_NO_COLOR=1          # Disable colors
export CLAUDE_PROJECTS_DIR="/path"    # Custom projects directory
```

Errors logged to `~/.claude/statusline-error.log`.
