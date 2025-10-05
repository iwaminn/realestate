# 本番環境マイグレーション手順: current_price追加

## 概要
`master_properties`テーブルに`current_price`カラムを追加し、既存の価格フィールド（`min_price`/`max_price`/`majority_price`）を統一します。

## 変更内容
- **追加カラム**: `master_properties.current_price` (INTEGER型、NULL許可)
- **データ更新**: 全物件の`current_price`を計算して設定
- **影響範囲**:
  - バックエンドAPI 4箇所（properties, buildings, bookmarks, properties_recent_updates）
  - フロントエンド 4箇所（PropertyCard, BuildingPropertiesPage, PropertyDetailPage, BookmarksPage）
  - 型定義 1箇所（property.ts）

## 前提条件
- PostgreSQL 15以上
- データベース接続権限
- 本番環境へのSSHアクセス
- バックアップが取得済みであること

## マイグレーション手順

### 1. 事前準備（本番サーバーで実行）

```bash
# 本番サーバーにSSH接続
ssh your-production-server

# プロジェクトディレクトリに移動
cd /path/to/realestate

# 最新コードを取得
git pull origin master

# バックアップを取得（重要！）
docker exec realestate-postgres pg_dump -U realestate -d realestate > backup_before_migration_$(date +%Y%m%d_%H%M%S).sql
```

### 2. データベースマイグレーション実行

```bash
# マイグレーションスクリプトをPostgreSQLコンテナにコピー
docker cp backend/scripts/migrate_add_current_price.sql realestate-postgres:/tmp/

# PostgreSQLコンテナに接続してマイグレーション実行
docker exec -it realestate-postgres psql -U realestate -d realestate -f /tmp/migrate_add_current_price.sql
```

**期待される出力例**:
```
NOTICE:  current_priceカラムを追加しました
UPDATE 1234  # 更新された物件数
 total_properties | properties_with_price | properties_without_price | min_price | max_price | avg_price
------------------+-----------------------+--------------------------+-----------+-----------+-----------
             1234 |                  1200 |                       34 |      2000 |   500000 |     45000
```

### 3. データ整合性確認

```bash
# データベースに接続
docker exec -it realestate-postgres psql -U realestate -d realestate

# 以下のSQLを実行して確認
```

```sql
-- 1. current_priceが設定されている物件数
SELECT
    COUNT(*) as total,
    COUNT(current_price) as with_price,
    COUNT(*) - COUNT(current_price) as without_price
FROM master_properties;

-- 2. 販売中物件でcurrent_priceがNULLの件数（少数であるべき）
SELECT COUNT(*)
FROM master_properties
WHERE sold_at IS NULL
    AND current_price IS NULL;

-- 3. サンプルデータ確認（物件一覧APIで使用される価格）
SELECT
    mp.id,
    b.normalized_name,
    mp.room_number,
    mp.current_price,
    mp.sold_at,
    mp.final_price
FROM master_properties mp
JOIN buildings b ON b.id = mp.building_id
ORDER BY mp.id DESC
LIMIT 20;
```

### 4. アプリケーション再起動

```bash
# バックエンドとフロントエンドを再ビルド＆再起動
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build

# nginxも再起動（コンテナIPが変わるため）
docker compose -f docker-compose.prod.yml restart nginx

# 起動確認
docker compose -f docker-compose.prod.yml ps

# ログ確認
docker compose -f docker-compose.prod.yml logs backend --tail 100
docker compose -f docker-compose.prod.yml logs frontend --tail 100
```

### 5. 動作確認

以下のページで価格が正しく表示されることを確認：

1. **物件一覧ページ**: `https://your-domain.com/`
   - 物件カードに価格が表示されること
   - 並び替え（価格順）が正常に動作すること

2. **物件詳細ページ**: `https://your-domain.com/properties/123`
   - 価格が表示されること

3. **建物別物件一覧**: `https://your-domain.com/buildings/456/properties`
   - 各物件の価格が表示されること
   - 平均坪単価が表示されること

4. **ブックマーク一覧**: `https://your-domain.com/bookmarks`
   - 保存した物件の価格が表示されること

5. **新規掲載物件一覧**: `https://your-domain.com/updates?tab=1`
   - 新規掲載物件の価格が表示されること

6. **価格改定履歴**: `https://your-domain.com/updates?tab=0`
   - 価格改定情報が正しく表示されること

### 6. トラブルシューティング

#### 問題: 価格が表示されない

**原因**: `current_price`がNULLの可能性

**対処**:
```sql
-- current_priceがNULLの物件を調査
SELECT
    mp.id,
    mp.building_id,
    COUNT(pl.id) as listing_count,
    STRING_AGG(DISTINCT pl.current_price::TEXT, ', ') as listing_prices
FROM master_properties mp
LEFT JOIN property_listings pl ON pl.master_property_id = mp.id AND pl.is_active = TRUE
WHERE mp.current_price IS NULL
    AND mp.sold_at IS NULL
GROUP BY mp.id, mp.building_id
LIMIT 20;

-- 手動で再計算
UPDATE master_properties mp
SET current_price = (
    SELECT pl.current_price
    FROM property_listings pl
    WHERE pl.master_property_id = mp.id
        AND pl.is_active = TRUE
        AND pl.current_price IS NOT NULL
    ORDER BY pl.current_price DESC
    LIMIT 1
)
WHERE mp.current_price IS NULL
    AND mp.sold_at IS NULL;
```

#### 問題: APIエラーが発生

**原因**: コンテナが正しく起動していない

**対処**:
```bash
# エラーログ確認
docker compose -f docker-compose.prod.yml logs backend --tail 200

# コンテナ再起動
docker compose -f docker-compose.prod.yml restart backend
docker compose -f docker-compose.prod.yml restart frontend
docker compose -f docker-compose.prod.yml restart nginx
```

## ロールバック手順

マイグレーションに問題があった場合：

```bash
# バックアップから復元
docker cp backup_before_migration_YYYYMMDD_HHMMSS.sql realestate-postgres:/tmp/
docker exec -it realestate-postgres psql -U realestate -d realestate -c "DROP DATABASE realestate;"
docker exec -it realestate-postgres psql -U realestate -c "CREATE DATABASE realestate;"
docker exec -it realestate-postgres psql -U realestate -d realestate -f /tmp/backup_before_migration_YYYYMMDD_HHMMSS.sql

# 旧バージョンのコードに戻す
git checkout <前のコミットハッシュ>
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
```

## チェックリスト

マイグレーション実施前に以下を確認：

- [ ] バックアップが取得済み
- [ ] 最新コードがpullされている
- [ ] マイグレーションスクリプトが本番サーバーにコピーされている
- [ ] メンテナンス時間を確保している（推奨: 30分）

マイグレーション実施後に以下を確認：

- [ ] マイグレーションSQLが正常に完了
- [ ] データ整合性確認SQLで異常なし
- [ ] アプリケーションが正常に起動
- [ ] 物件一覧ページで価格が表示される
- [ ] 物件詳細ページで価格が表示される
- [ ] 建物別物件一覧で価格が表示される
- [ ] ブックマーク一覧で価格が表示される
- [ ] 新規掲載物件一覧で価格が表示される
- [ ] 価格改定履歴で価格が表示される

## 推定所要時間

- バックアップ取得: 2-5分
- マイグレーション実行: 1-3分（データ量に依存）
- アプリケーション再起動: 2-5分
- 動作確認: 5-10分

**合計: 約15-30分**

## 注意事項

1. **メンテナンス時間**: ユーザーアクセスが少ない時間帯（深夜など）に実施を推奨
2. **バックアップ必須**: 必ずマイグレーション前にバックアップを取得
3. **段階的確認**: 各ステップごとに結果を確認してから次に進む
4. **ロールバック準備**: 問題発生時は迅速にロールバックできるよう準備
