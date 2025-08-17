# statusline.py

A comprehensive real-time status line tool for Claude Code that displays session information, token usage, costs, and productivity metrics.

## Overview

`statusline.py` is a Python script that provides a rich, real-time status display for Claude Code sessions. It shows essential information like token usage, session duration, costs, Git status, and productivity metrics in a compact, color-coded format optimized for terminal displays.

### Key Features

- **ccusage-Compatible Token Tracking**: Advanced deduplication system with high accuracy vs ccusage
- **Real-time Session Monitoring**: Live tracking of current Claude Code sessions with precise time calculations
- **5-Hour Block Analysis**: Professional billing block detection compatible with ccusage session boundaries
- **Multi-Project Support**: Analyzes transcript files across all Claude Code projects with duplicate filtering
- **Advanced Token Analytics**: Session-specific token counting with messageId:requestId deduplication
- **Git Integration**: Branch status, modified files, and repository information
- **Visual Progress Indicators**: Color-coded progress bars for token usage and session time blocks
- **Cost Monitoring**: Real-time cost tracking with model-specific pricing (Claude 4 support)
- **Live Burn Rate Display**: 30-minute trend sparklines integrated into compact status line
- **Professional Usage Reports**: Daily usage analysis with comprehensive statistics
- **Terminal-Optimized Display**: 4-line compact status with Unicode sparkline visualization

## Installation

### Prerequisites

- Python 3.7+
- Claude Code with active sessions
- Git (optional, for repository information)

### Setup

1. Clone or download `statusline.py` to your desired location
2. Make it executable:
   ```bash
   chmod +x statusline.py
   ```

3. Configure Claude Code to use statusline (add to your Claude Code settings):
   ```json
   {
     "statusLine": {
       "command": "~/.claude/statusline.py"
     }
   }
   ```

## Usage

### Basic Display (Real-time Status)

When properly configured with Claude Code, statusline automatically displays a comprehensive 4-line status:

```
[claude-sonnet-4] | 🌿 main M1 | 📁 statusline | 💬 583
🪙  Compact: 118.1K/160.0K ████████▒▒▒▒ 74% 💰 Cost: $0.214 ♻️  98% cached
⏱️  Session: 1h6m/5h (from 16:00) ███▒▒▒▒▒▒▒▒▒▒▒▒ 22% 17:06
🔥 Burn: 17,106,109 (Rate: 258,455 t/m) ▂▁▄▂▁▁▁▁▁▁▁▁▁▁▁▃▁▃▁▂▃█▁▁▄▄▃▃▇▃
```

### Usage Analysis Commands

For usage analysis, statusline supports multiple commands:

```bash
# Show current session status (default)
statusline

# Show today's usage summary
statusline daily

# Show usage for specific date
statusline daily --date 2025-01-15

# Show visual charts and graphs (ccusage-style)
statusline graph

# Real-time burn rate monitoring (like ccusage)
statusline burn

# Show help
statusline --help
```

### Sample Daily Usage Report

```
📊 Daily Usage Report - 2025-08-17
============================================================
📈 Summary
  Sessions: 7
  Projects: 2
  Models: claude-sonnet-4-20250514

🪙 Token Usage
  Input:         28
  Output:       118
  Cache Write: 162.7K
  Cache Read:  387.4K
  Total:        146
  Cache Efficiency: 265361.0%

💰 Cost Analysis
  Total Cost:  $0.728
  Avg/Session: $0.104

📁 Projects
  • statusline
  • extension-monolith
```

### Visual Graph Display

The `statusline graph` command provides ccusage-style visual analytics:

```
📊 Token Usage Visualization
============================================================

🔥 Burn Rate Trend (tokens/min)
   ·········●···
   ···●···●··●●●·
   ··●●●·●●·●●●·●
   ●●●●●●●●●●●●●●
   ──────────────────────────────
   Last 30 minutes

📈 Current Session Metrics
   Tokens:     ████████████████████▏░░░░ 81%
   Efficiency: ●●●●●●●●●●●●●●●●●●●○○○○○○ 78%
   Block:      ███████████░░░░░░░░░░░░░░ 45%

💰 Cost Analysis
   Input   : ██████░░░░░░░░░░░░░░ 30.0% ($0.300)
   Output  : █████████░░░░░░░░░░░ 45.0% ($0.450)
   Cache   : █████░░░░░░░░░░░░░░░ 25.0% ($0.250)

⏱️ Session Blocks (5-hour periods)
   Block 1: █████████████░░░░░░░ ACTIVE   $2.45
   Block 2: ███████░░░░░░░░░░░░░ IDLE     $1.23
   Block 3: ░░░░░░░░░░░░░░░░░░░░ PENDING  $0.00
```

### Real-time Burn Rate Monitoring

The `statusline burn` command provides live burn rate monitoring similar to ccusage:

```
🔥 Live Burn Rate Monitor - 14:32:15
======================================================================

Current Burn Rate: 42.3 tokens/min
Average (30min):   38.7 tokens/min
Peak (30min):      65.2 tokens/min

Burn Rate Trend:
   ●●●···●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●● 65.2
   ●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
   ●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
   ······●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●● 0.0
   ──────────────────────────────────────────────────
   Last 30 minutes

Compact View: ▁▂▃▅▄▃▄▇▅▃▄▆▅▄▃▂▃▄▅▃▄▆▄▃▂▃▄▅▆▄
```

Features:
- Updates every 5 seconds with current burn rate
- 30-minute rolling window of burn rate data  
- Color-coded current burn rate (green/yellow/red)
- ASCII charts showing trends over time
- ccusage-compatible burn rate calculation using 1-minute intervals

### Display Elements

#### Line 1: Basic Information
- **[claude-sonnet-4]**: Current AI model
- **🌿 main M1**: Git branch with M1 indicating modified files
- **📁 statusline**: Current project directory
- **💬 583**: Total message count in current session

#### Line 2: Compact Token Usage (5-hour Block)
- **🪙 Compact: 118.1K/160.0K**: 5-hour block tokens / Compaction threshold
- **████████▒▒▒▒**: Visual progress bar (74% of block limit)
- **💰 Cost: $0.214**: Estimated 5-hour block cost
- **♻️ 98% cached**: Cache efficiency percentage

#### Line 3: Session Time Analytics
- **⏱️ Session: 1h6m/5h**: Current session duration within 5-hour block
- **(from 16:00)**: Session start time (ccusage-compatible floorToHour calculation)
- **███▒▒▒▒▒▒▒▒▒▒▒▒**: Session progress bar (22% of 5-hour block)
- **17:06**: Current time

#### Line 4: Burn Rate with ccusage-Compatible Token Tracking
- **🔥 Burn: 17,106,109**: Session-specific cumulative tokens (ccusage-compatible calculation)
  - Uses advanced deduplication algorithm (messageId:requestId hash)
  - Filters messages within current session time range (16:00 onwards)
  - High accuracy vs ccusage through duplicate message filtering
- **(Rate: 258,455 t/m)**: Real-time token consumption rate
- **▂▁▄▂▁▁▁▁▁▁▁▁▁▁▁▃▁▃▁▂▃█▁▁▄▄▃▃▇▃**: 30-minute burn rate trend sparkline

### Color Coding

- **Green**: Normal operation, healthy metrics
- **Yellow**: Warning levels (70-90% thresholds)
- **Red**: Critical levels (90%+ thresholds)
- **Cyan/Blue**: Informational elements
- **Pink**: Attention items
- **White**: Primary data

## Features in Detail

### ccusage-Compatible Token Tracking

**Advanced Deduplication System**
- Implements ccusage's exact deduplication algorithm using messageId:requestId hash
- Prevents double-counting of duplicate messages across sessions
- Compatible with ccusage's identifySessionBlocks and createBlock algorithms

**Real-time Burn Rate Monitoring**  
- Session-specific token calculation within 5-hour billing blocks
- Real-time rate calculation showing tokens consumed per minute
- 30-minute trend visualization using Unicode sparkline characters
- Compact single-line display integrated into status line

**Session Efficiency Analysis**
- Measures active vs. idle time within sessions
- Calculates productivity ratios similar to ccusage efficiency metrics
- Helps optimize coding session effectiveness

**Cost Projection System**
- Projects final cost based on current burn rate and block progress
- Estimates remaining time in current 5-hour billing block
- Provides budget planning capabilities for extended sessions

### Visual Graph Display (ccusage-inspired)

**Integrated Sparkline Display**
- Real-time burn rate sparklines embedded in status line
- 20-minute trend visualization using Unicode block characters (▁▂▃▄▅▆▇█)
- ccusage-compatible thresholds with visual status indicators
- Compact single-line display for maximum terminal efficiency

**Interactive Graph Commands**
- `statusline graph`: Full visual charts and session analytics
- `statusline burn`: Live monitoring mode with real-time updates
- ASCII charts for burn rate, efficiency, and cost breakdown
- Session block visualization with ACTIVE/IDLE/PENDING states

**Terminal-Optimized Display**
- Adaptive width handling for different terminal sizes
- Unicode-based sparkline characters for crisp visualization
- Color-coded status indicators for immediate pattern recognition
- Compact 4-line display with integrated burn rate trends

### Session Management

**5-Hour Block Detection**
- Professional 5-hour billing block system compatible with Claude's billing structure
- Tracks progress within current 5-hour period
- Provides recommendations for optimal work sessions

**Multi-Project Analysis**
- Scans all Claude Code projects in `~/.claude/projects/`
- Chronologically orders messages across sessions
- Maintains session boundaries and context

**Active Period Detection**
- Identifies actual working time vs idle periods
- Uses 5-minute idle threshold for activity detection
- Calculates efficiency ratios and productivity metrics

### Token Tracking

**ccusage-Compatible Calculation**
- **Session Tokens**: Filtered by session time range with deduplication
- **Input tokens**: User message content
- **Output tokens**: Assistant responses  
- **Cache creation**: New context caching
- **Cache read**: Cached context reuse
- **Total calculation**: Includes all token types like ccusage getTotalTokens()

**Advanced Deduplication**
- Prevents counting duplicate messages using messageId:requestId combination
- Compatible with ccusage's createUniqueHash algorithm
- Maintains session boundary accuracy while filtering duplicates

**Smart Caching Metrics**
- Cache hit ratio calculation
- Cache efficiency analysis  
- Cost savings from cache usage

### Cost Calculation

**Model-Specific Pricing** (2025 rates)
- **Claude Sonnet 4**: $3.00/$15.00 per million tokens (input/output)
- **Claude Opus 4**: $15.00/$75.00 per million tokens (input/output)
- **Claude Haiku 3.5**: $1.00/$5.00 per million tokens (input/output)
- Cache pricing: Write 1.25x input rate, Read 0.10x input rate

### Git Integration

- Branch name and status
- Modified file count
- Untracked file count
- Repository state monitoring

## Configuration

### Environment Variables

```bash
# Optional: Custom project directory
export CLAUDE_PROJECTS_DIR="/custom/path/to/projects"

# Optional: Custom cache directory
export CLAUDE_CACHE_DIR="/custom/path/to/cache"
```

### Advanced Configuration

The script automatically detects:
- Claude Code project directories
- Session transcript files (`.jsonl`)
- Git repository information
- System timezone settings

## Troubleshooting

### Common Issues

**No data displayed**
- Ensure Claude Code is running with an active session
- Check that transcript files exist in `~/.claude/projects/`
- Verify Python 3.7+ is installed

**Incorrect session times**
- Session times are calculated from transcript timestamps
- Times are automatically converted to local timezone
- 5-hour blocks for standardized billing analysis

**Git information missing**
- Ensure you're in a Git repository
- Check that `.git` directory is accessible
- Git integration is optional and won't affect other features

### Debug Mode

Error logs are automatically written to:
```
~/.claude/statusline-error.log
```

Check this file for detailed error information if issues occur.

## Technical Details

### Architecture

- **Single-file design**: Optimized for fast startup and minimal dependencies
- **Stream processing**: Efficient JSONL transcript parsing
- **Memory efficient**: Minimal memory footprint (~5-10MB)
- **Fast execution**: Typically <100ms startup time

### Data Sources

- **Transcript files**: `~/.claude/projects/*/session-id.jsonl`
- **Git repositories**: `.git/` directories for project status
- **System time**: Local timezone for accurate session timing

### Compatibility

- **Python**: 3.7+ (uses standard library only)
- **Claude Code**: All current versions
- **Operating Systems**: macOS, Linux, Windows
- **Terminals**: Any ANSI color-capable terminal

## Development

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with appropriate tests
4. Submit a pull request

### Testing

```bash
# Run with sample data
python3 statusline.py < sample-session-data.json

# Test error handling
python3 statusline.py < invalid-data.json
```

### Code Structure

```python
# Main components
- Token calculation and analysis
- Session duration and block detection
- Git repository information
- Cost calculation with model pricing
- Multi-line colored display rendering
- Error handling and logging
```

## License

This project is open source. Please check the license file for specific terms.

## Related Projects

- Industry-standard 5-hour billing periods for usage tracking
- **Claude Code**: Official Anthropic CLI tool

## Support

For issues, questions, or contributions:
1. Check the troubleshooting section
2. Review error logs in `~/.claude/statusline-error.log`
3. Create an issue with detailed information about your setup

---

**statusline.py** - Making Claude Code sessions visible, measurable, and optimized.