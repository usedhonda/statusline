# Token Calculation Guide - statusline.py

## CRITICAL: Token Types and Usage

### 📊 2つの異なるトークン累計の定義

#### 1. CURRENT_TRANSCRIPT_TOKENS (現在のトランスクリプト累計)
- **定義**: 現在のJSONLファイル内の全メッセージの累積トークン数
- **範囲**: コンパクション後〜現在まで
- **上限**: 160K程度（コンパクション制限）
- **計算元**: `calculate_tokens_from_transcript(current_file.jsonl)`
- **用途**: Compact行の表示（コンパクション制限との比較）

#### 2. FIVE_HOUR_BLOCK_TOKENS (5時間ブロック累計)  
- **定義**: 現在の5時間ブロック内の全メッセージの累積トークン数
- **範囲**: 5時間ブロック開始〜現在まで
- **上限**: 数百万トークン可能（セッション制限まで）
- **計算元**: `calculate_block_statistics(current_block)`
- **用途**: Burn行の表示（セッション使用量）

### 🚨 絶対に混同してはいけない理由

1. **スケールが違う**: 160K vs 数百万トークン
2. **目的が違う**: コンパクション vs セッション制限
3. **時間範囲が違う**: 最後のコンパクション後 vs 5時間ブロック内

## 表示行の定義

### Line 2: 🪙 Compact
```python
# ALWAYS use FIVE_HOUR_BLOCK_TOKENS for Compact display
compact_tokens = total_tokens  # From 5-hour block calculation
display = f"🪙 Compact: {compact_tokens}/160.0K"
```
- **目的**: コンパクション制限(160K)への進捗表示
- **値**: 5時間ブロック累計
- **理由**: 5時間の中でコンパクションが発生するため

### Line 4: 🔥 Burn  
```python
# ALWAYS use CURRENT_TRANSCRIPT_TOKENS for Burn display
burn_tokens = calculate_true_session_cumulative(session_id)
display = f"🔥 Burn: {burn_tokens} (Rate: {rate}/min)"
```
- **目的**: 現在のトランスクリプト累計とburn rate表示
- **値**: 現在のトランスクリプト累計
- **理由**: burn rateは現在のファイル内の活動を示すため

## 関数の責任分担

### ✅ 正しい使い方

```python
# Compact行用: 5時間ブロック統計から取得
if block_stats:
    compact_tokens = block_stats['total_tokens']  # 5時間ブロック累計

# Burn行用: 現在のトランスクリプトから計算
burn_tokens = calculate_true_session_cumulative(session_id)  # 現在ファイル累計
```

### ❌ 間違った使い方
```python
# これは混乱を招く - 絶対にやらない
compact_tokens = calculate_true_session_cumulative(session_id)  # ❌ 
burn_tokens = block_stats['total_tokens']  # ❌
```

## デバッグ時のチェックポイント

### 値の妥当性確認
1. **Compact値**: 50K〜200K程度が正常
2. **Burn値**: 数万〜数十万程度が正常  
3. **異常**: どちらかが数百万なら計算エラー

### コード確認項目
1. `compact_tokens`の計算元は`block_stats['total_tokens']`か？
2. `burn_tokens`の計算元は`calculate_true_session_cumulative()`か？
3. 変数名は目的を正しく表しているか？

## 変数命名規則 - 正しい概念に基づく命名

### 推奨命名
```python
# 明確な命名（正しい概念）
conversation_compaction_tokens = calculate_current_conversation_tokens(session_id)
billing_window_tokens = block_stats['total_tokens']

# 表示用（正しい割り当て）
compact_display_tokens = conversation_compaction_tokens  # 会話圧縮監視
burn_display_tokens = billing_window_tokens  # 5時間課金ウィンドウ
```

### 避けるべき命名
```python
# 曖昧すぎる
tokens = get_tokens()  # ❌ どのトークン？
total = calculate_total()  # ❌ 何の合計？
session_tokens = get_session()  # ❌ どのセッション？
```

## 実装時のチェックリスト - 正しい概念確認

- [ ] Compact行は現在の会話のトークンのみを使用している（会話圧縮監視）
- [ ] Burn行は5時間課金ウィンドウの累積を使用している（課金追跡）
- [ ] 変数名が正しい概念（圧縮監視 vs 課金追跡）を明確に示している
- [ ] コメントで正しい概念と計算元を明記している
- [ ] 値の妥当性をテストで確認している

## 緊急時の修正手順

1. **症状**: 値が数百万で異常に大きい
2. **原因**: 累積計算の重複またはトークン種別の混同
3. **修正**: 
   - 関数の計算元を確認
   - 変数の代入先を確認  
   - このガイドと照合

---
**重要**: 修正時は必ずこのドキュメントを参照し、2つの累計を混同しないこと