#!/usr/bin/env python3

# ============================================
# 📝 CONFIGURATION - Edit these values
# ============================================

# Display settings (True = show, False = hide)
SHOW_LINE1    = True   # [Sonnet 4] | 🌿 main M2 | 📁 project | 💬 254
SHOW_LINE2    = True   # Context: 91.8K/200.0K ████████▒▒▒ 58%
SHOW_LINE3    = True   # Session: 1h15m/5h ███▒▒▒▒▒▒▒▒ 25%
SHOW_LINE4    = True   # Weekly: [64%] 32m, Extra: 7% $3.59/$50
SHOW_SCHEDULE = True   # 📅 14:00 Meeting (in 30m) - swaps with Line1

# Schedule settings (requires `gog` command)
SCHEDULE_SWAP_INTERVAL = 1    # Swap interval (seconds)
SCHEDULE_CACHE_TTL     = 300  # Cache time (seconds)

# ============================================
# Internal (don't edit below)
# ============================================
SCHEDULE_CACHE_FILE = None

# IMPORTS AND SYSTEM CODE

import json
import sys
import os
import subprocess
import argparse
import shutil
import re
import unicodedata
from pathlib import Path
from datetime import datetime, timedelta, timezone
import time

# CONSTANTS

# Block stats cache settings
BLOCK_STATS_CACHE_TTL = 30  # 30 seconds
BLOCK_STATS_CACHE_FILE = None

# Transcript stats cache settings
TRANSCRIPT_STATS_CACHE_TTL = 15  # 15 seconds
TRANSCRIPT_STATS_CACHE_FILE = None

# Ratelimit cache settings
RATELIMIT_CACHE_TTL = 300  # 5 minutes
RATELIMIT_CACHE_FILE = None
RATELIMIT_LOCK_FILE = None

# Token compaction threshold - FALLBACK VALUE ONLY
# Dynamic value is now calculated from API: context_window_size * 0.8
# This constant is kept for backwards compatibility if API data is unavailable
COMPACTION_THRESHOLD = 200000 * 0.8  # 80% of 200K tokens (fallback). 1M context: 800K

# TWO DISTINCT TOKEN CALCULATION SYSTEMS

# This application uses TWO completely separate token calculation systems:

# 🗜️ COMPACT LINE SYSTEM (Conversation Compaction)
# ==============================================
# Purpose: Tracks current conversation progress toward compaction threshold
# Data Source: Current conversation tokens (until 160K compaction limit)
# Scope: Single conversation, monitors compression timing
# Calculation: block_stats['total_tokens'] from detect_five_hour_blocks()
# Display: Compact line (Line 2) - "118.1K/160.0K ████████▒▒▒▒ 74%"
# Range: 0 to context_window_size (200K or 1M, until conversation gets compressed)
# Reset Point: When conversation gets compacted/compressed

# 🕐 SESSION WINDOW SYSTEM (Session Management)
# ===================================================
# Purpose: Tracks usage periods
# Data Source: Messages within usage windows
# Scope: Usage period tracking
# Calculation: calculate_tokens_since_time() with 5-hour window start
# Display: Session line (Line 3) + Burn line (Line 4)
# Range: usage window scope with real-time burn rate
# Reset Point: Every 5 hours per usage limits

# ⚠️  CRITICAL RULES:
# 1. COMPACT = conversation compaction monitoring (160K threshold)
# 2. SESSION/BURN = usage window tracking
# 3. These track DIFFERENT concepts: compression vs usage periods
# 4. Compact = compression timing, Session = official usage window

# ANSI color codes optimized for black backgrounds
class Colors:
    _colors = {
        'BRIGHT_CYAN': '\033[1;96m',
        'BRIGHT_BLUE': '\033[1;94m',
        'BRIGHT_MAGENTA': '\033[1;95m',
        'BRIGHT_GREEN': '\033[1;92m',
        'BRIGHT_YELLOW': '\033[1;93m',
        'BRIGHT_RED': '\033[1;95m',
        'BRIGHT_WHITE': '\033[1;97m',
        'LIGHT_GRAY': '\033[1;97m',
        'DIM': '\033[1;97m',
        'DIM_GREEN': '\033[32m',
        'DIM_YELLOW': '\033[33m',
        'DIM_RED': '\033[31m',
        'BOLD': '\033[1m',
        'BLINK': '\033[5m',
        'BG_RED': '\033[41m',
        'BG_YELLOW': '\033[43m',
        'RESET': '\033[0m'
    }
    
    def __getattr__(self, name):
        if os.environ.get('NO_COLOR') or os.environ.get('STATUSLINE_NO_COLOR'):
            return ''
        return self._colors.get(name, '')

# Create single instance
Colors = Colors()

# ========================================
# TERMINAL WIDTH UTILITIES
# ========================================

def strip_ansi(text):
    """ANSIエスケープコードを除去"""
    return re.sub(r'\x1b\[[0-9;]*m', '', text)

def get_display_width(text):
    """表示幅を計算（絵文字/CJK対応）

    ANSIコードを除去し、各文字の表示幅を計算。
    East Asian Width が 'W' (Wide) または 'F' (Fullwidth) の文字は幅2、それ以外は幅1。
    """
    clean = strip_ansi(text)
    width = 0
    for char in clean:
        ea = unicodedata.east_asian_width(char)
        width += 2 if ea in ('W', 'F') else 1
    return width

def get_terminal_size():
    """ターミナルサイズ(幅, 高さ)を同時取得

    優先順位:
    1. tmux -t $TMUX_PANE (幅・高さ同時、最も正確)
    2. shutil.get_terminal_size() (ioctl経由、TTY必要)
    3. tput cols/lines (TERM依存)
    4. COLUMNS/LINES 環境変数 (override用)
    5. デフォルト (80, 24)

    COLUMNS/LINESは部分override対応: COLUMNSだけ設定されていれば幅のみ上書き。

    Returns:
        tuple[int, int]: (幅, 高さ)  ※幅は右端問題対策で-1済み、最小10
    """
    raw_width = 0
    raw_height = 0

    try:
        # 1. tmux: 1コマンドで幅・高さ同時取得（最も正確）
        if 'TMUX' in os.environ:
            try:
                pane_id = os.environ.get('TMUX_PANE', '')
                cmd = ['tmux', 'display-message', '-p', '#{pane_width} #{pane_height}']
                if pane_id:
                    cmd = ['tmux', 'display-message', '-t', pane_id, '-p', '#{pane_width} #{pane_height}']
                result = subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=1
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split()
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        raw_width = int(parts[0])
                        raw_height = int(parts[1])
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

        # 2. shutil.get_terminal_size() (ioctl経由)
        if raw_width == 0 or raw_height == 0:
            try:
                if sys.stdout.isatty():
                    size = shutil.get_terminal_size()
                    if size.columns > 0 and raw_width == 0:
                        raw_width = size.columns
                    if size.lines > 0 and raw_height == 0:
                        raw_height = size.lines
            except (OSError, AttributeError):
                pass

        # 3. tput cols/lines (TERM依存)
        if raw_width == 0:
            try:
                result = subprocess.run(
                    ['tput', 'cols'],
                    capture_output=True, text=True, timeout=1
                )
                if result.returncode == 0 and result.stdout.strip().isdigit():
                    raw_width = int(result.stdout.strip())
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
        if raw_height == 0:
            try:
                result = subprocess.run(
                    ['tput', 'lines'],
                    capture_output=True, text=True, timeout=1
                )
                if result.returncode == 0 and result.stdout.strip().isdigit():
                    raw_height = int(result.stdout.strip())
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

        # 4. COLUMNS/LINES 環境変数 (override: 個別上書き対応)
        if 'COLUMNS' in os.environ:
            try:
                raw_width = int(os.environ['COLUMNS'])
            except ValueError:
                pass
        if 'LINES' in os.environ:
            try:
                raw_height = int(os.environ['LINES'])
            except ValueError:
                pass

    except (OSError, AttributeError):
        pass

    # デフォルト値
    if raw_width == 0:
        raw_width = 80
    if raw_height == 0:
        raw_height = 24

    # clamp: 幅は-1して最小10、高さは最小1
    width = max(10, raw_width - 1)
    height = max(1, raw_height)

    return width, height


def get_terminal_width():
    """後方互換ラッパー"""
    w, _ = get_terminal_size()
    return w


def get_terminal_height():
    """後方互換ラッパー"""
    _, h = get_terminal_size()
    return h

def get_height_mode(height):
    """高さからモードを判定（ヒステリシス付き）

    モードフラップ防止:
    - minimal -> normal: 高さ >= 10 で切替（余裕を持たせる）
    - normal -> minimal: 高さ <= 7 で切替（すぐには戻さない）
    - 8, 9 は前回モード維持（デッドゾーン）

    ファイルが存在しない場合は閾値 8 で従来通り判定（初回互換）。

    Returns: 'minimal' or 'normal'
    """
    state_file = Path.home() / '.claude' / 'statusline-height-mode.txt'
    prev_mode = None
    try:
        prev_mode = state_file.read_text().strip()
        if prev_mode not in ('minimal', 'normal'):
            prev_mode = None
    except (FileNotFoundError, OSError):
        pass

    if prev_mode is None:
        # 初回: 従来の閾値 8 で判定
        mode = 'minimal' if height <= 8 else 'normal'
    elif height >= 10:
        mode = 'normal'
    elif height <= 7:
        mode = 'minimal'
    else:
        mode = prev_mode  # 8-9 はデッドゾーン

    if mode != prev_mode:
        try:
            state_file.write_text(mode)
        except OSError:
            pass

    return mode


def get_display_mode(width):
    """ターミナル幅からモードを決定

    | モード | 幅 | 最長行 | 表示内容 |
    |--------|-----|--------|---------|
    | full | >= 55 | 可変 | 4行・全項目・装飾あり・グラフ幅可変 |
    | compact | 35-54 | 30文字 | 4行・ラベル短縮・装飾削減 |
    | tight | < 35 | 23文字 | 4行・最短表示 |

    Args:
        width: ターミナル幅
    Returns:
        str: 'full', 'compact', or 'tight'
    """
    if width >= 55:
        return 'full'
    elif width >= 35:
        return 'compact'
    else:
        return 'tight'

def get_total_tokens(usage_data):
    """Calculate total tokens from usage data (UNIVERSAL HELPER) - external tool compatible
    
    Used by session/burn line systems for usage window tracking.
    Sums all token types: input + output + cache_creation + cache_read
    
    CRITICAL FIX: Implements external tool compatible logic to avoid double-counting
    
    Args:
        usage_data: Token usage dictionary from assistant message
    Returns:
        int: Total tokens across all types
    """
    if not usage_data:
        return 0
    
    # Handle both field name variations
    input_tokens = usage_data.get('input_tokens', 0)
    output_tokens = usage_data.get('output_tokens', 0)
    
    # Cache creation tokens - external tool compatible logic
    # Use direct field first, fallback to nested if not present
    if 'cache_creation_input_tokens' in usage_data:
        cache_creation = usage_data['cache_creation_input_tokens']
    elif 'cache_creation' in usage_data and isinstance(usage_data['cache_creation'], dict):
        cache_creation = usage_data['cache_creation'].get('ephemeral_5m_input_tokens', 0)
    else:
        cache_creation = (
            usage_data.get('cacheCreationInputTokens', 0) or
            usage_data.get('cacheCreationTokens', 0)
        )
    
    # Cache read tokens - external tool compatible logic  
    if 'cache_read_input_tokens' in usage_data:
        cache_read = usage_data['cache_read_input_tokens']
    elif 'cache_read' in usage_data and isinstance(usage_data['cache_read'], dict):
        cache_read = usage_data['cache_read'].get('ephemeral_5m_input_tokens', 0)
    else:
        cache_read = (
            usage_data.get('cacheReadInputTokens', 0) or
            usage_data.get('cacheReadTokens', 0)
        )
    
    return input_tokens + output_tokens + cache_creation + cache_read

def format_token_count(tokens):
    """Format token count for display"""
    if tokens >= 1000000:
        return f"{tokens / 1000000:.1f}M"
    elif tokens >= 1000:
        return f"{tokens / 1000:.1f}K"
    return str(tokens)

def format_token_count_short(tokens):
    """Format token count for display (3 significant digits)"""
    if tokens >= 1000000:
        val = tokens / 1000000
        if val >= 100:
            return f"{round(val)}M"      # 100M, 200M
        else:
            return f"{val:.1f}M"         # 14.0M, 1.5M
    elif tokens >= 1000:
        val = tokens / 1000
        if val >= 100:
            return f"{round(val)}K"      # 332K, 500K
        else:
            return f"{val:.1f}K"         # 14.0K, 99.5K
    return str(tokens)

def convert_utc_to_local(utc_time):
    """Convert UTC timestamp to local time (common utility)"""
    if hasattr(utc_time, 'tzinfo') and utc_time.tzinfo:
        return utc_time.astimezone()
    else:
        # UTC timestamp without timezone info
        utc_with_tz = utc_time.replace(tzinfo=timezone.utc)
        return utc_with_tz.astimezone()

def convert_local_to_utc(local_time):
    """Convert local timestamp to UTC (common utility)"""
    if hasattr(local_time, 'tzinfo') and local_time.tzinfo:
        return local_time.astimezone(timezone.utc)
    else:
        # Local timestamp without timezone info
        return local_time.replace(tzinfo=timezone.utc)

def get_percentage_color(percentage):
    """Get color based on percentage threshold"""
    if percentage >= 90:
        return '\033[1;91m'  # bright red
    elif percentage >= 80:
        return Colors.BRIGHT_YELLOW
    return Colors.BRIGHT_GREEN

def get_percentage_color_dim(percentage):
    """Get dim (non-bold) color for fractional progress bar segments"""
    if percentage >= 90:
        return Colors.DIM_RED
    elif percentage >= 80:
        return Colors.DIM_YELLOW
    return Colors.DIM_GREEN

def calculate_dynamic_padding(compact_text, session_text):
    """Calculate dynamic padding to align progress bars
    
    Args:
        compact_text: Text part of compact line (e.g., "Context: 111.6K/200.0K")
        session_text: Text part of session line (e.g., "Session: 3h26m/5h")
    
    Returns:
        str: Padding spaces for session line
    """
    # Remove ANSI color codes for accurate length calculation
    import re
    clean_compact = re.sub(r'\x1b\[[0-9;]*m', '', compact_text)
    clean_session = re.sub(r'\x1b\[[0-9;]*m', '', session_text)
    
    compact_len = len(clean_compact)
    session_len = len(clean_session)
    
    
    
    if session_len < compact_len:
        return ' ' * (compact_len - session_len + 1)  # +1 for visual adjustment
    else:
        return ' '

def get_progress_bar(percentage, width=20, show_current_segment=False):
    """Create a visual progress bar with optional current segment highlighting

    Fractional segments are shown in dim (non-bold) color to indicate partial fill.
    """
    filled_exact = width * percentage / 100
    filled = int(filled_exact)
    fraction = filled_exact - filled
    has_fraction = fraction > 0.01 and filled < width

    color = get_percentage_color(percentage)
    dim_color = get_percentage_color_dim(percentage)

    if show_current_segment and filled < width:
        completed_bar = color + '█' * filled if filled > 0 else ''
        current_bar = Colors.BRIGHT_WHITE + '▓' + Colors.RESET
        remaining = width - filled - 1
        remaining_bar = Colors.LIGHT_GRAY + '▒' * remaining + Colors.RESET if remaining > 0 else ''
        bar = completed_bar + current_bar + remaining_bar
    else:
        bar = color + '█' * filled
        if has_fraction:
            bar += dim_color + '█'
            empty = width - filled - 1
        else:
            empty = width - filled
        bar += Colors.LIGHT_GRAY + '▒' * empty + Colors.RESET

    return bar

# REMOVED: create_line_graph() - unused function (replaced by create_mini_chart)

# REMOVED: create_bar_chart() - unused function (replaced by create_horizontal_chart)

def create_sparkline(values, width=20):
    """Create a compact sparkline graph"""
    if not values:
        return ""
    
    # Use unicode block characters for sparkline
    chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    
    max_val = max(values)
    min_val = min(values)
    
    if max_val == min_val:
        # If all values are the same
        if max_val == 0:
            # All zeros (idle) - show lowest bars
            return Colors.LIGHT_GRAY + chars[0] * min(width, len(values)) + Colors.RESET
        else:
            # All same non-zero value - show medium bars
            return Colors.BRIGHT_GREEN + chars[4] * min(width, len(values)) + Colors.RESET
    
    sparkline = ""
    data_width = min(width, len(values))
    step = len(values) / data_width if len(values) > data_width else 1
    
    for i in range(data_width):
        idx = int(i * step) if step > 1 else i
        if idx < len(values):
            normalized = (values[idx] - min_val) / (max_val - min_val)
            char_idx = min(len(chars) - 1, int(normalized * len(chars)))
            
            # Color based on value
            if normalized > 0.7:
                color = Colors.BRIGHT_RED
            elif normalized > 0.4:
                color = Colors.BRIGHT_YELLOW
            else:
                color = Colors.BRIGHT_GREEN
            
            sparkline += color + chars[char_idx] + Colors.RESET
    
    return sparkline

# REMOVED: get_all_messages() - unused function (replaced by load_all_messages_chronologically)

def get_real_time_burn_data(session_id=None):
    """Get real-time burn rate data from recent session activity with idle detection (30 minutes)"""
    try:
        if not session_id:
            return []
            
        # Get transcript file for current session
        transcript_file = find_session_transcript(session_id)
        if not transcript_file:
            return []
        
        now = datetime.now()
        thirty_min_ago = now - timedelta(minutes=30)
        
        # Read messages from transcript
        messages_with_time = []
        
        with open(transcript_file, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    timestamp_str = entry.get('timestamp')
                    if not timestamp_str:
                        continue
                    
                    # Parse timestamp and convert to local time
                    msg_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    msg_time = msg_time.astimezone().replace(tzinfo=None)  # Convert to local time
                    
                    # Only consider messages from last 30 minutes
                    if msg_time >= thirty_min_ago:
                        messages_with_time.append((msg_time, entry))
                        
                except (json.JSONDecodeError, ValueError):
                    continue
        
        if not messages_with_time:
            return []
        
        # Sort by time
        messages_with_time.sort(key=lambda x: x[0])
        
        # Calculate burn rates per minute
        burn_rates = []
        
        for minute in range(30):
            # Define 1-minute interval
            interval_start = thirty_min_ago + timedelta(minutes=minute)
            interval_end = interval_start + timedelta(minutes=1)
            
            # Count tokens in this interval
            interval_tokens = 0
            
            for msg_time, msg in messages_with_time:
                if interval_start <= msg_time < interval_end:
                    # Check for token usage in assistant messages
                    if msg.get('type') == 'assistant' and msg.get('message', {}).get('usage'):
                        usage = msg['message']['usage']
                        interval_tokens += get_total_tokens(usage)
            
            # Burn rate = tokens per minute
            burn_rates.append(interval_tokens)
        
        return burn_rates
    
    except Exception:
        return []

# REMOVED: show_live_burn_graph() - unused function (replaced by get_burn_line)
def calculate_tokens_from_transcript(file_path):
    """Calculate total tokens from transcript file by summing all message usage data"""
    # Check 15s file cache (TTL + path + mtime validation)
    file_path = Path(file_path) if not isinstance(file_path, Path) else file_path
    cached = _load_transcript_stats_cache(file_path)
    if cached:
        return (cached['total_tokens'], cached['message_count'], cached['error_count'],
                cached['user_messages'], cached['assistant_messages'],
                cached['input_tokens'], cached['output_tokens'],
                cached['cache_creation'], cached['cache_read'])

    message_count = 0
    error_count = 0
    user_messages = 0
    assistant_messages = 0

    # トークンの詳細追跡（全メッセージの合計）
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_creation = 0
    total_cache_read = 0

    try:
        with open(file_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    
                    # Count message types
                    if entry.get('type') == 'user':
                        user_messages += 1
                        message_count += 1
                    elif entry.get('type') == 'assistant':
                        assistant_messages += 1
                        message_count += 1
                    
                    # Count errors
                    if 'error' in entry or entry.get('type') == 'error':
                        error_count += 1
                    
                    # 最後の有効なassistantメッセージのusageを使用（累積値）
                    if entry.get('type') == 'assistant' and entry.get('message', {}).get('usage'):
                        usage = entry['message']['usage']
                        # 0でないusageのみ更新（エラーメッセージのusage=0を無視）
                        total_tokens_in_usage = (usage.get('input_tokens', 0) + 
                                               usage.get('output_tokens', 0) + 
                                               usage.get('cache_creation_input_tokens', 0) + 
                                               usage.get('cache_read_input_tokens', 0))
                        if total_tokens_in_usage > 0:
                            total_input_tokens = usage.get('input_tokens', 0)
                            total_output_tokens = usage.get('output_tokens', 0)
                            total_cache_creation = usage.get('cache_creation_input_tokens', 0)
                            total_cache_read = usage.get('cache_read_input_tokens', 0)
                        
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return 0, 0, 0, 0, 0, 0, 0, 0, 0
    except Exception as e:
        # Log error for debugging
        with open(Path.home() / '.claude' / 'statusline-error.log', 'a') as f:
            f.write(f"\n{datetime.now()}: Error in calculate_tokens_from_transcript: {e}\n")
            f.write(f"File path: {file_path}\n")
        return 0, 0, 0, 0, 0, 0, 0, 0, 0
    
    # 総トークン数（professional calculation）
    total_tokens = get_total_tokens({
        'input_tokens': total_input_tokens,
        'output_tokens': total_output_tokens,
        'cache_creation_input_tokens': total_cache_creation,
        'cache_read_input_tokens': total_cache_read
    })

    result = (total_tokens, message_count, error_count, user_messages, assistant_messages,
              total_input_tokens, total_output_tokens, total_cache_creation, total_cache_read)
    _save_transcript_stats_cache(file_path, result)
    return result

def find_session_transcript(session_id):
    """Find transcript file for the current session"""
    if not session_id:
        return None
    
    projects_dir = Path.home() / '.claude' / 'projects'
    
    if not projects_dir.exists():
        return None
    
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            transcript_file = project_dir / f"{session_id}.jsonl"
            if transcript_file.exists():
                return transcript_file
    
    return None

def find_all_transcript_files(hours_limit=6):
    """Find transcript files updated within the specified time limit

    Args:
        hours_limit: Only return files modified within this many hours (default: 6)
                     Set to None to return all files (not recommended for performance)
    """
    projects_dir = Path.home() / '.claude' / 'projects'

    if not projects_dir.exists():
        return []

    transcript_files = []
    cutoff_time = time.time() - (hours_limit * 3600) if hours_limit else 0

    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            for file_path in project_dir.glob("*.jsonl"):
                # Only include files modified within the time limit
                if hours_limit is None or file_path.stat().st_mtime >= cutoff_time:
                    transcript_files.append(file_path)

    return transcript_files

def load_all_messages_chronologically(hours_limit=6):
    """Load messages from recently updated transcripts in chronological order

    Args:
        hours_limit: Only load from files modified within this many hours (default: 6)
    """
    all_messages = []
    transcript_files = find_all_transcript_files(hours_limit=hours_limit)

    for transcript_file in transcript_files:
        try:
            with open(transcript_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get('timestamp'):
                            # UTC タイムスタンプをローカルタイムゾーンに変換、但しUTCも保持
                            timestamp_utc = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                            timestamp_local = timestamp_utc.astimezone()
                            
                            all_messages.append({
                                'timestamp': timestamp_local,
                                'timestamp_utc': timestamp_utc,  # compatibility
                                'session_id': entry.get('sessionId'),
                                'type': entry.get('type'),
                                'usage': entry.get('message', {}).get('usage') if entry.get('message') else entry.get('usage'),
                                'uuid': entry.get('uuid'),  # For deduplication
                                'requestId': entry.get('requestId'),  # For deduplication
                                'file_path': transcript_file
                            })
                    except (json.JSONDecodeError, ValueError):
                        continue
        except (FileNotFoundError, PermissionError):
            continue
    
    # 時系列でソート
    all_messages.sort(key=lambda x: x['timestamp'])

    return all_messages

def detect_five_hour_blocks(all_messages, block_duration_hours=5):
    """🕐 SESSION WINDOW: Detect usage periods
    
    Creates usage windows as per usage limits.
    These blocks track the 5-hour reset periods.
    
    Primarily used by session/burn lines for usage window tracking.
    Compact line uses different logic for conversation compaction monitoring.
    
    Args:
        all_messages: All messages across all sessions/projects
        block_duration_hours: Block duration (default: 5 hours per usage spec)
    Returns:
        List of usage tracking blocks with statistics
    """
    if not all_messages:
        return []
    
    # Step 1: Sort ALL entries by timestamp
    sorted_messages = sorted(all_messages, key=lambda x: x['timestamp'])
    
    # Step 1.5: Filter to recent messages only (for accurate block detection)
    # Only consider messages from the last 6 hours to improve accuracy
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff_time = now - timedelta(hours=6)  # Last 6 hours only
    
    recent_messages = []
    for msg in sorted_messages:
        msg_time = msg['timestamp']
        if hasattr(msg_time, 'tzinfo') and msg_time.tzinfo:
            msg_time = msg_time.astimezone(timezone.utc).replace(tzinfo=None)
        
        if msg_time >= cutoff_time:
            recent_messages.append(msg)
    
    # Use recent messages instead of all messages
    sorted_messages = recent_messages

    blocks = []
    block_duration_ms = block_duration_hours * 60 * 60 * 1000
    current_block_start = None
    current_block_entries = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # Step 2: Process entries in chronological order ()
    for entry in sorted_messages:
        entry_time = entry['timestamp']
        
        # Ensure all timestamps are timezone-naive for consistent comparison
        if hasattr(entry_time, 'tzinfo') and entry_time.tzinfo:
            entry_time = entry_time.astimezone(timezone.utc).replace(tzinfo=None)
        
        if current_block_start is None:
            # First entry - start a new block (floored to the hour)
            current_block_start = floor_to_hour(entry_time)
            current_block_entries = [entry]
        else:
            # Check if we need to close current block -  123
            time_since_block_start_ms = (entry_time - current_block_start).total_seconds() * 1000
            
            if len(current_block_entries) > 0:
                last_entry_time = current_block_entries[-1]['timestamp']
                # Ensure timezone consistency
                if hasattr(last_entry_time, 'tzinfo') and last_entry_time.tzinfo:
                    last_entry_time = last_entry_time.astimezone(timezone.utc).replace(tzinfo=None)
                time_since_last_entry_ms = (entry_time - last_entry_time).total_seconds() * 1000
            else:
                time_since_last_entry_ms = 0
            
            if time_since_block_start_ms > block_duration_ms or time_since_last_entry_ms > block_duration_ms:
                # Close current block -  125
                block = create_session_block(current_block_start, current_block_entries, now, block_duration_ms)
                blocks.append(block)
                
                # TODO: Add gap block creation if needed ( 129-134)
                
                # Start new block (floored to the hour)
                current_block_start = floor_to_hour(entry_time)
                current_block_entries = [entry]
            else:
                # Add to current block -  142
                current_block_entries.append(entry)
    
    # Close the last block -  148
    if current_block_start is not None and len(current_block_entries) > 0:
        block = create_session_block(current_block_start, current_block_entries, now, block_duration_ms)
        blocks.append(block)
    
    return blocks
def floor_to_hour(timestamp):
    """Floor timestamp to hour boundary"""
    # Convert to UTC if timezone-aware
    if hasattr(timestamp, 'tzinfo') and timestamp.tzinfo:
        utc_timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        utc_timestamp = timestamp
    
    # UTC-based flooring: Use UTC time and floor to hour
    floored = utc_timestamp.replace(minute=0, second=0, microsecond=0)
    return floored
def create_session_block(start_time, entries, now, session_duration_ms):
    """Create session block from entries"""
    end_time = start_time + timedelta(milliseconds=session_duration_ms)
    
    if entries:
        last_entry = entries[-1]
        actual_end_time = last_entry['timestamp']
        if hasattr(actual_end_time, 'tzinfo') and actual_end_time.tzinfo:
            actual_end_time = actual_end_time.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        actual_end_time = start_time
    
    
    time_since_last_activity = (now - actual_end_time).total_seconds() * 1000
    is_active = time_since_last_activity < session_duration_ms and now < end_time
    
    # Calculate duration: for active blocks use current time, for completed blocks use actual_end_time
    if is_active:
        duration_seconds = (now - start_time).total_seconds()
    else:
        duration_seconds = (actual_end_time - start_time).total_seconds()
    
    return {
        'start_time': start_time,
        'end_time': end_time,
        'actual_end_time': actual_end_time,
        'messages': entries,
        'duration_seconds': duration_seconds,
        'is_active': is_active
    }

def find_current_session_block(blocks, target_session_id):
    """Find the most recent active block containing the target session"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # First priority: Find currently active block (current time within block duration)
    for block in reversed(blocks):  # 新しいブロックから探す
        block_start = block['start_time']
        block_end = block['end_time']
        
        # Check if current time is within this block's 5-hour window
        if block_start <= now <= block_end:
            return block
    
    # Fallback: Find block containing target session
    for block in reversed(blocks):
        for message in block['messages']:
            msg_session_id = message.get('session_id') or message.get('sessionId')
            if msg_session_id == target_session_id:
                return block
    
    return None

def calculate_block_statistics_with_deduplication(block, session_id):
    """Calculate comprehensive statistics for a 5-hour block with proper deduplication"""
    if not block:
        return None
    
    # ⚠️ BUG: This reads ONLY current session file, not ALL projects in the block
    # Should use block['messages'] which contains all projects' messages
    # 
    # FIXED: Use block messages directly instead of single session file
    return calculate_block_statistics_from_messages(block)

def calculate_block_statistics_from_messages(block):
    """Calculate statistics directly from block messages (all projects)"""
    if not block or 'messages' not in block:
        return None
    
    # FINAL APPROACH: Sum individual messages with enhanced deduplication
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_creation = 0
    total_cache_read = 0
    total_messages = 0
    processed_hashes = set()
    processed_session_messages = set()  # Additional session-level dedup
    skipped_duplicates = 0
    debug_samples = []
    
    # Process ALL messages in the block (from all projects) with enhanced deduplication
    for i, message in enumerate(block['messages']):
        if message.get('type') == 'assistant' and message.get('usage'):
            # Primary deduplication: messageId + requestId
            message_id = message.get('uuid') or message.get('message_id')
            request_id = message.get('requestId') or message.get('request_id')
            session_id = message.get('session_id')

            unique_hash = None
            if message_id and request_id:
                unique_hash = f"{message_id}:{request_id}"
            
            # Enhanced deduplication: Also check session+timestamp to catch cumulative duplicates
            timestamp = message.get('timestamp')
            session_message_key = f"{session_id}:{timestamp}" if session_id and timestamp else None
            
            skip_message = False
            if unique_hash and unique_hash in processed_hashes:
                skipped_duplicates += 1
                skip_message = True
            elif session_message_key and session_message_key in processed_session_messages:
                skipped_duplicates += 1  
                skip_message = True
                
            if skip_message:
                continue  # Skip duplicate
                
            # Record this message as processed
            if unique_hash:
                processed_hashes.add(unique_hash)
            if session_message_key:
                processed_session_messages.add(session_message_key)
            
            total_messages += 1
            
            # Use individual token components (not cumulative)
            usage = message['usage']
            
            # Get individual incremental tokens (not cumulative)
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            
            # Cache tokens using external tool compatible logic
            if 'cache_creation_input_tokens' in usage:
                cache_creation = usage['cache_creation_input_tokens']
            elif 'cache_creation' in usage and isinstance(usage['cache_creation'], dict):
                cache_creation = usage['cache_creation'].get('ephemeral_5m_input_tokens', 0)
            else:
                cache_creation = 0
                
            if 'cache_read_input_tokens' in usage:
                cache_read = usage['cache_read_input_tokens']
            elif 'cache_read' in usage and isinstance(usage['cache_read'], dict):
                cache_read = usage['cache_read'].get('ephemeral_5m_input_tokens', 0)
            else:
                cache_read = 0
            
            # Accumulate individual message tokens
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
            total_cache_creation += cache_creation
            total_cache_read += cache_read
            
            # Debug samples  
            if len(debug_samples) < 3:
                debug_samples.append({
                    'idx': i,
                    'session_id': session_id,
                    'input': input_tokens,
                    'cache_creation': cache_creation,
                    'cache_read': cache_read,
                    'total': input_tokens + output_tokens + cache_creation + cache_read
                })
    
    # Final calculation - use actual accumulated values
    total_tokens = total_input_tokens + total_output_tokens + total_cache_creation + total_cache_read

    return {
        'start_time': block['start_time'],
        'duration_seconds': block.get('duration_seconds', 0),
        'total_tokens': total_tokens,
        'input_tokens': total_input_tokens,
        'output_tokens': total_output_tokens,
        'cache_creation': total_cache_creation,
        'cache_read': total_cache_read,
        'total_messages': total_messages
    }

def calculate_tokens_from_jsonl_with_dedup(transcript_file, block_start_time, duration_seconds):
    """Calculate tokens with proper deduplication from JSONL file"""
    try:
        import json
        from datetime import datetime, timezone
        
        # 時間範囲を計算
        if hasattr(block_start_time, 'tzinfo') and block_start_time.tzinfo:
            block_start_utc = block_start_time.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            block_start_utc = block_start_time
        
        block_end_time = block_start_utc + timedelta(seconds=duration_seconds)
        
        # 重複除去とトークン計算
        processed_hashes = set()
        total_input_tokens = 0
        total_output_tokens = 0
        total_cache_creation = 0
        total_cache_read = 0
        user_messages = 0
        assistant_messages = 0
        error_count = 0
        total_messages = 0
        skipped_duplicates = 0
        
        with open(transcript_file, 'r') as f:
            for line in f:
                try:
                    message_data = json.loads(line.strip())
                    if not message_data:
                        continue
                    
                    # 時間フィルタリング
                    timestamp_str = message_data.get('timestamp')
                    if not timestamp_str:
                        continue
                    
                    msg_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if msg_time.tzinfo:
                        msg_time_utc = msg_time.astimezone(timezone.utc).replace(tzinfo=None)
                    else:
                        msg_time_utc = msg_time
                    
                    # 5時間ウィンドウ内チェック
                    if not (block_start_utc <= msg_time_utc <= block_end_time):
                        continue
                    
                    total_messages += 1
                    
                    # External tool compatible deduplication (messageId + requestId only)
                    message_id = message_data.get('uuid')
                    request_id = message_data.get('requestId')
                    
                    unique_hash = None
                    if message_id and request_id:
                        unique_hash = f"{message_id}:{request_id}"
                    
                    if unique_hash:
                        if unique_hash in processed_hashes:
                            skipped_duplicates += 1
                            continue
                        processed_hashes.add(unique_hash)
                    
                    # メッセージ種別カウント
                    msg_type = message_data.get('type', '')
                    if msg_type == 'user':
                        user_messages += 1
                    elif msg_type == 'assistant':
                        assistant_messages += 1
                    elif msg_type == 'error':
                        error_count += 1
                    
                    # トークン計算（assistantメッセージのusageのみ）
                    usage = None
                    if msg_type == 'assistant':
                        # usageは最上位またはmessage.usageにある
                        usage = message_data.get('usage') or message_data.get('message', {}).get('usage')
                    
                    if usage:
                        total_input_tokens += usage.get('input_tokens', 0)
                        total_output_tokens += usage.get('output_tokens', 0)
                        total_cache_creation += usage.get('cache_creation_input_tokens', 0)
                        total_cache_read += usage.get('cache_read_input_tokens', 0)
                
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
        
        total_tokens = get_total_tokens({
            'input_tokens': total_input_tokens,
            'output_tokens': total_output_tokens,
            'cache_creation_input_tokens': total_cache_creation,
            'cache_read_input_tokens': total_cache_read
        })
        
        # 重複除去の統計（本番では無効化可能）
        # dedup_rate = (skipped_duplicates / total_messages) * 100 if total_messages > 0 else 0
        
        return {
            'start_time': block_start_time,
            'duration_seconds': duration_seconds,
            'total_tokens': total_tokens,
            'input_tokens': total_input_tokens,
            'output_tokens': total_output_tokens,
            'cache_creation': total_cache_creation,
            'cache_read': total_cache_read,
            'user_messages': user_messages,
            'assistant_messages': assistant_messages,
            'error_count': error_count,
            'total_messages': total_messages,
            'skipped_duplicates': skipped_duplicates,
            'active_duration': duration_seconds,  # 概算
            'efficiency_ratio': 0.8,  # 概算
            'is_active': True,
            'burn_timeline': generate_burn_timeline_from_jsonl(transcript_file, block_start_utc, duration_seconds)
        }

    except Exception:
        return None

def generate_burn_timeline_from_jsonl(transcript_file, block_start_utc, duration_seconds):
    """Generate 15-minute interval burn timeline from JSONL file"""
    try:
        import json
        from datetime import datetime, timezone
        
        timeline = [0] * 20  # 20 segments (5 hours / 15 minutes each)
        block_end_time = block_start_utc + timedelta(seconds=duration_seconds)
        
        with open(transcript_file, 'r') as f:
            for line in f:
                try:
                    message_data = json.loads(line.strip())
                    if not message_data or message_data.get('type') != 'assistant':
                        continue
                    
                    # Get timestamp
                    timestamp_str = message_data.get('timestamp')
                    if not timestamp_str:
                        continue
                    
                    msg_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if msg_time.tzinfo:
                        msg_time_utc = msg_time.astimezone(timezone.utc).replace(tzinfo=None)
                    else:
                        msg_time_utc = msg_time
                    
                    # Check if within 5-hour window
                    if not (block_start_utc <= msg_time_utc <= block_end_time):
                        continue
                    
                    # Get usage data
                    usage = message_data.get('usage') or message_data.get('message', {}).get('usage')
                    if not usage:
                        continue
                    
                    # Calculate elapsed minutes from block start
                    elapsed_seconds = (msg_time_utc - block_start_utc).total_seconds()
                    elapsed_minutes = elapsed_seconds / 60
                    
                    # Calculate 15-minute segment index (0-19)
                    segment_index = int(elapsed_minutes / 15)
                    if 0 <= segment_index < 20:
                        # Add tokens to the segment
                        tokens = (usage.get('input_tokens', 0) + 
                                usage.get('output_tokens', 0) + 
                                usage.get('cache_creation_input_tokens', 0) + 
                                usage.get('cache_read_input_tokens', 0))
                        timeline[segment_index] += tokens
                
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
        
        return timeline
        
    except Exception:
        return [0] * 20

def calculate_block_statistics_fallback(block):
    """Fallback: existing logic without deduplication"""
    if not block or not block['messages']:
        return None
    
    # トークン使用量の計算
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_creation = 0
    total_cache_read = 0
    
    user_messages = 0
    assistant_messages = 0
    error_count = 0
    processed_hashes = set()  # 重複除去用（messageId:requestId）
    total_messages = 0
    skipped_duplicates = 0
    
    for message in block['messages']:
        total_messages += 1
        
        # メッセージがタプル(timestamp, data)の場合は2番目の要素を取得
        if isinstance(message, tuple):
            message_data = message[1]
        else:
            message_data = message
        
        # メッセージ構造の確認（デバッグ時のみ有効化）
        # if total_messages <= 3:
        #     import sys
        #     print(f"DEBUG: message structure check", file=sys.stderr)
        
        # External tool compatible deduplication (messageId + requestId only)
        message_id = message_data.get('uuid')  # 実際のメッセージID
        request_id = message_data.get('requestId')  # requestIdは最上位
        
        unique_hash = None
        if message_id and request_id:
            unique_hash = f"{message_id}:{request_id}"
        
        if unique_hash:
            if unique_hash in processed_hashes:
                skipped_duplicates += 1
                continue  # 重複メッセージをスキップ
            processed_hashes.add(unique_hash)
        
        # メッセージ種別のカウント
        if message_data['type'] == 'user':
            user_messages += 1
        elif message_data['type'] == 'assistant':
            assistant_messages += 1
        elif message_data['type'] == 'error':
            error_count += 1
        
        # トークン使用量の合計（assistantメッセージのusageのみ - 外部ツール互換）
        if message_data['type'] == 'assistant' and message_data.get('usage'):
            total_input_tokens += message_data['usage'].get('input_tokens', 0)
            total_output_tokens += message_data['usage'].get('output_tokens', 0)
            total_cache_creation += message_data['usage'].get('cache_creation_input_tokens', 0)
            total_cache_read += message_data['usage'].get('cache_read_input_tokens', 0)
    
    total_tokens = get_total_tokens({
        'input_tokens': total_input_tokens,
        'output_tokens': total_output_tokens,
        'cache_creation_input_tokens': total_cache_creation,
        'cache_read_input_tokens': total_cache_read
    })
    
    # アクティブ期間の検出（ブロック内）
    active_periods = detect_active_periods(block['messages'])
    total_active_duration = sum((end - start).total_seconds() for start, end in active_periods)
    
    # Use duration already calculated in create_session_block
    actual_duration = block['duration_seconds']
    
    # Use duration already calculated in create_session_block
    actual_duration = block['duration_seconds']
    
    # アクティブ期間の検出（ブロック内）
    active_periods = detect_active_periods(block['messages'])
    total_active_duration = sum((end - start).total_seconds() for start, end in active_periods)
    
    # 5時間ブロック内での15分間隔Burnデータを生成（20セグメント）- 同じデータソース使用
    burn_timeline = generate_realtime_burn_timeline(block['start_time'], actual_duration)

    return {
        'start_time': block['start_time'],
        'duration_seconds': actual_duration,
        'total_tokens': total_tokens,
        'input_tokens': total_input_tokens,
        'output_tokens': total_output_tokens,
        'cache_creation': total_cache_creation,
        'cache_read': total_cache_read,
        'user_messages': user_messages,
        'assistant_messages': assistant_messages,
        'error_count': error_count,
        'total_messages': total_messages,
        'skipped_duplicates': skipped_duplicates,
        'active_duration': total_active_duration,
        'efficiency_ratio': total_active_duration / actual_duration if actual_duration > 0 else 0,
        'is_active': block.get('is_active', False),
        'burn_timeline': burn_timeline
    }

def generate_block_burn_timeline(block):
    """5時間ブロック内を20個の15分セグメントに分割してburn rate計算（時間ベース）"""
    if not block:
        return [0] * 20
    
    timeline = [0] * 20  # 20セグメント（各15分）
    
    # 現在時刻とブロック開始時刻から実際の経過時間を計算
    block_start = block['start_time']
    current_time = datetime.now()
    
    # タイムゾーン統一（ローカル時間に合わせる）
    if hasattr(block_start, 'tzinfo') and block_start.tzinfo:
        block_start_local = block_start.astimezone().replace(tzinfo=None)
    else:
        block_start_local = block_start
    
    # 経過時間（分）
    elapsed_minutes = (current_time - block_start_local).total_seconds() / 60
    
    # 経過した15分セグメント数
    completed_segments = min(20, int(elapsed_minutes / 15) + 1)
    
    # メッセージデータからトークン使用量を取得
    messages = block.get('messages', [])
    total_tokens_in_block = 0
    
    for message in messages:
        if message.get('usage'):
            tokens = get_total_tokens(message['usage'])
            total_tokens_in_block += tokens
    
    # トークン使用量を経過セグメントに分散（実際の活動パターンを反映）
    if total_tokens_in_block > 0 and completed_segments > 0:
        # 基本的な分散パターン（前半重め、中盤軽め、後半やや重め）
        activity_pattern = [0.8, 1.2, 0.9, 1.1, 0.7, 1.3, 0.6, 1.0, 0.9, 1.1, 0.8, 1.2, 0.7, 1.4, 1.0, 1.1, 0.9, 1.3, 1.2, 1.0]
        
        # 経過したセグメントにのみデータを配置
        for i in range(completed_segments):
            if i < len(activity_pattern):
                segment_ratio = activity_pattern[i] / sum(activity_pattern[:completed_segments])
                timeline[i] = int(total_tokens_in_block * segment_ratio)
    
    return timeline

def generate_realtime_burn_timeline(block_start_time, duration_seconds):
    """Sessionと同じ時間データでBurnスパークラインを生成"""
    timeline = [0] * 20  # 20セグメント（各15分）
    
    # Sessionと同じ計算：経過時間から現在のセグメントまでを算出
    current_time = datetime.now()
    
    # タイムゾーン統一（両方をローカルタイムのnaiveに統一）
    if hasattr(block_start_time, 'tzinfo') and block_start_time.tzinfo:
        block_start_local = block_start_time.astimezone().replace(tzinfo=None)
    else:
        block_start_local = block_start_time
        
    # 実際の経過時間（Sessionと同じ）
    elapsed_minutes = (current_time - block_start_local).total_seconds() / 60
    
    # 経過した15分セグメント数
    completed_segments = min(20, int(elapsed_minutes / 15))
    if elapsed_minutes % 15 > 0:  # 現在のセグメントも部分的に含める
        completed_segments += 1
    completed_segments = min(20, completed_segments)
    
    
    # 経過したセグメントに活動データを設定（実際の時間ベース）
    for i in range(completed_segments):
        # 基本活動量 + ランダムな変動で現実的なパターン
        base_activity = 1000
        variation = (i * 47) % 800  # 疑似ランダム変動
        timeline[i] = base_activity + variation
    
    return timeline

def generate_real_burn_timeline(block_stats, current_block, api_block_start_utc=None):
    """実際のメッセージデータからBurnスパークラインを生成（5時間ウィンドウ全体対応）

    CRITICAL: Uses REAL message timing data ONLY. NO fake patterns allowed.
    Distributes tokens based on actual message timestamps across 15-minute segments.

    Args:
        api_block_start_utc: If provided (from API five_hour.resets_at - 5h),
            overrides block_stats['start_time'] to align sparkline with API window.
    """
    timeline = [0] * 20  # 20セグメント（各15分）

    if not block_stats or not current_block or 'messages' not in current_block:
        return timeline

    try:
        # Use API-derived start time if available, otherwise fall back to local detection
        if api_block_start_utc is not None:
            block_start_utc = api_block_start_utc
        else:
            block_start = block_stats['start_time']
            if hasattr(block_start, 'tzinfo') and block_start.tzinfo:
                block_start_utc = block_start.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                block_start_utc = block_start
        
        # デバッグ: メッセージの時間分散を確認 (デバッグ時のみ有効化)
        # import sys
        # print(f"DEBUG: Processing {len(current_block['messages'])} messages for burn timeline", file=sys.stderr)
        
        # 実際のメッセージ数を各セグメントで計算
        message_count_per_segment = [0] * 20
        total_processed = 0
        
        # 5時間ウィンドウ内の全メッセージを処理（Sessionと同じデータソース）
        for message in current_block['messages']:
            try:
                # assistantメッセージのusageデータのみ処理
                if message.get('type') != 'assistant' or not message.get('usage'):
                    continue
                
                # タイムスタンプ取得
                msg_time = message.get('timestamp')
                if not msg_time:
                    continue
                
                # タイムスタンプをUTCに統一
                if hasattr(msg_time, 'tzinfo') and msg_time.tzinfo:
                    msg_time_utc = msg_time.astimezone(timezone.utc).replace(tzinfo=None)
                else:
                    msg_time_utc = msg_time  # 既にUTC前提
                
                # ブロック開始からの経過時間（分）
                elapsed_minutes = (msg_time_utc - block_start_utc).total_seconds() / 60
                
                # 負の値（ブロック開始前）や5時間超過はスキップ
                if elapsed_minutes < 0 or elapsed_minutes >= 300:  # 5時間 = 300分
                    continue
                
                # 15分セグメントのインデックス（0-19）
                segment_index = int(elapsed_minutes / 15)
                if 0 <= segment_index < 20:
                    # 実際のトークン使用量を取得
                    usage = message['usage']
                    tokens = get_total_tokens(usage)
                    timeline[segment_index] += tokens
                    message_count_per_segment[segment_index] += 1
                    total_processed += 1
            
            except (ValueError, KeyError, TypeError):
                continue
        
        # デバッグ: 時間分散を確認 (デバッグ時のみ有効化)
        # print(f"DEBUG: Processed {total_processed} messages across segments", file=sys.stderr)
        # active_segments = sum(1 for count in message_count_per_segment if count > 0)
        # print(f"DEBUG: Active segments: {active_segments}/20, timeline sum: {sum(timeline):,}", file=sys.stderr)
        # 
        # # デバッグ: 各セグメントのメッセージ数（最初の10セグメント）
        # segment_info = [f"{i}:{message_count_per_segment[i]}" for i in range(min(10, len(message_count_per_segment))) if message_count_per_segment[i] > 0]
        # if segment_info:
        #     print(f"DEBUG: Segment message counts (first 10): {', '.join(segment_info)}", file=sys.stderr)
    
    except Exception:
        # import sys
        # print(f"DEBUG: Error in generate_real_burn_timeline: {e}", file=sys.stderr)
        # エラー時は空のタイムラインを返す
        pass
    
    return timeline

def get_git_info(directory):
    """Get git branch and status"""
    try:
        git_dir = Path(directory) / '.git'
        if not git_dir.exists():
            return None, 0, 0
        
        # Get branch
        branch = None
        head_file = git_dir / 'HEAD'
        if head_file.exists():
            with open(head_file, 'r') as f:
                head = f.read().strip()
                if head.startswith('ref: refs/heads/'):
                    branch = head.replace('ref: refs/heads/', '')
        
        # Get detailed status
        try:
            # Check for uncommitted changes
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=1
            )
            
            changes = result.stdout.strip().split('\n') if result.stdout.strip() else []
            modified = len([c for c in changes if c.startswith(' M') or c.startswith('M')])
            added = len([c for c in changes if c.startswith('??')])
            
            return branch, modified, added
        except:
            return branch, 0, 0
            
    except Exception:
        return None, 0, 0

def get_time_info():
    """Get current time"""
    now = datetime.now()
    return now.strftime("%H:%M")

# ========================================
# SCHEDULE DISPLAY FUNCTIONS (gog integration)
# ========================================

def get_schedule_cache_file():
    """Get schedule cache file path (lazy initialization)"""
    global SCHEDULE_CACHE_FILE
    if SCHEDULE_CACHE_FILE is None:
        SCHEDULE_CACHE_FILE = Path.home() / '.claude' / '.schedule_cache.json'
    return SCHEDULE_CACHE_FILE

def parse_event_time(event):
    """Parse event time from gog JSON format

    Args:
        event: dict with 'start' containing either 'dateTime' or 'date'

    Returns:
        tuple: (datetime, is_all_day)
    """
    start = event.get('start', {})

    # Check for all-day event (date field instead of dateTime)
    if 'date' in start:
        # All-day event: parse date only
        date_str = start['date']
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        # Set to start of day in local timezone
        return dt.replace(hour=0, minute=0, second=0), True

    # Regular event with dateTime
    datetime_str = start.get('dateTime', '')
    if not datetime_str:
        return None, False

    # Parse RFC3339 format with timezone
    dt = datetime.fromisoformat(datetime_str)
    # Convert to local timezone
    return dt.astimezone(), False

def get_schedule_color(minutes_until):
    """Return color based on time until event

    Args:
        minutes_until: minutes until event starts (negative = ongoing)

    Returns:
        str: ANSI color code
    """
    if minutes_until <= 0:
        return Colors.BRIGHT_GREEN  # Ongoing
    elif minutes_until <= 10:
        return Colors.BRIGHT_RED    # Within 10 minutes (urgent)
    elif minutes_until <= 30:
        return Colors.BRIGHT_YELLOW # Within 30 minutes
    else:
        return Colors.BRIGHT_WHITE  # Normal

def fetch_from_gog():
    """Fetch next timed event from gog command (skip all-day events)

    Returns:
        dict or None: Event data or None if unavailable
    """
    try:
        # Fetch multiple events to skip all-day ones
        result = subprocess.run(
            ['gog', 'calendar', 'events', '--days=1', '--max=10', '--json'],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        events = data.get('events', [])

        if not events:
            return None

        # Find first timed event (skip all-day events)
        for event in events:
            start = event.get('start', {})
            # All-day events have 'date' instead of 'dateTime'
            if 'dateTime' in start:
                return event

        # No timed events found
        return None

    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, OSError):
        return None

def load_schedule_cache():
    """Load schedule cache from file

    Returns:
        dict or None: Cache data with 'timestamp' and 'data' keys
    """
    cache_file = get_schedule_cache_file()
    try:
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return None

def save_schedule_cache(event_data):
    """Save event data to cache file

    Args:
        event_data: Event dict to cache
    """
    cache_file = get_schedule_cache_file()
    try:
        cache = {
            'timestamp': time.time(),
            'data': event_data
        }
        with open(cache_file, 'w') as f:
            json.dump(cache, f)
    except IOError:
        pass

def get_next_event():
    """Get next calendar event with caching

    Returns:
        dict or None: {'time': '14:00', 'summary': '...', 'minutes_until': 30, 'is_all_day': False}
    """
    # Check cache first
    cache = load_schedule_cache()
    if cache and (time.time() - cache.get('timestamp', 0)) < SCHEDULE_CACHE_TTL:
        event = cache.get('data')
        if event:
            # Re-calculate minutes_until for cached event
            dt, is_all_day = parse_event_time(event)
            if dt:
                now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                delta = dt - now
                minutes_until = int(delta.total_seconds() / 60)

                # Skip past events
                end = event.get('end', {})
                end_dt = None
                if 'dateTime' in end:
                    end_dt = datetime.fromisoformat(end['dateTime']).astimezone()
                elif 'date' in end:
                    end_dt = datetime.strptime(end['date'], '%Y-%m-%d')

                if end_dt and now > end_dt:
                    # Event has ended, invalidate cache
                    pass
                else:
                    return {
                        'time': dt.strftime('%H:%M') if not is_all_day else None,
                        'summary': event.get('summary', 'Untitled'),
                        'minutes_until': minutes_until,
                        'is_all_day': is_all_day
                    }

    # Fetch fresh data
    event = fetch_from_gog()
    save_schedule_cache(event)

    if not event:
        return None

    dt, is_all_day = parse_event_time(event)
    if not dt:
        return None

    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    delta = dt - now
    minutes_until = int(delta.total_seconds() / 60)

    # Check if event has ended
    end = event.get('end', {})
    end_dt = None
    if 'dateTime' in end:
        end_dt = datetime.fromisoformat(end['dateTime']).astimezone()
    elif 'date' in end:
        end_dt = datetime.strptime(end['date'], '%Y-%m-%d')

    if end_dt and now > end_dt:
        # Event has ended
        return None

    return {
        'time': dt.strftime('%H:%M') if not is_all_day else None,
        'summary': event.get('summary', 'Untitled'),
        'minutes_until': minutes_until,
        'is_all_day': is_all_day
    }

def format_time_until(minutes):
    """Format time until event as human-readable string

    Args:
        minutes: minutes until event (can be negative for ongoing)

    Returns:
        str: e.g., "(in 30m)", "(in 2h)", "(now)"
    """
    if minutes <= 0:
        return "(now)"
    elif minutes < 60:
        return f"(in {minutes}m)"
    else:
        hours = minutes // 60
        mins = minutes % 60
        if mins > 0:
            return f"(in {hours}h{mins}m)"
        else:
            return f"(in {hours}h)"

def format_schedule_line(event, terminal_width):
    """Format schedule event as status line

    Args:
        event: dict with 'time', 'summary', 'minutes_until', 'is_all_day'
        terminal_width: available width for the line

    Returns:
        str: Formatted schedule line e.g., "📅 14:00 ミーティング (in 30m)"
    """
    if not event:
        return None

    color = get_schedule_color(event['minutes_until'])
    time_until = format_time_until(event['minutes_until'])

    if event['is_all_day']:
        time_part = "終日"
    else:
        time_part = event['time']

    summary = event['summary']

    # Build the line: 📅 14:00 summary (in Xm)
    prefix = f"📅 {time_part} "
    suffix = f" {time_until}"

    # Calculate available space for summary
    prefix_width = get_display_width(prefix)
    suffix_width = get_display_width(suffix)
    available = terminal_width - prefix_width - suffix_width - 2  # margin

    # Truncate summary if needed
    summary_width = get_display_width(summary)
    if summary_width > available and available > 3:
        # Truncate with ellipsis
        truncated = ""
        current_width = 0
        for char in summary:
            char_width = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
            if current_width + char_width + 1 > available:  # +1 for ellipsis
                break
            truncated += char
            current_width += char_width
        summary = truncated + "…"

    return f"{color}📅 {time_part} {summary} {time_until}{Colors.RESET}"

# REMOVED: detect_session_boundaries() - unused function (replaced by 5-hour block system)

def detect_active_periods(messages, idle_threshold=5*60):
    """Detect active periods within session (exclude idle time)"""
    if not messages:
        return []
    
    active_periods = []
    current_start = None
    last_time = None
    
    for msg in messages:
        try:
            msg_time_utc = datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00'))
            # システムのローカルタイムゾーンに自動変換
            msg_time = msg_time_utc.astimezone()
            
            if current_start is None:
                current_start = msg_time
                last_time = msg_time
                continue
            
            time_diff = (msg_time - last_time).total_seconds()
            
            if time_diff > idle_threshold:
                # 前のアクティブ期間を終了
                if current_start and last_time:
                    active_periods.append((current_start, last_time))
                # 新しいアクティブ期間を開始
                current_start = msg_time
            
            last_time = msg_time
            
        except:
            continue
    
    # 最後のアクティブ期間を追加
    if current_start and last_time:
        active_periods.append((current_start, last_time))
    
    return active_periods

# REMOVED: get_enhanced_session_analysis() - unused function (replaced by 5-hour block system)

# REMOVED: get_session_duration() - unused function (replaced by calculate_block_statistics)

# REMOVED: get_session_efficiency_metrics() - unused function (data available in calculate_block_statistics)

# REMOVED: get_time_progress_bar() - unused function (replaced by get_progress_bar)

def calculate_cost(input_tokens, output_tokens, cache_creation, cache_read, model_name="Unknown", model_id=""):
    """Calculate estimated cost based on token usage
    
    Pricing (per million tokens) - Claude 4 models (2025):
    
    Claude Opus 4 / Opus 4.1:
    - Input: $15.00
    - Output: $75.00
    - Cache write: $18.75 (input * 1.25)
    - Cache read: $1.50 (input * 0.10)
    
    Claude Sonnet 4:
    - Input: $3.00
    - Output: $15.00
    - Cache write: $3.75 (input * 1.25)
    - Cache read: $0.30 (input * 0.10)
    
    Claude 3.5 Haiku (if still used):
    - Input: $1.00
    - Output: $5.00
    - Cache write: $1.25
    - Cache read: $0.10
    """
    
    # モデル名またはIDからタイプを判定
    model_lower = model_name.lower()
    id_lower = model_id.lower() if model_id else ""

    if "haiku" in model_lower or "haiku" in id_lower:
        # Claude 3.5 Haiku pricing (legacy)
        input_rate = 1.00
        output_rate = 5.00
        cache_write_rate = 1.25
        cache_read_rate = 0.10
    elif "sonnet" in model_lower or "sonnet" in id_lower:
        # Claude Sonnet 4 pricing
        input_rate = 3.00
        output_rate = 15.00
        cache_write_rate = 3.75
        cache_read_rate = 0.30
    else:
        # Default to Opus 4/4.1 pricing (most expensive, safe default)
        input_rate = 15.00
        output_rate = 75.00
        cache_write_rate = 18.75
        cache_read_rate = 1.50
    
    # コスト計算（per million tokens）
    input_cost = (input_tokens / 1_000_000) * input_rate
    output_cost = (output_tokens / 1_000_000) * output_rate
    cache_write_cost = (cache_creation / 1_000_000) * cache_write_rate
    cache_read_cost = (cache_read / 1_000_000) * cache_read_rate
    
    total_cost = input_cost + output_cost + cache_write_cost + cache_read_cost
    
    return total_cost

def format_cost(cost):
    """Format cost for display"""
    if cost < 0.01:
        return f"${cost:.4f}"
    elif cost < 1:
        return f"${cost:.3f}"
    else:
        return f"${cost:.2f}"

# ========================================
# RESPONSIVE DISPLAY MODE FORMATTERS
# ========================================

def shorten_model_name(model, tight=False):
    """モデル名を短縮形に変換

    tight=False: "Claude " 除去のみ → "Opus 4.6"
    tight=True: ファミリー名も短縮 → "Op4.6"
    """
    import re
    # "Claude " プレフィックスを除去
    name = re.sub(r'^Claude\s+', '', model, flags=re.IGNORECASE)

    # "(1M context)" "(200k context)" などのコンテキストサイズ suffix を除去
    name = re.sub(r'\s*\([\d.]+[kKmM]?\s+context\)', '', name).strip()

    # "3.5 Haiku" → "Haiku 3.5" に正規化（バージョンが前にある場合）
    m = re.match(r'^([\d.]+)\s+(Haiku|Sonnet|Opus)', name, re.IGNORECASE)
    if m:
        name = f"{m.group(2)} {m.group(1)}"

    if tight:
        # ファミリー名を短縮
        name = re.sub(r'Opus', 'Op', name, flags=re.IGNORECASE)
        name = re.sub(r'Sonnet', 'Son', name, flags=re.IGNORECASE)
        name = re.sub(r'Haiku', 'Hai', name, flags=re.IGNORECASE)
        # スペース除去 → "Op4.6", "Son4.5", "Hai3.5"
        name = name.replace(' ', '')

    return name

def truncate_text(text, max_len):
    """テキストを最大長で切り詰め、...を追加"""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[:max_len-3] + "..."

def build_line1_parts(ctx, max_branch_len=20, max_dir_len=None,
                      include_active_files=True, include_messages=True,
                      include_lines=True, include_errors=True, include_cost=True,
                      tight_model=False, include_context_badge=True,
                      include_dir=True):
    """Line 1の各パーツを構築する

    Args:
        ctx: コンテキスト辞書
        max_branch_len: ブランチ名の最大長（デフォルト20、Noneで無制限）
        max_dir_len: ディレクトリ名の最大長（Noneで無制限）
        include_active_files: アクティブファイル数を含めるか
        include_messages: メッセージ数を含めるか
        include_lines: 行変更数を含めるか
        include_errors: エラー数を含めるか
        include_cost: コストを含めるか
        tight_model: モデル名を超短縮形式にするか（Op4.6など）
        include_context_badge: 1Mコンテキストバッジを表示するか
        include_dir: ディレクトリを含めるか

    Returns:
        list: Line 1のパーツのリスト
    """
    parts = []

    # Model (normal or tight)
    model_name = shorten_model_name(ctx['model'], tight=tight_model)
    ctx_suffix = "(1M)" if include_context_badge and ctx.get('context_size', 200000) > 200000 else ""
    parts.append(f"{Colors.BRIGHT_YELLOW}[{model_name}{Colors.BRIGHT_MAGENTA}{ctx_suffix}{Colors.BRIGHT_YELLOW}]{Colors.RESET}")

    # Git branch (no untracked files count)
    if ctx['git_branch']:
        branch = ctx['git_branch']
        if max_branch_len and len(branch) > max_branch_len:
            branch = truncate_text(branch, max_branch_len)
        git_display = f"{Colors.BRIGHT_GREEN}🌿 {branch}"
        if ctx['modified_files'] > 0:
            git_display += f" {Colors.BRIGHT_YELLOW}M{ctx['modified_files']}"
        git_display += Colors.RESET
        parts.append(git_display)

    # Directory
    if include_dir:
        dir_name = ctx['current_dir']
        if max_dir_len and len(dir_name) > max_dir_len:
            dir_name = truncate_text(dir_name, max_dir_len)
        parts.append(f"{Colors.BRIGHT_CYAN}📁 {dir_name}{Colors.RESET}")

    # Active files
    if include_active_files and ctx['active_files'] > 0:
        parts.append(f"{Colors.BRIGHT_WHITE}📝 {ctx['active_files']}{Colors.RESET}")

    # Messages
    if include_messages and ctx['total_messages'] > 0:
        parts.append(f"{Colors.BRIGHT_CYAN}💬 {ctx['total_messages']}{Colors.RESET}")

    # Lines changed
    if include_lines and (ctx['lines_added'] > 0 or ctx['lines_removed'] > 0):
        parts.append(f"{Colors.BRIGHT_GREEN}+{ctx['lines_added']}{Colors.RESET}/{Colors.BRIGHT_RED}-{ctx['lines_removed']}{Colors.RESET}")

    # Errors
    if include_errors and ctx['error_count'] > 0:
        parts.append(f"{Colors.BRIGHT_RED}⚠️ {ctx['error_count']}{Colors.RESET}")

    # Cost
    if include_cost and ctx['session_cost'] > 0:
        cost_color = Colors.BRIGHT_YELLOW if ctx['session_cost'] > 10 else Colors.BRIGHT_WHITE
        parts.append(f"{cost_color}💰 {format_cost(ctx['session_cost'])}{Colors.RESET}")

    return parts

def get_dead_agents():
    """Read dead agents file written by team-watcher"""
    try:
        with open('/tmp/tproj-dead-agents', 'r') as f:
            agents = [line.strip() for line in f if line.strip()]
            return agents
    except (FileNotFoundError, PermissionError):
        return []

def format_agent_line(ctx, agent_name):
    """Agent Teams teammate: single-line status"""
    parts = []

    # Agent name
    parts.append(f"{Colors.BRIGHT_MAGENTA}\U0001F916 {agent_name}{Colors.RESET}")

    # Model
    model_name = shorten_model_name(ctx['model'])
    parts.append(f"{Colors.BRIGHT_YELLOW}[{model_name}]{Colors.RESET}")

    # Messages
    if ctx['total_messages'] > 0:
        parts.append(f"{Colors.BRIGHT_CYAN}\U0001F4AC {ctx['total_messages']}{Colors.RESET}")

    # Compact percentage
    parts.append(f"{ctx['percentage']}%")

    # Cost
    if ctx['session_cost'] > 0:
        parts.append(f"\U0001F4B0 ${ctx['session_cost']:.2f}")

    return " | ".join(parts)

def format_output_full(ctx, terminal_width=None):
    """Full mode (>= 55 chars): 4行・全項目・装飾あり・グラフ幅可変

    Example (width >= 68):
    [Son4] | 🌿 main M2 | 📁 statusline | 💬 254 | 💰 $1.23
    Context: ████████▒▒▒▒▒▒▒ [58%] 91.8K/200.0K ♻️ 99%
    Session: █▇▁▁▂▄▁▁▁▁▁▁▁▁▁▁▁▁▁▁ 1h27m/5h, 40.3M token(462K t/m) (3am-8am)
    Weekly:  ████████████▒▒▒▒▒▒▒▒ [64%] 32m, Extra: 7% $3.59/$50

    Example (width 55-67):
    [Son4] | 🌿 main M2 | 📁 statusline
    Context: ████▒▒▒▒▒ [58%] 91.8K/200.0K ♻️ 99%
    Session: █▇▁▁▂▄▁▁▁ 1h27m/5h, 40.3M token (3am-8am)
    Weekly:  ████████▒▒ [64%] 32m, Extra: 7% $3.59/$50

    Args:
        ctx: コンテキスト辞書
        terminal_width: ターミナル幅（Noneの場合は自動取得）
    """
    lines = []

    # Line 1: Model/Git/Dir/Messages (with dynamic length adjustment)
    # Or schedule display if --schedule is enabled (time-based swap)
    if terminal_width is None:
        terminal_width = get_terminal_width()

    # Determine graph width: smoothly scale with terminal width
    # Non-graph content of longest line (L4 Weekly) is ~39 chars + ~4 margin,
    # so graph_width = terminal_width - 43, clamped to [8, 20]
    graph_width = min(20, max(8, terminal_width - 43))

    if ctx['show_line1']:
        # Check if we should show schedule line (swap every SCHEDULE_SWAP_INTERVAL seconds)
        show_schedule_now = False
        schedule_line = None
        if ctx.get('show_schedule'):
            # Time-based swap: 0-4s = normal, 5-9s = schedule
            is_schedule_turn = (int(time.time()) // SCHEDULE_SWAP_INTERVAL) % 2 == 1
            if is_schedule_turn:
                event = get_next_event()
                if event:
                    schedule_line = format_schedule_line(event, terminal_width)
                    if schedule_line:
                        show_schedule_now = True

        if show_schedule_now and schedule_line:
            lines.append(schedule_line)
        else:
            # Normal Line 1: progressive shrinking by priority
            #
            # 優先度（高→低）: モデル > ブランチ > git status > 💬メッセージ > 📁ディレクトリ > 💰コスト > +/-行数 > ⚠️エラー > 📝ファイル > (1M)バッジ
            #
            # 段階:
            #  1. 全要素（ブランチ15文字）
            #  2. 💰コスト・+/-行数・⚠️エラー削除
            #  3. 📝ファイル削除・モデル名短縮
            #  4. ブランチ12・ディレクトリ12に短縮
            #  5. ブランチ10・(1M)バッジ削除
            #  6. 💬メッセージ削除・ディレクトリ10
            #  7. 📁ディレクトリ削除（ブランチのほうが重要）
            #  8. セパレータ " | " → " "（compact風）
            shrink_steps = [
                # (separator, build_line1_parts kwargs)
                (" | ", dict(max_branch_len=15)),
                (" | ", dict(include_cost=False, include_lines=False, include_errors=False)),
                (" | ", dict(include_cost=False, include_lines=False, include_errors=False,
                             include_active_files=False, tight_model=True, max_branch_len=15)),
                (" | ", dict(include_cost=False, include_lines=False, include_errors=False,
                             include_active_files=False, tight_model=True,
                             max_branch_len=12, max_dir_len=12)),
                (" | ", dict(include_cost=False, include_lines=False, include_errors=False,
                             include_active_files=False, tight_model=True,
                             max_branch_len=10, max_dir_len=12, include_context_badge=False)),
                (" | ", dict(include_cost=False, include_lines=False, include_errors=False,
                             include_active_files=False, include_messages=False, tight_model=True,
                             max_branch_len=10, max_dir_len=10, include_context_badge=False)),
                (" | ", dict(include_cost=False, include_lines=False, include_errors=False,
                             include_active_files=False, include_messages=False, include_dir=False,
                             tight_model=True, max_branch_len=10, include_context_badge=False)),
                (" ",   dict(include_cost=False, include_lines=False, include_errors=False,
                             include_active_files=False, include_messages=False, include_dir=False,
                             tight_model=True, max_branch_len=8, include_context_badge=False)),
            ]
            for sep, kwargs in shrink_steps:
                line1_parts = build_line1_parts(ctx, **kwargs)
                line1 = sep.join(line1_parts)
                if get_display_width(line1) <= terminal_width:
                    break
            lines.append(line1)

    # Line 2: Compact tokens
    if ctx['show_line2']:
        line2_parts = []
        percentage = ctx['percentage']
        compact_display = format_token_count(ctx['compact_tokens'])
        percentage_color = get_percentage_color(percentage)

        if percentage >= 85:
            title_color = f"{Colors.BG_RED}{Colors.BRIGHT_WHITE}{Colors.BOLD}"
            percentage_display = f"{Colors.BG_RED}{Colors.BRIGHT_WHITE}{Colors.BOLD}[{percentage}%]{Colors.RESET}"
            compact_label = f"{title_color}Context:{Colors.RESET}"
        else:
            compact_label = f"{Colors.BRIGHT_CYAN}Context:{Colors.RESET}"
            percentage_display = f"{percentage_color}{Colors.BOLD}[{percentage}%]{Colors.RESET}"

        line2_parts.append(compact_label)
        line2_parts.append(get_progress_bar(percentage, width=graph_width))
        line2_parts.append(percentage_display)
        denom = ctx['context_size']
        line2_parts.append(f"{Colors.BRIGHT_WHITE}{compact_display}/{format_token_count(denom)}{Colors.RESET}")

        if ctx['cache_ratio'] >= 50:
            line2_parts.append(f"{Colors.BRIGHT_GREEN}♻️ {int(ctx['cache_ratio'])}% cached{Colors.RESET}")

        if ctx.get('exceeds_200k'):
            if ctx.get('context_size', 200000) > 200000:
                line2_parts.append(f"{Colors.BG_YELLOW}{Colors.BOLD} PREMIUM {Colors.RESET}")
            else:
                line2_parts.append(f"{Colors.BG_RED}{Colors.BRIGHT_WHITE} >200K {Colors.RESET}")

        lines.append(" ".join(line2_parts))

    # Line 3: Session (sparkline + 5h utilization + tokens + API time range)
    if ctx['show_line3'] and (ctx['session_duration'] or ctx.get('api_session_range')):
        line3_parts = []
        line3_parts.append(f"{Colors.BRIGHT_CYAN}Session:{Colors.RESET}")
        # Use burn sparkline instead of progress bar
        if ctx['burn_timeline']:
            sparkline = create_sparkline(ctx['burn_timeline'], width=graph_width)
            line3_parts.append(sparkline)
        else:
            line3_parts.append(get_progress_bar(ctx['block_progress'], width=graph_width, show_current_segment=True))
        # 5-hour utilization from API
        if ctx.get('five_hour_utilization') is not None:
            util = int(ctx['five_hour_utilization'])
            util_color = _get_utilization_color(util)
            line3_parts.append(f"{util_color}[{util}%]{Colors.RESET}")
        # Token count (without burn rate)
        if ctx['block_tokens'] > 0:
            tokens_display = format_token_count_short(ctx['block_tokens'])
            line3_parts.append(f"{Colors.BRIGHT_WHITE}{tokens_display} token{Colors.RESET}")
        # Time range from API
        if ctx.get('api_session_range'):
            start, end = ctx['api_session_range']
            line3_parts.append(f"{Colors.BRIGHT_GREEN}({start}-{end}){Colors.RESET}")
        lines.append(" ".join(line3_parts))

    # Line 4: Weekly usage
    if ctx['show_line4'] and ctx.get('weekly_line'):
        if graph_width != 20 and ctx.get('ratelimit_data'):
            # Regenerate weekly line with narrower graph width
            weekly_line = get_weekly_line(ctx['ratelimit_data'], ctx.get('weekly_timeline'),
                                         sparkline_width=graph_width)
            if weekly_line:
                lines.append(weekly_line)
            else:
                lines.append(ctx['weekly_line'])
        else:
            lines.append(ctx['weekly_line'])

    return lines

def format_output_compact(ctx):
    """Compact mode (35-54 chars): 4行・ラベル短縮・装飾削減

    Example:
    [Son4] main M2+1 statusline 💬254
    C: ████████▒▒▒ [58%] 91K/160K
    S: ███▒▒▒▒▒▒▒▒ [25%] 1h15m/5h
    B: ▁▂▃▄▅▆▇█▇▆▅ 14M
    """
    lines = []

    # Line 1: Shortened model/git/dir
    if ctx['show_line1']:
        line1_parts = []
        # Compact mode: use tight model name for space efficiency
        short_model = shorten_model_name(ctx['model'], tight=True)
        ctx_suffix = "(1M)" if ctx.get('context_size', 200000) > 200000 else ""
        line1_parts.append(f"{Colors.BRIGHT_YELLOW}[{short_model}{Colors.BRIGHT_MAGENTA}{ctx_suffix}{Colors.BRIGHT_YELLOW}]{Colors.RESET}")

        if ctx['git_branch']:
            branch = ctx['git_branch']
            # Compact mode: truncate long branch names
            if len(branch) > 10:
                branch = truncate_text(branch, 10)
            git_display = f"{Colors.BRIGHT_GREEN}{branch}"
            if ctx['modified_files'] > 0:
                git_display += f" M{ctx['modified_files']}"
            if ctx['untracked_files'] > 0:
                git_display += f"+{ctx['untracked_files']}"
            git_display += Colors.RESET
            line1_parts.append(git_display)

        line1_parts.append(f"{Colors.BRIGHT_CYAN}{ctx['current_dir']}{Colors.RESET}")

        if ctx['total_messages'] > 0:
            line1_parts.append(f"{Colors.BRIGHT_CYAN}💬{ctx['total_messages']}{Colors.RESET}")

        lines.append(" ".join(line1_parts))

    # Line 2: Compact tokens (shortened)
    if ctx['show_line2']:
        percentage = ctx['percentage']
        compact_display = format_token_count_short(ctx['compact_tokens'])
        denom = ctx['context_size']
        threshold_display = format_token_count_short(denom)
        percentage_color = get_percentage_color(percentage)

        line2 = f"{Colors.BRIGHT_CYAN}C:{Colors.RESET} {get_progress_bar(percentage, width=12)} "
        line2 += f"{percentage_color}[{percentage}%]{Colors.RESET} "
        line2 += f"{Colors.BRIGHT_WHITE}{compact_display}/{threshold_display}{Colors.RESET}"
        if ctx.get('exceeds_200k'):
            if ctx.get('context_size', 200000) > 200000:
                line2 += f" {Colors.BG_YELLOW}PRM{Colors.RESET}"
            else:
                line2 += f" {Colors.BG_RED}>200K{Colors.RESET}"
        lines.append(line2)

    # Line 3: Session (shortened with sparkline + utilization% + time range)
    if ctx['show_line3'] and (ctx['session_duration'] or ctx.get('api_session_range')):
        if ctx['burn_timeline']:
            sparkline = create_sparkline(ctx['burn_timeline'], width=12)
            line3 = f"{Colors.BRIGHT_CYAN}S:{Colors.RESET} {sparkline} "
        else:
            line3 = f"{Colors.BRIGHT_CYAN}S:{Colors.RESET} {get_progress_bar(ctx['block_progress'], width=12)} "
        if ctx.get('five_hour_utilization') is not None:
            util = int(ctx['five_hour_utilization'])
            util_color = _get_utilization_color(util)
            line3 += f"{util_color}[{util}%]{Colors.RESET}"
        if ctx.get('api_session_range'):
            start, end = ctx['api_session_range']
            line3 += f" {Colors.BRIGHT_GREEN}({start}-{end}){Colors.RESET}"
        lines.append(line3)

    # Line 4: Weekly (shortened with remaining time)
    if ctx['show_line4'] and ctx.get('weekly_line'):
        rl = ctx.get('ratelimit_data')
        if rl and rl.get('seven_day'):
            util = rl['seven_day'].get('utilization', 0)
            util_color = _get_utilization_color(util)
            wt = ctx.get('weekly_timeline')
            if wt and any(v > 0 for v in wt):
                spark = create_sparkline(wt, width=12)
                line4 = f"{Colors.BRIGHT_CYAN}W:{Colors.RESET} {spark} {util_color}[{int(util)}%]{Colors.RESET}"
            else:
                line4 = f"{Colors.BRIGHT_CYAN}W:{Colors.RESET} {get_progress_bar(util, width=12)} {util_color}[{int(util)}%]{Colors.RESET}"
            # Add remaining time (e.g. "6d10h07m")
            resets_at_str = rl['seven_day'].get('resets_at')
            if resets_at_str:
                try:
                    resets_at = datetime.fromisoformat(resets_at_str)
                    remaining_s = max(0, (resets_at - datetime.now(timezone.utc)).total_seconds())
                    if remaining_s < 3600:
                        line4 += f" {Colors.BRIGHT_WHITE}{int(remaining_s / 60)}m{Colors.RESET}"
                    elif remaining_s < 86400:
                        h = int(remaining_s / 3600)
                        m = int((remaining_s % 3600) / 60)
                        line4 += f" {Colors.BRIGHT_WHITE}{h}h{m:02d}m{Colors.RESET}"
                    else:
                        d = int(remaining_s / 86400)
                        h = int((remaining_s % 86400) / 3600)
                        m = int((remaining_s % 3600) / 60)
                        line4 += f" {Colors.BRIGHT_WHITE}{d}d{h}h{m:02d}m{Colors.RESET}"
                except (ValueError, TypeError):
                    pass
            lines.append(line4)

    return lines

def format_output_tight(ctx):
    """Tight mode (45-54 chars): 4行維持・さらに短縮

    Example:
    [Son4.5] main M1+5
    C: ████████ [58%] 91K
    S: ███░░░░░ [25%] 1h15m
    B: ▁▂▃▄▅▆▇█ 14M
    """
    lines = []

    # Line 1: Model, branch (ultra short)
    if ctx['show_line1']:
        line1_parts = []
        short_model = shorten_model_name(ctx['model'], tight=True)
        ctx_suffix = "(1M)" if ctx.get('context_size', 200000) > 200000 else ""
        line1_parts.append(f"{Colors.BRIGHT_YELLOW}[{short_model}{Colors.BRIGHT_MAGENTA}{ctx_suffix}{Colors.BRIGHT_YELLOW}]{Colors.RESET}")

        if ctx['git_branch']:
            branch = ctx['git_branch']
            # Tight mode: truncate long branch names more aggressively
            if len(branch) > 10:
                branch = truncate_text(branch, 10)
            git_display = f"{Colors.BRIGHT_GREEN}{branch}"
            if ctx['modified_files'] > 0 or ctx['untracked_files'] > 0:
                git_display += f" M{ctx['modified_files']}+{ctx['untracked_files']}"
            git_display += Colors.RESET
            line1_parts.append(git_display)

        lines.append(" ".join(line1_parts))

    # Line 2: Compact tokens (ultra short)
    if ctx['show_line2']:
        percentage = ctx['percentage']
        compact_display = format_token_count_short(ctx['compact_tokens'])
        percentage_color = get_percentage_color(percentage)

        line2 = f"{Colors.BRIGHT_CYAN}C:{Colors.RESET} {get_progress_bar(percentage, width=8)} "
        line2 += f"{percentage_color}[{percentage}%]{Colors.RESET} {Colors.BRIGHT_WHITE}{compact_display}{Colors.RESET}"
        if ctx.get('exceeds_200k'):
            if ctx.get('context_size', 200000) > 200000:
                line2 += f" {Colors.BG_YELLOW}PRM{Colors.RESET}"
            else:
                line2 += f" {Colors.BG_RED}>200K{Colors.RESET}"
        lines.append(line2)

    # Line 3: Session (ultra short with sparkline + utilization%)
    if ctx['show_line3'] and (ctx['session_duration'] or ctx.get('api_session_range')):
        if ctx['burn_timeline']:
            sparkline = create_sparkline(ctx['burn_timeline'], width=8)
            line3 = f"{Colors.BRIGHT_CYAN}S:{Colors.RESET} {sparkline} "
        else:
            line3 = f"{Colors.BRIGHT_CYAN}S:{Colors.RESET} {get_progress_bar(ctx['block_progress'], width=8)} "
        if ctx.get('five_hour_utilization') is not None:
            util = int(ctx['five_hour_utilization'])
            util_color = _get_utilization_color(util)
            line3 += f"{util_color}[{util}%]{Colors.RESET}"
        if ctx.get('api_session_range'):
            start, end = ctx['api_session_range']
            line3 += f" {Colors.BRIGHT_GREEN}({start}-{end}){Colors.RESET}"
        lines.append(line3)

    # Line 4: Weekly (ultra short with remaining time)
    if ctx['show_line4'] and ctx.get('weekly_line'):
        rl = ctx.get('ratelimit_data')
        if rl and rl.get('seven_day'):
            util = rl['seven_day'].get('utilization', 0)
            util_color = _get_utilization_color(util)
            wt = ctx.get('weekly_timeline')
            if wt and any(v > 0 for v in wt):
                spark = create_sparkline(wt, width=8)
                line4 = f"{Colors.BRIGHT_CYAN}W:{Colors.RESET} {spark} {util_color}[{int(util)}%]{Colors.RESET}"
            else:
                line4 = f"{Colors.BRIGHT_CYAN}W:{Colors.RESET} {get_progress_bar(util, width=8)} {util_color}[{int(util)}%]{Colors.RESET}"
            # Add remaining time (e.g. "6d10h07m")
            resets_at_str = rl['seven_day'].get('resets_at')
            if resets_at_str:
                try:
                    resets_at = datetime.fromisoformat(resets_at_str)
                    remaining_s = max(0, (resets_at - datetime.now(timezone.utc)).total_seconds())
                    if remaining_s < 3600:
                        line4 += f" {Colors.BRIGHT_WHITE}{int(remaining_s / 60)}m{Colors.RESET}"
                    elif remaining_s < 86400:
                        h = int(remaining_s / 3600)
                        m = int((remaining_s % 3600) / 60)
                        line4 += f" {Colors.BRIGHT_WHITE}{h}h{m:02d}m{Colors.RESET}"
                    else:
                        d = int(remaining_s / 86400)
                        h = int((remaining_s % 86400) / 3600)
                        m = int((remaining_s % 3600) / 60)
                        line4 += f" {Colors.BRIGHT_WHITE}{d}d{h}h{m:02d}m{Colors.RESET}"
                except (ValueError, TypeError):
                    pass
            lines.append(line4)

    return lines

def format_output_minimal(ctx, terminal_width):
    """Minimal 1-line mode for short terminal heights (<= 8 lines)

    Example:
    Cpt58% 91K/160K ♻99%
    """
    percentage = ctx['percentage']
    compact_display = format_token_count_short(ctx['compact_tokens'])
    denom = ctx['context_size']
    threshold_display = format_token_count_short(denom)
    percentage_color = get_percentage_color(percentage)

    parts = []
    if ctx.get('exceeds_200k'):
        if ctx.get('context_size', 200000) > 200000:
            parts.append(f"{Colors.BG_YELLOW}PRM{Colors.RESET}")
        else:
            parts.append(f"{Colors.BG_RED}{Colors.BRIGHT_WHITE}>200K{Colors.RESET}")
    parts.append(f"{percentage_color}Cpt{percentage}%{Colors.RESET}")
    parts.append(f"{Colors.BRIGHT_WHITE}{compact_display}/{threshold_display}{Colors.RESET}")

    line = " ".join(parts)

    # Add cache ratio if it fits
    if ctx['cache_ratio'] >= 50:
        cache_part = f" {Colors.BRIGHT_GREEN}\u267b{int(ctx['cache_ratio'])}%{Colors.RESET}"
        if get_display_width(line + cache_part) <= terminal_width:
            line += cache_part

    return [line]

def main():
    # Force line-buffered stdout to prevent partial output when piped to Claude Code
    # Without this, Python uses block buffering for pipes, causing intermittent display issues
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass  # Python < 3.7

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Claude Code statusline with configurable output', add_help=False)
    parser.add_argument('--show', type=str, help='Lines to show: 1,2,3,4 or all (default: use config settings)')
    parser.add_argument('--schedule', action='store_true', help='Show next calendar event (requires gog command)')
    parser.add_argument('--help', action='store_true', help='Show help')

    # Initialize args with default values first
    args = argparse.Namespace(show=None, schedule=False, help=False)

    # Parse arguments, but don't exit on failure (for stdin compatibility)
    try:
        args, _ = parser.parse_known_args()
    except:
        # Keep the default args initialized above
        pass
    
    # Handle help
    if args.help:
        print("statusline.py - Claude Code Status Line")
        print("Usage:")
        print("  echo '{\"session_id\":\"...\"}' | statusline.py")
        print("  echo '{\"session_id\":\"...\"}' | statusline.py --show 1,2")
        print("  echo '{\"session_id\":\"...\"}' | statusline.py --show simple")
        print("  echo '{\"session_id\":\"...\"}' | statusline.py --show all")
        print()
        print("Options:")
        print("  --show 1,2,3,4    Show specific lines (comma-separated)")
        print("  --show simple     Show compact and session lines (2,3)")
        print("  --show all        Show all lines")
        print("  --schedule        Show next calendar event (swaps with Line 1)")
        print("  --help            Show this help")
        return
    
    # Override display settings based on --show argument
    global SHOW_LINE1, SHOW_LINE2, SHOW_LINE3, SHOW_LINE4
    if args.show:
        # Reset all to False first
        SHOW_LINE1 = SHOW_LINE2 = SHOW_LINE3 = SHOW_LINE4 = False
        
        if args.show.lower() == 'all':
            SHOW_LINE1 = SHOW_LINE2 = SHOW_LINE3 = SHOW_LINE4 = True
        elif args.show.lower() == 'simple':
            SHOW_LINE2 = SHOW_LINE3 = True  # Show lines 2,3 (compact and session)
        else:
            # Parse comma-separated line numbers
            try:
                lines = [int(x.strip()) for x in args.show.split(',')]
                if 1 in lines: SHOW_LINE1 = True
                if 2 in lines: SHOW_LINE2 = True
                if 3 in lines: SHOW_LINE3 = True
                if 4 in lines: SHOW_LINE4 = True
            except ValueError:
                print("Error: Invalid --show format. Use: 1,2,3,4, simple, or all", file=sys.stderr)
                return

    # Agent name: resolved after JSON parse (API field > env var)
    agent_name = None

    try:
        # Read JSON from stdin
        input_data = sys.stdin.read()
        if not input_data.strip():
            # No input provided - just exit silently
            return
        data = json.loads(input_data)

        # ========================================
        # API DATA EXTRACTION (Claude Code stdin)
        # ========================================
        api_cost = data.get('cost', {})
        api_context = data.get('context_window', {})

        # API provided values (use these instead of manual calculation where possible)
        api_total_cost = api_cost.get('total_cost_usd', 0)
        api_input_tokens = api_context.get('total_input_tokens', 0)
        api_output_tokens = api_context.get('total_output_tokens', 0)
        api_context_size = api_context.get('context_window_size', 200000)

        # Lines changed (v2.1.6+ feature)
        api_lines_added = api_cost.get('total_lines_added', 0)
        api_lines_removed = api_cost.get('total_lines_removed', 0)

        # Session duration from API (fallback when block_stats unavailable)
        api_total_duration_ms = api_cost.get('total_duration_ms')

        # 200K token exceeded flag
        api_exceeds_200k = data.get('exceeds_200k_tokens', False)

        # Current usage cache details (fallback for cache ratio)
        api_current_usage = api_context.get('current_usage') or {}
        api_current_cache_creation = api_current_usage.get('cache_creation_input_tokens', 0)
        api_current_cache_read = api_current_usage.get('cache_read_input_tokens', 0)

        # Context window percentage (v2.1.6+ feature)
        # These are pre-calculated by Claude Code and more accurate than manual calculation
        api_used_percentage = api_context.get('used_percentage')  # v2.1.6+
        api_remaining_percentage = api_context.get('remaining_percentage')  # v2.1.6+

        # Dynamic compaction threshold (80% of context window)
        compaction_threshold = api_context_size * 0.8

        # Extract basic values
        model = data.get('model', {}).get('display_name', 'Unknown')
        model_id = data.get('model', {}).get('id', '')

        workspace = data.get('workspace', {})
        current_dir = os.path.basename(workspace.get('current_dir', data.get('cwd', '.')))
        session_id = data.get('session_id') or data.get('sessionId')

        # Agent name: API field > env var > None
        if not args.show:
            agent_name = data.get('agent', {}).get('name') or os.environ.get('CLAUDE_CODE_AGENT_NAME')
        
        # Get git info
        git_branch, modified_files, untracked_files = get_git_info(
            workspace.get('current_dir', data.get('cwd', '.'))
        )
        
        # Get token usage
        total_tokens = 0
        error_count = 0
        user_messages = 0
        assistant_messages = 0
        input_tokens = 0
        output_tokens = 0
        cache_creation = 0
        cache_read = 0
        
        # 5時間ブロック検出システム (cached: 30s TTL)
        block_stats = None
        current_block = None  # 初期化して変数スコープ問題を回避
        if session_id:
            try:
                block_stats, current_block = _get_cached_block_data(session_id)

                # 統計データを設定 - Compact用は現在セッションのみ
                # Compact line用: 現在セッションのトークンのみ（block_statsの有無に関わらず計算）
                # transcript_pathが提供されていればそれを使用、なければsession_idから探す
                transcript_path_str = data.get('transcript_path')
                if transcript_path_str:
                    transcript_file = Path(transcript_path_str)
                else:
                    transcript_file = find_session_transcript(session_id)

                if transcript_file and transcript_file.exists():
                    try:
                        (total_tokens, _, error_count, user_messages, assistant_messages,
                         input_tokens, output_tokens, cache_creation, cache_read) = calculate_tokens_from_transcript(transcript_file)
                    except Exception as e:
                        # Log error for debugging Compact freeze issue
                        with open(Path.home() / '.claude' / 'statusline-error.log', 'a') as f:
                            f.write(f"\n{datetime.now()}: Error calculating Compact tokens: {e}\n")
                            f.write(f"Transcript file: {transcript_file}\n")
                        # Use block_stats as fallback if available
                        if block_stats:
                            total_tokens = 0
                            user_messages = block_stats.get('user_messages', 0)
                            assistant_messages = block_stats.get('assistant_messages', 0)
                            error_count = block_stats.get('error_count', 0)
                        else:
                            total_tokens = 0
                else:
                    # フォールバック: block_statsがあればそれを使用
                    if block_stats:
                        total_tokens = 0
                        user_messages = block_stats.get('user_messages', 0)
                        assistant_messages = block_stats.get('assistant_messages', 0)
                        error_count = block_stats.get('error_count', 0)
                        input_tokens = 0
                        output_tokens = 0
                        cache_creation = 0
                        cache_read = 0
            except Exception:

                # フォールバック: 従来の単一ファイル方式
                # transcript_pathが提供されていればそれを使用、なければsession_idから探す
                transcript_path_str = data.get('transcript_path')
                if transcript_path_str:
                    transcript_file = Path(transcript_path_str)
                else:
                    transcript_file = find_session_transcript(session_id)

                if transcript_file and transcript_file.exists():
                    (total_tokens, _, error_count, user_messages, assistant_messages,
                     input_tokens, output_tokens, cache_creation, cache_read) = calculate_tokens_from_transcript(transcript_file)
        
        # Calculate percentage for Compact display (dynamic threshold)
        # Prefer API-provided percentage (v2.1.6+) for accuracy, fallback to manual calculation
        compact_tokens = total_tokens
        if api_used_percentage is not None:
            # Use Claude Code's pre-calculated percentage (more accurate)
            # This is relative to full context_window_size (200K or 1M)
            percentage = min(100, round(api_used_percentage))
            percentage_of_full_context = True
        else:
            # Fallback: manual calculation for older Claude Code versions
            # NOTE: API tokens (total_input/output_tokens) are CUMULATIVE session totals,
            # NOT current context window usage. Must use transcript-calculated tokens.
            # Use api_context_size (200K) as denominator to match api_used_percentage path
            percentage = min(100, round((compact_tokens / api_context_size) * 100))
            percentage_of_full_context = False
        
        # Get additional info
        active_files = len(workspace.get('active_files', []))
        task_status = data.get('task', {}).get('status', 'idle')
        current_time = get_time_info()
        # 5時間ブロック時間計算
        duration_seconds = None
        session_duration = None
        if block_stats:
            # ブロック統計から時間情報を取得
            duration_seconds = block_stats['duration_seconds']
        elif api_total_duration_ms is not None:
            # Fallback: API-provided total session duration
            duration_seconds = api_total_duration_ms / 1000.0

        if duration_seconds is not None:
            if duration_seconds < 60:
                session_duration = f"{int(duration_seconds)}s"
            elif duration_seconds < 3600:
                session_duration = f"{int(duration_seconds/60)}m"
            else:
                hours = int(duration_seconds/3600)
                minutes = int((duration_seconds % 3600) / 60)
                session_duration = f"{hours}h{minutes}m" if minutes > 0 else f"{hours}h"
        
        # Calculate cost - prefer API value, fallback to manual calculation
        if api_total_cost > 0:
            session_cost = api_total_cost
        else:
            # Fallback to manual calculation if API cost unavailable
            session_cost = calculate_cost(input_tokens, output_tokens, cache_creation, cache_read, model, model_id)
        
        # Format displays - use API tokens for Compact line
        token_display = format_token_count(compact_tokens)
        percentage_color = get_percentage_color(percentage)

        # ========================================
        # RESPONSIVE DISPLAY MODE SYSTEM
        # ========================================

        # Get terminal size (1 call, width and height together)
        terminal_width, terminal_height = get_terminal_size()
        display_mode = get_display_mode(terminal_width)

        # 環境変数で強制モード指定（テスト/デバッグ用）
        forced_mode = os.environ.get('STATUSLINE_DISPLAY_MODE')
        if forced_mode in ('full', 'compact', 'tight'):
            display_mode = forced_mode

        # 従来の環境変数（後方互換性）
        output_mode = os.environ.get('STATUSLINE_MODE', 'multi')
        if output_mode == 'single':
            display_mode = 'tight'

        # Calculate common values
        total_messages = user_messages + assistant_messages

        # Calculate cache ratio (with API current_usage fallback)
        cache_ratio = 0
        eff_cache_read = cache_read if cache_read > 0 else api_current_cache_read
        eff_cache_creation = cache_creation if cache_creation > 0 else api_current_cache_creation
        if eff_cache_read > 0 or eff_cache_creation > 0:
            all_tokens = compact_tokens + eff_cache_read + eff_cache_creation
            cache_ratio = (eff_cache_read / all_tokens * 100) if all_tokens > 0 else 0

        # Calculate block progress
        block_progress = 0
        if duration_seconds is not None:
            hours_elapsed = duration_seconds / 3600
            block_progress = (hours_elapsed % 5) / 5 * 100

        # Generate session time info
        session_time_info = ""
        if block_stats and duration_seconds is not None:
            try:
                start_time_utc = block_stats['start_time']
                start_time_local = convert_utc_to_local(start_time_utc)
                session_start_time = start_time_local.strftime("%H:%M")
                end_time_local = start_time_local + timedelta(hours=5)
                session_end_time = end_time_local.strftime("%H:%M")

                now_local = datetime.now()
                if now_local > end_time_local:
                    session_time_info = f"{Colors.BRIGHT_YELLOW}{current_time}{Colors.RESET} {Colors.BRIGHT_YELLOW}(ended at {session_end_time}){Colors.RESET}"
                else:
                    session_time_info = f"{Colors.BRIGHT_WHITE}{current_time}{Colors.RESET} {Colors.BRIGHT_GREEN}({session_start_time} to {session_end_time}){Colors.RESET}"
            except Exception:
                session_time_info = f"{Colors.BRIGHT_WHITE}{current_time}{Colors.RESET}"

        # Get ratelimit data first (needed for sparkline alignment and Weekly line)
        # Wrapped in try/except so failures don't crash the entire statusline
        ratelimit_data = None
        api_session_range = None
        weekly_line = None
        api_block_start_utc = None
        try:
            ratelimit_data = get_ratelimit_info() if SHOW_LINE4 or SHOW_LINE3 else None
            api_session_range = get_api_session_time_range(ratelimit_data) if ratelimit_data else None
            weekly_timeline = generate_weekly_timeline(ratelimit_data) if SHOW_LINE4 and ratelimit_data else None
            weekly_line = get_weekly_line(ratelimit_data, weekly_timeline) if SHOW_LINE4 and ratelimit_data else None
            # Derive API block start time (UTC, naive) for sparkline alignment
            if ratelimit_data and (ratelimit_data.get('five_hour') or {}).get('resets_at'):
                resets_at = datetime.fromisoformat(ratelimit_data['five_hour']['resets_at'])
                api_start = resets_at - timedelta(hours=5)
                api_block_start_utc = api_start.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            pass

        # Generate burn line and timeline for context
        # burn_timeline is needed by Line 3 (Session sparkline)
        burn_line = ""
        burn_timeline = []
        block_tokens = 0
        if (SHOW_LINE3 or SHOW_LINE4) and block_stats:
            session_data = {
                'total_tokens': block_stats['total_tokens'],
                'duration_seconds': duration_seconds if duration_seconds and duration_seconds > 0 else 1,
                'start_time': block_stats.get('start_time'),
                'efficiency_ratio': block_stats.get('efficiency_ratio', 0),
                'current_cost': session_cost
            }
            burn_line = get_burn_line(session_data, session_id, block_stats, current_block)
            burn_timeline = generate_real_burn_timeline(block_stats, current_block, api_block_start_utc)
            block_tokens = block_stats.get('total_tokens', 0)

        # Build context dictionary for formatters
        ctx = {
            'model': model,
            'git_branch': git_branch,
            'modified_files': modified_files,
            'untracked_files': untracked_files,
            'current_dir': current_dir,
            'active_files': active_files,
            'total_messages': total_messages,
            'lines_added': api_lines_added,
            'lines_removed': api_lines_removed,
            'error_count': error_count,
            'task_status': task_status,
            'session_cost': session_cost,
            'compact_tokens': compact_tokens,
            'compaction_threshold': compaction_threshold,
            'percentage': percentage,
            'cache_ratio': cache_ratio,
            'session_duration': session_duration,
            'block_progress': block_progress,
            'session_time_info': session_time_info,
            'burn_line': burn_line,
            'burn_timeline': burn_timeline,
            'block_tokens': block_tokens,
            'weekly_line': weekly_line,
            'weekly_timeline': weekly_timeline if SHOW_LINE4 else None,
            'ratelimit_data': ratelimit_data,
            'api_session_range': api_session_range,
            'five_hour_utilization': (ratelimit_data.get('five_hour') or {}).get('utilization') if ratelimit_data else None,
            'session_duration_seconds': duration_seconds,
            'show_line1': SHOW_LINE1,
            'show_line2': SHOW_LINE2,
            'show_line3': SHOW_LINE3,
            'show_line4': SHOW_LINE4,
            'show_schedule': SHOW_SCHEDULE or args.schedule,
            'exceeds_200k': api_exceeds_200k,
            'context_size': api_context_size,
            'percentage_of_full_context': percentage_of_full_context,
        }

        # Select formatter based on display mode and terminal height (with hysteresis)
        height_mode = get_height_mode(terminal_height)

        if agent_name:
            lines = [format_agent_line(ctx, agent_name)]
        elif not args.show and height_mode == 'minimal':
            # Short terminal: 1-line minimal mode
            lines = format_output_minimal(ctx, terminal_width)
        elif display_mode == 'full':
            lines = format_output_full(ctx, terminal_width)
        elif display_mode == 'compact':
            lines = format_output_compact(ctx)
        else:  # tight
            lines = format_output_tight(ctx)

        # Prepend dead agent warning if any
        dead_agents = get_dead_agents()
        if dead_agents and not agent_name:  # Don't show on agent panes themselves
            dead_names = ", ".join(dead_agents)
            warning = f"{Colors.BRIGHT_RED}\u26a0\ufe0f DEAD: {dead_names}{Colors.RESET}"
            lines.insert(0, warning)

        # Output lines (flush=True to avoid partial reads when piped to Claude Code)
        output = "\n".join(f"\033[0m\033[1;97m{line}\033[0m" for line in lines)
        sys.stdout.write(output + "\n")
        sys.stdout.flush()

    except Exception as e:
        # Fallback status line on error
        sys.stdout.write(f"{Colors.BRIGHT_RED}[Error]{Colors.RESET} . | 0 | 0%\n")
        sys.stdout.write(f"{Colors.LIGHT_GRAY}Check ~/.claude/statusline-error.log{Colors.RESET}\n")
        sys.stdout.flush()
        
        # Debug logging with traceback
        import traceback
        with open(Path.home() / '.claude' / 'statusline-error.log', 'a') as f:
            f.write(f"{datetime.now()}: {e}\n")
            f.write(traceback.format_exc() + "\n")
            f.write(f"Input data: {locals().get('input_data', 'No input')}\n\n")

def calculate_tokens_since_time(start_time, session_id):
    """📊 SESSION LINE SYSTEM: Calculate tokens for current session only
    
    Calculates tokens from session start time to now for the burn line display.
    This is SESSION scope, NOT block scope. Used for burn rate calculations.
    
    CRITICAL: This is for the Burn line, NOT the Compact line.
    
    Args:
        start_time: Session start time (from Session line display)
        session_id: Current session ID
    Returns:
        int: Session tokens for burn rate calculation
    """
    try:
        if not start_time or not session_id:
            return 0
        
        transcript_file = find_session_transcript(session_id)
        if not transcript_file:
            return 0
        
        # Normalize start_time to UTC for comparison
        start_time_utc = convert_local_to_utc(start_time)
        
        session_messages = []
        processed_hashes = set()  # For duplicate removal 
        
        with open(transcript_file, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if not data:
                        continue
                    
                    # Remove duplicates: messageId + requestId
                    message_id = data.get('message', {}).get('id')
                    request_id = data.get('requestId')
                    if message_id and request_id:
                        unique_hash = f"{message_id}:{request_id}"
                        if unique_hash in processed_hashes:
                            continue  # Skip duplicate
                        processed_hashes.add(unique_hash)
                    
                    # Get message timestamp
                    msg_timestamp = data.get('timestamp')
                    if not msg_timestamp:
                        continue
                    
                    # Parse timestamp and normalize to UTC
                    if isinstance(msg_timestamp, str):
                        msg_time = datetime.fromisoformat(msg_timestamp.replace('Z', '+00:00'))
                        if msg_time.tzinfo is None:
                            msg_time = msg_time.replace(tzinfo=timezone.utc)
                        msg_time_utc = msg_time.astimezone(timezone.utc)
                    else:
                        continue
                    
                    # Only include messages from session start time onwards
                    if msg_time_utc >= start_time_utc:
                        # Check for any messages with usage data (not just assistant)
                        if data.get('message', {}).get('usage'):
                            session_messages.append(data)
                
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
        
        # Sum all usage from session messages (each message is individual usage)
        total_input_tokens = 0
        total_output_tokens = 0
        total_cache_creation = 0
        total_cache_read = 0
        
        for message in session_messages:
            usage = message.get('message', {}).get('usage', {})
            if usage:
                total_input_tokens += usage.get('input_tokens', 0)
                total_output_tokens += usage.get('output_tokens', 0)
                total_cache_creation += usage.get('cache_creation_input_tokens', 0)
                total_cache_read += usage.get('cache_read_input_tokens', 0)
        
        #  nonCacheTokens for display (like burn rate indicator)
        non_cache_tokens = total_input_tokens + total_output_tokens
        cache_tokens = total_cache_creation + total_cache_read
        total_with_cache = non_cache_tokens + cache_tokens
        
        # Return cache-included tokens (like )
        return total_with_cache  #  cache tokens in display
        
    except Exception:
        return 0

# REMOVED: calculate_true_session_cumulative() - unused function (replaced by calculate_tokens_since_time)

# REMOVED: get_session_cumulative_usage() - unused function (5th line display not implemented)

# ============================================
# Ratelimit cache management (OAuth API)
# ============================================

def _get_block_stats_cache_file():
    """Get block stats cache file path (lazy initialization)"""
    global BLOCK_STATS_CACHE_FILE
    if BLOCK_STATS_CACHE_FILE is None:
        BLOCK_STATS_CACHE_FILE = Path.home() / '.claude' / '.block_stats_cache.json'
    return BLOCK_STATS_CACHE_FILE

def _get_transcript_stats_cache_file():
    """Get transcript stats cache file path (lazy initialization)"""
    global TRANSCRIPT_STATS_CACHE_FILE
    if TRANSCRIPT_STATS_CACHE_FILE is None:
        TRANSCRIPT_STATS_CACHE_FILE = Path.home() / '.claude' / '.transcript_stats_cache.json'
    return TRANSCRIPT_STATS_CACHE_FILE

def _serialize_datetime(dt):
    """Convert datetime to ISO string for JSON cache serialization."""
    if dt is None:
        return None
    if hasattr(dt, 'isoformat'):
        return dt.isoformat()
    return str(dt)

def _deserialize_datetime(s):
    """Convert ISO string back to datetime object."""
    if s is None:
        return None
    if isinstance(s, str):
        return datetime.fromisoformat(s)
    return s

def _get_cached_block_data(session_id):
    """Get block_stats and current_block from 30s file cache or by computing.

    On cache hit:  returns (block_stats, current_block) from disk (<1ms).
    On cache miss: runs full JSONL scan, saves result, returns data.
    Returns (None, None) on error.
    """
    # --- cache hit path ---
    cache_file = _get_block_stats_cache_file()
    try:
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                cached = json.load(f)
            if (time.time() - cached.get('timestamp', 0) < BLOCK_STATS_CACHE_TTL
                    and cached.get('session_id') == session_id):
                # Deserialize block_stats
                bs = cached.get('block_stats')
                if bs:
                    bs['start_time'] = _deserialize_datetime(bs.get('start_time'))
                # Deserialize current_block
                cb = cached.get('current_block')
                if cb:
                    cb['start_time'] = _deserialize_datetime(cb.get('start_time'))
                    cb['end_time'] = _deserialize_datetime(cb.get('end_time'))
                    cb['actual_end_time'] = _deserialize_datetime(cb.get('actual_end_time'))
                    for msg in cb.get('messages', []):
                        msg['timestamp'] = _deserialize_datetime(msg.get('timestamp'))
                return bs, cb
    except (json.JSONDecodeError, OSError):
        pass

    # --- cache miss path ---
    block_stats = None
    current_block = None
    try:
        all_messages = load_all_messages_chronologically()
        try:
            blocks = detect_five_hour_blocks(all_messages)
        except Exception:
            blocks = []
        current_block = find_current_session_block(blocks, session_id)
        if current_block:
            try:
                block_stats = calculate_block_statistics_with_deduplication(current_block, session_id)
            except Exception:
                block_stats = None
        elif blocks:
            active_blocks = [b for b in blocks if b.get('is_active', False)]
            if active_blocks:
                current_block = active_blocks[-1]
                try:
                    block_stats = calculate_block_statistics_with_deduplication(current_block, session_id)
                except Exception:
                    block_stats = None
    except Exception:
        return None, None

    # --- write cache ---
    if block_stats is not None or current_block is not None:
        try:
            cache_data = {
                'timestamp': time.time(),
                'session_id': session_id,
            }
            if block_stats:
                bs_copy = dict(block_stats)
                bs_copy['start_time'] = _serialize_datetime(bs_copy.get('start_time'))
                cache_data['block_stats'] = bs_copy
            if current_block:
                cb_ser = {
                    'start_time': _serialize_datetime(current_block.get('start_time')),
                    'end_time': _serialize_datetime(current_block.get('end_time')),
                    'actual_end_time': _serialize_datetime(current_block.get('actual_end_time')),
                    'duration_seconds': current_block.get('duration_seconds'),
                    'is_active': current_block.get('is_active'),
                    'messages': [],
                }
                for msg in current_block.get('messages', []):
                    cb_ser['messages'].append({
                        'timestamp': _serialize_datetime(msg.get('timestamp')),
                        'session_id': msg.get('session_id'),
                        'type': msg.get('type'),
                        'usage': msg.get('usage'),
                        'uuid': msg.get('uuid'),
                        'requestId': msg.get('requestId'),
                    })
                cache_data['current_block'] = cb_ser
            tmp = cache_file.with_suffix('.tmp')
            with open(tmp, 'w') as f:
                json.dump(cache_data, f)
            tmp.rename(cache_file)
        except (OSError, TypeError):
            pass

    return block_stats, current_block

def _load_transcript_stats_cache(file_path):
    """Load transcript stats from cache if valid (TTL + path + mtime match).
    Returns cached data dict or None on miss."""
    cache_file = _get_transcript_stats_cache_file()
    try:
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                cached = json.load(f)
            if (time.time() - cached.get('timestamp', 0) < TRANSCRIPT_STATS_CACHE_TTL
                    and cached.get('file_path') == str(file_path)
                    and cached.get('file_mtime') == file_path.stat().st_mtime):
                return cached
    except (json.JSONDecodeError, OSError):
        pass
    return None

def _save_transcript_stats_cache(file_path, stats_tuple):
    """Write transcript stats cache atomically."""
    cache_file = _get_transcript_stats_cache_file()
    (total_tokens, message_count, error_count, user_messages, assistant_messages,
     input_tokens, output_tokens, cache_creation, cache_read) = stats_tuple
    try:
        tmp = cache_file.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            json.dump({
                'timestamp': time.time(),
                'file_path': str(file_path),
                'file_mtime': file_path.stat().st_mtime,
                'total_tokens': total_tokens,
                'message_count': message_count,
                'error_count': error_count,
                'user_messages': user_messages,
                'assistant_messages': assistant_messages,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cache_creation': cache_creation,
                'cache_read': cache_read,
            }, f)
        tmp.rename(cache_file)
    except OSError:
        pass

def get_ratelimit_cache_file():
    """Get rate limit cache file path (lazy initialization)"""
    global RATELIMIT_CACHE_FILE
    if RATELIMIT_CACHE_FILE is None:
        RATELIMIT_CACHE_FILE = Path.home() / '.claude' / '.ratelimit_cache.json'
    return RATELIMIT_CACHE_FILE

def get_ratelimit_lock_file():
    """Get rate limit lock file path (lazy initialization)"""
    global RATELIMIT_LOCK_FILE
    if RATELIMIT_LOCK_FILE is None:
        RATELIMIT_LOCK_FILE = Path.home() / '.claude' / '.ratelimit_lock.json'
    return RATELIMIT_LOCK_FILE

def load_ratelimit_cache():
    """Load ratelimit cache from disk."""
    cache_file = get_ratelimit_cache_file()
    try:
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        pass
    return None

def _acquire_pid_lock():
    """Acquire PID lock for probe mutual exclusion."""
    lock_file = get_ratelimit_lock_file()
    try:
        if lock_file.exists():
            with open(lock_file) as f:
                lock_data = json.load(f)
            pid = lock_data.get('pid')
            start_time_val = lock_data.get('start_time', 0)
            # Check if process is still alive and lock is not stale (60s)
            if pid and time.time() - start_time_val < 60:
                try:
                    os.kill(pid, 0)
                    return False  # Process alive, lock held
                except OSError:
                    pass  # Process dead, steal lock
    except (json.JSONDecodeError, IOError, OSError):
        pass
    return True

def _write_pid_lock(pid):
    """Write PID to lock file."""
    lock_file = get_ratelimit_lock_file()
    try:
        with open(lock_file, 'w') as f:
            json.dump({'pid': pid, 'start_time': time.time()}, f)
    except (IOError, OSError):
        pass

def _release_pid_lock():
    """Release PID lock file."""
    lock_file = get_ratelimit_lock_file()
    try:
        lock_file.unlink()
    except (FileNotFoundError, OSError):
        pass

# ============================================
# OAuth token retrieval (cross-platform)
# ============================================

def _parse_keychain_content(content):
    """Parse keychain content: JSON format or raw token."""
    if content.startswith('{'):
        try:
            parsed = json.loads(content)
            token = parsed.get('claudeAiOauth', {}).get('accessToken')
            if token and token.startswith('sk-ant-oat'):
                return token
        except json.JSONDecodeError:
            pass
    if content.startswith('sk-ant-oat'):
        return content
    return None

def _get_oauth_token_macos():
    """macOS: Extract OAuth token from Keychain, including hash-suffixed service names."""
    try:
        result = subprocess.run(
            ['security', 'dump-keychain'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=5
        )
        service_names = []
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if 'Claude Code-credentials' in line:
                    m = re.search(r'"(Claude Code-credentials[^"]*)"', line)
                    if m:
                        service_names.append(m.group(1))
        service_names = sorted(set(service_names), key=len, reverse=True)
        if not service_names:
            service_names = ['Claude Code-credentials']
        for name in service_names:
            try:
                result = subprocess.run(
                    ['security', 'find-generic-password', '-s', name, '-w'],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    token = _parse_keychain_content(result.stdout.strip())
                    if token:
                        return token
            except (subprocess.TimeoutExpired, OSError):
                continue
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None

def _get_oauth_token_linux():
    """Linux: Extract OAuth token from GNOME Keyring via secret-tool."""
    try:
        result = subprocess.run(
            ['secret-tool', 'lookup', 'service', 'Claude Code'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            token = _parse_keychain_content(result.stdout.strip())
            if token:
                return token
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None

def _get_oauth_token_from_files():
    """Credential files fallback (all platforms)."""
    home = Path.home()
    paths = [
        home / '.claude' / '.credentials.json',
        home / '.claude' / 'credentials.json',
        home / '.config' / 'claude-code' / 'credentials.json',
    ]
    if os.name == 'nt':
        for env_var in ('APPDATA', 'LOCALAPPDATA'):
            d = os.environ.get(env_var)
            if d:
                paths.append(Path(d) / 'Claude Code' / 'credentials.json')
    for p in paths:
        try:
            if not p.exists():
                continue
            with open(p) as f:
                creds = json.load(f)
            token = creds.get('claudeAiOauth', {}).get('accessToken')
            if token and token.startswith('sk-ant-oat'):
                return token
            for key in ('oauth_token', 'token', 'accessToken'):
                token = creds.get(key)
                if token and isinstance(token, str) and token.startswith('sk-ant-oat'):
                    return token
        except (json.JSONDecodeError, IOError, OSError):
            continue
    return None

def _get_oauth_token():
    """Extract OAuth access token (cross-platform).
    Fallback chain: macOS Keychain -> Linux secret-tool -> credential files.
    """
    import platform
    system = platform.system()
    token = None
    if system == 'Darwin':
        token = _get_oauth_token_macos()
    elif system == 'Linux':
        token = _get_oauth_token_linux()
    if token and token.startswith('sk-ant-oat'):
        return token
    token = _get_oauth_token_from_files()
    if token and token.startswith('sk-ant-oat'):
        return token
    return None

# ============================================
# Background probe for OAuth usage API
# ============================================

def probe_ratelimit_background():
    """Launch background probe to fetch usage data from Anthropic OAuth API.
    Cross-platform: macOS Keychain, Linux secret-tool, credential files fallback.
    """
    if not _acquire_pid_lock():
        return

    try:
        cache_file = str(get_ratelimit_cache_file())
        lock_file = str(get_ratelimit_lock_file())

        probe_script = f'''
import json, sys, subprocess, os, time, tempfile, signal, platform, re
from pathlib import Path

def handler(signum, frame):
    sys.exit(1)

if hasattr(signal, 'SIGALRM'):
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(15)
else:
    import threading
    threading.Timer(15, lambda: os._exit(1)).start()

def parse_keychain_content(content):
    if content.startswith('{{'):
        try:
            parsed = json.loads(content)
            t = parsed.get('claudeAiOauth', {{}}).get('accessToken')
            if t and t.startswith('sk-ant-oat'):
                return t
        except json.JSONDecodeError:
            pass
    if content.startswith('sk-ant-oat'):
        return content
    return None

def get_token_macos():
    try:
        r = subprocess.run(['security', 'dump-keychain'],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, timeout=5)
        names = []
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if 'Claude Code-credentials' in line:
                    m = re.search(r'"(Claude Code-credentials[^"]*)"', line)
                    if m:
                        names.append(m.group(1))
        names = sorted(set(names), key=len, reverse=True)
        if not names:
            names = ['Claude Code-credentials']
        for name in names:
            try:
                r2 = subprocess.run(
                    ['security', 'find-generic-password', '-s', name, '-w'],
                    capture_output=True, text=True, timeout=5)
                if r2.returncode == 0 and r2.stdout.strip():
                    t = parse_keychain_content(r2.stdout.strip())
                    if t:
                        return t
            except (subprocess.TimeoutExpired, OSError):
                continue
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None

def get_token_linux():
    try:
        r = subprocess.run(
            ['secret-tool', 'lookup', 'service', 'Claude Code'],
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            t = parse_keychain_content(r.stdout.strip())
            if t:
                return t
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None

def get_token_from_files():
    home = Path.home()
    paths = [
        home / '.claude' / '.credentials.json',
        home / '.claude' / 'credentials.json',
        home / '.config' / 'claude-code' / 'credentials.json',
    ]
    if os.name == 'nt':
        for ev in ('APPDATA', 'LOCALAPPDATA'):
            d = os.environ.get(ev)
            if d:
                paths.append(Path(d) / 'Claude Code' / 'credentials.json')
    for p in paths:
        try:
            if not p.exists():
                continue
            with open(p) as f:
                creds = json.load(f)
            t = creds.get('claudeAiOauth', {{}}).get('accessToken')
            if t and t.startswith('sk-ant-oat'):
                return t
            for key in ('oauth_token', 'token', 'accessToken'):
                t = creds.get(key)
                if t and isinstance(t, str) and t.startswith('sk-ant-oat'):
                    return t
        except (json.JSONDecodeError, IOError, OSError):
            continue
    return None

def get_token():
    system = platform.system()
    token = None
    if system == 'Darwin':
        token = get_token_macos()
    elif system == 'Linux':
        token = get_token_linux()
    if token and token.startswith('sk-ant-oat'):
        return token
    token = get_token_from_files()
    if token and token.startswith('sk-ant-oat'):
        return token
    return None

try:
    token = get_token()
    if not token:
        sys.exit(1)

    result = subprocess.run(
        ['curl', '-s', '--max-time', '10',
         '-H', f'Authorization: Bearer {{token}}',
         '-H', 'anthropic-beta: oauth-2025-04-20',
         'https://api.anthropic.com/api/oauth/usage'],
        capture_output=True, text=True, timeout=15
    )

    if result.returncode != 0 or not result.stdout.strip():
        sys.exit(1)

    usage_data = json.loads(result.stdout.strip())

    cache = {{"timestamp": time.time(), "data": usage_data}}
    cache_dir = os.path.dirname("{cache_file}")
    fd, tmp = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cache, f)
        os.rename(tmp, "{cache_file}")
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
finally:
    try:
        os.unlink("{lock_file}")
    except (FileNotFoundError, OSError):
        pass
'''

        proc = subprocess.Popen(
            [sys.executable, '-c', probe_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        _write_pid_lock(proc.pid)

    except Exception:
        _release_pid_lock()

# ============================================
# Ratelimit data access + display helpers
# ============================================

def get_ratelimit_info():
    """Get rate limit info, triggering background probe if stale."""
    cache = load_ratelimit_cache()
    if cache:
        age = time.time() - cache.get('timestamp', 0)
        if age < RATELIMIT_CACHE_TTL:
            return cache.get('data')
        probe_ratelimit_background()
        return cache.get('data')
    probe_ratelimit_background()
    return None

def _get_utilization_color(pct):
    """Get color based on utilization percentage."""
    if pct >= 90:
        return f"{Colors.BG_RED}{Colors.BRIGHT_WHITE}"
    elif pct >= 75:
        return Colors.BRIGHT_RED
    elif pct >= 50:
        return Colors.BRIGHT_YELLOW
    return Colors.BRIGHT_GREEN

def get_api_session_time_range(ratelimit_data):
    """Extract 5-hour session time range from API data.
    Returns (start_local_str, end_local_str) like ('3am', '8am') or None.
    """
    if not ratelimit_data:
        return None
    five_hour = ratelimit_data.get('five_hour')
    if not five_hour or not five_hour.get('resets_at'):
        return None
    try:
        resets_at = datetime.fromisoformat(five_hour['resets_at'])
        end_local = resets_at.astimezone()  # Convert to local timezone
        start_local = end_local - timedelta(hours=5)

        def fmt_hour(dt):
            h = dt.hour
            suffix = 'am' if h < 12 else 'pm'
            h12 = h % 12 or 12
            if dt.minute == 0:
                return f"{h12}{suffix}"
            return f"{h12}:{dt.minute:02d}{suffix}"

        return (fmt_hour(start_local), fmt_hour(end_local))
    except (ValueError, TypeError):
        return None

WEEKLY_TIMELINE_CACHE_TTL = 300  # 5 minutes

def _get_weekly_timeline_cache_file():
    return Path.home() / '.claude' / '.weekly_timeline_cache.json'

def generate_weekly_timeline(ratelimit_data, num_segments=20):
    """Generate timeline of token consumption across the 7-day window.

    Uses resets_at from the API to determine the window, then scans JSONL transcripts
    for token usage in each segment. 20 segments across 7 days (~8.4h each) to match
    Session sparkline width.

    Results are cached with a 5-minute TTL to avoid slow 7-day transcript scans.

    Returns:
        list: num_segments values representing token consumption per segment (oldest to newest)
    """
    empty = [0] * num_segments

    seven_day = ratelimit_data.get('seven_day') if ratelimit_data else None
    if not seven_day or not seven_day.get('resets_at'):
        return empty

    # Check cache first
    cache_file = _get_weekly_timeline_cache_file()
    try:
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                cached = json.load(f)
            if time.time() - cached.get('timestamp', 0) < WEEKLY_TIMELINE_CACHE_TTL:
                tl = cached.get('timeline', empty)
                if len(tl) == num_segments:
                    return tl
    except (json.JSONDecodeError, OSError):
        pass

    # Generate fresh timeline
    timeline = _scan_weekly_timeline(seven_day['resets_at'], num_segments)

    # Write cache (atomic)
    try:
        tmp = cache_file.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            json.dump({'timestamp': time.time(), 'timeline': timeline}, f)
        tmp.rename(cache_file)
    except OSError:
        pass

    return timeline

def _scan_weekly_timeline(resets_at_str, num_segments):
    """Scan JSONL transcripts and build token timeline for the 7-day window."""
    timeline = [0] * num_segments
    total_seconds = 7 * 86400
    seg_seconds = total_seconds / num_segments

    try:
        resets_at = datetime.fromisoformat(resets_at_str)
        window_start = resets_at - timedelta(days=7)
        window_start_utc = window_start.astimezone(timezone.utc).replace(tzinfo=None)

        transcript_files = find_all_transcript_files(hours_limit=168)
        processed_hashes = set()

        for transcript_file in transcript_files:
            try:
                with open(transcript_file, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            if not entry.get('timestamp'):
                                continue

                            entry_type = entry.get('type')
                            usage = None
                            if entry_type == 'assistant':
                                msg = entry.get('message', {})
                                usage = msg.get('usage') if msg else entry.get('usage')
                            if not usage:
                                continue

                            msg_id = entry.get('uuid') or (entry.get('message', {}) or {}).get('id')
                            req_id = entry.get('requestId')
                            if msg_id and req_id:
                                h = f"{msg_id}:{req_id}"
                                if h in processed_hashes:
                                    continue
                                processed_hashes.add(h)

                            ts = datetime.fromisoformat(
                                entry['timestamp'].replace('Z', '+00:00')
                            ).astimezone(timezone.utc).replace(tzinfo=None)

                            if ts < window_start_utc:
                                continue

                            elapsed = (ts - window_start_utc).total_seconds()
                            seg = min(num_segments - 1, int(elapsed / seg_seconds))

                            tokens = usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
                            timeline[seg] += tokens

                        except (json.JSONDecodeError, ValueError, KeyError):
                            continue
            except (FileNotFoundError, PermissionError):
                continue

    except (ValueError, TypeError):
        pass

    return timeline

def get_weekly_line(ratelimit_data, weekly_timeline=None, sparkline_width=20):
    """Generate Weekly line display (Line 4).
    Format: Weekly:  ▁▂▃▅▆▇█▃ [64%] 32m, Extra: 7% $3.59/$50

    Args:
        ratelimit_data: Rate limit data dict
        weekly_timeline: Weekly timeline data for sparkline
        sparkline_width: Width of sparkline/progress bar (default: 20)
    """
    if not ratelimit_data:
        return None

    seven_day = ratelimit_data.get('seven_day')
    if not seven_day:
        return None

    utilization = seven_day.get('utilization', 0)
    util_color = _get_utilization_color(utilization)

    parts = []
    parts.append(f"{Colors.BRIGHT_CYAN}Weekly:  {Colors.RESET}")
    if weekly_timeline and any(v > 0 for v in weekly_timeline):
        parts.append(create_sparkline(weekly_timeline, width=sparkline_width))
    else:
        parts.append(get_progress_bar(utilization, width=sparkline_width))
    parts.append(f" {util_color}[{int(utilization)}%]{Colors.RESET}")

    # Time remaining until reset
    resets_at_str = seven_day.get('resets_at')
    if resets_at_str:
        try:
            resets_at = datetime.fromisoformat(resets_at_str)
            now = datetime.now(timezone.utc)
            remaining = resets_at - now
            remaining_seconds = max(0, remaining.total_seconds())
            if remaining_seconds < 3600:
                parts.append(f" {Colors.BRIGHT_WHITE}{int(remaining_seconds / 60)}m{Colors.RESET}")
            elif remaining_seconds < 86400:
                hours = int(remaining_seconds / 3600)
                mins = int((remaining_seconds % 3600) / 60)
                parts.append(f" {Colors.BRIGHT_WHITE}{hours}h{mins:02d}m{Colors.RESET}")
            else:
                days = int(remaining_seconds / 86400)
                hours = int((remaining_seconds % 86400) / 3600)
                mins = int((remaining_seconds % 3600) / 60)
                parts.append(f" {Colors.BRIGHT_WHITE}{days}d{hours}h{mins:02d}m{Colors.RESET}")
        except (ValueError, TypeError):
            pass

    # Extra usage info
    extra = ratelimit_data.get('extra_usage')
    if extra and extra.get('is_enabled'):
        extra_pct = extra.get('utilization', 0)
        used = extra.get('used_credits', 0)
        limit = extra.get('monthly_limit', 0)
        # Credits are in cents - convert to dollars
        used_str = f"${used / 100:.2f}" if used >= 100 else f"${used:.2f}"
        limit_str = f"${limit / 100:.0f}" if limit >= 100 else f"${limit:.0f}"
        parts.append(f", {Colors.BRIGHT_YELLOW}Ext:{Colors.RESET}")
        parts.append(f" {Colors.BRIGHT_WHITE}{used_str}/{limit_str}{Colors.RESET}")

    return "".join(parts)

def get_burn_line(current_session_data=None, session_id=None, block_stats=None, current_block=None):
    """Generate burn line display (Line 4)

    Creates the Burn line showing session tokens and burn rate.
    Uses 5-hour block timeline data with 15-minute intervals (20 segments).

    Format: "Burn: 14.0M (Rate: 321.1K t/m) [sparkline]"
    
    Args:
        current_session_data: Session data with session tokens
        session_id: Current session ID for sparkline data
        block_stats: Block statistics with burn_timeline data
    Returns:
        str: Formatted burn line for display
    """
    try:
        # Calculate burn rate
        burn_rate = 0
        if current_session_data:
            recent_tokens = current_session_data.get('total_tokens', 0)
            duration = current_session_data.get('duration_seconds', 0)
            if duration > 0:
                burn_rate = (recent_tokens / duration) * 60
        
        
        # 📊 BURN LINE TOKENS: 5-hour window total (from block_stats)
        # ===========================================================
        # 
        # Use 5-hour window total from block statistics
        # This should be ~21M tokens as expected
        #
        block_total_tokens = block_stats.get('total_tokens', 0) if block_stats else 0
        
        # Format session tokens for display (short format for Burn line)
        tokens_formatted = format_token_count_short(block_total_tokens)
        burn_rate_formatted = format_token_count_short(int(burn_rate))
        
        # Generate 5-hour timeline sparkline from REAL message data ONLY
        if block_stats and 'start_time' in block_stats and current_block:
            burn_timeline = generate_real_burn_timeline(block_stats, current_block)
        else:
            burn_timeline = [0] * 20
        
        sparkline = create_sparkline(burn_timeline, width=20)
        
        return (f"{Colors.BRIGHT_CYAN}Burn:   {Colors.RESET} {sparkline} "
                f"{Colors.BRIGHT_WHITE}{tokens_formatted} token(w/cache){Colors.RESET}, Rate: {burn_rate_formatted} t/m")

    except Exception:
        return f"{Colors.BRIGHT_CYAN}Burn:   {Colors.RESET} {Colors.BRIGHT_WHITE}ERROR{Colors.RESET}"
if __name__ == "__main__":
    main()