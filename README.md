# ccsl

[![CI](https://github.com/usedhonda/statusline/actions/workflows/ci.yml/badge.svg)](https://github.com/usedhonda/statusline/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ccsl)](https://pypi.org/project/ccsl/)

Enhanced status line for Claude Code showing context usage, session time, and weekly budget.

![screenshot](assets/screenshot.png)

```
[Fable 5] | 📁 statusline | 🌿 main | 💰 $7.36 | Ext 23% $11.50/$50
Context:    ████████▒▒▒▒▒▒▒▒▒▒▒▒ [49%] 98.4K/200.0K
Session:    ▅█▃▁▂▄▁▁▁▁▁▁▁▁▁▁▁▁▁▁ [7%] 67.7M token (5am-10am) $12.40
Weekly:     ▅▃▁▇▂▇▁▁▄▁▆█▁▁▁▁▁▁▁▁ [42%] 3d0h24m, $34.20, Ext: 23% $11.50/$50
```

## Install

```bash
brew install usedhonda/tap/ccsl
ccsl --setup
```

Restart Claude Code. Done.

<details>
<summary>Other install methods</summary>

**pip**

```bash
pip install ccsl
ccsl --setup
```

**From source**

```bash
git clone https://github.com/usedhonda/statusline.git
cd statusline
python3 install.py
```

</details>

## What it shows

- **Line 1** — Model, directory, git branch. Metered-billing models (e.g. Fable 5) add the cost of the latest turn (💰) and extra-usage credit consumption (Ext)
- **Line 2** — Context window token usage with progress bar and cache ratio
- **Line 3** — Session sparkline with 5-hour utilization, token count, time range, and the 5-hour window's metered spend
- **Line 4** — Weekly sparkline with 7-day token distribution, remaining time, the 7-day window's metered spend, extra usage

Supports **1M context** — the context line scales to the active window size (e.g. `122K/1.0M`).

## Features

- Metered-model cost tracking — models billed via usage credits (Fable 5) show what the latest turn cost, computed per-message so mixed-model sessions only count the metered share
- Context window progress bar with color warnings (yellow 80%, red 90%)
- 5-hour session sparkline (20 segments, 15min each)
- Weekly usage sparkline with remaining time and budget tracking
- Responsive layout adapting to terminal width and height
- Agent team support with single-line format and dead agent warnings
- Schedule integration showing upcoming calendar events

## Customize

Control which lines to display:

```bash
ccsl --show all      # All 4 lines (default)
ccsl --show simple   # Lines 2 and 3 only
ccsl --show 1,2      # Specific lines
```

## Requirements

- Python 3.9+
- Claude Code
