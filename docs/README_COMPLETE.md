# 🏠 中古不動産横断検索システム - 完全版

## 🎯 システム概要

SUUMO、アットホームなどの主要不動産ポータルサイトから定期的に中古不動産情報を収集し、重複排除・価格履歴追跡・通知機能を備えた横断検索システムです。

### 📍 対象エリア
- **初期対象**: 東京都港区
- **拡張対応**: 他市区町村・都道府県への拡張が容易な設計

## 🚀 実装済み機能

### 1. 📊 データ収集システム
- **規約遵守型スクレイピング**: robots.txt自動チェック、適切な遅延制御
- **高精度データ抽出**: 価格、間取り、面積、築年数、管理費等
- **キャッシュ機能**: レスポンス時間短縮とサーバー負荷軽減
- **エラーハンドリング**: 自動リトライ、ログ記録

### 2. 🔄 重複排除エンジン
- **高精度マッチング**: 住所・間取り・面積・築年数による類似度判定
- **自動統合**: 閾値を超えた類似物件の自動マージ
- **手動確認**: 微妙な類似度の物件は手動確認可能
- **データ保全**: 統合時の情報補完と履歴保持

### 3. 📈 価格履歴追跡
- **変動検出**: 価格変更の自動検出・記録
- **トレンド分析**: 上昇・下降・安定の判定
- **統計情報**: 最高・最低価格、平均変動率等
- **市場分析**: 価格帯別分布、間取り別統計

### 4. 🔔 通知システム
- **価格下落通知**: 指定閾値以上の価格下落を検知
- **新着物件通知**: 新規登録物件の即座通知
- **日次サマリー**: 毎日の活動概要レポート
- **多チャンネル対応**: メール、Slack、Discord、Webhook

### 5. ⏰ 定期実行スケジューラー
- **自動スクレイピング**: 毎日定時実行
- **重複排除**: 収集後の自動重複処理
- **価格履歴更新**: 定期的な価格変動チェック
- **データベース最適化**: 定期クリーンアップ・バックアップ

### 6. 🌐 API システム
- **RESTful API**: 物件検索、比較、統計情報提供
- **リアルタイム検索**: 価格・間取り・面積等での絞り込み
- **物件比較**: 複数物件の詳細比較
- **統計ダッシュボード**: 市場トレンド分析

## 📁 ファイル構成

```
realestate/
├── 📋 設定・ドキュメント
│   ├── CLAUDE.md                    # プロジェクト仕様
│   ├── README_COMPLETE.md           # 完全版ドキュメント
│   └── scraping_guidelines.md       # スクレイピング規約
│
├── 🗄️ データベース・サーバー
│   ├── realestate.db               # SQLiteデータベース
│   ├── server.py                   # APIサーバー
│   └── db_helper.py                # データベース管理ツール
│
├── 🔧 コア機能
│   ├── scraper.py                  # 基本スクレイピング
│   ├── enhanced_scraper.py         # 改良版スクレイピング
│   ├── deduplication_engine.py     # 重複排除エンジン
│   ├── price_history_tracker.py    # 価格履歴追跡
│   └── notification_system.py      # 通知システム
│
├── ⚙️ 運用・管理
│   ├── scheduler.py                # 定期実行スケジューラー
│   ├── test_scraper.py            # テストツール
│   └── test_scraper_limited.py    # 制限付きテスト
│
└── 📁 ディレクトリ
    ├── cache/                      # スクレイピングキャッシュ
    ├── backups/                    # データベースバックアップ
    └── logs/                       # ログファイル
```

## 🔧 セットアップ・使用方法

### 1. 基本環境構築
```bash
# 必要ライブラリのインストール
pip install requests beautifulsoup4 schedule

# データベースの初期化
python3 db_helper.py tables
```

### 2. 各機能の実行

#### 🔍 スクレイピング
```bash
# 基本スクレイピング
python3 scraper.py

# 改良版スクレイピング（推奨）
python3 enhanced_scraper.py

# テスト実行
python3 test_scraper.py
```

#### 🔄 重複排除
```bash
# 重複排除エンジン起動
python3 deduplication_engine.py

# 自動統合実行
python3 -c "from deduplication_engine import DeduplicationEngine; DeduplicationEngine().run_deduplication(auto_merge=True)"
```

#### 📈 価格履歴管理
```bash
# 価格履歴追跡システム
python3 price_history_tracker.py

# 価格履歴の更新
python3 -c "from price_history_tracker import PriceHistoryTracker; PriceHistoryTracker().update_all_price_history()"
```

#### 🔔 通知システム
```bash
# 通知設定テスト
python3 notification_system.py test

# 定期チェック実行
python3 notification_system.py check

# 日次サマリー送信
python3 notification_system.py summary
```

#### ⏰ スケジューラー
```bash
# スケジューラー開始
python3 scheduler.py run

# 個別ジョブ実行
python3 scheduler.py run-job scraping
python3 scheduler.py run-job deduplication

# 実行履歴確認
python3 scheduler.py history
```

#### 🌐 APIサーバー
```bash
# サーバー起動
python3 server.py

# API利用例
curl "http://localhost:8000/api/v1/properties"
curl "http://localhost:8000/api/v1/properties/1"
curl "http://localhost:8000/api/v1/stats"
```

#### 🗄️ データベース管理
```bash
# データベース統計
python3 db_helper.py stats

# 物件データ表示
python3 db_helper.py properties

# 任意のSQL実行
python3 db_helper.py query "SELECT * FROM properties LIMIT 5"
```

## 🔧 設定ファイル

### スケジューラー設定 (`scheduler_config.json`)
```json
{
  "scraping": {
    "enabled": true,
    "schedule": "0 6 * * *"
  },
  "deduplication": {
    "enabled": true,
    "schedule": "0 7 * * *"
  }
}
```

### 通知設定 (`notification_config.json`)
```json
{
  "email": {
    "enabled": false,
    "smtp_server": "smtp.gmail.com",
    "username": "your-email@gmail.com",
    "to_addresses": ["recipient@example.com"]
  },
  "slack": {
    "enabled": false,
    "webhook_url": "https://hooks.slack.com/..."
  }
}
```

## 📊 データベース構造

### 主要テーブル
- **properties**: 物件情報（住所、間取り、価格等）
- **property_listings**: リスティング情報（サイト別掲載情報）
- **price_history**: 価格履歴（変動記録）
- **areas**: エリア情報（拡張用）

### 🔄 PostgreSQL移行対応
現在のSQLite実装は、将来的なPostgreSQL移行を想定した設計になっています。

## ⚠️ 利用上の注意

### 🛡️ 規約遵守
- **各サイトの利用規約を必ず確認**
- **robots.txt準拠**: 自動チェック機能搭載
- **適切な遅延**: サーバー負荷軽減
- **商用利用**: 各サイトの許可が必要

### 🔒 セキュリティ
- **個人情報保護**: 適切なデータ管理
- **アクセス制御**: API認証の実装推奨
- **データ暗号化**: 機密データの保護

### 📈 パフォーマンス
- **キャッシュ活用**: レスポンス時間短縮
- **バッチ処理**: 大量データの効率的処理
- **インデックス**: データベース最適化

## 🛠️ 今後の拡張予定

### 1. 機能拡張
- **地図表示**: Google Maps API連携
- **フロントエンド**: React.js GUI
- **機械学習**: 価格予測モデル
- **画像認識**: 物件写真解析

### 2. 技術向上
- **PostgreSQL移行**: 本格運用対応
- **Docker化**: 簡単デプロイ
- **CI/CD**: 自動テスト・デプロイ
- **監視**: システム監視・アラート

### 3. データ拡張
- **新サイト対応**: 楽待、ホームズ等
- **エリア拡張**: 全国対応
- **物件種別**: 賃貸、新築等

## 🤝 サポート

### 📞 問題が発生した場合
1. **ログ確認**: `scheduler.log`, `scraper.log`
2. **設定確認**: JSON設定ファイル
3. **データベース状態**: `db_helper.py stats`
4. **通知テスト**: `notification_system.py test`

### 🔄 メンテナンス
- **定期バックアップ**: 自動バックアップ機能
- **ログローテーション**: 定期的なログ削除
- **設定更新**: 動的設定変更対応

---

**📝 このシステムは、不動産情報の効率的な収集・管理・分析を目的として開発されました。各サイトの利用規約を遵守し、適切にご利用ください。**