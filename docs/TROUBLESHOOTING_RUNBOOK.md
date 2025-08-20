# Troubleshooting Runbook - Token Calculation & Tool Compatibility Issues

**作成日**: 2025-08-20  
**目的**: statusline vs ccusage問題で確立された再発防止・トラブルシューティング手順の標準化  
**対象**: 将来発生する類似問題の迅速解決

## 1. 緊急対応プロトコル

### 1.1 問題検知時の初動対応（最初の30分）

#### 1.1.1 トリアージフローチャート
```
問題報告・検知
    ↓
【差異 < 5%】 → 情報収集継続 → 定期監視
    ↓
【5% ≤ 差異 < 20%】 → レベル2対応 → 調査チーム招集
    ↓  
【20% ≤ 差異 < 50%】 → レベル3対応 → 緊急調査・修正検討
    ↓
【差異 ≥ 50%】 → レベル4対応 → 即座に緊急対応チーム招集
```

#### 1.1.2 初動チェックリスト
```bash
#!/bin/bash
# 緊急診断スクリプト（5分以内で実行）

echo "=== EMERGENCY DIAGNOSTIC SCRIPT ==="
echo "Timestamp: $(date)"

# 1. 両ツールの現在値取得
echo "1. Current Values Comparison:"
ccusage_tokens=$(npx ccusage@latest blocks --json 2>/dev/null | jq -r '.blocks[] | select(.isActive == true) | .totalTokens' 2>/dev/null || echo "ERROR")
statusline_tokens=$(echo '{"session_id":"test"}' | python3 statusline.py --show 4 2>/dev/null | grep -o '[0-9,]*' | head -1 | tr -d ',' 2>/dev/null || echo "ERROR")

echo "  ccusage: $ccusage_tokens tokens"
echo "  statusline: $statusline_tokens tokens"

if [[ "$ccusage_tokens" != "ERROR" && "$statusline_tokens" != "ERROR" ]]; then
    diff_absolute=$((statusline_tokens - ccusage_tokens))
    diff_percentage=$(echo "scale=1; ($diff_absolute * 100.0) / $ccusage_tokens" | bc 2>/dev/null || echo "CALC_ERROR")
    echo "  Difference: $diff_absolute tokens ($diff_percentage%)"
else
    echo "  ERROR: Failed to retrieve values"
fi

# 2. システム基本ヘルスチェック
echo "2. System Health Check:"
echo "  Python available: $(which python3 >/dev/null && echo "OK" || echo "ERROR")"
echo "  ccusage available: $(which npx >/dev/null && echo "OK" || echo "ERROR")" 
echo "  statusline.py exists: $(test -f statusline.py && echo "OK" || echo "ERROR")"
echo "  Project files accessible: $(ls ~/.claude/projects/ >/dev/null 2>&1 && echo "OK" || echo "ERROR")"

# 3. 最近の変更確認
echo "3. Recent Changes:"
echo "  Last statusline.py modification: $(stat -f "%Sm" statusline.py 2>/dev/null || echo "UNKNOWN")"
echo "  Recent git commits:"
git log --oneline -5 2>/dev/null || echo "  No git history available"

echo "=== END DIAGNOSTIC ==="
```

### 1.2 レベル別対応手順

#### レベル2対応（差異5-20%）
**担当**: 開発チーム  
**目標**: 24時間以内の原因特定

```bash
# レベル2調査スクリプト
python3 -c "
import json
import sys
from datetime import datetime

# 詳細比較実行
def detailed_comparison():
    # 時系列での値変化を追跡
    measurements = []
    for i in range(12):  # 1時間にわたり5分間隔で測定
        ccusage_val = get_ccusage_value()
        statusline_val = get_statusline_value()
        measurements.append({
            'timestamp': datetime.now(),
            'ccusage': ccusage_val,
            'statusline': statusline_val,
            'diff': statusline_val - ccusage_val if ccusage_val and statusline_val else None
        })
        time.sleep(300)  # 5分待機
    
    # トレンド分析
    return analyze_trend(measurements)

result = detailed_comparison()
print(json.dumps(result, indent=2))
"
```

#### レベル3対応（差異20-50%）
**担当**: シニア開発者 + アーキテクト  
**目標**: 12時間以内の根本原因特定と修正計画策定

#### レベル4対応（差異≥50%）  
**担当**: 緊急対応チーム全員  
**目標**: 2時間以内の緊急措置実施

## 2. 根本原因分析（RCA）標準手順

### 2.1 データ収集フェーズ（30分）

#### 2.1.1 環境情報収集
```bash
#!/bin/bash
# 環境情報収集スクリプト

RCA_DIR="./rca_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RCA_DIR"

echo "Collecting environmental data..."

# システム情報
{
    echo "=== SYSTEM INFORMATION ==="
    echo "Date: $(date)"
    echo "OS: $(uname -a)"
    echo "Python version: $(python3 --version 2>&1)"
    echo "Node.js version: $(node --version 2>&1)"
    echo "npm version: $(npm --version 2>&1)"
    echo ""
} > "$RCA_DIR/system_info.txt"

# ツールバージョン情報
{
    echo "=== TOOL VERSIONS ==="
    echo "ccusage version:"
    npx ccusage@latest --version 2>&1
    echo ""
    echo "statusline.py modification time:"
    stat -f "%Sm" statusline.py 2>&1
    echo ""
} >> "$RCA_DIR/system_info.txt"

# Git状態
{
    echo "=== GIT STATUS ==="
    git status 2>&1
    echo ""
    echo "=== RECENT COMMITS ==="
    git log --oneline -10 2>&1
} > "$RCA_DIR/git_info.txt"

# データファイル状態
{
    echo "=== DATA FILES STATUS ==="
    echo "Project directories:"
    ls -la ~/.claude/projects/ 2>&1
    echo ""
    echo "Recent transcript files (last 5):"
    find ~/.claude/projects/ -name "*.jsonl" -type f -exec stat -f "%Sm %N" {} \; 2>/dev/null | sort -r | head -5
} > "$RCA_DIR/data_info.txt"

echo "Environmental data collected in $RCA_DIR/"
```

#### 2.1.2 動作ログ収集
```python
# 詳細動作ログ取得スクリプト
import logging
import json
import subprocess
import sys
from datetime import datetime

# デバッグレベルのロギング設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'rca_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

def collect_detailed_logs():
    """詳細なデバッグ情報収集"""
    
    logging.info("Starting detailed log collection...")
    
    # ccusageの詳細実行ログ
    try:
        result = subprocess.run(['npx', 'ccusage@latest', 'blocks', '--json'], 
                              capture_output=True, text=True, timeout=30)
        logging.info(f"ccusage stdout: {result.stdout}")
        if result.stderr:
            logging.warning(f"ccusage stderr: {result.stderr}")
    except Exception as e:
        logging.error(f"Failed to execute ccusage: {e}")
    
    # statuslineの詳細実行ログ  
    try:
        process = subprocess.Popen(['python3', 'statusline.py', '--show', '4'], 
                                 stdin=subprocess.PIPE, 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE, 
                                 text=True)
        stdout, stderr = process.communicate(input='{"session_id":"debug_test"}', timeout=30)
        
        logging.info(f"statusline stdout: {stdout}")
        if stderr:
            logging.warning(f"statusline stderr: {stderr}")
            
    except Exception as e:
        logging.error(f"Failed to execute statusline: {e}")

if __name__ == "__main__":
    collect_detailed_logs()
```

### 2.2 分析フェーズ（60分）

#### 2.2.1 差異パターン分析
```python
def analyze_discrepancy_pattern():
    """差異パターンの統計的分析"""
    
    import numpy as np
    import pandas as pd
    from scipy import stats
    
    # 複数回測定による統計分析
    measurements = []
    for i in range(20):  # 20回測定
        ccusage_val = get_ccusage_measurement()
        statusline_val = get_statusline_measurement()
        timestamp = datetime.now()
        
        measurements.append({
            'timestamp': timestamp,
            'ccusage': ccusage_val,
            'statusline': statusline_val,
            'difference': statusline_val - ccusage_val,
            'ratio': statusline_val / ccusage_val if ccusage_val > 0 else None
        })
        
        time.sleep(10)  # 10秒間隔
    
    df = pd.DataFrame(measurements)
    
    analysis = {
        'statistical_summary': {
            'mean_difference': df['difference'].mean(),
            'std_difference': df['difference'].std(),
            'mean_ratio': df['ratio'].mean(),
            'std_ratio': df['ratio'].std(),
            'consistency': df['ratio'].std() < 0.1  # 比率の標準偏差が0.1以下なら一貫している
        },
        'trend_analysis': {
            'difference_trend': analyze_trend(df['timestamp'], df['difference']),
            'is_increasing': df['difference'].corr(range(len(df))) > 0.5,
            'is_stable': df['difference'].std() / df['difference'].mean() < 0.1
        },
        'categorization': categorize_discrepancy_type(df)
    }
    
    return analysis

def categorize_discrepancy_type(df):
    """差異タイプの分類"""
    mean_ratio = df['ratio'].mean()
    ratio_std = df['ratio'].std()
    
    if ratio_std < 0.05:  # 非常に一貫している
        if abs(mean_ratio - 1.0) < 0.01:
            return "IDENTICAL"
        elif abs(mean_ratio - 2.0) < 0.1:
            return "DOUBLE_COUNTING"  # 2倍になっている
        elif mean_ratio > 1.5:
            return "SYSTEMATIC_OVERCOUNTING"
        elif mean_ratio < 0.5:
            return "SYSTEMATIC_UNDERCOUNTING"
        else:
            return "CONSISTENT_BIAS"
    else:
        return "INCONSISTENT_CALCULATION"
```

#### 2.2.2 コードレベル分析
```bash
# コード差分分析スクリプト
#!/bin/bash

echo "=== CODE-LEVEL ANALYSIS ==="

# 最近の変更箇所特定
echo "1. Recent changes in token calculation code:"
git log -p --since="1 week ago" -- statusline.py | grep -A5 -B5 -E "(token|usage|calculate)" || echo "No recent token-related changes"

echo ""

# トークン計算関連関数の抽出
echo "2. Current token calculation functions:"
grep -n -A10 -B2 "def.*token" statusline.py | head -50

echo ""

# usage field アクセスパターンの確認
echo "3. Usage field access patterns:"
grep -n "usage\." statusline.py | head -20
grep -n "\.get.*token" statusline.py | head -20

echo ""

# 疑わしいパターンの検出
echo "4. Suspicious patterns:"
echo "  - Use of 'or' in token calculation:"
grep -n -C3 "\.get.*or.*\.get" statusline.py | grep -i token
echo "  - Fallback logic in cache token handling:"
grep -n -C3 "cache.*or.*cache" statusline.py
```

### 2.3 仮説検証フェーズ（90分）

#### 2.3.1 仮説駆動型テスト
```python
def test_hypotheses():
    """主要仮説の体系的検証"""
    
    hypotheses = [
        {
            'name': 'double_counting_cache_tokens',
            'description': 'キャッシュトークンの二重カウント',
            'test_function': test_cache_double_counting,
            'expected_evidence': 'ファーム内tokens increase by factor of 2'
        },
        {
            'name': 'field_name_mismatch', 
            'description': 'フィールド名の不整合',
            'test_function': test_field_name_issues,
            'expected_evidence': 'Different field access patterns'
        },
        {
            'name': 'deduplication_difference',
            'description': '重複除去ロジックの違い',
            'test_function': test_deduplication_logic,
            'expected_evidence': 'Different message counts processed'
        },
        {
            'name': 'time_window_mismatch',
            'description': '時間窓の不一致',
            'test_function': test_time_window_alignment,
            'expected_evidence': 'Different time range processing'
        }
    ]
    
    results = {}
    
    for hypothesis in hypotheses:
        print(f"Testing hypothesis: {hypothesis['name']}")
        
        try:
            test_result = hypothesis['test_function']()
            results[hypothesis['name']] = {
                'tested': True,
                'evidence_found': test_result['evidence_found'],
                'confidence': test_result['confidence'],
                'details': test_result['details']
            }
            
            if test_result['evidence_found']:
                print(f"  ✅ Evidence found (confidence: {test_result['confidence']})")
            else:
                print(f"  ❌ No evidence found")
                
        except Exception as e:
            results[hypothesis['name']] = {
                'tested': False,
                'error': str(e)
            }
            print(f"  ⚠️  Test failed: {e}")
    
    return results

def test_cache_double_counting():
    """キャッシュトークン二重カウントのテスト"""
    
    # テスト用データの作成
    test_usage_data = {
        'input_tokens': 100,
        'output_tokens': 200,
        'cache_creation_input_tokens': 1000,
        'cache_creation': {
            'ephemeral_5m_input_tokens': 1000  # 同じ値
        }
    }
    
    # 現在の実装でテスト
    current_result = get_total_tokens(test_usage_data)
    
    # 正しい実装でテスト
    correct_result = get_total_tokens_correct(test_usage_data)
    
    evidence_found = current_result != correct_result
    confidence = 1.0 if evidence_found else 0.0
    
    return {
        'evidence_found': evidence_found,
        'confidence': confidence,
        'details': {
            'current_result': current_result,
            'correct_result': correct_result,
            'difference': current_result - correct_result
        }
    }
```

## 3. 修正実装ガイド

### 3.1 段階的修正アプローチ

#### 3.1.1 修正プランテンプレート
```python
class FixImplementationPlan:
    
    def __init__(self, root_cause):
        self.root_cause = root_cause
        self.phases = self.design_fix_phases()
        
    def design_fix_phases(self):
        """修正フェーズの設計"""
        
        base_phases = [
            {
                'name': 'validation_setup',
                'description': '修正前後の検証環境構築', 
                'duration_minutes': 15,
                'rollback_possible': True
            },
            {
                'name': 'core_logic_fix',
                'description': '核心ロジックの修正',
                'duration_minutes': 30,
                'rollback_possible': True  
            },
            {
                'name': 'integration_test',
                'description': '統合テスト実行',
                'duration_minutes': 20,
                'rollback_possible': True
            },
            {
                'name': 'production_validation',
                'description': '本番環境での検証',
                'duration_minutes': 15,
                'rollback_possible': True
            }
        ]
        
        # 根本原因に応じた特殊フェーズの追加
        if 'double_counting' in self.root_cause:
            base_phases.insert(1, {
                'name': 'field_access_refactor',
                'description': 'フィールドアクセスパターンの修正',
                'duration_minutes': 45,
                'rollback_possible': True
            })
            
        return base_phases
```

#### 3.1.2 修正前後検証スクリプト
```bash
#!/bin/bash
# 修正前後の自動検証スクリプト

VALIDATION_DIR="./validation_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$VALIDATION_DIR"

echo "=== PRE-FIX VALIDATION ==="

# 修正前の値取得
ccusage_before=$(npx ccusage@latest blocks --json | jq -r '.blocks[] | select(.isActive == true) | .totalTokens')
statusline_before=$(echo '{"session_id":"test"}' | python3 statusline.py --show 4 2>/dev/null | grep -o '[0-9,]*' | head -1 | tr -d ',')

echo "ccusage (before): $ccusage_before"
echo "statusline (before): $statusline_before"

if [[ "$ccusage_before" != "" && "$statusline_before" != "" ]]; then
    diff_before=$((statusline_before - ccusage_before))
    diff_pct_before=$(echo "scale=1; ($diff_before * 100.0) / $ccusage_before" | bc)
    echo "Difference (before): $diff_before tokens ($diff_pct_before%)"
else
    echo "ERROR: Could not get baseline measurements"
    exit 1
fi

# 結果保存
{
    echo "timestamp: $(date)"
    echo "ccusage_before: $ccusage_before"
    echo "statusline_before: $statusline_before" 
    echo "difference_before: $diff_before"
    echo "percentage_before: $diff_pct_before"
} > "$VALIDATION_DIR/baseline.txt"

echo ""
echo "*** APPLY YOUR FIX NOW ***"
echo "Press ENTER when fix is applied..."
read

echo ""
echo "=== POST-FIX VALIDATION ==="

# 修正後の値取得
ccusage_after=$(npx ccusage@latest blocks --json | jq -r '.blocks[] | select(.isActive == true) | .totalTokens')
statusline_after=$(echo '{"session_id":"test"}' | python3 statusline.py --show 4 2>/dev/null | grep -o '[0-9,]*' | head -1 | tr -d ',')

echo "ccusage (after): $ccusage_after"
echo "statusline (after): $statusline_after"

if [[ "$ccusage_after" != "" && "$statusline_after" != "" ]]; then
    diff_after=$((statusline_after - ccusage_after))
    diff_pct_after=$(echo "scale=1; ($diff_after * 100.0) / $ccusage_after" | bc)
    echo "Difference (after): $diff_after tokens ($diff_pct_after%)"
    
    # 改善率計算
    improvement=$(echo "scale=1; $diff_pct_before - $diff_pct_after" | bc)
    echo "Improvement: $improvement percentage points"
    
    # 成功判定
    if (( $(echo "$diff_pct_after < 5.0" | bc -l) )); then
        echo "✅ SUCCESS: Difference within acceptable range (<5%)"
        exit 0
    else
        echo "⚠️  WARNING: Difference still significant (≥5%)"
        exit 1
    fi
else
    echo "❌ ERROR: Could not get post-fix measurements"
    exit 2
fi
```

### 3.2 よくある修正パターン

#### 3.2.1 キャッシュトークン二重カウント修正
```python
# 修正前（問題あり）
def get_total_tokens_problematic(usage_data):
    cache_creation = (
        usage_data.get('cache_creation_input_tokens', 0) or
        usage_data.get('cache_creation', {}).get('ephemeral_5m_input_tokens', 0)
    )
    # ↑ `or`演算子により両方が非ゼロの場合に最初の値のみ使用、
    #   しかし実際には同じ値が格納されているため問題なし？
    #   実際の問題は別の箇所にある可能性

# 修正後（ccusage互換）
def get_total_tokens_fixed(usage_data):
    """ccusageと完全互換のトークン計算"""
    if not usage_data:
        return 0
    
    input_tokens = usage_data.get('input_tokens', 0)
    output_tokens = usage_data.get('output_tokens', 0)
    
    # ccusageの条件分岐ロジックを正確に再現
    if 'cache_creation_input_tokens' in usage_data:
        cache_creation = usage_data['cache_creation_input_tokens']
    else:
        # ccusageは cacheCreationTokens をチェックするが、
        # Claude Codeでは cache_creation.ephemeral_5m_input_tokens を使用
        cache_creation = usage_data.get('cache_creation', {}).get('ephemeral_5m_input_tokens', 0)
    
    if 'cache_read_input_tokens' in usage_data:
        cache_read = usage_data['cache_read_input_tokens']
    else:
        cache_read = usage_data.get('cache_read', {}).get('ephemeral_5m_input_tokens', 0)
    
    return input_tokens + output_tokens + cache_creation + cache_read
```

#### 3.2.2 重複除去ロジック修正
```python
# ccusage互換の重複除去
def create_message_hash_ccusage_compatible(message):
    """ccusage互換のメッセージハッシュ生成"""
    
    # ccusageのhash生成ロジックを再現
    message_id = message.get('message', {}).get('id')  # ネストされたアクセス
    request_id = message.get('requestId')
    
    if message_id and request_id:
        return f"{message_id}:{request_id}"
    else:
        return None  # ccusageは該当しないメッセージは処理しない

# 修正版の重複除去実装
def deduplicate_messages_ccusage_style(messages):
    """ccusage方式の重複除去"""
    
    seen_hashes = set()
    deduplicated = []
    duplicate_count = 0
    
    for message in messages:
        message_hash = create_message_hash_ccusage_compatible(message)
        
        if message_hash is None:
            # ハッシュ生成できないメッセージはccusageでは無視
            continue
            
        if message_hash not in seen_hashes:
            seen_hashes.add(message_hash)
            deduplicated.append(message)
        else:
            duplicate_count += 1
    
    return deduplicated, duplicate_count
```

## 4. 予防的監視システム

### 4.1 継続的監視の設定

#### 4.1.1 自動監視スクリプト
```python
#!/usr/bin/env python3
"""
継続的互換性監視システム
定期的にccusageとstatuslineの差異を監視し、閾値を超えた場合にアラート
"""

import time
import json
import subprocess
import logging
from datetime import datetime
import smtplib
from email.mime.text import MIMEText

class CompatibilityMonitor:
    
    def __init__(self, config_file='monitoring_config.json'):
        with open(config_file) as f:
            self.config = json.load(f)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('compatibility_monitor.log'),
                logging.StreamHandler()
            ]
        )
        
    def measure_current_difference(self):
        """現在の差異を測定"""
        try:
            # ccusage値取得
            ccusage_result = subprocess.run(
                ['npx', 'ccusage@latest', 'blocks', '--json'],
                capture_output=True, text=True, timeout=30
            )
            ccusage_data = json.loads(ccusage_result.stdout)
            ccusage_tokens = next(
                (block['totalTokens'] for block in ccusage_data['blocks'] if block.get('isActive')),
                None
            )
            
            # statusline値取得
            statusline_result = subprocess.run(
                ['python3', 'statusline.py', '--show', '4'],
                input='{"session_id":"monitoring"}',
                capture_output=True, text=True, timeout=30
            )
            # statusline出力から数値抽出
            import re
            statusline_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s+token', statusline_result.stdout)
            statusline_tokens = int(statusline_match.group(1).replace(',', '')) if statusline_match else None
            
            if ccusage_tokens and statusline_tokens:
                difference = statusline_tokens - ccusage_tokens
                percentage = (difference / ccusage_tokens) * 100
                
                return {
                    'timestamp': datetime.now(),
                    'ccusage_tokens': ccusage_tokens,
                    'statusline_tokens': statusline_tokens,
                    'difference': difference,
                    'percentage': percentage,
                    'success': True
                }
            else:
                return {'success': False, 'error': 'Failed to extract token values'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def evaluate_alert_level(self, measurement):
        """アラートレベルの判定"""
        if not measurement['success']:
            return 'ERROR'
        
        percentage = abs(measurement['percentage'])
        
        if percentage >= 50:
            return 'CRITICAL'
        elif percentage >= 20:
            return 'WARNING'
        elif percentage >= 5:
            return 'INFO'
        else:
            return 'OK'
    
    def send_alert(self, level, measurement):
        """アラート送信"""
        
        alert_config = self.config['alerts'][level.lower()]
        
        if not alert_config.get('enabled', False):
            return
            
        message = f"""
Compatibility Alert - Level {level}

Timestamp: {measurement['timestamp']}
ccusage tokens: {measurement['ccusage_tokens']:,}
statusline tokens: {measurement['statusline_tokens']:,}
Difference: {measurement['difference']:,} tokens ({measurement['percentage']:.1f}%)

Alert threshold: {alert_config.get('threshold', 'N/A')}%

Please investigate immediately.
"""
        
        # Slack通知
        if alert_config.get('slack_enabled'):
            self.send_slack_alert(message, level)
            
        # Email通知
        if alert_config.get('email_enabled'):
            self.send_email_alert(message, level, alert_config['email_recipients'])
    
    def run_monitoring_loop(self):
        """監視ループの実行"""
        
        logging.info("Starting compatibility monitoring...")
        
        while True:
            try:
                measurement = self.measure_current_difference()
                alert_level = self.evaluate_alert_level(measurement)
                
                logging.info(f"Measurement: {alert_level} - "
                           f"Difference: {measurement.get('percentage', 'N/A'):.1f}%")
                
                if alert_level != 'OK':
                    self.send_alert(alert_level, measurement)
                    
                # 測定結果の記録
                self.record_measurement(measurement, alert_level)
                
                # 次回測定まで待機
                time.sleep(self.config['monitoring']['interval_seconds'])
                
            except KeyboardInterrupt:
                logging.info("Monitoring stopped by user")
                break
            except Exception as e:
                logging.error(f"Monitoring loop error: {e}")
                time.sleep(60)  # エラー時は1分待機

if __name__ == "__main__":
    monitor = CompatibilityMonitor()
    monitor.run_monitoring_loop()
```

#### 4.1.2 監視設定ファイル
```json
{
  "monitoring": {
    "interval_seconds": 300,
    "retention_days": 30
  },
  "alerts": {
    "critical": {
      "enabled": true,
      "threshold": 50,
      "slack_enabled": true,
      "email_enabled": true,
      "email_recipients": ["dev-team@company.com", "on-call@company.com"]
    },
    "warning": {
      "enabled": true, 
      "threshold": 20,
      "slack_enabled": true,
      "email_enabled": false
    },
    "info": {
      "enabled": true,
      "threshold": 5,
      "slack_enabled": false,
      "email_enabled": false
    },
    "error": {
      "enabled": true,
      "slack_enabled": true,
      "email_enabled": true,
      "email_recipients": ["dev-team@company.com"]
    }
  }
}
```

### 4.2 早期警戒システム

#### 4.2.1 トレンド異常検出
```python
def detect_trend_anomalies(measurement_history, lookback_hours=24):
    """トレンド異常の検出"""
    
    import numpy as np
    from scipy import stats
    
    if len(measurement_history) < 10:
        return {'anomaly_detected': False, 'reason': 'Insufficient data'}
    
    # 直近のデータ取得
    recent_data = [m for m in measurement_history 
                   if (datetime.now() - m['timestamp']).total_seconds() < lookback_hours * 3600]
    
    percentages = [m['percentage'] for m in recent_data]
    
    # 統計的異常検出
    z_scores = np.abs(stats.zscore(percentages))
    outliers = z_scores > 2.5  # 2.5σを超える値
    
    # トレンド分析
    if len(percentages) >= 5:
        slope, _, r_value, p_value, _ = stats.linregress(range(len(percentages)), percentages)
        
        trend_anomaly = {
            'anomaly_detected': False,
            'reasons': []
        }
        
        # 急激な増加トレンド
        if slope > 1.0 and p_value < 0.05:
            trend_anomaly['anomaly_detected'] = True
            trend_anomaly['reasons'].append(f'Rapid increasing trend: {slope:.2f}%/measurement')
        
        # 統計的外れ値の存在  
        if np.sum(outliers) > len(percentages) * 0.2:
            trend_anomaly['anomaly_detected'] = True
            trend_anomaly['reasons'].append(f'Statistical outliers: {np.sum(outliers)}/{len(percentages)} measurements')
        
        # 分散の急激な増加
        recent_std = np.std(percentages[-5:]) if len(percentages) >= 5 else 0
        historical_std = np.std(percentages[:-5]) if len(percentages) >= 10 else recent_std
        
        if recent_std > historical_std * 2:
            trend_anomaly['anomaly_detected'] = True
            trend_anomaly['reasons'].append(f'Increased volatility: {recent_std:.2f} vs {historical_std:.2f}')
        
        return trend_anomaly
    
    return {'anomaly_detected': False, 'reason': 'Insufficient data for trend analysis'}
```

## 5. 事後対応・学習システム

### 5.1 インシデント記録システム

#### 5.1.1 構造化されたインシデントレポート
```python
class IncidentReportGenerator:
    
    def __init__(self):
        self.template = self.load_incident_template()
    
    def generate_incident_report(self, incident_data):
        """構造化されたインシデントレポート生成"""
        
        report = {
            'incident_id': incident_data.get('id', f"INC_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
            'summary': {
                'title': incident_data.get('title', 'Token Calculation Discrepancy'),
                'severity': incident_data.get('severity', 'UNKNOWN'),
                'affected_systems': ['statusline', 'ccusage_compatibility'],
                'detection_time': incident_data.get('detection_time'),
                'resolution_time': incident_data.get('resolution_time'),
                'total_duration': self.calculate_duration(
                    incident_data.get('detection_time'),
                    incident_data.get('resolution_time')
                )
            },
            'impact_assessment': {
                'business_impact': incident_data.get('business_impact', 'LOW'),
                'user_impact': incident_data.get('user_impact', 'MINIMAL'),
                'data_accuracy_impact': incident_data.get('accuracy_impact', 'HIGH')
            },
            'timeline': self.structure_timeline(incident_data.get('timeline', [])),
            'root_cause_analysis': {
                'primary_cause': incident_data.get('root_cause'),
                'contributing_factors': incident_data.get('contributing_factors', []),
                'why_not_detected_earlier': incident_data.get('detection_failure_reason')
            },
            'resolution': {
                'actions_taken': incident_data.get('resolution_actions', []),
                'code_changes': incident_data.get('code_changes', []),
                'verification_method': incident_data.get('verification_method')
            },
            'prevention_measures': {
                'immediate_actions': incident_data.get('immediate_prevention', []),
                'long_term_improvements': incident_data.get('long_term_prevention', []),
                'monitoring_enhancements': incident_data.get('monitoring_improvements', [])
            },
            'lessons_learned': incident_data.get('lessons_learned', []),
            'action_items': self.extract_action_items(incident_data)
        }
        
        return report
    
    def extract_action_items(self, incident_data):
        """アクションアイテムの抽出"""
        
        action_items = []
        
        # 予防措置からのアクションアイテム
        for action in incident_data.get('immediate_prevention', []):
            action_items.append({
                'description': action,
                'type': 'prevention',
                'priority': 'HIGH',
                'due_date': (datetime.now() + timedelta(days=7)).isoformat(),
                'owner': 'dev_team'
            })
        
        # 監視改善のアクションアイテム  
        for improvement in incident_data.get('monitoring_improvements', []):
            action_items.append({
                'description': improvement,
                'type': 'monitoring',
                'priority': 'MEDIUM',
                'due_date': (datetime.now() + timedelta(days=14)).isoformat(),
                'owner': 'devops_team'
            })
        
        return action_items
```

### 5.2 継続的改善プロセス

#### 5.2.1 四半期振り返りレポート
```python
def generate_quarterly_retrospective():
    """四半期ごとの振り返りレポート生成"""
    
    # 過去3ヶ月のインシデントデータ収集
    incidents = load_incidents_last_quarter()
    
    # メトリクス集計
    metrics = {
        'total_incidents': len(incidents),
        'by_severity': count_by_severity(incidents),
        'by_root_cause': count_by_root_cause(incidents),
        'average_detection_time': calculate_average_detection_time(incidents),
        'average_resolution_time': calculate_average_resolution_time(incidents),
        'prevention_effectiveness': calculate_prevention_effectiveness(incidents)
    }
    
    # 傾向分析
    trends = {
        'incident_frequency_trend': analyze_frequency_trend(incidents),
        'severity_trend': analyze_severity_trend(incidents),
        'resolution_time_trend': analyze_resolution_time_trend(incidents)
    }
    
    # 改善提案
    recommendations = generate_improvement_recommendations(metrics, trends)
    
    return {
        'period': 'Q4 2025',
        'metrics': metrics,
        'trends': trends,
        'top_issues': identify_top_recurring_issues(incidents),
        'success_stories': identify_success_stories(incidents),
        'recommendations': recommendations,
        'next_quarter_goals': define_next_quarter_goals(recommendations)
    }
```

## 6. チェックリスト・テンプレート集

### 6.1 緊急対応チェックリスト

```markdown
# 🚨 緊急対応チェックリスト - Token Calculation Issue

## Phase 1: Initial Assessment (0-30 minutes)
- [ ] Confirm the issue is reproducible
- [ ] Measure current difference percentage: _____%
- [ ] Check if both tools are accessible and working
- [ ] Verify recent code changes in git log
- [ ] Determine severity level: [INFO / WARNING / CRITICAL / EMERGENCY]
- [ ] Notify appropriate stakeholders based on severity

## Phase 2: Quick Diagnostics (30-60 minutes)
- [ ] Run emergency diagnostic script
- [ ] Collect environmental information
- [ ] Check for recent ccusage version updates
- [ ] Verify transcript file accessibility
- [ ] Rule out infrastructure issues

## Phase 3: Root Cause Investigation (1-3 hours)
- [ ] Run hypothesis-driven testing
- [ ] Analyze code for suspicious patterns
- [ ] Compare field access logic between tools
- [ ] Test with isolated data samples
- [ ] Document findings with evidence

## Phase 4: Fix Implementation (30-90 minutes)
- [ ] Design fix based on root cause
- [ ] Implement fix with proper testing
- [ ] Run pre/post-fix validation
- [ ] Verify improvement meets target (<5% difference)
- [ ] Deploy to production

## Phase 5: Verification & Monitoring (30 minutes)
- [ ] Confirm fix effectiveness in production
- [ ] Set up enhanced monitoring
- [ ] Update documentation
- [ ] Schedule follow-up checks
- [ ] Close incident with proper documentation

**Emergency Contacts:**
- Dev Team Lead: ________________
- On-Call Engineer: ________________
- System Administrator: ________________
```

### 6.2 RCAレポートテンプレート

```markdown
# Root Cause Analysis Report

**Incident ID:** INC_YYYYMMDD_HHMMSS  
**Date:** YYYY-MM-DD  
**Prepared by:** [Name]  
**Review by:** [Senior Engineer/Architect]

## Executive Summary
- **Issue:** Brief description of the compatibility issue
- **Impact:** Business/technical impact assessment  
- **Root Cause:** One-sentence root cause summary
- **Resolution:** High-level resolution approach
- **Prevention:** Key prevention measures implemented

## Incident Timeline

| Time | Event | Impact | Action Taken |
|------|-------|---------|--------------|
| HH:MM | Issue first detected | Monitoring alerts triggered | Investigation started |
| HH:MM | Root cause identified | Development team assigned | Fix implementation began |
| HH:MM | Fix implemented | Testing initiated | Validation performed |
| HH:MM | Resolution verified | Issue resolved | Monitoring enhanced |

## Technical Analysis

### Environment Details
- **statusline version:** [commit hash / date]
- **ccusage version:** [npm version]
- **System environment:** [OS, Python, Node.js versions]
- **Data scope:** [number of transcript files, date range]

### Root Cause Deep Dive
**Primary Cause:** [Detailed technical explanation]

**Evidence:**
1. [Specific evidence item 1]
2. [Specific evidence item 2]  
3. [Code samples, data examples, calculations]

**Contributing Factors:**
1. [Factor 1: why it wasn't caught earlier]
2. [Factor 2: what made it manifest now]

### Fix Implementation
**Solution Approach:** [Technical solution description]

**Code Changes:** [List of modified files and functions]

**Before/After Comparison:**
- Before: statusline=XXX, ccusage=YYY (Z% difference)
- After: statusline=AAA, ccusage=BBB (C% difference)
- Improvement: [% improvement achieved]

## Prevention Measures

### Immediate Actions (Next 7 days)
1. [Specific preventive action 1] - Owner: [Name] - Due: [Date]
2. [Specific preventive action 2] - Owner: [Name] - Due: [Date]

### Long-term Improvements (Next 30-90 days)  
1. [Strategic improvement 1] - Owner: [Team] - Due: [Date]
2. [Strategic improvement 2] - Owner: [Team] - Due: [Date]

### Process Improvements
1. [Monitoring enhancement]
2. [Testing improvement]  
3. [Documentation update]

## Lessons Learned
1. **Technical:** [Key technical insight]
2. **Process:** [Process improvement identified]
3. **Communication:** [Communication enhancement needed]

## Success Factors
- [What went well during the incident response]
- [Effective practices to continue]

---
**Follow-up Review Scheduled:** [Date]  
**Next Quarterly Review:** [Date]
```

---

**このRunbookの使用方法**: 問題発生時は Section 1から開始し、重要度に応じて適切な対応レベルを選択。必ずチェックリストを使用して対応漏れを防ぐこと。対応完了後は必ずSection 5の事後対応でナレッジベースに記録すること。