#!/usr/bin/env python3

# OUTPUT CONFIGURATION - CHOOSE WHICH LINES TO DISPLAY

# Set which lines to display (True = show, False = hide)
SHOW_LINE1 = True   # [Sonnet 4] | 🌿 main M2 +1 | 📁 statusline | 💬 254
SHOW_LINE2 = True   # 🪙  Compact: 91.8K/160.0K ████████▒▒▒▒▒▒▒ 58% ♻️  99% cached 💰 Cost: $0.031
SHOW_LINE3 = True   # ⏱️  Session: 1h15m/5h    ███▒▒▒▒▒▒▒▒▒▒▒▒ 25% 09:15 (08:00 to 13:00)
SHOW_LINE4 = True   # 🔥 Burn:    0 (Rate: 0 t/m) ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁

# Alternative quick configurations (uncomment one to use):
# SHOW_LINE1, SHOW_LINE2, SHOW_LINE3, SHOW_LINE4 = True, True, False, False   # Only lines 1-2
# SHOW_LINE1, SHOW_LINE2, SHOW_LINE3, SHOW_LINE4 = False, True, True, True    # Skip line 1
# SHOW_LINE1, SHOW_LINE2, SHOW_LINE3, SHOW_LINE4 = False, False, True, True   # Only lines 3-4

# IMPORTS AND SYSTEM CODE

import json
import sys
import os
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone, date
import time
from collections import defaultdict

# CONSTANTS

# Token compaction threshold (when Claude Code compresses conversation history)
COMPACTION_THRESHOLD = 200000 * 0.8  # 80% of 200K tokens

# TWO DISTINCT TOKEN CALCULATION SYSTEMS

# This application uses TWO completely separate token calculation systems:

# 🗜️ COMPACT LINE SYSTEM (Conversation Compaction)
# ==============================================
# Purpose: Tracks current conversation progress toward compaction threshold
# Data Source: Current conversation tokens (until 160K compaction limit)
# Scope: Single conversation, monitors compression timing
# Calculation: block_stats['total_tokens'] from detect_five_hour_blocks()
# Display: 🪙 Compact line (Line 2) - "118.1K/160.0K ████████▒▒▒▒ 74%"
# Range: 0-200K tokens (until conversation gets compressed)
# Reset Point: When conversation gets compacted/compressed

# 🕐 SESSION WINDOW SYSTEM (Session Management)
# ===================================================
# Purpose: Tracks usage periods
# Data Source: Messages within usage windows
# Scope: Usage period tracking
# Calculation: calculate_tokens_since_time() with 5-hour window start
# Display: ⏱️ Session line (Line 3) + 🔥 Burn line (Line 4)
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

def get_total_tokens(usage_data):
    """Calculate total tokens from usage data (UNIVERSAL HELPER)
    
    Used by session/burn line systems for usage window tracking.
    Sums all token types: input + output + cache_creation + cache_read
    
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
    
    # Cache creation tokens (multiple possible field names)
    cache_creation = (
        usage_data.get('cache_creation_input_tokens', 0) or
        usage_data.get('cacheCreationInputTokens', 0) or
        usage_data.get('cacheCreationTokens', 0)
    )
    
    # Cache read tokens (multiple possible field names)  
    cache_read = (
        usage_data.get('cache_read_input_tokens', 0) or
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
        compact_text: Text part of compact line (e.g., "🪙  Compact: 111.6K/160.0K")
        session_text: Text part of session line (e.g., "⏱️  Session: 3h26m/5h")
    
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
    except Exception:
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

def find_all_transcript_files():
    """Find all transcript files across all projects"""
    projects_dir = Path.home() / '.claude' / 'projects'
    
    if not projects_dir.exists():
        return []
    
    transcript_files = []
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            for file_path in project_dir.glob("*.jsonl"):
                transcript_files.append(file_path)
    
    return transcript_files

def load_all_messages_chronologically():
    """Load all messages from all transcripts in chronological order"""
    all_messages = []
    transcript_files = find_all_transcript_files()
    
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
                                'usage': entry.get('message', {}).get('usage') if entry.get('message') else None,
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
            # First entry - start a new block (floored to the hour) -  111
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
                
                # Start new block (floored to the hour) -  137
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
    
    # Set minutes, seconds, microseconds to 0
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
    # 現在のセッションは最新のアクティブブロックにあるべき
    for block in reversed(blocks):  # 新しいブロックから探す
        if block.get('is_active', False):  # アクティブブロックのみ
            for message in block['messages']:
                msg_session_id = message.get('session_id') or message.get('sessionId')
                if msg_session_id == target_session_id:
                    return block
    
    # フォールバック: アクティブブロックにセッションが見つからない場合
    # セッションIDが含まれる最後のブロックを返す
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
    
    # 元のJSONLファイルから直接読み取って重複除去
    transcript_file = find_session_transcript(session_id)
    if not transcript_file:
        return calculate_block_statistics_fallback(block)
    
    return calculate_tokens_from_jsonl_with_dedup(transcript_file, block['start_time'], block.get('duration_seconds', 18000))

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
                    
                    # 重複除去チェック（ccost互換）
                    message_id = message_data.get('uuid')
                    request_id = message_data.get('requestId')
                    session_id = message_data.get('sessionId')
                    
                    unique_hash = None
                    if message_id and request_id:
                        unique_hash = f"req:{message_id}:{request_id}"
                    elif message_id and session_id:
                        unique_hash = f"session:{message_id}:{session_id}"
                    
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
        
    except Exception as e:
        import sys
        print(f"DEBUG: Error in JSONL dedup: {e}", file=sys.stderr)
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
        
        # 重複除去チェック（ccost互換：requestId優先 + sessionId fallback）
        # 実際のJSONL構造に基づく修正
        message_id = message_data.get('uuid')  # 実際のメッセージID
        request_id = message_data.get('requestId')  # requestIdは最上位
        session_id = message_data.get('sessionId')  # sessionIdも最上位
        
        unique_hash = None
        if message_id and request_id:
            unique_hash = f"req:{message_id}:{request_id}"  # Priority 1
        elif message_id and session_id:
            unique_hash = f"session:{message_id}:{session_id}"  # Fallback
        
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
        
        # トークン使用量の合計（assistantメッセージのusageのみ - ccusage互換）
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
    
    # デバッグ出力：重複除去の効果を確認
    if total_messages > 0:
        dedup_rate = (skipped_duplicates / total_messages) * 100
        import sys
        print(f"DEBUG: total_messages={total_messages}, skipped_duplicates={skipped_duplicates}, dedup_rate={dedup_rate:.1f}%", file=sys.stderr)
    
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
    """実際のメッセージデータからBurnスパークラインを生成（5時間ウィンドウ全体対応）"""
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
        
        # 現在の経過時間を計算（現在進行中のセグメント特定用）
        current_elapsed_minutes = (current_time - block_start_utc).total_seconds() / 60
        current_segment_index = int(current_elapsed_minutes / 15)
        segment_progress = (current_elapsed_minutes % 15) / 15.0  # セグメント内の進捗率
        
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
            
            except (ValueError, KeyError, TypeError):
                continue
        
        # リアルタイム対応：現在進行中のセグメントに部分的な値を設定
        # （実際のメッセージがない場合でも、時間経過を視覚的に示す）
        if 0 <= current_segment_index < 20:
            # 現在のセグメントにデータがない場合、最小限の値を設定
            if timeline[current_segment_index] == 0 and segment_progress > 0.1:
                # 10%以上進行している場合は最小値を設定
                timeline[current_segment_index] = int(100 * segment_progress)
    
    except Exception:
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
def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Claude Code statusline with configurable output', add_help=False)
    parser.add_argument('--show', type=str, help='Lines to show: 1,2,3,4 or all (default: use config settings)')
    parser.add_argument('--help', action='store_true', help='Show help')
    
    # Parse arguments, but don't exit on failure (for stdin compatibility)
    try:
        args, _ = parser.parse_known_args()
    except:
        args = argparse.Namespace(show=None, help=False)
    
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
                except Exception as e:
                    print(f"DEBUG: Error in detect_five_hour_blocks: {e}", file=sys.stderr)
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
                if block_stats:
                    # Compact line用: 現在セッションのトークンのみ
                    transcript_file = find_session_transcript(session_id)
                    if transcript_file:
                        (total_tokens, _, error_count, user_messages, assistant_messages,
                         input_tokens, output_tokens, cache_creation, cache_read) = calculate_tokens_from_transcript(transcript_file)
                    else:
                        # フォールバック
                        total_tokens = 0
                        user_messages = block_stats['user_messages'] 
                        assistant_messages = block_stats['assistant_messages']
                        error_count = block_stats['error_count']
                        input_tokens = 0
                        output_tokens = 0
                        cache_creation = 0
                        cache_read = 0
            except Exception as e:
                
                # フォールバック: 従来の単一ファイル方式
                transcript_file = find_session_transcript(session_id)
                if transcript_file:
                    (total_tokens, _, error_count, user_messages, assistant_messages,
                     input_tokens, output_tokens, cache_creation, cache_read) = calculate_tokens_from_transcript(transcript_file)
        
        # Calculate percentage for Compact display (use conversation compaction tokens)
        percentage = min(100, round((total_tokens / COMPACTION_THRESHOLD) * 100))
        
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
        
        # Calculate cost with model name
        session_cost = calculate_cost(input_tokens, output_tokens, cache_creation, cache_read, model)
        
        # Format displays
        token_display = format_token_count(total_tokens)
        percentage_color = get_percentage_color(percentage)
        
        # === 複数行版 ===
        # 行1: 基本情報とトークン状況
        line1_parts = []
        
        # Model - 正式名称を表示（最も明るく）
        line1_parts.append(f"{Colors.BRIGHT_YELLOW}[{model}]{Colors.RESET}")
        
        # Git
        if git_branch:
            git_display = f"{Colors.BRIGHT_GREEN}🌿 {git_branch}"
            if modified_files > 0:
                git_display += f" {Colors.BRIGHT_YELLOW}M{modified_files}"
            if untracked_files > 0:
                git_display += f" {Colors.BRIGHT_CYAN}+{untracked_files}"
            git_display += Colors.RESET
            line1_parts.append(git_display)
        
        # Directory（より明るく）
        line1_parts.append(f"{Colors.BRIGHT_CYAN}📁 {current_dir}{Colors.RESET}")
        
        # Files - 明るい色で表示（0の場合は非表示）
        if active_files > 0:
            line1_parts.append(f"{Colors.BRIGHT_WHITE}📝 {active_files}{Colors.RESET}")
        
        # Messages - 総数のみ表示
        total_messages = user_messages + assistant_messages
        if total_messages > 0:
            line1_parts.append(f"{Colors.BRIGHT_CYAN}💬 {total_messages}{Colors.RESET}")
        
        # Errors
        if error_count > 0:
            line1_parts.append(f"{Colors.BRIGHT_RED}⚠️ {error_count}{Colors.RESET}")
        
        # Task status
        if task_status != 'idle':
            line1_parts.append(f"{Colors.BRIGHT_YELLOW}⚡ {task_status}{Colors.RESET}")
        
        # Cost display (moved from line 2)
        if session_cost > 0:
            cost_color = Colors.BRIGHT_YELLOW if session_cost > 10 else Colors.BRIGHT_WHITE
            line1_parts.append(f"{cost_color}💰 {format_cost(session_cost)}{Colors.RESET}")
        
        # Current time moved to Session line
        
        # 行2: Token情報の統合
        line2_parts = []
        
        # Compact line: Shows conversation tokens vs compaction threshold
        conversation_tokens = total_tokens
        compact_display = format_token_count(conversation_tokens)
        
        # グラフ先頭表示: アイコン + タイトル + プログレスバー + 詳細情報
        # 85%以上で警告表示
        if percentage >= 85:
            warning_icon = "🚨"
            title_color = f"{Colors.BG_RED}{Colors.BRIGHT_WHITE}{Colors.BOLD}"
            percentage_display = f"{Colors.BG_RED}{Colors.BRIGHT_WHITE}{Colors.BOLD}[{percentage}%] ⚠️{Colors.RESET}"
            # 🚨の表示幅調整でスペースを1つ減らす
            compact_label = f"{title_color}{warning_icon} Compact:{Colors.RESET}"
        else:
            warning_icon = "🪙"
            title_color = Colors.BRIGHT_CYAN
            percentage_display = f"{percentage_color}{Colors.BOLD}[{percentage}%]{Colors.RESET}"
            # 通常の🪙では2スペース
            compact_label = f"{title_color}{warning_icon}  Compact:{Colors.RESET}"
        
        line2_parts.append(compact_label)
        line2_parts.append(get_progress_bar(percentage, width=20))
        line2_parts.append(percentage_display)
        line2_parts.append(f"{Colors.BRIGHT_WHITE}{compact_display}/{format_token_count(COMPACTION_THRESHOLD)}{Colors.RESET}")
        
        # キャッシュ情報（説明付き簡潔版）
        if cache_read > 0 or cache_creation > 0:
            cache_ratio = (cache_read / total_tokens * 100) if total_tokens > 0 else 0
            if cache_ratio >= 50:  # 50%以上の場合のみ表示
                line2_parts.append(f"{Colors.BRIGHT_GREEN}♻️  {int(cache_ratio)}% cached{Colors.RESET}")
        
        # 警告表示を削除（ユーザーリクエスト）
        
        # 行3: Session情報の統合（元に戻す）
        line3_parts = []
        if duration_seconds is not None and session_duration:
            # 5時間制限での計算
            hours_elapsed = duration_seconds / 3600
            block_progress = (hours_elapsed % 5) / 5 * 100  # 5時間内の進捗
            
            # セッション開始時間を取得 ()
            session_start_time = None
            if block_stats:
                try:
                    start_time_utc = block_stats['start_time']
                    # Convert UTC to local time for display
                    start_time_local = convert_utc_to_local(start_time_utc)
                    session_start_time = start_time_local.strftime("%H:%M")
                except Exception as e:
                    # Fallback: use UTC time directly
                    session_start_time = block_stats['start_time'].strftime("%H:%M")
            
            # Session情報（動的パディングでプログレスバー位置を2行目と揃える）
            compact_text = f"🪙  Compact: {compact_display}/{format_token_count(COMPACTION_THRESHOLD)}"
            
            # グラフ先頭表示: アイコン + タイトル + プログレスバー + 詳細情報
            line3_parts.append(f"{Colors.BRIGHT_CYAN}⏱️  Session:{Colors.RESET}")
            session_bar = get_progress_bar(block_progress, width=20, show_current_segment=True)
            line3_parts.append(session_bar)
            line3_parts.append(f"{Colors.BRIGHT_WHITE}[{int(block_progress)}%]{Colors.RESET}")
            line3_parts.append(f"{Colors.BRIGHT_WHITE}{session_duration}/5h{Colors.RESET}")
            
            # 現在時刻をSession行に追加（開始時刻と終了時刻付き）
            if session_start_time:
                # 5時間ブロックの終了時刻を計算
                try:
                    start_time_utc = block_stats['start_time']
                    start_time_local = convert_utc_to_local(start_time_utc)
                    
                    # 5時間後の終了時刻を計算
                    end_time_local = start_time_local + timedelta(hours=5)
                    session_end_time = end_time_local.strftime("%H:%M")
                    
                    line3_parts.append(f"{Colors.BRIGHT_WHITE}{current_time}{Colors.RESET} {Colors.BRIGHT_GREEN}({session_start_time} to {session_end_time}){Colors.RESET}")
                except Exception:
                    # フォールバック: 開始時刻のみ表示
                    line3_parts.append(f"{Colors.BRIGHT_WHITE}{current_time}{Colors.RESET} {Colors.BRIGHT_GREEN}(from {session_start_time}){Colors.RESET}")
            else:
                line3_parts.append(f"{Colors.BRIGHT_WHITE}{current_time}{Colors.RESET}")
        
        # 出力モード（環境変数で制御）
        output_mode = os.environ.get('STATUSLINE_MODE', 'multi')
        
        if output_mode == 'single':
            # 1行集約版（公式仕様準拠）
            single_line = []
            if line1_parts:
                single_line.extend(line1_parts[:3])  # モデル、Git、ディレクトリのみ
            if token_display and percentage:
                single_line.append(f"🪙 Tokens: {token_display}({percentage}%)")
            if session_duration:
                single_line.append(f"⏱️ Time: {session_duration}")
            print(" | ".join(single_line))
        else:
            # 複数行版（設定に基づいて表示）
            # より強力な色リセット + 明るい色設定
            if SHOW_LINE1:
                print(f"\033[0m\033[1;97m" + " | ".join(line1_parts) + f"\033[0m")
            
            if SHOW_LINE2:
                print(f"\033[0m\033[1;97m" + " ".join(line2_parts) + f"\033[0m") 
            
            # 3行目（セッション時間の詳細）を表示する場合
            if SHOW_LINE3 and line3_parts:
                print(f"\033[0m\033[1;97m" + " ".join(line3_parts) + f"\033[0m")
            
            # ═══════════════════════════════════════════════════════════════════
            # 📊 SESSION LINE SYSTEM: Line 4 - Burn Rate Display
            # ═══════════════════════════════════════════════════════════════════
            if SHOW_LINE4:
                session_data = None
                if block_stats:
                    # Calculate SESSION tokens (different from block tokens above)
                    session_start_time = block_stats.get('start_time')
                    session_tokens = calculate_tokens_since_time(session_start_time, session_id) if session_start_time else 0
                    session_data = {
                        'total_tokens': session_tokens,  # SESSION tokens for burn rate
                        'duration_seconds': duration_seconds,
                        'start_time': block_stats.get('start_time'),
                        'efficiency_ratio': block_stats.get('efficiency_ratio', 0),
                        'current_cost': session_cost
                    }
                line4_parts = get_burn_line(session_data, session_id, block_stats, current_block)
                if line4_parts:
                    print(f"\033[0m\033[1;97m{line4_parts}\033[0m")
        
    except Exception as e:
        # Fallback status line on error
        print(f"{Colors.BRIGHT_RED}[Error]{Colors.RESET} 📁 . | 🪙 0 | 0%")
        print(f"{Colors.LIGHT_GRAY}Check ~/.claude/statusline-error.log{Colors.RESET}")
        
        # Debug logging
        with open(Path.home() / '.claude' / 'statusline-error.log', 'a') as f:
            f.write(f"{datetime.now()}: {e}\n")
            f.write(f"Input data: {locals().get('input_data', 'No input')}\n\n")

def calculate_tokens_since_time(start_time, session_id):
    """📊 SESSION LINE SYSTEM: Calculate tokens for current session only
    
    Calculates tokens from session start time to now for the burn line display.
    This is SESSION scope, NOT block scope. Used for burn rate calculations.
    
    CRITICAL: This is for the 🔥 Burn line, NOT the 🪙 Compact line.
    
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
    """📊 SESSION LINE SYSTEM: Generate burn line display (Line 4)
    
    Creates the 🔥 Burn line showing session tokens and burn rate.
    Uses 5-hour block timeline data with 15-minute intervals (20 segments).
    
    Format: "🔥 Burn:    17,106,109 (Rate: 258,455 t/m) [sparkline]"
    
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
        
        # Format session tokens for display
        tokens_formatted = f"{block_total_tokens:,}"
        burn_rate_formatted = f"{burn_rate:,.0f}"
        
        # Generate 5-hour timeline sparkline from REAL message data ONLY
        if block_stats and 'start_time' in block_stats and current_block:
            burn_timeline = generate_real_burn_timeline(block_stats, current_block)
        else:
            burn_timeline = [0] * 20
        
        sparkline = create_sparkline(burn_timeline, width=20)
        
        return (f"{Colors.BRIGHT_CYAN}🔥 Burn:    {Colors.RESET}{sparkline} "
                f"{Colors.BRIGHT_WHITE}{tokens_formatted} token(w/cache){Colors.RESET}, Rate: {burn_rate_formatted} t/m")
        
    except Exception as e:
        print(f"DEBUG: Burn line error: {e}", file=sys.stderr)
        return f"{Colors.BRIGHT_CYAN}🔥 Burn: {Colors.RESET}   {Colors.BRIGHT_WHITE}ERROR{Colors.RESET}"
if __name__ == "__main__":
    main()