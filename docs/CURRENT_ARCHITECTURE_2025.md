# Current Architecture Documentation (2025)

## システム概要

Statuslineは**2つの独立したトークン追跡システム**を提供します：

### 🗜️ システム1: 会話圧縮監視 (Compact Line)
- **表示**: Line 2 - `🪙  Compact: 140.5K/160.0K`
- **目的**: 現在の会話が160K圧縮閾値に到達するタイミングを監視
- **データ源**: 現在の会話セッションのトークン
- **リセット**: 会話が圧縮される時

### 🕐 システム2: 5時間課金ウィンドウ (Session/Burn Lines)
- **表示**: Line 3-4 - `⏱️ Session` + `🔥 Burn`
- **目的**: Claude Code公式の5時間課金期間を追跡
- **データ源**: 5時間ウィンドウ内の全セッション
- **リセット**: 5時間毎 (Claude Code公式仕様)

## 詳細実装

### データフロー

#### Compact Line (Line 2) 処理
```python
# メイン処理フロー
main() 
  → detect_five_hour_blocks()      # 5時間ウィンドウ検出
  → calculate_block_statistics()   # ウィンドウ統計計算
  → total_tokens = block_stats['total_tokens']  # 現在の実装
  → percentage = (total_tokens / COMPACTION_THRESHOLD) * 100
  → 🪙 Compact表示
```

**注意**: 現在の実装では5時間ウィンドウのデータを使用していますが、本来は現在の会話のみを追跡すべきです。

#### Session/Burn Lines (Lines 3-4) 処理  
```python
# Session Line (Line 3) - ハイライト機能付き
block_stats['duration_seconds'] → session_duration
block_stats['start_time'] → session_start_time
block_progress = (hours_elapsed % 5) / 5 * 100
session_bar = get_progress_bar(block_progress, show_current_segment=True)
⏱️ Session表示 (現在セグメントを白く強調)

# Burn Line (Line 4) - 5時間ウィンドウ統合  
generate_real_burn_timeline(block_stats, current_block) → burn_timeline
create_sparkline(burn_timeline) → スパークライン
🔥 Burn表示 + 5時間ウィンドウ全体のスパークライン
```

### 動的位置揃えシステム

#### calculate_dynamic_padding()
```python
def calculate_dynamic_padding(compact_text, session_text):
    # ANSI色コード除去
    clean_compact = re.sub(r'\x1b\[[0-9;]*m', '', compact_text)
    clean_session = re.sub(r'\x1b\[[0-9;]*m', '', session_text)
    
    # 長さ差分計算 + 視覚調整
    if session_len < compact_len:
        return ' ' * (compact_len - session_len + 1)  # +1 for visual adjustment
```

#### 適用箇所
- Line 2/3のプログレスバー位置揃え
- 可変長テキスト対応 (`1m` → `23h59m`)
- Line 4の数値位置調整 (`🔥 Burn:    numbers`)

### Claude Code JSONL統合

#### データ構造理解
```python
# 各メッセージのusage = そのメッセージ時点での累積値
message_usage = {
    "input_tokens": 5,              # 新規入力
    "output_tokens": 267,           # 新規出力  
    "cache_creation_input_tokens": 748,    # 新規キャッシュ作成
    "cache_read_input_tokens": 80473       # キャッシュ再利用
}
# 合計: 81,493トークン (98%がキャッシュ再利用)
```

#### コスト計算の現実
```python
# 典型的なコスト内訳 (Claude Sonnet 4)
input_cost = (5 * $3.00) / 1M = $0.000015
output_cost = (267 * $15.00) / 1M = $0.004005
cache_creation = (748 * $3.75) / 1M = $0.002805
cache_read = (80473 * $0.30) / 1M = $0.024142
# 合計: $0.031 (98%がキャッシュ読み取りのため安価)
```

### 重要な関数マップ

#### 5時間ウィンドウ関連
```python
detect_five_hour_blocks()
├── Purpose: Claude Code 5時間課金ウィンドウ検出
├── Input: all_messages (全プロジェクト)
├── Output: 5時間ブロックリスト
└── Used by: Session/Burn lines

calculate_block_statistics()
├── Purpose: 5時間ウィンドウの統計計算
├── Input: 5時間ブロック
├── Output: 累積トークン・メッセージ数
└── Used by: Both systems (要改善)
```

#### セッション関連
```python
calculate_tokens_since_time()
├── Purpose: 指定時刻からのトークン計算
├── Input: session_id, start_time
├── Output: セッション累積トークン
└── Used by: Burn line

get_burn_line()
├── Purpose: 🔥 Burn line生成
├── Input: session_data, session_id
├── Output: フォーマット済み表示
└── Features: sparkline, burn rate
```

#### UI関連
```python
get_progress_bar()
├── Purpose: プログレスバー生成（ハイライト機能付き）
├── Input: percentage, width, show_current_segment
├── Output: Unicode progress bar (現在セグメント強調可能)
└── Used by: Lines 2, 3 (Line 3では現在セグメント強調)

create_sparkline()
├── Purpose: Unicode sparkline生成
├── Input: values, width
├── Output: ▁▂▃▄▅▆▇█ visualization
└── Used by: Burn line
```

## 設定とインストール

### 自動インストール
```bash
cd statusline
python3 install.py
```

### 手動設定
```json
# ~/.claude/settings.json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline.py",
    "padding": 0
  }
}
```

### 環境変数 (オプション)
```bash
export CLAUDE_PROJECTS_DIR="/custom/path/to/projects"
export CLAUDE_CACHE_DIR="/custom/path/to/cache"
export STATUSLINE_MODE="multi"  # single|multi
```

## トラブルシューティング

### 一般的な問題

#### 1. データが表示されない
- Claude Codeセッションが実行中か確認
- `~/.claude/projects/*/session-id.jsonl` ファイルの存在確認
- Python 3.7+ の確認

#### 2. 時間が正しくない
- トランスクリプトのタイムスタンプがローカルタイムゾーンに変換済み
- 5時間ブロックは標準化された課金分析用

#### 3. プログレスバーのずれ
- 動的パディングが自動調整
- 極端に長い文字列の場合は微調整が必要

#### 4. コストが安すぎる
- 正常: 98-99%がキャッシュ再利用
- 新規処理は数百トークンレベル
- $0.03-0.05は典型的

### ログ確認
```bash
tail -f ~/.claude/statusline-error.log
```

## 開発者向け注意事項

### 絶対に守るべき原則
1. **概念分離**: Compact ≠ Session/Burn
2. **動的対応**: 固定スペースの使用禁止
3. **テスト後報告**: 推測での成功報告禁止
4. **既存機能保護**: 動作する機能の削除禁止

### 改善が必要な箇所
1. **Compact Line**: 5時間ウィンドウデータではなく会話データを使用
2. **エラーハンドリング**: より詳細なエラー情報
3. **設定ファイル**: より柔軟な設定オプション
4. **テストスイート**: 自動テストの追加

### 最新の改善完了事項 (2025-08-19)
1. ✅ **Burn Line統合**: Session lineと同じ5時間ウィンドウデータを使用
2. ✅ **現在セグメント強調**: Session lineで進行中セグメントを白くハイライト
3. ✅ **データソース統一**: current_block['messages']で完全統合
4. ✅ **リアルタイム同期**: Session/Burn lineの完全時間軸一致

### 拡張ポイント
1. **新しい表示モード**: 1行版、簡易版
2. **アラート機能**: 閾値到達時の通知
3. **ログ分析**: 詳細な使用パターン分析
4. **GUI版**: Webベースのダッシュボード