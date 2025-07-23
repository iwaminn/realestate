# 保持すべきファイル一覧

## backend/scripts/ ディレクトリの主要ファイル

### 運用スクリプト
- `run_scrapers.py` - メインスクレイパー実行スクリプト
- `scrape_all.py` - 全スクレイパー実行スクリプト  
- `init_schema.py` - データベース初期化
- `init_v2_schema.py` - v2スキーマ初期化
- `check_migrations.py` - マイグレーション状態確認
- `auto_merge_duplicates.py` - 重複物件自動統合
- `recalculate_property_hash.py` - property_hash再計算
- `update_sold_properties.py` - 売却済み物件更新
- `detect_resale_properties.py` - 再販物件検出

### アクティブなスクレイパー（backend/app/scrapers/）
- `base_scraper.py` - ベーススクレイパークラス
- `suumo_scraper.py` - SUUMOスクレイパー
- `athome_scraper.py` - AtHomeスクレイパー  
- `homes_scraper.py` - HOMESスクレイパー

## 削除対象ファイル（約139ファイル）

### テスト・デバッグ・分析スクリプト（約100ファイル）
- `test_*.py` - 開発時のテストスクリプト（61ファイル）
- `debug_*.py` - デバッグ用スクリプト（20ファイル）
- `analyze_*.py` - 分析用スクリプト（11ファイル）
- `check_*.py` - チェック用スクリプト（15ファイル、check_migrations.py以外）

### 一時的な修正スクリプト（15ファイル）
- `fix_*.py` - 一度だけ実行する修正スクリプト

### 実行済み移行スクリプト（8ファイル）
- `add_*.py` - データベースカラム追加スクリプト
- `migrate_*.py` - データ移行スクリプト

### 重複・テスト用スクレイピングスクリプト（7ファイル）
- `scrape_10_*.py`, `scrape_300_*.py` など

### 未使用のスクレイパー（4ファイル）
- `nomu_scraper.py` - ノムコムスクレイパー（使用されていない）
- `rakumachi_scraper.py` - 楽待スクレイパー（ユーザー要望により除外）
- `rehouse_scraper.py` - リハウススクレイパー（使用されていない）
- `athome_scraper_advanced.py` - AtHomeの別実装

### バージョン付きファイル（2ファイル）
- `*_v2.py` - CLAUDE.md によると使用すべきでない

## 整理の利点
- ディレクトリがクリーンになり、現在使用中のファイルが明確になる
- 新規開発者が混乱しない
- 不要なファイルのメンテナンスコストがなくなる
- バックアップディレクトリに移動するため、必要に応じて復元可能