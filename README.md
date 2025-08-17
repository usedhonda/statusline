# statusline.py

A comprehensive real-time status line tool for Claude Code that displays session information, token usage, costs, and productivity metrics.

## Overview

`statusline.py` is a Python script that provides a rich, real-time status display for Claude Code sessions. It shows essential information like token usage, session duration, costs, Git status, and productivity metrics in a compact, color-coded format optimized for terminal displays.

### Key Features

- **Real-time Session Monitoring**: Live tracking of current Claude Code sessions
- **5-Hour Block Analysis**: ccusage-compatible billing block detection and tracking
- **Multi-Project Support**: Analyzes transcript files across all Claude Code projects
- **Token Usage Tracking**: Detailed breakdown of input/output/cache tokens with cost calculations
- **Productivity Metrics**: Active time detection, efficiency ratios, and session statistics
- **Git Integration**: Branch status, modified files, and repository information
- **Visual Progress Bars**: Color-coded progress indicators for token usage and time blocks
- **Cost Monitoring**: Real-time cost tracking with model-specific pricing (Claude 4 support)

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
       "command": "/path/to/statusline.py"
     }
   }
   ```

## Usage

### Basic Display

When properly configured with Claude Code, statusline automatically displays a 3-line status:

```
[Claude Sonnet 4] 🌿 main ±2 📁 statusline 📝 3 💬 12/8 ⏱️ 2h15m 14:30
🪙 45.2K/160K ████████████▒▒▒ 28% 💰 $2.45
⏱️ Block 1/∞: 2h15m (45% of block) ████████▒▒▒▒▒▒▒ ⚡ 78% active (98m) ♻️ 12.1K cached (27%)
```

### Display Elements

#### Line 1: Basic Information
- **[Claude Sonnet 4]**: Current AI model
- **🌿 main ±2**: Git branch with 2 modified files
- **📁 statusline**: Current project directory
- **📝 3**: Number of active files
- **💬 12/8**: User messages / Assistant messages
- **⏱️ 2h15m**: Current session duration
- **14:30**: Current time

#### Line 2: Token Usage & Costs
- **🪙 45.2K/160K**: Current tokens / Compaction threshold
- **████████████▒▒▒**: Visual progress bar
- **28%**: Percentage of token limit used
- **💰 $2.45**: Estimated session cost

#### Line 3: Session Analytics
- **⏱️ Block 1/∞**: Current 5-hour billing block
- **45% of block**: Progress within current block
- **⚡ 78% active**: Efficiency ratio (active time vs total time)
- **♻️ 12.1K cached**: Cache hit tokens and percentage

### Color Coding

- **Green**: Normal operation, healthy metrics
- **Yellow**: Warning levels (70-90% thresholds)
- **Red**: Critical levels (90%+ thresholds)
- **Cyan/Blue**: Informational elements
- **Pink**: Attention items
- **White**: Primary data

## Features in Detail

### Session Management

**5-Hour Block Detection**
- Compatible with ccusage billing block system
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

**Comprehensive Token Analysis**
- Input tokens: User message content
- Output tokens: Assistant responses
- Cache creation: New context caching
- Cache read: Cached context reuse

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
- 5-hour blocks align with ccusage billing periods

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

- **ccusage**: Claude Code usage analysis tool
- **Claude Code**: Official Anthropic CLI tool

## Support

For issues, questions, or contributions:
1. Check the troubleshooting section
2. Review error logs in `~/.claude/statusline-error.log`
3. Create an issue with detailed information about your setup

---

**statusline.py** - Making Claude Code sessions visible, measurable, and optimized.