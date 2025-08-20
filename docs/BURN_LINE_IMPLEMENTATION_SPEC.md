# Burn Line Implementation Specification

**作成日**: 2025-08-19  
**最終更新**: 2025-08-19  
**目的**: Burn line（4行目）の5時間ウィンドウ全体対応実装

## 1. 概要

### 1.1 Burn行の役割
```
🔥 Burn:    ▁▁█▂▁▁▅█▁▁▁▁▁▁▃▁▁▁▁▁ 1,639,577 token(w/cache), Rate: 6,419 t/m
```

- **スパークライン**: 5時間ウィンドウ全体の15分間隔トークン消費グラフ
- **トークン数**: 現在セッションの累積トークン数
- **レート**: 現在セッションの分あたりトークン消費率
- **データソース**: Session lineと同じ5時間ウィンドウデータ

### 1.2 Session lineとの整合性
- **時間軸統一**: Session line（3行目）と同じ5時間ウィンドウを使用
- **データソース統一**: `detect_five_hour_blocks()` → `current_block['messages']`
- **リアルタイム更新**: 15分セグメント毎のトークン集計

## 2. 実装アーキテクチャ

### 2.1 データフロー
```python
main()
  → detect_five_hour_blocks(all_messages)           # 5時間ウィンドウ検出
  → find_current_session_block(blocks, session_id)  # 現在ブロック特定
  → calculate_block_statistics(current_block)       # ブロック統計計算
  → get_burn_line(session_data, session_id, block_stats, current_block)
    → generate_real_burn_timeline(block_stats, current_block)  # グラフ生成
    → create_sparkline(burn_timeline)               # スパークライン描画
```

### 2.2 主要関数

#### generate_real_burn_timeline(block_stats, current_block)
```python
def generate_real_burn_timeline(block_stats, current_block):
    """5時間ウィンドウ全体のトークン消費を15分間隔で集計"""
    timeline = [0] * 20  # 20セグメント（各15分）
    
    # 5時間ウィンドウ内の全メッセージを処理
    for message in current_block['messages']:
        if message.get('type') == 'assistant' and message.get('usage'):
            # メッセージ時刻からセグメントindex計算
            segment_index = int(elapsed_minutes / 15)
            if 0 <= segment_index < 20:
                tokens = get_total_tokens(message['usage'])
                timeline[segment_index] += tokens
    
    return timeline
```

#### get_burn_line(current_session_data, session_id, block_stats, current_block)
```python
def get_burn_line(current_session_data, session_id, block_stats, current_block):
    """Burn line表示生成"""
    # 現在セッションのトークン数とレート計算
    session_tokens = current_session_data.get('total_tokens', 0)
    burn_rate = (session_tokens / duration_seconds) * 60 if duration_seconds > 0 else 0
    
    # 5時間ウィンドウ全体のスパークライン生成
    burn_timeline = generate_real_burn_timeline(block_stats, current_block)
    sparkline = create_sparkline(burn_timeline, width=20)
    
    return f"🔥 Burn:    {sparkline} {session_tokens:,} token(w/cache), Rate: {burn_rate:,.0f} t/m"
```

## 3. 時間セグメント処理

### 3.1 15分間隔分割
- **総セグメント数**: 20個（5時間 ÷ 15分 = 20）
- **セグメント計算**: `segment_index = int(elapsed_minutes / 15)`
- **時間範囲**: ブロック開始時刻から現在時刻まで

### 3.2 UTC統一処理
```python
# 内部計算は全てUTCで統一
if hasattr(block_start, 'tzinfo') and block_start.tzinfo:
    block_start_utc = block_start.astimezone(timezone.utc).replace(tzinfo=None)
else:
    block_start_utc = block_start

# メッセージタイムスタンプもUTCに統一
if hasattr(msg_time, 'tzinfo') and msg_time.tzinfo:
    msg_time_utc = msg_time.astimezone(timezone.utc).replace(tzinfo=None)
else:
    msg_time_utc = msg_time
```

### 3.3 リアルタイム対応
```python
# 現在進行中のセグメントに部分的な値を設定
current_segment_index = int(current_elapsed_minutes / 15)
segment_progress = (current_elapsed_minutes % 15) / 15.0

if 0 <= current_segment_index < 20:
    if timeline[current_segment_index] == 0 and segment_progress > 0.1:
        # 10%以上進行している場合は最小値を設定
        timeline[current_segment_index] = int(100 * segment_progress)
```

## 4. データソース統合

### 4.1 Session lineとの整合性確保
**修正前の問題**:
- Session line: 5時間ウィンドウ全体の統計
- Burn line: 現在セッションのtranscriptファイルのみ

**修正後の解決**:
- Session line: `current_block['messages']` から統計計算
- Burn line: 同じ `current_block['messages']` からグラフ生成

### 4.2 メッセージフィルタリング
```python
# assistantメッセージのusageデータのみ処理
if message.get('type') != 'assistant' or not message.get('usage'):
    continue

# 5時間ウィンドウ内の時間範囲チェック
elapsed_minutes = (msg_time_utc - block_start_utc).total_seconds() / 60
if elapsed_minutes < 0 or elapsed_minutes >= 300:  # 5時間 = 300分
    continue
```

## 5. スパークライン表示

### 5.1 Unicode文字使用
```python
# Unicode block characters for sparkline
chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
```

### 5.2 値の正規化
```python
# 最大値で正規化してスケール調整
max_val = max(values) if values else 1
normalized = [int((v / max_val) * (len(chars) - 1)) for v in values]
```

### 5.3 色分け
- **高活動**: 赤系 (`Colors.BRIGHT_RED`)
- **中活動**: 緑系 (`Colors.BRIGHT_GREEN`) 
- **低活動**: グレー系 (`Colors.LIGHT_GRAY`)

## 6. パフォーマンス特性

### 6.1 処理効率
- **時間計算**: O(1) 数学計算
- **メッセージ処理**: O(n) nは5時間ウィンドウ内メッセージ数
- **セグメント集計**: O(1) 配列アクセス

### 6.2 メモリ使用量
- **タイムライン配列**: 20 integers = 160 bytes
- **メッセージデータ**: 既存のcurrent_blockを参照使用
- **追加メモリ**: 最小限

### 6.3 リアルタイム性
- **更新頻度**: メッセージ毎
- **描画遅延**: <10ms
- **データ同期**: Session lineと完全同期

## 7. エラーハンドリング

### 7.1 データ不整合対応
```python
if not block_stats or not current_block or 'messages' not in current_block:
    return [0] * 20  # 空のタイムライン返却
```

### 7.2 タイムスタンプエラー処理
```python
try:
    # タイムスタンプ処理
    elapsed_minutes = (msg_time_utc - block_start_utc).total_seconds() / 60
except (ValueError, KeyError, TypeError):
    continue  # 無効なメッセージをスキップ
```

### 7.3 フォールバック表示
```python
except Exception:
    return f"{Colors.BRIGHT_CYAN}🔥 Burn: {Colors.RESET}   {Colors.BRIGHT_WHITE}ERROR{Colors.RESET}"
```

## 8. 検証・テスト

### 8.1 データ整合性確認
```bash
# デバッグモードで確認
echo '{"session_id":"test","..."}' | ~/.claude/statusline.py 2>/tmp/debug.log
```

### 8.2 期待される出力例
```
DEBUG Burn: total_messages=1702, assistant_with_usage=985, processed=985
DEBUG Burn: block_start=2025-08-18 12:00:00, current_elapsed_min=563.5
DEBUG Burn: timeline_nonzero=[(0, 966670), (1, 88980), (3, 871343), ...]
```

### 8.3 整合性チェックポイント
- Session line進捗とBurn lineグラフの時間軸一致
- 5時間ウィンドウ全体のデータ使用確認
- リアルタイム更新の動作確認

## 9. 実装完了基準

### 9.1 機能要件
- ✅ 5時間ウィンドウ全体のデータ使用
- ✅ Session lineとの時間軸統合
- ✅ 15分間隔での正確なセグメント分割
- ✅ リアルタイム進行中セグメント表示

### 9.2 性能要件
- ✅ メッセージ処理速度 <100ms
- ✅ メモリ使用量 最小限
- ✅ UI応答性 良好

### 9.3 保守性要件
- ✅ コードコメント充実
- ✅ エラーハンドリング完備
- ✅ デバッグ情報対応

---

**実装完了**: 2025-08-19  
**主要改善**: Session lineとBurn lineの完全データ統合  
**次回開発**: このドキュメントを参照して継続開発