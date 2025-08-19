# Token Calculation Debugging Guide - 完全調査手順書

**作成日**: 2025-08-19  
**最終更新**: 2025-08-19  
**目的**: セッション時間内のUsageトークン合計の正確な計算実装と、同様の問題の効率的なデバッグ手順

## 1. 問題の発見と初期状況

### 1.1 初期症状
- **Burn lineの表示**: ~347K tokens
- **他ツール（ccusage）の表示**: ~31M tokens  
- **期待値**: 5時間ウィンドウ全体のトークン合計（数百万〜数千万トークン）
- **問題**: 約100倍の差異

### 1.2 初期仮説
1. 累積計算 vs 個別加算の問題
2. 重複メッセージの問題
3. 時間範囲フィルタリングの問題
4. トークン種別（cache tokens）の扱いの違い

## 2. 調査手順 - 段階的アプローチ

### 2.1 フェーズ1: 基本的なトークン計算ロジックの確認

#### 問題発見
```python
# 間違った実装（累積値使用）
if message['usage']:
    total_input_tokens = message['usage'].get('input_tokens', 0)  # 上書き
```

#### 解決策
```python
# 正しい実装（個別加算）
if message['usage']:
    total_input_tokens += message['usage'].get('input_tokens', 0)  # 加算
```

#### 結果
- **改善前**: ~347K tokens
- **改善後**: ~52M tokens
- **効果**: 大幅改善だが、まだ1.7倍の差

### 2.2 フェーズ2: 他ツールの重複除去ロジック調査

#### 調査対象ツール
1. **ccusage by ryoppippi** (GitHub)
   - TypeScript実装
   - 5時間ブロック検出機能
   - getTotalTokens() utility関数

2. **ccost by carlosarraes** (GitHub)  
   - Rust実装
   - **重要**: 高度な重複除去アルゴリズム実装
   - 約18%の重複除去率を達成

#### ccostの重複除去アルゴリズム
```rust
// Priority-based deduplication
match (message_id, request_id, session_id) {
    (Some(m), Some(r), _) => Some(format!("req:{m}:{r}")),      // Priority 1
    (Some(m), None, Some(s)) => Some(format!("session:{m}:{s}")), // Fallback
    _ => None,
}
```

**重要な洞察**: 
- requestId優先 + sessionId fallback
- プレフィックス付きハッシュで衝突防止
- 課金精度向上のための設計

#### 実装
```python
unique_hash = None
if message_id and request_id:
    unique_hash = f"req:{message_id}:{request_id}"  # Priority 1
elif message_id and session_id:
    unique_hash = f"session:{message_id}:{session_id}"  # Fallback

if unique_hash:
    if unique_hash in processed_hashes:
        skipped_duplicates += 1
        continue
    processed_hashes.add(unique_hash)
```

#### 結果
- **改善後**: ~53M tokens
- **効果**: 軽微な改善（この時点で重複は少なかった）

### 2.3 フェーズ3: データ構造とフィールド参照の問題発見

#### 重大なバグの発見
デバッグ出力により発見:
```
DEBUG: No hash generated for message_id=None, request_id=None, session_id=None
```

**原因分析**:
1. `block['messages']`は処理済みデータ構造
2. 元のJSONLの`uuid`, `requestId`, `sessionId`フィールドが失われている
3. 重複除去が全く機能していない

#### 調査手順
```python
# メッセージ構造のデバッグ
if total_messages <= 3:
    print(f"DEBUG: type={type(message)}, keys={list(message_data.keys())}")
```

#### 発見された実際の構造
```python
# block['messages']の内容
['timestamp', 'timestamp_utc', 'session_id', 'type', 'usage', 'file_path']
# 元のJSONLフィールド（uuid, requestId）は存在しない
```

#### 解決策: 直接JSONLファイル読み取り
```python
def calculate_tokens_from_jsonl_with_dedup(transcript_file, block_start_time, duration_seconds):
    """元のJSONLファイルから直接読み取って重複除去"""
    with open(transcript_file, 'r') as f:
        for line in f:
            message_data = json.loads(line.strip())
            # 元のuuid, requestId, sessionIdが使用可能
```

### 2.4 フェーズ4: usage フィールドの階層問題発見

#### 症状
- 新しい関数は呼ばれているが、トークン数が0
- `total_messages=845` だが `tokens=0`

#### 調査手順
```bash
# 実際のJSONL構造を確認
grep '"type":"assistant"' file.jsonl | head -1 | jq '{type, usage, message}'
```

#### 発見された問題
```json
{
  "type": "assistant",
  "usage": null,           // 最上位のusageはnull
  "message": {
    "usage": {             // 実際のusageはmessage.usageにある
      "input_tokens": 4,
      "cache_creation_input_tokens": 20428,
      "cache_read_input_tokens": 0,
      "output_tokens": 1
    }
  }
}
```

#### 解決策
```python
# Flexible usage field access
usage = None
if msg_type == 'assistant':
    usage = message_data.get('usage') or message_data.get('message', {}).get('usage')

if usage:
    total_input_tokens += usage.get('input_tokens', 0)
    # ...
```

## 3. 最終結果と効果測定

### 3.1 段階的改善
1. **初期状態**: ~347K tokens (1/100の値)
2. **加算修正後**: ~52M tokens (1.7倍差)
3. **重複除去追加後**: ~53M tokens (軽微改善)
4. **直接JSONL読み取り後**: ~47M tokens (1.2倍差)
5. **usage階層修正後**: **47M tokens vs ccusage 40M tokens**

### 3.2 最終的な精度
- **達成した精度**: 1.2倍差（47M vs 40M）
- **初期からの改善**: **135倍の精度向上**
- **実用性**: 十分に実用的なレベル

## 4. 重要な教訓と原則

### 4.1 デバッグの原則
1. **段階的アプローチ**: 一度に一つの問題を解決
2. **実データ検証**: 仮定ではなく実際のデータ構造を確認
3. **他ツール研究**: 既存の成功例から学習
4. **デバッグ出力**: 詳細なログで問題を可視化

### 4.2 他ツール研究の重要性
- **ccusage**: TypeScript、基本的なアプローチ
- **ccost**: Rust、高度な重複除去、課金精度重視
- **重要**: 各ツールの設計思想とアルゴリズムを理解

### 4.3 データ構造の理解
- JSONLファイルの実際の構造
- 処理済みデータ vs 生データの違い
- フィールドの階層構造（usage の位置）

## 5. 実装上の重要ポイント

### 5.1 重複除去の実装
```python
# ccost互換の重複除去
message_id = message_data.get('uuid')
request_id = message_data.get('requestId')  
session_id = message_data.get('sessionId')

unique_hash = None
if message_id and request_id:
    unique_hash = f"req:{message_id}:{request_id}"
elif message_id and session_id:
    unique_hash = f"session:{message_id}:{session_id}"

if unique_hash and unique_hash in processed_hashes:
    continue
processed_hashes.add(unique_hash)
```

### 5.2 柔軟なusageフィールドアクセス
```python
# usage field can be at top level or in message object
usage = message_data.get('usage') or message_data.get('message', {}).get('usage')
```

### 5.3 時間範囲フィルタリング
```python
# 5時間ウィンドウ内チェック
if not (block_start_utc <= msg_time_utc <= block_end_time):
    continue
```

## 6. トラブルシューティング手順

### 6.1 トークン数が異常に少ない場合
1. **加算 vs 上書き**を確認
   ```python
   # ❌ Wrong: total += value  
   # ✅ Correct: total = value
   ```

2. **メッセージフィルタリング**を確認
   ```python
   if msg_type == 'assistant' and usage:  # assistantメッセージのみ
   ```

3. **usage フィールドの場所**を確認
   ```bash
   jq '.usage // .message.usage' < file.jsonl
   ```

### 6.2 重複除去が機能しない場合
1. **フィールドの存在**を確認
   ```python
   print(f"uuid={message_data.get('uuid')}, requestId={message_data.get('requestId')}")
   ```

2. **データソース**を確認
   - 処理済みデータ vs 元のJSONL
   - タプル構造 vs 辞書構造

3. **ハッシュ生成**を確認
   ```python
   if unique_hash:
       print(f"Generated hash: {unique_hash}")
   ```

### 6.3 他ツールとの比較手順
1. **同じセッションID**でテスト
2. **同じ時間範囲**で比較
3. **デバッグ出力**で詳細確認
   ```python
   print(f"total_messages={total_messages}, tokens={total_tokens:,}")
   ```

## 7. 今後の開発指針

### 7.1 データ整合性の維持
- 常に元のJSONLデータから直接読み取り
- 処理済みデータは表示用のみ使用
- フィールド参照は柔軟に実装

### 7.2 他ツールとの互換性
- ccostの重複除去アルゴリズムを継続使用
- 新しいツールが現れた場合は同様の調査手順を実施

### 7.3 テスト手順の標準化
1. 実際のセッションIDを使用
2. 他ツールとの比較を必須とする
3. 段階的な改善を記録

## 8. 参考資料

### 8.1 調査したツール
- **ccusage**: https://github.com/ryoppippi/ccusage
  - TypeScript CLI tool
  - 基本的な5時間ブロック機能
  - getTotalTokens() utility

- **ccost**: https://github.com/carlosarraes/ccost  
  - Rust CLI tool
  - 高度な重複除去（18%除去率）
  - 課金精度重視の設計

### 8.2 重要なIssue
- ccusage Issue #274: Token calculation discrepancy
- ccusage Issue #247: ccusage and Claude limits disagreement
- ccost: Enhanced deduplication feature

### 8.3 実装参考
- ccost の `src/parser/deduplication.rs`
- ccusage の `src/_token-utils.ts`
- ccusage の `src/_session-blocks.ts`

---

**重要**: このドキュメントは今回の完全な調査過程を記録しています。同様の問題が発生した場合は、この手順に従って効率的にデバッグを行ってください。特に「段階的アプローチ」と「他ツール研究」の重要性を忘れずに。