# スクレイピング遅延仕様

最終更新日: 2025-07-29

## 概要

このドキュメントは、マンション一括検索システムにおけるスクレイピング時の遅延（レート制限）仕様について説明します。

## 基本設定

### デフォルト遅延時間

- **base_scraper.py**: 環境変数 `SCRAPER_DELAY` で設定（デフォルト: 1秒）
- **scraper_config.py**: `DEFAULT_DELAY = 2` （デフォルト: 2秒）
- **fetch_page メソッド**: ハードコーディングで2秒の遅延

### 実際の遅延実装

#### 1. 基本的なページ取得（base_scraper.py）
```python
def fetch_page(self, url: str) -> BeautifulSoup:
    """ページを取得してBeautifulSoupオブジェクトを返す"""
    try:
        time.sleep(2)  # レート制限対策（ハードコーディング）
        response = self.http_session.get(url, timeout=30)
```

#### 2. 各スクレイパーでの詳細ページ取得
- **SUUMO**: `time.sleep(self.delay)` - 環境変数に基づく遅延
- **LIFULL HOME'S**: 
  - 通常: `time.sleep(3)` - 3秒の固定遅延
  - リトライ時: `time.sleep(5)` - 5秒の固定遅延
- **東急リバブル**: `time.sleep(self.delay)` - 環境変数に基づく遅延

## スクレイパー別の遅延設定

### LIFULL HOME'S（最も厳格）
```python
# 通常のページ取得
time.sleep(3)  # 3秒の固定遅延

# リトライ時
time.sleep(5)  # 5秒の固定遅延
```
理由: LIFULL HOME'Sは最もアクセス制限が厳しいため、長めの遅延を設定

### SUUMO、東急リバブル、三井のリハウス、ノムコム
```python
time.sleep(self.delay)  # 環境変数に基づく遅延（デフォルト1-2秒）
```

## 環境変数による設定

### グローバル設定
```bash
# 全スクレイパー共通の遅延時間（秒）
export SCRAPER_DELAY=2
```

### スクレイパー固有の設定
```bash
# SUUMOのみ異なる遅延時間を設定
export SCRAPER_SUUMO_DELAY=3

# LIFULL HOME'Sのみ異なる遅延時間を設定
export SCRAPER_HOMES_DELAY=5
```

## 一時停止機能での遅延

タスクの一時停止チェック時には、0.1秒の短い遅延を使用：
```python
time.sleep(0.1)  # 一時停止チェック用の短い遅延
```

## 推奨設定

### 通常運用
- **デフォルト**: 2秒
- **LIFULL HOME'S**: 3-5秒（ハードコーディングで対応済み）
- **その他**: 1-2秒

### 高負荷時期（例：夜間、週末）
- **全体**: 3-5秒に増加
- **LIFULL HOME'S**: 5-7秒に増加

### エラー発生時
- 自動的により長い遅延を適用（LIFULL HOME'Sでは5秒）

## 注意事項

1. **ハードコーディングされた遅延**
   - `base_scraper.py` の `fetch_page` メソッドには2秒の固定遅延がある
   - LIFULL HOME'Sには3秒と5秒の固定遅延がある
   - これらは環境変数では変更できない

2. **実効的な遅延**
   - 実際の遅延は「fetch_pageの2秒」+「各スクレイパーの遅延」の合計
   - 例：SUUMOの場合、2秒（fetch_page）+ 1秒（self.delay）= 3秒

3. **サイト別の配慮**
   - LIFULL HOME'Sは最も厳格なため、独自の長い遅延を実装
   - 他のサイトは環境変数で調整可能

## 今後の改善提案

1. **統一的な遅延管理**
   - ハードコーディングされた遅延を環境変数に移行
   - サイト別の遅延設定を設定ファイルで管理

2. **動的な遅延調整**
   - エラー率に基づいて自動的に遅延を調整
   - 時間帯による遅延の自動調整

3. **詳細なモニタリング**
   - 各サイトのレスポンス時間を記録
   - 遅延の効果を測定して最適化