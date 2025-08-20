# External Tool Validation Best Practices

**作成日**: 2025-08-20  
**目的**: 外部ツールとの互換性検証で確立されたベストプラクティスの文書化  
**対象**: statusline vs ccusage で得られた検証手法の汎用化

## 1. 検証戦略の基本原則

### 1.1 Ground Truth の確立
```bash
# 1. 複数の独立した検証手段を用意
ccusage_reference=$(npx ccusage@latest blocks --json | jq -r '.blocks[] | select(.isActive == true) | .totalTokens')
manual_calculation=$(jq -r '.usage.input_tokens + .usage.output_tokens' ~/.claude/projects/*/*.jsonl | paste -sd+ | bc)

# 2. 結果の相互検証
echo "ccusage: $ccusage_reference"
echo "manual: $manual_calculation"  
echo "statusline: $statusline_result"
```

### 1.2 差異の許容範囲設定
```python
# 業務要件に基づく許容範囲の設定
TOLERANCE_LEVELS = {
    'billing_critical': 0.1,    # 課金関連：0.1%以内
    'monitoring': 1.0,          # 監視用：1%以内  
    'analytics': 5.0,           # 分析用：5%以内
    'display_only': 10.0        # 表示のみ：10%以内
}

def validate_within_tolerance(actual, expected, purpose='monitoring'):
    tolerance = TOLERANCE_LEVELS.get(purpose, 1.0)
    diff_percentage = abs(actual - expected) / expected * 100
    return diff_percentage <= tolerance
```

### 1.3 検証頻度の戦略的設定
```yaml
# 継続的検証スケジュール
validation_schedule:
  critical_path: "every_commit"      # 重要機能は毎コミット
  integration: "daily"               # 統合テストは日次
  compatibility: "weekly"            # 互換性チェックは週次
  full_regression: "release"         # 全回帰テストはリリース前
```

## 2. 逆エンジニアリング手法

### 2.1 ソースコード分析のアプローチ

#### 2.1.1 段階的分析手法
```bash
# Phase 1: リポジトリ構造の把握
find /path/to/external/tool -type f -name "*.ts" -o -name "*.js" | head -20
find /path/to/external/tool -type f -name "package.json" -exec cat {} \;

# Phase 2: エントリーポイント特定
grep -r "getTotalTokens\|calculateTokens\|tokenCount" /path/to/external/tool/src/

# Phase 3: 依存関係マッピング
npm list --depth=2  # Node.jsプロジェクトの場合
```

#### 2.1.2 重要ロジックの抽出
```typescript
// 分析対象のコード例
interface TokenCounts {
    inputTokens: number;
    outputTokens: number;
    cacheCreationInputTokens?: number;  // 注目：オプショナルフィールド
    cacheCreationTokens?: number;       // 注目：代替フィールド
}

// 重要な条件分岐ロジック
const cacheCreation = 'cacheCreationInputTokens' in tokenCounts
    ? tokenCounts.cacheCreationInputTokens    // 第一優先
    : tokenCounts.cacheCreationTokens || 0;   // フォールバック
```

### 2.2 動作解析手法

#### 2.2.1 入出力トレーシング
```bash
# 外部ツールの詳細出力を取得
npx ccusage@latest blocks --json --verbose 2>&1 | tee external_tool_trace.log

# デバッグモードでの実行
DEBUG=* npx ccusage@latest blocks --json 2>&1 | grep -E "(token|usage|calculate)"
```

#### 2.2.2 中間結果の比較検証
```python
def trace_calculation_steps(usage_data):
    """計算過程の詳細トレース"""
    steps = {}
    
    # Step 1: 基本トークン
    steps['input'] = usage_data.get('input_tokens', 0)
    steps['output'] = usage_data.get('output_tokens', 0)
    
    # Step 2: キャッシュトークン選択ロジック
    if 'cache_creation_input_tokens' in usage_data:
        steps['cache_creation'] = usage_data['cache_creation_input_tokens']
        steps['cache_source'] = 'direct_field'
    else:
        steps['cache_creation'] = usage_data.get('cache_creation_tokens', 0)
        steps['cache_source'] = 'fallback_field'
    
    # Step 3: 最終結果
    steps['total'] = steps['input'] + steps['output'] + steps['cache_creation']
    
    return steps
```

## 3. データ構造互換性検証

### 3.1 フィールドマッピングの体系的分析

#### 3.1.1 全フィールドの出現頻度調査
```bash
# 全transcript fileからusageフィールドを集計
find ~/.claude/projects/ -name "*.jsonl" -exec jq -r '.usage | keys[]' {} \; 2>/dev/null | sort | uniq -c | sort -nr > usage_field_frequency.txt

# 結果例：
#    15823 input_tokens
#    15823 output_tokens  
#    12456 cache_creation_input_tokens
#     3367 cache_creation_tokens
#      892 cache_creation
```

#### 3.1.2 フィールド値の分布分析
```python
def analyze_field_value_distribution():
    """フィールド値分布の統計的分析"""
    import json
    from collections import defaultdict, Counter
    
    field_stats = defaultdict(list)
    field_coexistence = Counter()
    
    # 全JSONLファイルを処理
    for file_path in get_transcript_files():
        with open(file_path) as f:
            for line in f:
                data = json.loads(line)
                usage = data.get('usage', {})
                
                # フィールドの共存パターンを記録
                if 'cache_creation_input_tokens' in usage and 'cache_creation' in usage:
                    field_coexistence['both_cache_fields'] += 1
                    
                    # 値の一致/不一致を確認
                    direct_value = usage['cache_creation_input_tokens']
                    nested_value = usage['cache_creation'].get('ephemeral_5m_input_tokens', 0)
                    
                    if direct_value == nested_value:
                        field_coexistence['values_match'] += 1
                    else:
                        field_coexistence['values_differ'] += 1
                        print(f"CONFLICT: direct={direct_value}, nested={nested_value}")
    
    return field_coexistence
```

### 3.2 エッジケースの特定

#### 3.2.1 境界値テスト
```python
# 特殊なデータパターンのテストケース
EDGE_CASES = [
    # ケース1: フィールドが存在しない
    {"usage": {"input_tokens": 100, "output_tokens": 200}},
    
    # ケース2: 値が0
    {"usage": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0}},
    
    # ケース3: 片方のフィールドのみ存在
    {"usage": {"input_tokens": 100, "cache_creation_tokens": 500}},
    
    # ケース4: 両方存在するが値が異なる（異常ケース）  
    {"usage": {"cache_creation_input_tokens": 1000, "cache_creation": {"ephemeral_5m_input_tokens": 2000}}},
]

for i, case in enumerate(EDGE_CASES):
    result_ours = calculate_tokens_our_way(case["usage"])
    result_external = calculate_tokens_external_way(case["usage"])
    print(f"Case {i+1}: Ours={result_ours}, External={result_external}, Diff={result_ours-result_external}")
```

#### 3.2.2 時系列データでの整合性確認
```python
def validate_temporal_consistency():
    """時系列での計算結果の整合性確認"""
    timestamps = []
    our_cumulative = []
    external_cumulative = []
    
    # 時系列順でメッセージを処理
    for message in get_messages_chronologically():
        timestamp = message['timestamp']
        our_tokens = calculate_our_tokens(message)
        external_tokens = estimate_external_tokens(message)
        
        timestamps.append(timestamp)
        our_cumulative.append(sum(our_cumulative) + our_tokens if our_cumulative else our_tokens)
        external_cumulative.append(sum(external_cumulative) + external_tokens if external_cumulative else external_tokens)
    
    # 差異の推移をプロット
    plot_divergence_over_time(timestamps, our_cumulative, external_cumulative)
```

## 4. 自動化されたテストフレームワーク

### 4.1 継続的互換性テスト

#### 4.1.1 自動テストスイート
```python
import unittest
from decimal import Decimal

class ExternalToolCompatibilityTest(unittest.TestCase):
    
    def setUp(self):
        self.test_data = load_test_dataset()
        self.tolerance = Decimal('0.01')  # 1%の許容誤差
    
    def test_token_calculation_compatibility(self):
        """トークン計算の互換性テスト"""
        for test_case in self.test_data:
            with self.subTest(test_case=test_case['description']):
                our_result = calculate_tokens_our_implementation(test_case['input'])
                external_result = test_case['expected_external_result']
                
                diff_percentage = abs(our_result - external_result) / external_result
                self.assertLessEqual(
                    diff_percentage, 
                    self.tolerance,
                    f"Difference {diff_percentage*100:.2f}% exceeds tolerance {self.tolerance*100}%"
                )
    
    def test_edge_cases_handling(self):
        """エッジケースの処理テスト"""
        edge_cases = get_edge_cases()
        for case in edge_cases:
            # 例外が発生しないことを確認
            try:
                result = calculate_tokens_our_implementation(case['input'])
                self.assertIsInstance(result, (int, float))
                self.assertGreaterEqual(result, 0)
            except Exception as e:
                self.fail(f"Edge case {case['description']} caused exception: {e}")
```

#### 4.1.2 パフォーマンステスト
```python
def performance_comparison_test():
    """パフォーマンス比較テスト"""
    import time
    
    large_dataset = generate_large_test_dataset(size=10000)
    
    # 我々の実装のパフォーマンス
    start_time = time.time()
    for data in large_dataset:
        calculate_tokens_our_implementation(data)
    our_time = time.time() - start_time
    
    # 外部ツール（参考値として）
    start_time = time.time() 
    for data in large_dataset:
        # 外部ツールの呼び出しシミュレーション
        simulate_external_tool_call(data)
    external_time = time.time() - start_time
    
    print(f"Performance comparison:")
    print(f"  Our implementation: {our_time:.2f}s")
    print(f"  External tool: {external_time:.2f}s")
    print(f"  Ratio: {our_time/external_time:.2f}x")
```

### 4.2 リアルタイム監視システム

#### 4.2.1 差異アラートシステム
```python
class CompatibilityMonitor:
    def __init__(self, alert_threshold=5.0):
        self.alert_threshold = alert_threshold  # パーセンテージ
        self.alert_handlers = []
    
    def add_alert_handler(self, handler):
        self.alert_handlers.append(handler)
    
    def check_compatibility(self):
        """定期的な互換性チェック"""
        try:
            our_result = get_current_tokens_our_way()
            external_result = get_current_tokens_external_way()
            
            if external_result > 0:
                diff_percentage = abs(our_result - external_result) / external_result * 100
                
                if diff_percentage > self.alert_threshold:
                    alert_message = f"Compatibility Alert: {diff_percentage:.1f}% difference detected"
                    for handler in self.alert_handlers:
                        handler(alert_message, our_result, external_result)
                        
        except Exception as e:
            error_message = f"Compatibility check failed: {e}"
            for handler in self.alert_handlers:
                handler(error_message)
```

#### 4.2.2 トレンド分析
```python
def analyze_compatibility_trends():
    """互換性の長期トレンド分析"""
    historical_data = load_historical_compatibility_data()
    
    # 差異の時系列変化
    timestamps = [record['timestamp'] for record in historical_data]
    differences = [record['difference_percentage'] for record in historical_data]
    
    # トレンド検出
    import numpy as np
    from scipy import stats
    
    slope, intercept, r_value, p_value, std_err = stats.linregress(range(len(differences)), differences)
    
    if slope > 0.1:  # 差異が増加傾向
        print("⚠️  WARNING: Compatibility is degrading over time")
    elif slope < -0.1:  # 差異が減少傾向
        print("✅ GOOD: Compatibility is improving over time")
    else:
        print("➡️  STABLE: Compatibility remains consistent")
    
    return {
        'trend_slope': slope,
        'r_squared': r_value**2,
        'p_value': p_value
    }
```

## 5. 問題発生時の対応手順

### 5.1 緊急対応プロトコル

#### 5.1.1 トリアージフロー
```
差異検出
    ↓
［差異 < 1%］ → 監視継続
    ↓
［1% ≤ 差異 < 5%］ → 注意深く監視、次回リリースで修正検討  
    ↓
［5% ≤ 差異 < 20%］ → 緊急調査開始、根本原因特定
    ↓
［差異 ≥ 20%］ → 即座にロールバック検討、緊急修正
```

#### 5.1.2 エスカレーション基準
```python
ESCALATION_LEVELS = {
    'info': {'threshold': 1.0, 'action': 'log_only'},
    'warning': {'threshold': 5.0, 'action': 'notify_team'},  
    'critical': {'threshold': 15.0, 'action': 'page_oncall'},
    'emergency': {'threshold': 50.0, 'action': 'rollback_immediately'}
}

def handle_compatibility_issue(difference_percentage):
    for level, config in ESCALATION_LEVELS.items():
        if difference_percentage >= config['threshold']:
            execute_action(config['action'], difference_percentage)
            break
```

### 5.2 根本原因分析（RCA）テンプレート

#### 5.2.1 情報収集チェックリスト
```markdown
## 互換性問題 RCA チェックリスト

### 基本情報
- [ ] 発生日時: ________________
- [ ] 検出方法: [自動監視 / 手動テスト / ユーザー報告]
- [ ] 影響範囲: ________________
- [ ] 差異の大きさ: ___________% 

### 環境情報
- [ ] 外部ツールバージョン: ________________
- [ ] 内部ツールバージョン: ________________
- [ ] 関連する最近の変更: ________________
- [ ] データソースの変更: [あり / なし]

### 技術的調査
- [ ] ソースコード差分確認済み
- [ ] テストデータでの再現確認済み  
- [ ] ログ・デバッグ情報収集済み
- [ ] フィールドマッピング検証済み

### 修正計画
- [ ] 根本原因特定: ________________
- [ ] 修正方針: ________________ 
- [ ] 影響度評価: [低 / 中 / 高]
- [ ] 修正予定日: ________________
```

## 6. 継続的改善プロセス

### 6.1 学習ループの確立

#### 6.1.1 事後分析プロセス
```python
class PostMortemAnalysis:
    def __init__(self, incident_id):
        self.incident_id = incident_id
        self.timeline = []
        self.root_causes = []
        self.lessons_learned = []
        
    def add_timeline_event(self, timestamp, event, impact):
        self.timeline.append({
            'timestamp': timestamp,
            'event': event, 
            'impact': impact
        })
    
    def identify_root_cause(self, cause, evidence):
        self.root_causes.append({
            'cause': cause,
            'evidence': evidence,
            'preventable': self.assess_preventability(cause)
        })
    
    def add_lesson(self, lesson, action_item, owner):
        self.lessons_learned.append({
            'lesson': lesson,
            'action_item': action_item,
            'owner': owner,
            'due_date': self.calculate_due_date()
        })
        
    def generate_report(self):
        """改善につながる構造化されたレポート生成"""
        return {
            'summary': self.create_executive_summary(),
            'timeline': self.timeline,
            'root_causes': self.root_causes,
            'lessons_learned': self.lessons_learned,
            'action_items': self.extract_action_items()
        }
```

#### 6.1.2 ナレッジベースの構築
```markdown
# 互換性問題ナレッジベース

## 問題パターン集

### Pattern 1: フィールド名の不整合
**症状**: 特定のフィールドで計算結果が2倍になる
**原因**: `or`演算子による複数フィールドの意図しない加算
**解決**: 条件分岐による明示的なフィールド選択
**検出方法**: エッジケースでのテスト
**予防策**: フィールドアクセスパターンの標準化

### Pattern 2: タイムゾーン処理の不整合  
**症状**: 時間窓の境界で結果が変わる
**原因**: ローカル時間とUTCの混在
**解決**: 全時刻処理をUTCに統一
**検出方法**: 異なるタイムゾーンでのテスト
**予防策**: 時刻処理ライブラリの統一
```

### 6.2 プロセス改善サイクル

#### 6.2.1 四半期レビュープロセス
```python
def quarterly_compatibility_review():
    """四半期ごとの互換性レビュー"""
    
    # 1. メトリクス収集
    metrics = {
        'average_difference': calculate_average_difference_last_quarter(),
        'incident_count': count_compatibility_incidents_last_quarter(),
        'detection_time': average_detection_time_last_quarter(),
        'resolution_time': average_resolution_time_last_quarter()
    }
    
    # 2. 改善機会の特定
    improvement_opportunities = identify_improvement_opportunities(metrics)
    
    # 3. アクションプランの策定
    action_plan = create_action_plan(improvement_opportunities)
    
    # 4. レポート生成
    report = generate_quarterly_report(metrics, action_plan)
    
    return report
```

#### 6.2.2 自動化の拡張
```yaml
# 改善施策の例
automation_roadmap:
  phase1_current:
    - basic_compatibility_testing
    - manual_root_cause_analysis
    
  phase2_next_quarter:  
    - automated_root_cause_detection
    - predictive_compatibility_alerts
    
  phase3_future:
    - self_healing_compatibility_issues  
    - ai_powered_code_adaptation
```

## 7. 組織的側面

### 7.1 チーム間コラボレーション

#### 7.1.1 責任分担マトリックス
```
| 活動                     | 開発 | QA | DevOps | 外部ツール管理者 |
|--------------------------|------|----|---------|--------------------|
| 互換性テスト設計         | R    | A  | C       | I                  |
| 自動テスト実装           | R    | C  | A       | I                  |
| 監視システム運用         | C    | I  | R       | C                  |
| 問題発生時の対応         | R    | C  | R       | C                  |
| 外部ツール更新対応       | C    | R  | C       | R                  |

R=Responsible, A=Accountable, C=Consulted, I=Informed
```

#### 7.1.2 コミュニケーションプロトコル
```python
# 自動通知システムの例
class CompatibilityNotificationSystem:
    def __init__(self):
        self.notification_channels = {
            'slack': SlackNotifier(),
            'email': EmailNotifier(),
            'pagerduty': PagerDutyNotifier()
        }
        
    def send_compatibility_alert(self, severity, details):
        """重要度に応じた通知先の選択"""
        channels = {
            'info': ['slack'],
            'warning': ['slack', 'email'],
            'critical': ['slack', 'email', 'pagerduty']
        }.get(severity, ['slack'])
        
        for channel in channels:
            self.notification_channels[channel].send(details)
```

### 7.2 外部ベンダーとの関係管理

#### 7.2.1 SLA定義例
```yaml
external_tool_sla:
  api_compatibility:
    backward_compatibility_period: "12_months"
    breaking_change_notice: "30_days_minimum"
    
  response_time:
    compatibility_issues: "24_hours"
    breaking_changes: "2_weeks" 
    
  communication:
    update_notifications: "automatic"
    beta_access: "provided"
    direct_contact: "available"
```

---

**このガイドの活用法**: 新しい外部ツールとの互換性問題に直面した際は、Section 2から開始し、問題の性質に応じて適切なセクションを参照すること。継続的改善のため、解決事例をSection 6.1.2のナレッジベースに追加すること。