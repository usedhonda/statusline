# Multi-Tool Compatibility Debugging Guide

**作成日**: 2025-08-20  
**目的**: statusline vs ccusage トークン差異解決で確立された再利用可能な手法の文書化  
**適用範囲**: 任意の外部ツールとの互換性問題デバッグ

## 1. 概要

### 1.1 ガイドの目的
外部ツール（ccusageなど）と内部ツール（statuslineなど）の間で計算結果に大きな差異が発生した場合の体系的デバッグ手法。

### 1.2 今回のケースサマリー
- **問題**: statusline 96.7M tokens vs ccusage 59.7M tokens（62%差異）
- **根本原因**: キャッシュトークンの二重カウント + 重複処理不足
- **最終結果**: 13.9%差異まで改善（76%の精度向上）

## 2. 段階的デバッグ戦略

### 2.1 Phase 1: 問題の定量化と範囲特定
```bash
# 1. 正確な数値の取得
ccusage_tokens=$(npx ccusage@latest blocks --json | jq -r '.blocks[] | select(.isActive == true) | .totalTokens')
statusline_tokens=$(echo '{"session_id":"test"}' | python3 statusline.py --show 4 2>/dev/null | grep -o '[0-9,]*' | head -1 | tr -d ',')

# 2. 差異率の計算
echo "ccusage: $ccusage_tokens"
echo "statusline: $statusline_tokens" 
echo "Difference: $(( statusline_tokens - ccusage_tokens ))"
echo "Percentage: $(echo "scale=1; ($statusline_tokens - $ccusage_tokens) * 100 / $ccusage_tokens" | bc)%"
```

#### チェックポイント
- [ ] 両ツールが同じ時間窓を使用しているか
- [ ] データソース（transcript files）が同じか  
- [ ] 基本的な計算ロジックの違いがあるか

### 2.2 Phase 2: 外部ツールの逆エンジニアリング

#### 2.2.1 ソースコード解析（例：ccusage）
```bash
# GitHub上のソースコード取得
git clone https://github.com/ryoppippi/ccusage.git /tmp/ccusage_analysis

# 重要ファイルの特定
find /tmp/ccusage_analysis -name "*.ts" -o -name "*.js" | grep -E "(token|usage|calculate)"
```

#### 2.2.2 重要な関数・アルゴリズムの特定
```typescript
// 例：ccusageのgetTotalTokens関数
export function getTotalTokens(tokenCounts: AnyTokenCounts): number {
    const cacheCreation = 'cacheCreationInputTokens' in tokenCounts
        ? tokenCounts.cacheCreationInputTokens
        : tokenCounts.cacheCreationTokens;

    const cacheRead = 'cacheReadInputTokens' in tokenCounts
        ? tokenCounts.cacheReadInputTokens
        : tokenCounts.cacheReadTokens;

    return (
        tokenCounts.inputTokens
        + tokenCounts.outputTokens
        + cacheCreation
        + cacheRead
    );
}
```

#### チェックポイント
- [ ] 外部ツールの正確なアルゴリズムを理解したか
- [ ] フィールド名のマッピングパターンを特定したか
- [ ] 条件分岐のロジックを把握したか

### 2.3 Phase 3: データ構造の詳細分析

#### 2.3.1 実際のJSONLファイル分析
```bash
# transcript filesの詳細検査
find ~/.claude/projects/ -name "*.jsonl" -exec jq -r '.usage | keys[]' {} \; | sort | uniq -c

# 問題のあるデータ構造例を特定  
jq '.usage | select(.cache_creation_input_tokens != null and .cache_creation != null)' ~/.claude/projects/*/*.jsonl | head -5
```

#### 2.3.2 フィールドアクセスパターンの比較
```json
// 実際のデータ例
{
  "usage": {
    "input_tokens": 10,
    "cache_creation_input_tokens": 10052,    // ← 直接フィールド
    "cache_read_input_tokens": 12000,
    "cache_creation": {                      // ← ネストされたオブジェクト
      "ephemeral_5m_input_tokens": 10052,    // ← 同じ値！
      "ephemeral_1h_input_tokens": 0
    },
    "output_tokens": 411
  }
}
```

#### チェックポイント
- [ ] 複数フィールドが同じ値を持つケースを特定したか
- [ ] ネストされた構造vs直接アクセスの違いを把握したか
- [ ] 実データでの出現頻度を測定したか

### 2.4 Phase 4: 体系的デバッグ実装

#### 2.4.1 比較実装の作成
```python
def get_total_tokens_original(usage_data):
    """現在の実装（問題あり）"""
    cache_creation = (
        usage_data.get('cache_creation_input_tokens', 0) or
        usage_data.get('cache_creation', {}).get('ephemeral_5m_input_tokens', 0)
    )
    return input_tokens + output_tokens + cache_creation + cache_read

def get_total_tokens_ccusage_compatible(usage_data):
    """ccusage互換実装"""
    if 'cache_creation_input_tokens' in usage_data:
        cache_creation = usage_data['cache_creation_input_tokens']
    else:
        cache_creation = usage_data.get('cache_creation', {}).get('ephemeral_5m_input_tokens', 0)
    return input_tokens + output_tokens + cache_creation + cache_read
```

#### 2.4.2 サンプルデータでの検証
```python
# 統制されたテストケース
test_cases = [
    {
        "usage": {
            "input_tokens": 100,
            "output_tokens": 200,
            "cache_creation_input_tokens": 1000,
            "cache_creation": {"ephemeral_5m_input_tokens": 1000}  # 同じ値
        }
    }
]

for case in test_cases:
    original = get_total_tokens_original(case["usage"])
    compatible = get_total_tokens_ccusage_compatible(case["usage"]) 
    print(f"Original: {original}, Compatible: {compatible}, Diff: {original - compatible}")
```

#### チェックポイント
- [ ] 制御されたテストケースで差異を再現できるか
- [ ] 修正版が期待通りの結果を出すか
- [ ] エッジケースでも正しく動作するか

## 3. マルチエージェント戦略

### 3.1 専門エージェントの効果的活用

#### 3.1.1 エージェント役割分担
```
ccusage-analyzer     → 外部ツールの逆エンジニアリング専門
claude-data-specialist → データ構造分析専門  
algorithm-debugger   → 体系的デバッグ専門
statusline-optimizer → 実装修正専門
```

#### 3.1.2 並行実行の利点
- **時間効率**: 複数の調査を同時並行
- **多角的視点**: 異なる専門分野からのアプローチ
- **相互検証**: エージェント間での結果クロスチェック

#### チェックポイント
- [ ] 各エージェントの専門分野が重複していないか
- [ ] 結果の統合プロセスが明確か
- [ ] エージェント間のコミュニケーションが効率的か

### 3.2 エージェント間の情報共有パターン

#### 3.2.1 発見事項の引き継ぎ
```
ccusage-analyzer の発見
  ↓ （具体的なアルゴリズム情報）
claude-data-specialist の検証
  ↓ （実データでの証拠）  
algorithm-debugger の実装
  ↓ （修正版コード）
statusline-optimizer の適用
```

## 4. 検証・バリデーション手法

### 4.1 リアルタイム比較検証
```bash
# 自動比較スクリプト
validate_compatibility() {
    ccusage_result=$(npx ccusage@latest blocks --json | jq -r '.blocks[] | select(.isActive == true) | .totalTokens')
    statusline_result=$(echo '{"session_id":"test"}' | python3 statusline.py --show 4 2>/dev/null | grep -o '[0-9,]*' | head -1 | tr -d ',')
    
    diff_absolute=$((statusline_result - ccusage_result))
    diff_percentage=$(echo "scale=2; ($diff_absolute * 100.0) / $ccusage_result" | bc)
    
    echo "ccusage: $ccusage_result tokens"
    echo "statusline: $statusline_result tokens"
    echo "Difference: $diff_absolute tokens ($diff_percentage%)"
    
    if (( $(echo "$diff_percentage < 5.0" | bc -l) )); then
        echo "✅ PASS: Difference within acceptable range"
        return 0
    else
        echo "❌ FAIL: Difference too large"
        return 1
    fi
}
```

### 4.2 継続的統合での自動検証
```yaml
# GitHub Actions example
name: Tool Compatibility Check
on: [push, pull_request]
jobs:
  compatibility:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup environment
        run: |
          npm install -g ccusage@latest
          python -m pip install -r requirements.txt
      - name: Run compatibility test
        run: ./scripts/validate_compatibility.sh
```

## 5. エラーパターンと対処法

### 5.1 よくある間違いパターン

#### 5.1.1 フィールドアクセスの落とし穴
```python
# ❌ 間違い：or演算子による意図しない値選択
cache_value = data.get('field_a', 0) or data.get('field_b', 0)

# ✅ 正しい：条件分岐による明示的選択  
if 'field_a' in data:
    cache_value = data['field_a']
elif 'field_b' in data:
    cache_value = data['field_b']
else:
    cache_value = 0
```

#### 5.1.2 タイムゾーン・時間窓の不整合
```python
# ❌ 間違い：ローカル時間での比較
if message_time > block_start:  # タイムゾーンが異なる可能性

# ✅ 正しい：UTC統一での比較
message_time_utc = message_time.astimezone(timezone.utc)
block_start_utc = block_start.astimezone(timezone.utc)  
if message_time_utc > block_start_utc:
```

### 5.2 デバッグ情報の効果的活用
```python
def debug_token_calculation(usage_data, context=""):
    """デバッグ情報付きトークン計算"""
    input_tokens = usage_data.get('input_tokens', 0)
    output_tokens = usage_data.get('output_tokens', 0)
    
    # キャッシュトークンのデバッグ情報
    cache_creation = 0
    cache_source = "none"
    
    if 'cache_creation_input_tokens' in usage_data:
        cache_creation = usage_data['cache_creation_input_tokens']
        cache_source = "direct_field"
    elif 'cache_creation' in usage_data:
        cache_creation = usage_data['cache_creation'].get('ephemeral_5m_input_tokens', 0)
        cache_source = "nested_field"
    
    total = input_tokens + output_tokens + cache_creation
    
    print(f"DEBUG[{context}]: input={input_tokens}, output={output_tokens}, cache={cache_creation}({cache_source}), total={total}")
    return total
```

## 6. 再発防止策

### 6.1 監視・アラート機能
```python
def setup_compatibility_monitoring():
    """互換性監視の自動化"""
    @schedule.every(1).hours
    def check_compatibility():
        if not validate_compatibility():
            send_alert("Tool compatibility check failed!")
            
    schedule.run_continuously()
```

### 6.2 回帰テスト自動化  
```python
# 重要なテストケースの自動化
class CompatibilityTestSuite:
    def test_token_calculation_consistency(self):
        """トークン計算の一貫性テスト"""
        test_data = load_test_messages()
        for message in test_data:
            statusline_result = calculate_tokens_statusline(message)
            expected_result = calculate_tokens_ccusage_compatible(message)
            self.assertAlmostEqual(statusline_result, expected_result, delta=0.01)
```

### 6.3 ドキュメント継続更新
- 新しい問題パターンの文書化
- 解決手法のナレッジベース蓄積
- エージェント活用ベストプラクティスの更新

## 7. 成功指標と評価基準

### 7.1 定量的指標
- **精度改善率**: 今回は76%の精度向上を達成
- **差異許容範囲**: <5%の差異を目標とする
- **解決時間**: 1-2時間以内での問題解決

### 7.2 定性的指標  
- **再現性**: 同じ手法で他の互換性問題も解決可能
- **保守性**: 修正が将来の変更に耐えうる設計
- **理解性**: 他の開発者も同じ手法を適用可能

---

**次回適用時の注意**: このガイドは今回の成功パターンを基に作成。ツールや問題の性質に応じて手法をカスタマイズすること。