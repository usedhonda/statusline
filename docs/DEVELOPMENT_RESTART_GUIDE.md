# Statusline Development Restart Guide

**最終更新**: 2025-08-19  
**目的**: 開発再開時に必要な情報をすべて集約

## 📋 開発再開前に必読

この文書を読むことで、statuslineプロジェクトの現在の状態と今後の開発継続に必要な知識をすべて把握できます。

## 🎯 現在の状態 (2025-08-19時点)

### ✅ 完全に実装済みの機能

1. **Burn Line統合完了** (最重要)
   - Session line（3行目）とBurn line（4行目）が同じ5時間ウィンドウデータを使用
   - `generate_real_burn_timeline(block_stats, current_block)`で完全統合
   - 以前の問題：Burn lineが現在セッションのみ → 解決済み

2. **Session Line視覚強化**
   - 現在進行中セグメントを白い`▓`でハイライト
   - `get_progress_bar(show_current_segment=True)`機能追加
   - 経過済み部分の色は保持

3. **データ統合アーキテクチャ**
   - `detect_five_hour_blocks()` → `current_block['messages']` で一元管理
   - Session/Burn line共通データソース確立
   - リアルタイム同期完全実現

### 📊 検証済み動作状況
```
🔥 Burn:    ▁▁█▂▁▁▅█▁▁▁▁▁▁▃▁▁▁▁▁ 1,639,577 token(w/cache), Rate: 6,419 t/m
⏱️  Session: █████████████████▓▒▒ [85%] 4h15m/5h 17:15 (13:00 to 18:00)
```
- 5時間ウィンドウ内1,702メッセージ中985件を正常処理
- 18セグメント（15分間隔）適切分散
- Session進捗とBurnグラフの完全一致

## 🏗️ アーキテクチャ概要

### 2つの独立システム
1. **🗜️ Compact Line** (Line 2): 会話圧縮監視 (160K閾値)
2. **🕐 Session/Burn** (Lines 3-4): 5時間課金ウィンドウ追跡

### 主要データフロー
```python
main()
  → load_all_messages_chronologically()        # 全プロジェクト横断
  → detect_five_hour_blocks(all_messages)      # 5時間ウィンドウ分割
  → find_current_session_block(blocks)         # 現在ブロック特定
  → calculate_block_statistics(current_block)  # 統計計算
  
  # Session Line (3行目)
  → get_progress_bar(block_progress, show_current_segment=True)
  
  # Burn Line (4行目)  
  → get_burn_line(session_data, session_id, block_stats, current_block)
    → generate_real_burn_timeline(block_stats, current_block)
    → create_sparkline(burn_timeline)
```

## 📁 ドキュメント構成

### 必読ファイル
1. **`CURRENT_ARCHITECTURE_2025.md`** - システム全体の構造理解
2. **`BURN_LINE_IMPLEMENTATION_SPEC.md`** - Burn line実装の詳細仕様  
3. **`DEVELOPMENT_SUMMARY_2025.md`** - これまでの開発経緯
4. **`TOKEN_CALCULATION_GUIDE.md`** - トークン計算ロジック

### このファイルの位置づけ
- 開発再開時の最初の読み物
- 他ドキュメントへのナビゲーション
- 現在の完成度と今後の方針

## 🔧 開発環境セットアップ

### 基本的な動作確認
```bash
# 1. リポジトリ状態確認
cd /Users/usedhonda/projects/statusline
git status
git log --oneline -5

# 2. 実動作テスト
echo '{"session_id":"test","workspace":{"directory":"./","active_files":[]}}' | ~/.claude/statusline.py

# 3. エラーログ確認
tail -f ~/.claude/statusline-error.log
```

### デバッグモード
```bash
# デバッグ情報出力
echo '{"session_id":"real_session_id","..."}' | ~/.claude/statusline.py 2>/tmp/debug.log
cat /tmp/debug.log
```

## 🚨 絶対に守るべきルール

### 概念分離の厳守
1. **Compact Line**: 会話圧縮監視専用 (現在は5時間データ使用だが本来は会話データ)
2. **Session/Burn**: 5時間課金ウィンドウ専用 (完全統合済み)
3. **データソース混同禁止**: この2つは完全に別概念

### データ統合の維持
- Session/Burn lineは必ず同じ`current_block['messages']`を使用
- `generate_real_burn_timeline()`は5時間ウィンドウ全体を処理
- 単一セッションのtranscriptファイルのみの使用は禁止

### UI一貫性
- Session lineの現在セグメント強調を維持
- 動的パディング機能を保持
- 既存の動作する機能の削除禁止

## 🛠️ 主要関数リファレンス

### データ取得・処理
```python
load_all_messages_chronologically()     # 全プロジェクトのメッセージ読み込み
detect_five_hour_blocks(all_messages)   # 5時間ウィンドウ分割
find_current_session_block(blocks, id)  # 現在ブロック特定
calculate_block_statistics(block)       # ブロック統計計算
```

### 表示生成
```python
get_progress_bar(%, width, show_current_segment)  # プログレスバー生成
generate_real_burn_timeline(stats, block)        # Burn timeline生成
create_sparkline(values, width)                  # スパークライン描画
get_burn_line(data, id, stats, block)           # Burn line完全生成
```

### ユーティリティ
```python
get_total_tokens(usage)              # 全タイプトークン合計
calculate_dynamic_padding(text1, text2)  # 動的位置揃え
get_time_info()                     # 時刻情報取得
```

## 📈 今後の開発方針

### 優先度：高
1. **Compact Line修正**: 5時間データではなく実際の会話データ使用
2. **エラーハンドリング強化**: より詳細な診断情報
3. **設定システム拡張**: 柔軟なカスタマイズ対応

### 優先度：中
1. **自動テストスイート**: リグレッション防止
2. **パフォーマンス最適化**: 大量メッセージ対応
3. **新表示モード**: 1行版、簡易版

### 優先度：低
1. **GUI版**: Webダッシュボード
2. **アラート機能**: 閾値通知
3. **ログ分析**: 使用パターン解析

## ⚠️ 修正禁止事項

### データ統合を破壊する変更
- `generate_real_burn_timeline()`を単一セッション処理に戻す
- Session/Burn lineで異なるデータソースを使用
- `current_block['messages']`以外のデータ使用

### UI一貫性を破壊する変更
- Session lineの現在セグメント強調機能削除
- 動的パディング機能の削除
- 経過済みセグメントの色変更

### 概念を混同する変更
- CompactとSession概念の混同
- 圧縮監視と課金ウィンドウ追跡の混同

## 🔄 開発ワークフロー

### 機能追加時
1. この文書で現在の状態を確認
2. `CURRENT_ARCHITECTURE_2025.md`でアーキテクチャ理解
3. 該当する仕様書（`BURN_LINE_IMPLEMENTATION_SPEC.md`等）確認
4. 実装・テスト
5. ドキュメント更新

### バグ修正時
1. `~/.claude/statusline-error.log`でエラー確認
2. デバッグモードで詳細調査
3. 関連仕様書で正常動作確認
4. 修正・テスト
5. 検証結果をドキュメントに反映

### リファクタリング時
1. 絶対に守るべきルール確認
2. 既存機能の動作確認
3. データ統合の維持確認
4. 段階的変更でリグレッション防止

## 📞 トラブルシューティング

### よくある問題
1. **Burn lineグラフが空**: current_blockの受け渡し確認
2. **Session/Burn不一致**: データソース統一確認  
3. **時間軸ずれ**: UTC統一処理確認
4. **プログレスバー位置ずれ**: 動的パディング確認

### デバッグ手順
1. エラーログ確認
2. デバッグモード実行
3. メッセージ数・処理数確認
4. タイムライン生成状況確認
5. 仕様書と実装の照合

---

**この文書を読み終えたら、statuslineプロジェクトの現在の状態を完全に把握し、効率的な開発継続が可能になります。**

**次のアクション**: 具体的な開発タスクに応じて上記の該当する仕様書を参照してください。