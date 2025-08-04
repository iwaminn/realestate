# 有効なスクレイパー一覧

最終更新日: 2025-07-24

## 現在有効なスクレイパー

以下のスクレイパーが現在実装されており、使用可能です：

| スクレイパー名 | 値 (value) | 表示名 (label) | ステータス | 備考 |
|------------|-----------|--------------|----------|------|
| SUUMO | `suumo` | SUUMO | ✅ 有効 | 最も安定して動作 |
| LIFULL HOME'S | `homes` | LIFULL HOME'S | ✅ 有効 | 新セレクタ対応済み |
| 三井のリハウス | `rehouse` | 三井のリハウス | ✅ 有効 | 2025年1月復活 |
| ノムコム | `nomu` | ノムコム | ✅ 有効 | 住所・総階数対応済み |
| 東急リバブル | `livable` | 東急リバブル | ✅ 有効 | 2025年7月追加 |

## 無効化されたスクレイパー

| スクレイパー名 | 値 (value) | 理由 | 無効化日 |
|------------|-----------|------|---------|
| AtHome | `athome` | CAPTCHA対策により現在スクレイピング不可（ファイル削除済み） | 2025-01-23 |
| 楽待 | - | ユーザー要望により除外 | - |

## 実装場所

### フロントエンド
- **管理画面のスクレイパー選択**: `/frontend/src/components/AdminScraping.tsx`
  ```typescript
  const scraperOptions = [
    { value: 'suumo', label: 'SUUMO' },
    { value: 'homes', label: "LIFULL HOME'S" },
    { value: 'rehouse', label: '三井のリハウス' },
    { value: 'nomu', label: 'ノムコム' },
    { value: 'livable', label: '東急リバブル' },
  ];
  ```

### バックエンド
- **APIエンドポイント**: `/backend/app/api/admin.py`
- **スクレイパー実行スクリプト**: `/backend/scripts/run_scrapers.py`
- **一括実行スクリプト**: `/backend/scripts/scrape_all.py`

### スクレイパー実装ファイル
- `/backend/app/scrapers/suumo_scraper.py`
- `/backend/app/scrapers/homes_scraper.py`
- `/backend/app/scrapers/rehouse_scraper.py`
- `/backend/app/scrapers/nomu_scraper.py`
- `/backend/app/scrapers/livable_scraper.py`

## 使用方法

### コマンドラインから実行
```bash
# 単一スクレイパーを実行
docker exec realestate-backend poetry run python /app/backend/scripts/run_scrapers.py --scraper suumo --area 13103 --max-properties 100

# 全スクレイパーを実行
docker exec realestate-backend poetry run python /app/backend/scripts/run_scrapers.py --area 13103 --max-properties 100
```

### 利用可能なスクレイパー値
- `suumo`
- `homes`
- `rehouse`
- `nomu`
- `livable`

## 注意事項

1. **新しいスクレイパーを追加する場合**、以下のファイルをすべて更新する必要があります：
   - `/frontend/src/components/AdminScraping.tsx`
   - `/backend/app/api/admin.py`
   - `/backend/scripts/run_scrapers.py`
   - `/backend/scripts/scrape_all.py`
   - このドキュメント

2. **スクレイパーを無効化する場合**も同様に、上記のファイルから該当するスクレイパーを削除し、このドキュメントの「無効化されたスクレイパー」セクションに移動してください。

3. **エリアコード**は東京23区の標準的な地域コード（13101〜13123）を使用します。