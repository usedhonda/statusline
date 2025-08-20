# Documentation Index - Statusline Project

**最終更新**: 2025-08-20  
**目的**: statusline プロジェクトの包括的な文書インデックス

## 📚 文書構成概要

### 🔧 実装・技術仕様書
| 文書名 | 説明 | 対象読者 | 最終更新 |
|--------|------|----------|----------|
| [BURN_LINE_IMPLEMENTATION_SPEC.md](./BURN_LINE_IMPLEMENTATION_SPEC.md) | Burn line（4行目）の実装仕様 | 開発者 | 2025-08-19 |
| [CURRENT_ARCHITECTURE_2025.md](./CURRENT_ARCHITECTURE_2025.md) | 現在のアーキテクチャ概要 | 開発者・アーキテクト | 2025年 |
| [TOKEN_CALCULATION_GUIDE.md](./TOKEN_CALCULATION_GUIDE.md) | トークン計算ロジック詳細 | 開発者 | 2025年 |

### 🐛 デバッグ・トラブルシューティング
| 文書名 | 説明 | 対象読者 | 最終更新 |
|--------|------|----------|----------|
| [TOKEN_CALCULATION_DEBUGGING_GUIDE.md](./TOKEN_CALCULATION_DEBUGGING_GUIDE.md) | トークン計算デバッグ手順 | 開発者・QA | 2025年 |
| **[TROUBLESHOOTING_RUNBOOK.md](./TROUBLESHOOTING_RUNBOOK.md)** | **緊急対応・トラブルシューティング完全ガイド** | **全員** | **2025-08-20** |

### 📖 開発手法・ベストプラクティス
| 文書名 | 説明 | 対象読者 | 最終更新 |
|--------|------|----------|----------|
| **[MULTI_TOOL_COMPATIBILITY_DEBUGGING_GUIDE.md](./MULTI_TOOL_COMPATIBILITY_DEBUGGING_GUIDE.md)** | **外部ツール互換性問題の体系的解決手法** | **開発者・アーキテクト** | **2025-08-20** |
| **[EXTERNAL_TOOL_VALIDATION_BEST_PRACTICES.md](./EXTERNAL_TOOL_VALIDATION_BEST_PRACTICES.md)** | **外部ツール検証のベストプラクティス** | **開発者・QA・DevOps** | **2025-08-20** |
| **[MULTI_AGENT_DEVELOPMENT_METHODOLOGY.md](./MULTI_AGENT_DEVELOPMENT_METHODOLOGY.md)** | **マルチエージェント開発手法** | **開発チーム・マネージャー** | **2025-08-20** |

### 🚀 開発・運用ガイド
| 文書名 | 説明 | 対象読者 | 最終更新 |
|--------|------|----------|----------|
| [DEVELOPMENT_RESTART_GUIDE.md](./DEVELOPMENT_RESTART_GUIDE.md) | 開発再開時のガイド | 開発者 | 2025年 |
| [DEVELOPMENT_SUMMARY_2025.md](./DEVELOPMENT_SUMMARY_2025.md) | 2025年開発サマリー | 全員 | 2025年 |

## 🎯 用途別文書ガイド

### 🚨 緊急時・問題発生時
1. **[TROUBLESHOOTING_RUNBOOK.md](./TROUBLESHOOTING_RUNBOOK.md)** - 緊急対応の完全ガイド
2. [TOKEN_CALCULATION_DEBUGGING_GUIDE.md](./TOKEN_CALCULATION_DEBUGGING_GUIDE.md) - トークン計算問題の詳細デバッグ

### 🔍 新しい互換性問題の調査
1. **[MULTI_TOOL_COMPATIBILITY_DEBUGGING_GUIDE.md](./MULTI_TOOL_COMPATIBILITY_DEBUGGING_GUIDE.md)** - 体系的な問題解決アプローチ
2. **[EXTERNAL_TOOL_VALIDATION_BEST_PRACTICES.md](./EXTERNAL_TOOL_VALIDATION_BEST_PRACTICES.md)** - 検証・監視のベストプラクティス

### 👥 複雑な問題の協調解決
1. **[MULTI_AGENT_DEVELOPMENT_METHODOLOGY.md](./MULTI_AGENT_DEVELOPMENT_METHODOLOGY.md)** - チーム協調・専門分化アプローチ

### 🛠️ 実装・開発作業
1. [BURN_LINE_IMPLEMENTATION_SPEC.md](./BURN_LINE_IMPLEMENTATION_SPEC.md) - Burn line機能の実装
2. [TOKEN_CALCULATION_GUIDE.md](./TOKEN_CALCULATION_GUIDE.md) - トークン計算ロジック
3. [CURRENT_ARCHITECTURE_2025.md](./CURRENT_ARCHITECTURE_2025.md) - アーキテクチャ理解

## 🌟 重要な成果文書（2025-08-20作成）

### 📋 statusline vs ccusage 問題解決から得られた知見

今回の **statusline 96.7M vs ccusage 59.7M トークン（62%差異）** 問題の解決過程で確立された以下の重要な手法を文書化：

#### 🎯 [MULTI_TOOL_COMPATIBILITY_DEBUGGING_GUIDE.md](./MULTI_TOOL_COMPATIBILITY_DEBUGGING_GUIDE.md)
- **段階的デバッグ戦略**: 問題定量化 → 外部ツール逆エンジニアリング → データ構造分析 → 体系的修正
- **実証された効果**: 62%差異を13.9%まで改善（76%の精度向上）
- **再利用可能**: 任意の外部ツール互換性問題に適用可能

#### 🔍 [EXTERNAL_TOOL_VALIDATION_BEST_PRACTICES.md](./EXTERNAL_TOOL_VALIDATION_BEST_PRACTICES.md)
- **継続的検証**: 自動監視・アラート・トレンド分析システム
- **品質保証**: 多次元品質評価・回帰テスト・パフォーマンス監視
- **組織的成功**: チーム体制・SLA定義・ベンダー関係管理

#### 🤖 [MULTI_AGENT_DEVELOPMENT_METHODOLOGY.md](./MULTI_AGENT_DEVELOPMENT_METHODOLOGY.md)
- **専門エージェント活用**: ccusage-analyzer, claude-data-specialist, algorithm-debugger, statusline-optimizer
- **協調的問題解決**: 並行実行・情報共有・相互検証による効率化
- **実証された成果**: 従来の1/3の時間で高品質な解決策を実現

#### 🚨 [TROUBLESHOOTING_RUNBOOK.md](./TROUBLESHOOTING_RUNBOOK.md)
- **緊急対応プロトコル**: 重要度別対応・初動チェックリスト・エスカレーション基準
- **再発防止**: 継続的監視・予防システム・学習機能
- **組織的改善**: インシデント記録・四半期振り返り・ナレッジ蓄積

## 📖 使用方法・読み方ガイド

### 新規参加者向け
```
1. CURRENT_ARCHITECTURE_2025.md        # 全体像の理解
2. BURN_LINE_IMPLEMENTATION_SPEC.md    # 主要機能の詳細
3. TOKEN_CALCULATION_GUIDE.md          # 核心ロジック
4. TROUBLESHOOTING_RUNBOOK.md          # 問題対応方法
```

### 問題発生時の緊急対応
```
1. TROUBLESHOOTING_RUNBOOK.md                    # まず最初にここを確認
2. MULTI_TOOL_COMPATIBILITY_DEBUGGING_GUIDE.md  # 体系的調査が必要な場合
3. TOKEN_CALCULATION_DEBUGGING_GUIDE.md         # トークン計算問題の場合
```

### 新機能開発時
```
1. MULTI_AGENT_DEVELOPMENT_METHODOLOGY.md       # 複雑な機能の協調開発
2. EXTERNAL_TOOL_VALIDATION_BEST_PRACTICES.md   # 外部連携機能の品質保証
3. 該当する実装仕様書                              # 具体的な実装ガイド
```

## 🔄 文書メンテナンス

### 更新頻度
- **緊急対応文書**: 問題発生・解決時に即座に更新
- **実装仕様書**: 機能変更時に更新
- **手法・ベストプラクティス**: 四半期ごとに見直し

### 品質保証
- 全ての新文書は最低1名のレビューア確認を経て登録
- 重要文書は複数の専門家による検証を実施
- 実際の問題解決で検証された内容のみを記載

### アクセシビリティ
- 緊急時でも迅速にアクセス可能な構成
- 用途別インデックスによる目的別ナビゲーション
- 実践的なコード例・チェックリスト・テンプレートを提供

---

**このインデックスの目的**: statusline プロジェクトの知見を効率的に活用し、同様の問題の再発防止と迅速解決を支援すること。新しい知見が得られた際は、適切な文書に追記し、必要に応じて新文書を作成すること。