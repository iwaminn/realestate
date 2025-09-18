# 管理画面機能仕様書

最終更新日: 2025-11-18

## 概要

このドキュメントは、都心マンションDBシステムの管理画面機能の仕様を記載しています。

## データ更新管理機能

### バッチ処理設定

管理画面のデータ更新管理機能では、以下のバッチサイズで処理を行います：

| 機能 | バッチサイズ | 説明 |
|------|------------|------|
| キューを処理 | 1000件 | 価格変更のあった物件を1000件ずつバッチ処理 |
| 価格改定履歴の更新 | 無制限 | すべてのアクティブな物件の価格履歴を一括更新 |

#### 実装詳細

- **フロントエンド**: `/frontend/src/components/admin/DataUpdateManagement.tsx`
  ```typescript
  // キューを処理
  const response = await fetch('/api/admin/price-changes/process', {
    method: 'POST',
    params: { limit: 1000 }  // 1000件まで処理
  });
  ```

- **バックエンド**: `/backend/app/api/admin/price_changes.py`
  ```python
  @router.post("/price-changes/process")
  async def process_price_changes(
      limit: int = Query(1000, description="処理する最大件数")
  ):
      # 最大1000件まで処理
  ```

### 価格変更検出機能

価格変更の検出と履歴管理は以下の流れで行われます：

1. **価格変更の検出**
   - 各物件の現在価格と過去の価格を比較
   - 変更があった物件をキューに追加

2. **バッチ処理**
   - キューから最大1000件を取得して処理
   - 価格履歴テーブルに新しい価格を記録
   - 物件の最終更新日時を更新

3. **履歴の一括更新**
   - すべてのアクティブな物件の価格を確認
   - 価格履歴が存在しない場合は新規作成
   - 履歴が古い場合は最新価格で更新

## スクレイピング管理機能

### タスクキャンセル時の動作

スクレイピングタスクをキャンセルした場合、以下の処理が行われます：

1. **親タスクのキャンセル**
   - タスクステータスを`cancelled`に変更
   - 完了時刻を記録

2. **個別スクレイパータスクのキャンセル**（2025-11-18追加）
   - 実行中（`running`）、一時停止中（`paused`）、待機中（`pending`）の個別タスクも`cancelled`に変更
   - 各個別タスクの完了時刻を記録

#### 実装詳細

- **バックエンド**: `/backend/app/api/admin/scraping.py`
  ```python
  @router.post("/scraping/cancel/{task_id}")
  def cancel_scraping(task_id: str, db: Session = Depends(get_db)):
      # 親タスクをキャンセル
      db_task.status = "cancelled"

      # 個別のスクレイパータスクもキャンセル
      if db_task.progress_detail:
          for scraper_key in db_task.progress_detail.keys():
              if db_task.progress_detail[scraper_key].get('status') in ['running', 'paused', 'pending']:
                  db_task.progress_detail[scraper_key]['status'] = 'cancelled'
  ```

### ログのページネーション処理

スクレイピング管理画面では、ログの差分更新時に以下の処理が行われます：

1. **ログの差分取得**
   - 前回取得時刻以降の新しいログのみを取得
   - 既存のログに追加

2. **ページネーション自動調整**（2025-11-18追加）
   - ログ数が変更された際、現在のページが範囲外の場合は自動的に1ページ目にリセット
   - 通常ログ、警告ログの両方に適用

#### 実装詳細

- **フロントエンド**: `/frontend/src/components/AdminScraping.tsx`
  ```typescript
  // ページ範囲外時の自動リセット
  React.useEffect(() => {
    if (logPage > totalPages && totalPages > 0) {
      setLogPage(1);  // 最新のログを表示するため1ページ目にリセット
    }
  }, [task.logs.length, logPage, totalPages]);
  ```

## データ検証設定

### 物件データの検証範囲

管理画面から入力される物件データには以下の検証が適用されます：

| フィールド | 最小値 | 最大値 | 備考 |
|-----------|--------|--------|------|
| 価格 | 100万円 | 100億円 | 異常な価格を除外 |
| 専有面積 | 10㎡ | 1000㎡ | 一般的な物件の範囲 |
| 所在階 | -5階 | 100階 | 地下5階まで対応 |
| 管理費 | 0円 | 300,000円 | 高級物件対応（2025-11-18更新） |
| 修繕積立金 | 0円 | 150,000円 | 高級物件対応（2025-11-18更新） |

#### 実装詳細

- **バックエンド**: `/backend/app/scrapers/components/data_validator.py`
  ```python
  FIELD_VALIDATORS = {
      'price': {'min': 1000000, 'max': 10000000000},
      'area': {'min': 10, 'max': 1000},
      'floor_number': {'min': -5, 'max': 100},
      'management_fee': {'min': 0, 'max': 300000},  # 30万円まで
      'repair_fund': {'min': 0, 'max': 150000},     # 15万円まで
  }
  ```

## 更新履歴

- 2025-11-18: 初版作成
  - データ更新管理のバッチ処理仕様を文書化
  - タスクキャンセル時の個別タスク更新処理を追加
  - ログページネーションの自動調整機能を追加
  - 管理費・修繕積立金の検証上限値を更新