#!/usr/bin/env python3

import json
import sys
import os
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timedelta, date
import time
from collections import defaultdict

# Constants
COMPACTION_THRESHOLD = 200000 * 0.8  # 80% of 200K tokens

# ANSI color codes optimized for black backgrounds - 全て明るいバージョン
class Colors:
    BRIGHT_CYAN = '\033[1;96m'     # 最も明るいシアン
    BRIGHT_BLUE = '\033[1;94m'      # 最も明るい青
    BRIGHT_MAGENTA = '\033[1;95m'   # 最も明るいマゼンタ
    BRIGHT_GREEN = '\033[1;92m'     # 最も明るい緑
    BRIGHT_YELLOW = '\033[1;93m'    # 最も明るい黄色
    BRIGHT_RED = '\033[1;95m'       # ピンク（マゼンタ）
    BRIGHT_WHITE = '\033[1;97m'     # 最も明るい白
    LIGHT_GRAY = '\033[1;97m'       # 明るいグレー（最明白）
    DIM = '\033[1;97m'              # DIMも最明白
    BOLD = '\033[1m'                # 太字
    RESET = '\033[0m'               # リセット

def format_token_count(tokens):
    """Format token count for display"""
    if tokens >= 1000000:
        return f"{tokens / 1000000:.1f}M"
    elif tokens >= 1000:
        return f"{tokens / 1000:.1f}K"
    return str(tokens)

def get_percentage_color(percentage):
    """Get color based on percentage threshold"""
    if percentage >= 90:
        return '\033[1;91m'  # 元の赤色
    elif percentage >= 70:
        return Colors.BRIGHT_YELLOW
    return Colors.BRIGHT_GREEN

def get_progress_bar(percentage, width=20):
    """Create a visual progress bar"""
    filled = int(width * percentage / 100)
    empty = width - filled
    
    color = get_percentage_color(percentage)
    # 明るい文字を使用
    bar = color + '█' * filled + Colors.LIGHT_GRAY + '▒' * empty + Colors.RESET
    
    return bar

def calculate_tokens_from_transcript(file_path):
    """Calculate total tokens from transcript file with cache token breakdown"""
    last_usage = None
    message_count = 0
    error_count = 0
    user_messages = 0
    assistant_messages = 0
    
    # トークンの詳細追跡
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
                    
                    # Check if this is an assistant message with usage data
                    if entry.get('type') == 'assistant' and entry.get('message', {}).get('usage'):
                        last_usage = entry['message']['usage']
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return 0, 0, 0, 0, 0, 0, 0, 0, 0
    except Exception:
        return 0, 0, 0, 0, 0, 0, 0, 0, 0
    
    if last_usage:
        # 累積値を使用（最後のusageには全ての合計が含まれる）
        total_input_tokens = last_usage.get('input_tokens', 0)
        total_output_tokens = last_usage.get('output_tokens', 0)
        total_cache_creation = last_usage.get('cache_creation_input_tokens', 0)
        total_cache_read = last_usage.get('cache_read_input_tokens', 0)
        
        # 総トークン数（全て含む）
        total_tokens = (
            total_input_tokens +
            total_output_tokens +
            total_cache_creation +
            total_cache_read
        )
    else:
        total_tokens = 0
    
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
                            # UTC タイムスタンプをローカルタイムゾーンに変換
                            timestamp_utc = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                            timestamp_local = timestamp_utc.astimezone()
                            
                            all_messages.append({
                                'timestamp': timestamp_local,
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
    """Detect 5-hour blocks from all messages for billing analysis"""
    if not all_messages:
        return []
    
    blocks = []
    block_duration_seconds = block_duration_hours * 3600
    
    # 最初のメッセージの時間を基準にブロック開始時刻を決定
    first_message = all_messages[0]
    session_start = first_message['timestamp'].replace(minute=0, second=0, microsecond=0)
    
    # 時間ベースでブロックを生成
    current_time = datetime.now(session_start.tzinfo) if session_start.tzinfo else datetime.now()
    total_elapsed = (current_time - session_start).total_seconds()
    
    # 必要なブロック数を計算
    num_blocks = int(total_elapsed / block_duration_seconds) + 1
    
    for block_num in range(num_blocks):
        block_start = session_start + timedelta(seconds=block_num * block_duration_seconds)
        block_end = session_start + timedelta(seconds=(block_num + 1) * block_duration_seconds)
        
        # このブロックに属するメッセージを収集
        block_messages = [
            msg for msg in all_messages
            if block_start <= msg['timestamp'] < block_end
        ]
        
        # 最後のブロック（現在アクティブ）は常に作成
        if block_messages or block_num == num_blocks - 1:
            # 実際の終了時刻
            if block_num == num_blocks - 1:  # 最後のブロック
                actual_end_time = current_time
                is_active = True
            else:
                actual_end_time = block_messages[-1]['timestamp'] if block_messages else block_end
                is_active = False
            
            blocks.append({
                'start_time': block_start,
                'end_time': actual_end_time,
                'messages': block_messages,
                'duration_seconds': (actual_end_time - block_start).total_seconds(),
                'is_active': is_active
            })
    
    return blocks

def find_current_session_block(blocks, target_session_id):
    """Find the most recent active block containing the target session"""
    # 現在のセッションは最新のアクティブブロックにあるべき
    for block in reversed(blocks):  # 新しいブロックから探す
        if block.get('is_active', False):  # アクティブブロックのみ
            for message in block['messages']:
                if message['session_id'] == target_session_id:
                    return block
    
    # フォールバック: アクティブブロックにセッションが見つからない場合
    # セッションIDが含まれる最後のブロックを返す
    for block in reversed(blocks):
        for message in block['messages']:
            if message['session_id'] == target_session_id:
                return block
    
    return None

def calculate_block_statistics(block):
    """Calculate comprehensive statistics for a 5-hour block"""
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
    
    for message in block['messages']:
        # メッセージ種別のカウント
        if message['type'] == 'user':
            user_messages += 1
        elif message['type'] == 'assistant':
            assistant_messages += 1
        elif message['type'] == 'error':
            error_count += 1
        
        # トークン使用量の累積（最後のusageを使用）
        if message['usage']:
            total_input_tokens = message['usage'].get('input_tokens', 0)
            total_output_tokens = message['usage'].get('output_tokens', 0)
            total_cache_creation = message['usage'].get('cache_creation_input_tokens', 0)
            total_cache_read = message['usage'].get('cache_read_input_tokens', 0)
    
    total_tokens = total_input_tokens + total_output_tokens + total_cache_creation + total_cache_read
    
    # アクティブ期間の検出（ブロック内）
    active_periods = detect_active_periods(block['messages'])
    total_active_duration = sum((end - start).total_seconds() for start, end in active_periods)
    
    # 現在時刻の考慮（アクティブブロックの場合）
    if block.get('is_active', False):
        current_time = datetime.now(block['start_time'].tzinfo)
        actual_duration = (current_time - block['start_time']).total_seconds()
    else:
        actual_duration = block['duration_seconds']
    
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
        'active_duration': total_active_duration,
        'efficiency_ratio': total_active_duration / actual_duration if actual_duration > 0 else 0,
        'is_active': block.get('is_active', False)
    }

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

def detect_session_boundaries(messages, session_break_threshold=30*60):
    """Detect session boundaries based on message gaps"""
    boundaries = []
    
    for i in range(1, len(messages)):
        try:
            prev_time_utc = datetime.fromisoformat(messages[i-1]['timestamp'].replace('Z', '+00:00'))
            curr_time_utc = datetime.fromisoformat(messages[i]['timestamp'].replace('Z', '+00:00'))
            
            # システムのローカルタイムゾーンに自動変換
            prev_time = prev_time_utc.astimezone()
            curr_time = curr_time_utc.astimezone()
            
            time_diff = (curr_time - prev_time).total_seconds()
            
            if time_diff > session_break_threshold:
                boundaries.append((prev_time, curr_time))
        except:
            continue
    
    return boundaries

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

def get_enhanced_session_analysis(transcript_file):
    """Enhanced session analysis with billing block features"""
    messages = []
    
    try:
        with open(transcript_file, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get('timestamp'):
                        messages.append(entry)
                except:
                    continue
    except:
        return None
    
    if not messages:
        return None
    
    # セッション境界検出
    boundaries = detect_session_boundaries(messages)
    
    # アクティブ期間検出
    active_periods = detect_active_periods(messages)
    
    # 最初と最後のタイムスタンプ
    first_timestamp = messages[0]['timestamp']
    last_timestamp = messages[-1]['timestamp']
    
    # UTC タイムスタンプをローカルタイムゾーンに変換
    first_dt_utc = datetime.fromisoformat(first_timestamp.replace('Z', '+00:00'))
    last_dt_utc = datetime.fromisoformat(last_timestamp.replace('Z', '+00:00'))
    
    # システムのローカルタイムゾーンを使用（より簡単な方法）
    first_dt = first_dt_utc.astimezone()  # システムのローカルタイムゾーンに自動変換
    last_dt = last_dt_utc.astimezone()
    
    # アクティブ時間の計算
    total_active_duration = sum(
        (end - start).total_seconds() 
        for start, end in active_periods
    )
    
    return {
        'first_message': first_dt,
        'last_message': last_dt,
        'session_boundaries': boundaries,
        'active_periods': active_periods,
        'total_active_duration': total_active_duration,
        'message_count': len(messages),
        'has_recent_activity': (datetime.now(first_dt.tzinfo if first_dt.tzinfo else None) - last_dt).total_seconds() < 300
    }

def get_session_duration(session_id):
    """Enhanced session duration calculation with 5-hour block features
    
    Improvements over basic version:
    - Session boundary detection
    - Active period analysis
    - Better continuation detection
    - More accurate session start time
    """
    if not session_id:
        return None, None
        
    transcript = find_session_transcript(session_id)
    if not transcript:
        return None, None
        
    try:
        # 拡張分析を実行
        analysis = get_enhanced_session_analysis(transcript)
        if not analysis:
            return None, None
        
        first_dt = analysis['first_message']
        last_dt = analysis['last_message']
        
        # 5時間ブロックベースのセッション開始時刻決定
        # 基本: 時間単位で切り捨て
        session_start = first_dt.replace(minute=0, second=0, microsecond=0)
        
        # ただし、深夜・早朝の異常な時間は実際の時刻を優先
        actual_hour = first_dt.hour
        if 2 <= actual_hour <= 6 and first_dt.minute > 30:
            # 深夜〜早朝で30分を超えている場合は実際の開始時刻を使用
            session_start = first_dt
        
        # セッション終了時刻の決定
        if analysis['has_recent_activity']:
            # 5分以内にアクティビティがある場合は現在時刻を使用
            if first_dt.tzinfo:
                end_time = datetime.now(first_dt.tzinfo)
            else:
                end_time = datetime.now()
        else:
            # そうでなければ最後のメッセージ時刻
            end_time = last_dt
        
        # セッション継続時間
        duration = (end_time - session_start).total_seconds()
        
        # 負の値や異常値の処理
        if duration < 0:
            return None, None
        
        # 24時間でキャップ
        duration = min(duration, 86400)
        
        # フォーマット済み文字列
        if duration < 60:
            formatted = f"{int(duration)}s"
        elif duration < 3600:
            formatted = f"{int(duration/60)}m"
        else:
            hours = int(duration/3600)
            minutes = int((duration % 3600) / 60)
            if minutes > 0:
                formatted = f"{hours}h{minutes}m"
            else:
                formatted = f"{hours}h"
        
        return duration, formatted
            
    except Exception:
        # エラーが発生した場合はNoneを返す
        pass
    
    return None, None

def get_session_efficiency_metrics(session_id):
    """Get session efficiency metrics (active time ratio, etc.)"""
    transcript = find_session_transcript(session_id)
    if not transcript:
        return None
    
    analysis = get_enhanced_session_analysis(transcript)
    if not analysis:
        return None
    
    duration_seconds, _ = get_session_duration(session_id)
    if not duration_seconds:
        return None
    
    active_duration = analysis['total_active_duration']
    efficiency_ratio = active_duration / duration_seconds if duration_seconds > 0 else 0
    
    return {
        'total_duration': duration_seconds,
        'active_duration': active_duration,
        'idle_duration': duration_seconds - active_duration,
        'efficiency_ratio': efficiency_ratio,
        'active_periods_count': len(analysis['active_periods']),
        'session_boundaries_count': len(analysis['session_boundaries'])
    }

def get_time_progress_bar(duration_seconds, max_hours=5, width=10):
    """Create a time progress bar (5 hours = 100%)"""
    if duration_seconds is None:
        return None, None
    
    max_seconds = max_hours * 3600
    percentage = min(100, (duration_seconds / max_seconds) * 100)
    filled = int(width * percentage / 100)
    empty = width - filled
    
    # 時間経過による色分け
    if percentage >= 80:
        color = Colors.BRIGHT_RED
    elif percentage >= 60:
        color = Colors.BRIGHT_YELLOW
    else:
        color = Colors.BRIGHT_GREEN
    
    bar = color + '▮' * filled + Colors.LIGHT_GRAY + '▯' * empty + Colors.RESET
    return bar, percentage

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

def print_help():
    """Print help information"""
    print("statusline.py - Enhanced Claude Code Status Line")
    print()
    print("USAGE:")
    print("  echo '{\"session_id\":\"...\"}' | statusline")
    print("  statusline --help")
    print()
    print("FEATURES:")
    print("  • Real-time token usage and cost tracking")
    print("  • 5-hour block session management for billing analysis")
    print("  • Git integration with branch and file status")
    print("  • Multi-project transcript analysis")
    print("  • Cache efficiency monitoring")
    print()
    print("CONFIGURATION:")
    print("  Add to .claude/settings.json:")
    print('  {"statusLine": {"command": "statusline"}}')

def print_version():
    """Print version information"""
    print("statusline.py v2.0 - enhanced status display with usage analytics")

def main():
    # Handle command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] in ['--help', '-h', 'help']:
            print_help()
            return
        elif sys.argv[1] in ['--version', '-v']:
            print_version()
            return
    
    try:
        # Read JSON from stdin
        input_data = sys.stdin.read()
        if not input_data.strip():
            print_help()
            return
        data = json.loads(input_data)
        
        # Extract basic values
        model = data.get('model', {}).get('display_name', 'Unknown')
        workspace = data.get('workspace', {})
        current_dir = os.path.basename(workspace.get('current_dir', data.get('cwd', '.')))
        session_id = data.get('session_id')
        
        # Get git info
        git_branch, modified_files, untracked_files = get_git_info(
            workspace.get('current_dir', data.get('cwd', '.'))
        )
        
        # Get token usage and message counts
        total_tokens = 0
        message_count = 0
        error_count = 0
        user_messages = 0
        assistant_messages = 0
        input_tokens = 0
        output_tokens = 0
        cache_creation = 0
        cache_read = 0
        
        # 5時間ブロック検出システム
        block_stats = None
        if session_id:
            try:
                # 全メッセージを時系列で読み込み
                all_messages = load_all_messages_chronologically()
                
                # 5時間ブロックを検出
                blocks = detect_five_hour_blocks(all_messages)
                
                # 現在のセッションが含まれるブロックを特定
                current_block = find_current_session_block(blocks, session_id)
                
                if current_block:
                    # ブロック全体の統計を計算
                    block_stats = calculate_block_statistics(current_block)
                elif blocks:
                    # セッションが見つからない場合は最新のアクティブブロックを使用
                    active_blocks = [b for b in blocks if b.get('is_active', False)]
                    if active_blocks:
                        current_block = active_blocks[-1]  # 最新のアクティブブロック
                        block_stats = calculate_block_statistics(current_block)
                
                # 統計データを既存の変数名に設定（互換性のため）
                if block_stats:
                    total_tokens = block_stats['total_tokens']
                    user_messages = block_stats['user_messages']
                    assistant_messages = block_stats['assistant_messages']
                    message_count = user_messages + assistant_messages
                    error_count = block_stats['error_count']
                    input_tokens = block_stats['input_tokens']
                    output_tokens = block_stats['output_tokens']
                    cache_creation = block_stats['cache_creation']
                    cache_read = block_stats['cache_read']
            except Exception:
                # フォールバック: 従来の単一ファイル方式
                transcript_file = find_session_transcript(session_id)
                if transcript_file:
                    (total_tokens, msg_count_unused, error_count, user_messages, assistant_messages,
                     input_tokens, output_tokens, cache_creation, cache_read) = calculate_tokens_from_transcript(transcript_file)
                    message_count = user_messages + assistant_messages
        
        # Calculate percentage
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
        
        # Model - 正式名称を表示
        line1_parts.append(f"{Colors.BRIGHT_WHITE}[{model}]{Colors.RESET}")
        
        # Git
        if git_branch:
            git_display = f"{Colors.BRIGHT_GREEN}🌿 {git_branch}"
            if modified_files > 0:
                git_display += f" {Colors.BRIGHT_YELLOW}±{modified_files}"
            if untracked_files > 0:
                git_display += f" {Colors.BRIGHT_CYAN}+{untracked_files}"
            git_display += Colors.RESET
            line1_parts.append(git_display)
        
        # Directory
        line1_parts.append(f"{Colors.BRIGHT_BLUE}📁 {current_dir}{Colors.RESET}")
        
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
        
        # Current time moved to Session line
        
        # 行2: Token情報の統合
        line2_parts = []
        
        # Token使用量（バランス版）
        line2_parts.append(f"{Colors.BRIGHT_CYAN}🪙  Token: {Colors.RESET}{Colors.BRIGHT_WHITE}{token_display}/{format_token_count(COMPACTION_THRESHOLD)}{Colors.RESET}")
        
        # プログレスバー
        line2_parts.append(get_progress_bar(percentage, width=12))
        
        # パーセンテージ（色付き）
        line2_parts.append(f"{percentage_color}{Colors.BOLD}{percentage}%{Colors.RESET}")
        
        # コスト表示
        if session_cost > 0:
            cost_color = Colors.BRIGHT_YELLOW if session_cost > 10 else Colors.BRIGHT_WHITE
            line2_parts.append(f"{cost_color}💰 Cost: {format_cost(session_cost)}{Colors.RESET}")
        
        # キャッシュ情報（説明付き簡潔版）
        if cache_read > 0 or cache_creation > 0:
            cache_ratio = (cache_read / total_tokens * 100) if total_tokens > 0 else 0
            if cache_ratio >= 50:  # 50%以上の場合のみ表示
                line2_parts.append(f"{Colors.BRIGHT_GREEN}♻️  {int(cache_ratio)}% cached{Colors.RESET}")
        
        # 警告表示を削除（ユーザーリクエスト）
        
        # 行3: Session情報の統合
        line3_parts = []
        if duration_seconds is not None and session_duration:
            # 5時間制限での計算
            hours_elapsed = duration_seconds / 3600
            block_progress = (hours_elapsed % 5) / 5 * 100  # 5時間内の進捗
            
            # 効率性指標は表示しない（削除）
            
            # セッション開始時間を取得
            session_start_time = None
            if block_stats:
                session_start_time = block_stats['start_time'].strftime("%H:%M")
            
            # Session情報（開始時間付き）
            if session_start_time:
                line3_parts.append(f"{Colors.BRIGHT_CYAN}⏱️  Session: {Colors.RESET}{Colors.BRIGHT_WHITE}{session_duration}/5h{Colors.RESET} {Colors.BRIGHT_GREEN}(from {session_start_time}){Colors.RESET}")
            else:
                line3_parts.append(f"{Colors.BRIGHT_CYAN}⏱️ Session: {Colors.RESET}{Colors.BRIGHT_WHITE}{session_duration}/5h{Colors.RESET}")
            
            # 統一されたプログレスバー（同じ文字を使用）
            session_bar = get_progress_bar(block_progress, width=15)
            line3_parts.append(session_bar)
            
            # パーセンテージのみ（残り時間削除）
            line3_parts.append(f"{Colors.BRIGHT_WHITE}{int(block_progress)}%{Colors.RESET}")
            
            # 現在時刻をSession行に追加
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
            # 複数行版（デフォルト、より詳細）
            print(" | ".join(line1_parts))
            print(" ".join(line2_parts))
            
            # 3行目（セッション時間の詳細）を表示する場合
            if line3_parts:
                print(" ".join(line3_parts))
        
    except Exception as e:
        # Fallback status line on error
        print(f"{Colors.BRIGHT_RED}[Error]{Colors.RESET} 📁 . | 🪙 0 | 0%")
        print(f"{Colors.LIGHT_GRAY}Check ~/.claude/statusline-error.log{Colors.RESET}")
        
        # Debug logging
        with open(Path.home() / '.claude' / 'statusline-error.log', 'a') as f:
            f.write(f"{datetime.now()}: {e}\n")
            f.write(f"Input data: {locals().get('input_data', 'No input')}\n\n")

def analyze_daily_usage(target_date=None):
    """Analyze daily usage with comprehensive reporting"""
    if target_date is None:
        target_date = date.today()
    
    # Find all transcript files
    projects_dir = Path.home() / '.claude' / 'projects'
    if not projects_dir.exists():
        print(f"{Colors.BRIGHT_RED}No Claude projects found{Colors.RESET}")
        return
    
    daily_stats = defaultdict(lambda: {
        'input_tokens': 0,
        'output_tokens': 0,
        'cache_creation': 0,
        'cache_read': 0,
        'total_cost': 0.0,
        'sessions': 0,
        'projects': set(),
        'models': set()
    })
    
    # Scan all transcript files
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
            
        for transcript_file in project_dir.glob('*.jsonl'):
            try:
                with open(transcript_file, 'r') as f:
                    session_data = defaultdict(lambda: {
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'cache_creation': 0,
                        'cache_read': 0,
                        'model': None,
                        'start_time': None
                    })
                    
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            timestamp_str = entry.get('timestamp')
                            if not timestamp_str:
                                continue
                                
                            # Parse timestamp and check if it's from target date
                            try:
                                entry_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                entry_date = entry_time.date()
                            except:
                                continue
                                
                            if entry_date != target_date:
                                continue
                            
                            # Track session start time
                            if session_data[transcript_file.name]['start_time'] is None:
                                session_data[transcript_file.name]['start_time'] = entry_time
                            
                            # Extract usage data
                            if entry.get('type') == 'assistant' and entry.get('message', {}).get('usage'):
                                usage = entry['message']['usage']
                                model = entry['message'].get('model', 'unknown')
                                
                                session_data[transcript_file.name]['input_tokens'] = usage.get('input_tokens', 0)
                                session_data[transcript_file.name]['output_tokens'] = usage.get('output_tokens', 0)
                                session_data[transcript_file.name]['cache_creation'] = usage.get('cache_creation_input_tokens', 0)
                                session_data[transcript_file.name]['cache_read'] = usage.get('cache_read_input_tokens', 0)
                                session_data[transcript_file.name]['model'] = model
                                
                        except json.JSONDecodeError:
                            continue
                    
                    # Aggregate session data to daily stats
                    for data in session_data.values():
                        if data['start_time'] is not None:
                            daily_stats[target_date]['input_tokens'] += data['input_tokens']
                            daily_stats[target_date]['output_tokens'] += data['output_tokens']
                            daily_stats[target_date]['cache_creation'] += data['cache_creation']
                            daily_stats[target_date]['cache_read'] += data['cache_read']
                            daily_stats[target_date]['sessions'] += 1
                            daily_stats[target_date]['projects'].add(project_dir.name)
                            if data['model']:
                                daily_stats[target_date]['models'].add(data['model'])
                            
                            # Calculate cost
                            cost = calculate_cost(
                                data['input_tokens'],
                                data['output_tokens'],
                                data['cache_creation'],
                                data['cache_read'],
                                data['model'] or 'claude-3-5-sonnet-20241022'
                            )
                            daily_stats[target_date]['total_cost'] += cost
                            
            except Exception:
                continue
    
    # Display results
    print(f"{Colors.BRIGHT_CYAN}📊 Daily Usage Report - {target_date.strftime('%Y-%m-%d')}{Colors.RESET}")
    print("=" * 60)
    
    if not daily_stats:
        print(f"{Colors.BRIGHT_YELLOW}No usage data found for {target_date}{Colors.RESET}")
        return
    
    stats = daily_stats[target_date]
    total_tokens = stats['input_tokens'] + stats['output_tokens']
    cache_total = stats['cache_creation'] + stats['cache_read']
    
    # Summary stats
    print(f"{Colors.BRIGHT_WHITE}📈 Summary{Colors.RESET}")
    print(f"  Sessions: {Colors.BRIGHT_GREEN}{stats['sessions']}{Colors.RESET}")
    print(f"  Projects: {Colors.BRIGHT_BLUE}{len(stats['projects'])}{Colors.RESET}")
    print(f"  Models: {Colors.BRIGHT_MAGENTA}{', '.join(stats['models'])}{Colors.RESET}")
    print()
    
    # Token breakdown
    print(f"{Colors.BRIGHT_WHITE}🪙 Token Usage{Colors.RESET}")
    print(f"  Input:       {Colors.BRIGHT_CYAN}{format_token_count(stats['input_tokens']):>8}{Colors.RESET}")
    print(f"  Output:      {Colors.BRIGHT_GREEN}{format_token_count(stats['output_tokens']):>8}{Colors.RESET}")
    print(f"  Cache Write: {Colors.BRIGHT_YELLOW}{format_token_count(stats['cache_creation']):>8}{Colors.RESET}")
    print(f"  Cache Read:  {Colors.BRIGHT_MAGENTA}{format_token_count(stats['cache_read']):>8}{Colors.RESET}")
    print(f"  {Colors.BOLD}Total:       {Colors.BRIGHT_WHITE}{format_token_count(total_tokens):>8}{Colors.RESET}")
    if cache_total > 0:
        cache_ratio = (stats['cache_read'] / total_tokens * 100) if total_tokens > 0 else 0
        print(f"  Cache Efficiency: {Colors.BRIGHT_GREEN}{cache_ratio:.1f}%{Colors.RESET}")
    print()
    
    # Cost breakdown
    print(f"{Colors.BRIGHT_WHITE}💰 Cost Analysis{Colors.RESET}")
    print(f"  Total Cost:  {Colors.BRIGHT_YELLOW}${stats['total_cost']:.3f}{Colors.RESET}")
    if stats['sessions'] > 0:
        avg_cost = stats['total_cost'] / stats['sessions']
        print(f"  Avg/Session: {Colors.BRIGHT_WHITE}${avg_cost:.3f}{Colors.RESET}")
    print()
    
    # Projects breakdown
    if len(stats['projects']) > 1:
        print(f"{Colors.BRIGHT_WHITE}📁 Projects{Colors.RESET}")
        for project in sorted(stats['projects']):
            print(f"  • {Colors.BRIGHT_BLUE}{project}{Colors.RESET}")
        print()

def show_usage_help():
    """Show usage help and available commands"""
    print(f"{Colors.BRIGHT_CYAN}statusline - Claude Code Usage Analysis{Colors.RESET}")
    print("=" * 40)
    print()
    print("Usage:")
    print(f"  {Colors.BRIGHT_WHITE}statusline{Colors.RESET}                    # Show current status (default)")
    print(f"  {Colors.BRIGHT_WHITE}statusline daily{Colors.RESET}              # Show today's usage")
    print(f"  {Colors.BRIGHT_WHITE}statusline daily --date YYYY-MM-DD{Colors.RESET}  # Show specific date")
    print(f"  {Colors.BRIGHT_WHITE}statusline --help{Colors.RESET}             # Show this help")
    print()
    print("Examples:")
    print(f"  {Colors.LIGHT_GRAY}statusline daily{Colors.RESET}")
    print(f"  {Colors.LIGHT_GRAY}statusline daily --date 2025-01-15{Colors.RESET}")
    print()

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Claude Code statusline and usage analysis', add_help=False)
    parser.add_argument('command', nargs='?', choices=['daily'], help='Usage analysis command')
    parser.add_argument('--date', type=str, help='Date for analysis (YYYY-MM-DD)')
    parser.add_argument('--help', action='store_true', help='Show help')
    
    try:
        args = parser.parse_args()
    except SystemExit:
        # If parsing fails, assume it's being called as statusline (no args)
        args = argparse.Namespace(command=None, date=None, help=False)
    
    # Handle help
    if args.help:
        show_usage_help()
        sys.exit(0)
    
    # Handle commands
    if args.command == 'daily':
        target_date = None
        if args.date:
            try:
                target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
            except ValueError:
                print(f"{Colors.BRIGHT_RED}Invalid date format. Use YYYY-MM-DD{Colors.RESET}")
                sys.exit(1)
        analyze_daily_usage(target_date)
    else:
        # Default: show current status line
        main()