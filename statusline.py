#!/usr/bin/env python3

# ============================================
# 📝 CONFIGURATION - Edit these values
# ============================================

# Display settings (True = show, False = hide)
SHOW_LINE1    = True   # [Sonnet 4] | 🌿 main M2 | 📁 project | 💬 254
SHOW_LINE2    = True   # Compact: 91.8K/160.0K ████████▒▒▒ 58%
SHOW_LINE3    = True   # Session: 1h15m/5h ███▒▒▒▒▒▒▒▒ 25%
SHOW_LINE4    = True   # Burn: 14.0M ▁▂▃▄▅▆▇█▇▆▅▄▃▂▁
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
from datetime import datetime, timedelta, timezone, date
import time
from collections import defaultdict

# CONSTANTS

# Token compaction threshold - FALLBACK VALUE ONLY
# Dynamic value is now calculated from API: context_window_size * 0.8
# This constant is kept for backwards compatibility if API data is unavailable
COMPACTION_THRESHOLD = 200000 * 0.8  # 80% of 200K tokens (fallback)

# TWO DISTINCT TOKEN CALCULATION SYSTEMS

# This application uses TWO completely separate token calculation systems:

# 🗜️ COMPACT LINE SYSTEM (Conversation Compaction)
# ==============================================
# Purpose: Tracks current conversation progress toward compaction threshold
# Data Source: Current conversation tokens (until 160K compaction limit)
# Scope: Single conversation, monitors compression timing
# Calculation: block_stats['total_tokens'] from detect_five_hour_blocks()
# Display: Compact line (Line 2) - "118.1K/160.0K ████████▒▒▒▒ 74%"
# Range: 0-200K tokens (until conversation gets compressed)
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

def get_terminal_width():
    """ターミナル幅を取得（安全なフォールバック付き）

    優先順位:
    1. COLUMNS環境変数（明示的指定）
    2. tmux pane幅（tmux環境の場合）
    3. tput cols（TTY不要）
    4. shutil.get_terminal_size()（TTY必要）
    5. デフォルト80

    Returns:
        int: ターミナル幅（右端1文字問題対策で-1）
    """
    try:
        # 1. 環境変数COLUMNSを最優先（テスト用・明示的指定）
        if 'COLUMNS' in os.environ:
            try:
                return int(os.environ['COLUMNS']) - 1
            except ValueError:
                pass

        # 2. tmux環境の場合、pane幅を取得
        if 'TMUX' in os.environ:
            try:
                result = subprocess.run(
                    ['tmux', 'display-message', '-p', '#{pane_width}'],
                    capture_output=True, text=True, timeout=1
                )
                if result.returncode == 0 and result.stdout.strip().isdigit():
                    return int(result.stdout.strip()) - 1
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

        # 3. tput cols（TTY不要、$TERMから取得）
        try:
            result = subprocess.run(
                ['tput', 'cols'],
                capture_output=True, text=True, timeout=1
            )
            if result.returncode == 0 and result.stdout.strip().isdigit():
                return int(result.stdout.strip()) - 1
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        # 4. shutil.get_terminal_size()（TTY必要）
        if sys.stdout.isatty():
            size = shutil.get_terminal_size()
            if size.columns > 0:
                return size.columns - 1

    except (OSError, AttributeError):
        pass

    return 80  # デフォルト

def get_display_mode(width):
    """ターミナル幅からモードを決定

    | モード | 幅 | 最長行 | 表示内容 |
    |--------|-----|--------|---------|
    | full | >= 68 | 66文字 | 4行・全項目・装飾あり |
    | compact | 35-67 | 30文字 | 4行・ラベル短縮・装飾削減 |
    | tight | < 35 | 23文字 | 4行・最短表示 |

    Args:
        width: ターミナル幅
    Returns:
        str: 'full', 'compact', or 'tight'
    """
    if width >= 68:
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
        return '\033[1;91m'  # 元の赤色
    elif percentage >= 70:
        return Colors.BRIGHT_YELLOW
    return Colors.BRIGHT_GREEN

def calculate_dynamic_padding(compact_text, session_text):
    """Calculate dynamic padding to align progress bars
    
    Args:
        compact_text: Text part of compact line (e.g., "Compact: 111.6K/160.0K")
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
    """Create a visual progress bar with optional current segment highlighting"""
    filled = int(width * percentage / 100)
    empty = width - filled
    
    color = get_percentage_color(percentage)
    
    if show_current_segment and filled < width:
        # 完了済みは元の色を保持、現在進行中のセグメントのみ特別表示
        completed_bar = color + '█' * filled if filled > 0 else ''
        current_bar = Colors.BRIGHT_WHITE + '▓' + Colors.RESET  # 白く点滅風
        remaining_bar = Colors.LIGHT_GRAY + '▒' * (empty - 1) + Colors.RESET if empty > 1 else ''
        
        bar = completed_bar + current_bar + remaining_bar
    else:
        # 従来の表示
        bar = color + '█' * filled + Colors.LIGHT_GRAY + '▒' * empty + Colors.RESET
    
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
    
    return (total_tokens, message_count, error_count, user_messages, assistant_messages,
            total_input_tokens, total_output_tokens, total_cache_creation, total_cache_read)

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

def generate_real_burn_timeline(block_stats, current_block):
    """実際のメッセージデータからBurnスパークラインを生成（5時間ウィンドウ全体対応）
    
    CRITICAL: Uses REAL message timing data ONLY. NO fake patterns allowed.
    Distributes tokens based on actual message timestamps across 15-minute segments.
    """
    timeline = [0] * 20  # 20セグメント（各15分）
    
    if not block_stats or not current_block or 'messages' not in current_block:
        return timeline
    
    try:
        block_start = block_stats['start_time']
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)  # UTC統一
        
        # 内部処理は全てUTCで統一
        if hasattr(block_start, 'tzinfo') and block_start.tzinfo:
            block_start_utc = block_start.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            block_start_utc = block_start  # 既にUTC前提
        
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
    
    except Exception as e:
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

def calculate_cost(input_tokens, output_tokens, cache_creation, cache_read, model_name="Unknown"):
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
    
    # モデル名からタイプを判定
    model_lower = model_name.lower()
    
    if "haiku" in model_lower:
        # Claude 3.5 Haiku pricing (legacy)
        input_rate = 1.00
        output_rate = 5.00
        cache_write_rate = 1.25
        cache_read_rate = 0.10
    elif "sonnet" in model_lower:
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
                      include_lines=True, include_errors=True, include_cost=True):
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

    Returns:
        list: Line 1のパーツのリスト
    """
    parts = []

    # Model (always shortened)
    model_name = shorten_model_name(ctx['model'])
    parts.append(f"{Colors.BRIGHT_YELLOW}[{model_name}]{Colors.RESET}")

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

def format_output_full(ctx, terminal_width=None):
    """Full mode (>= 68 chars): 4行・全項目・装飾あり

    Example:
    [Son4] | 🌿 main M2 | 📁 statusline | 💬 254 | 💰 $1.23
    Compact: ████████▒▒▒▒▒▒▒ [58%] 91.8K/160.0K ♻️ 99%
    Session: ███▒▒▒▒▒▒▒▒▒▒▒▒ [25%] 1h15m/5h (08:00-13:00)
    Burn:    ▁▂▃▄▅▆▇█▇▆▅▄▃▂▁ 14.0M tok

    Args:
        ctx: コンテキスト辞書
        terminal_width: ターミナル幅（Noneの場合は自動取得）
    """
    lines = []

    # Line 1: Model/Git/Dir/Messages (with dynamic length adjustment)
    # Or schedule display if --schedule is enabled (time-based swap)
    if ctx['show_line1']:
        if terminal_width is None:
            terminal_width = get_terminal_width()

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
            # Normal Line 1: Model/Git/Dir/Messages
            # Step 1: 全要素で構築
            line1_parts = build_line1_parts(ctx)
            line1 = " | ".join(line1_parts)

            if get_display_width(line1) <= terminal_width:
                lines.append(line1)
            else:
                # Step 2: 低優先度要素を削除（コスト、行変更、エラー）
                line1_parts = build_line1_parts(ctx, include_cost=False, include_lines=False,
                                                include_errors=False)
                line1 = " | ".join(line1_parts)

                if get_display_width(line1) <= terminal_width:
                    lines.append(line1)
                else:
                    # Step 3: アクティブファイルも削除
                    line1_parts = build_line1_parts(ctx, include_cost=False, include_lines=False,
                                                    include_errors=False, include_active_files=False)
                    line1 = " | ".join(line1_parts)

                    if get_display_width(line1) <= terminal_width:
                        lines.append(line1)
                    else:
                        # Step 4: ディレクトリ名を短縮
                        line1_parts = build_line1_parts(ctx, include_cost=False, include_lines=False,
                                                        include_errors=False, include_active_files=False,
                                                        max_dir_len=12)
                        line1 = " | ".join(line1_parts)

                        if get_display_width(line1) <= terminal_width:
                            lines.append(line1)
                        else:
                            # Step 5: ブランチ名をさらに短縮
                            line1_parts = build_line1_parts(ctx, include_cost=False, include_lines=False,
                                                            include_errors=False, include_active_files=False,
                                                            max_branch_len=12, max_dir_len=12)
                            line1 = " | ".join(line1_parts)

                            if get_display_width(line1) <= terminal_width:
                                lines.append(line1)
                            else:
                                # Step 6: メッセージも削除、最小構成
                                line1_parts = build_line1_parts(ctx, include_cost=False, include_lines=False,
                                                                include_errors=False, include_active_files=False,
                                                                include_messages=False,
                                                                max_branch_len=10, max_dir_len=10)
                                lines.append(" | ".join(line1_parts))

    # Line 2: Compact tokens
    if ctx['show_line2']:
        line2_parts = []
        percentage = ctx['percentage']
        compact_display = format_token_count(ctx['compact_tokens'])
        percentage_color = get_percentage_color(percentage)

        if percentage >= 85:
            title_color = f"{Colors.BG_RED}{Colors.BRIGHT_WHITE}{Colors.BOLD}"
            percentage_display = f"{Colors.BG_RED}{Colors.BRIGHT_WHITE}{Colors.BOLD}[{percentage}%]{Colors.RESET}"
            compact_label = f"{title_color}Compact:{Colors.RESET}"
        else:
            compact_label = f"{Colors.BRIGHT_CYAN}Compact:{Colors.RESET}"
            percentage_display = f"{percentage_color}{Colors.BOLD}[{percentage}%]{Colors.RESET}"

        line2_parts.append(compact_label)
        line2_parts.append(get_progress_bar(percentage, width=20))
        line2_parts.append(percentage_display)
        line2_parts.append(f"{Colors.BRIGHT_WHITE}{compact_display}/{format_token_count(ctx['compaction_threshold'])}{Colors.RESET}")

        if ctx['cache_ratio'] >= 50:
            line2_parts.append(f"{Colors.BRIGHT_GREEN}♻️ {int(ctx['cache_ratio'])}% cached{Colors.RESET}")

        lines.append(" ".join(line2_parts))

    # Line 3: Session time
    if ctx['show_line3'] and ctx['session_duration']:
        line3_parts = []
        line3_parts.append(f"{Colors.BRIGHT_CYAN}Session:{Colors.RESET}")
        line3_parts.append(get_progress_bar(ctx['block_progress'], width=20, show_current_segment=True))
        line3_parts.append(f"{Colors.BRIGHT_WHITE}[{int(ctx['block_progress'])}%]{Colors.RESET}")
        line3_parts.append(f"{Colors.BRIGHT_WHITE}{ctx['session_duration']}/5h{Colors.RESET}")

        if ctx['session_time_info']:
            line3_parts.append(ctx['session_time_info'])

        lines.append(" ".join(line3_parts))

    # Line 4: Burn rate
    if ctx['show_line4'] and ctx['burn_line']:
        lines.append(ctx['burn_line'])

    return lines

def format_output_compact(ctx):
    """Compact mode (55-71 chars): 4行・ラベル短縮・装飾削減

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
        short_model = shorten_model_name(ctx['model'])
        line1_parts.append(f"{Colors.BRIGHT_YELLOW}[{short_model}]{Colors.RESET}")

        if ctx['git_branch']:
            git_display = f"{Colors.BRIGHT_GREEN}{ctx['git_branch']}"
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
        threshold_display = format_token_count_short(ctx['compaction_threshold'])
        percentage_color = get_percentage_color(percentage)

        line2 = f"{Colors.BRIGHT_CYAN}C:{Colors.RESET} {get_progress_bar(percentage, width=12)} "
        line2 += f"{percentage_color}[{percentage}%]{Colors.RESET} "
        line2 += f"{Colors.BRIGHT_WHITE}{compact_display}/{threshold_display}{Colors.RESET}"
        lines.append(line2)

    # Line 3: Session (shortened)
    if ctx['show_line3'] and ctx['session_duration']:
        line3 = f"{Colors.BRIGHT_CYAN}S:{Colors.RESET} {get_progress_bar(ctx['block_progress'], width=12)} "
        line3 += f"{Colors.BRIGHT_WHITE}[{int(ctx['block_progress'])}%]{Colors.RESET} "
        line3 += f"{Colors.BRIGHT_WHITE}{ctx['session_duration']}/5h{Colors.RESET}"
        lines.append(line3)

    # Line 4: Burn (shortened)
    if ctx['show_line4'] and ctx['burn_timeline']:
        sparkline = create_sparkline(ctx['burn_timeline'], width=12)
        tokens_display = format_token_count_short(ctx['block_tokens'])
        line4 = f"{Colors.BRIGHT_CYAN}B:{Colors.RESET} {sparkline} {Colors.BRIGHT_WHITE}{tokens_display}{Colors.RESET}"
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
        line1_parts.append(f"{Colors.BRIGHT_YELLOW}[{short_model}]{Colors.RESET}")

        if ctx['git_branch']:
            git_display = f"{Colors.BRIGHT_GREEN}{ctx['git_branch']}"
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
        lines.append(line2)

    # Line 3: Session (ultra short)
    if ctx['show_line3'] and ctx['session_duration']:
        line3 = f"{Colors.BRIGHT_CYAN}S:{Colors.RESET} {get_progress_bar(ctx['block_progress'], width=8)} "
        line3 += f"{Colors.BRIGHT_WHITE}[{int(ctx['block_progress'])}%]{Colors.RESET} {Colors.BRIGHT_WHITE}{ctx['session_duration']}{Colors.RESET}"
        lines.append(line3)

    # Line 4: Burn (ultra short)
    if ctx['show_line4'] and ctx['burn_timeline']:
        sparkline = create_sparkline(ctx['burn_timeline'], width=8)
        tokens_display = format_token_count_short(ctx['block_tokens'])
        line4 = f"{Colors.BRIGHT_CYAN}B:{Colors.RESET} {sparkline} {Colors.BRIGHT_WHITE}{tokens_display}{Colors.RESET}"
        lines.append(line4)

    return lines

def main():
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

        # Context window percentage (v2.1.6+ feature)
        # These are pre-calculated by Claude Code and more accurate than manual calculation
        api_used_percentage = api_context.get('used_percentage')  # v2.1.6+
        api_remaining_percentage = api_context.get('remaining_percentage')  # v2.1.6+

        # Dynamic compaction threshold (80% of context window)
        compaction_threshold = api_context_size * 0.8

        # Extract basic values
        model = data.get('model', {}).get('display_name', 'Unknown')
        
        workspace = data.get('workspace', {})
        current_dir = os.path.basename(workspace.get('current_dir', data.get('cwd', '.')))
        session_id = data.get('session_id') or data.get('sessionId')
        
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
        
        # 5時間ブロック検出システム
        block_stats = None
        current_block = None  # 初期化して変数スコープ問題を回避
        if session_id:
            try:
                # 全メッセージを時系列で読み込み
                all_messages = load_all_messages_chronologically()
                
                # 5時間ブロックを検出
                try:
                    blocks = detect_five_hour_blocks(all_messages)
                except Exception:
                    blocks = []
                
                # 現在のセッションが含まれるブロックを特定
                current_block = find_current_session_block(blocks, session_id)
                
                if current_block:
                    # ブロック全体の統計を計算
                    try:
                        block_stats = calculate_block_statistics_with_deduplication(current_block, session_id)
                    except Exception:
                        block_stats = None
                elif blocks:
                    # セッションが見つからない場合は最新のアクティブブロックを使用
                    active_blocks = [b for b in blocks if b.get('is_active', False)]
                    if active_blocks:
                        current_block = active_blocks[-1]  # 最新のアクティブブロック
                        try:
                            block_stats = calculate_block_statistics_with_deduplication(current_block, session_id)
                        except Exception:
                            block_stats = None
                
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
            except Exception as e:

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
            percentage = min(100, round(api_used_percentage))
        else:
            # Fallback: manual calculation for older Claude Code versions
            # NOTE: API tokens (total_input/output_tokens) are CUMULATIVE session totals,
            # NOT current context window usage. Must use transcript-calculated tokens.
            percentage = min(100, round((compact_tokens / compaction_threshold) * 100))
        
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
            
            # フォーマット済み文字列
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
            session_cost = calculate_cost(input_tokens, output_tokens, cache_creation, cache_read, model)
        
        # Format displays - use API tokens for Compact line
        token_display = format_token_count(compact_tokens)
        percentage_color = get_percentage_color(percentage)

        # ========================================
        # RESPONSIVE DISPLAY MODE SYSTEM
        # ========================================

        # Get terminal width and determine display mode
        terminal_width = get_terminal_width()
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

        # Calculate cache ratio
        cache_ratio = 0
        if cache_read > 0 or cache_creation > 0:
            all_tokens = compact_tokens + cache_read + cache_creation
            cache_ratio = (cache_read / all_tokens * 100) if all_tokens > 0 else 0

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

        # Generate burn line and timeline for context
        burn_line = ""
        burn_timeline = []
        block_tokens = 0
        if SHOW_LINE4 and block_stats:
            session_data = {
                'total_tokens': block_stats['total_tokens'],
                'duration_seconds': duration_seconds if duration_seconds and duration_seconds > 0 else 1,
                'start_time': block_stats.get('start_time'),
                'efficiency_ratio': block_stats.get('efficiency_ratio', 0),
                'current_cost': session_cost
            }
            burn_line = get_burn_line(session_data, session_id, block_stats, current_block)
            burn_timeline = generate_real_burn_timeline(block_stats, current_block)
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
            'show_line1': SHOW_LINE1,
            'show_line2': SHOW_LINE2,
            'show_line3': SHOW_LINE3,
            'show_line4': SHOW_LINE4,
            'show_schedule': SHOW_SCHEDULE or args.schedule,
        }

        # Select formatter based on display mode
        if display_mode == 'full':
            lines = format_output_full(ctx, terminal_width)
        elif display_mode == 'compact':
            lines = format_output_compact(ctx)
        else:  # tight
            lines = format_output_tight(ctx)

        # Output lines
        for line in lines:
            print(f"\033[0m\033[1;97m{line}\033[0m")
        
    except Exception as e:
        # Fallback status line on error
        print(f"{Colors.BRIGHT_RED}[Error]{Colors.RESET} . | 0 | 0%")
        print(f"{Colors.LIGHT_GRAY}Check ~/.claude/statusline-error.log{Colors.RESET}")
        
        # Debug logging
        with open(Path.home() / '.claude' / 'statusline-error.log', 'a') as f:
            f.write(f"{datetime.now()}: {e}\n")
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