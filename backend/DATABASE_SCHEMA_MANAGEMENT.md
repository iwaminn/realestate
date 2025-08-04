# データベーススキーマ管理ガイド

## 重要な原則

1. **ORMモデルが真実の源** - `backend/app/models.py` のSQLAlchemyモデルが正式なスキーマ定義です
2. **既存テーブルへの変更は手動で** - `create_all()`は既存テーブルを変更しません
3. **必ずDocker環境でも実行** - ローカルとDocker環境の両方でスキーマを同期させる

## スキーマ変更手順

### 1. 新しいカラムを追加する場合

1. `backend/app/models.py` でモデルにカラムを追加
2. スキーマ同期スクリプトを実行：
   ```bash
   # ローカル環境
   poetry run python backend/scripts/sync_database_schema.py
   
   # Docker環境
   docker exec realestate-backend poetry run python /app/backend/scripts/sync_database_schema.py
   ```

### 2. 新しいテーブルを追加する場合

1. `backend/app/models.py` で新しいモデルクラスを定義
2. `backend/scripts/sync_database_schema.py` の `tables_to_sync` リストに追加
3. スキーマ同期スクリプトを実行

### 3. カラムの型を変更する場合

**注意**: 型の変更は複雑で、データ損失のリスクがあります

1. バックアップを取る
2. 手動でALTER TABLEを実行するスクリプトを作成
3. 十分にテストしてから本番環境で実行

## よくある問題と対処法

### 問題1: "column does not exist" エラー

**原因**: ORMモデルで定義されているカラムが実際のテーブルに存在しない

**対処法**:
```bash
# スキーマ同期スクリプトを実行
docker exec realestate-backend poetry run python /app/backend/scripts/sync_database_schema.py
```

### 問題2: テーブル構造の不整合

**原因**: 
- `create_all()` は既存テーブルを変更しない
- 手動でテーブルを作成/変更した
- 異なる環境で異なるスキーマバージョンが動作している

**対処法**:
1. 現在の状態を確認
2. 不足しているカラムを特定
3. スキーマ同期スクリプトで追加

### 問題3: Docker環境とローカル環境の不整合

**原因**: 片方の環境でのみスキーマ変更を実行した

**対処法**: 両環境でスキーマ同期スクリプトを実行

## 推奨される開発フロー

1. **開発開始時**: スキーマ同期スクリプトを実行して最新状態にする
2. **モデル変更後**: 即座にスキーマ同期スクリプトを実行
3. **プルリクエスト作成時**: スキーマ変更をREADMEに記載
4. **デプロイ時**: 本番環境でもスキーマ同期を実行

## スキーマのバージョン管理（将来の課題）

現在はスクリプトベースの管理ですが、将来的にはAlembicなどのマイグレーションツールの導入を検討してください。

### Alembic導入のメリット
- スキーマ変更の履歴管理
- ロールバック機能
- 複数環境での一貫性
- チーム開発での競合解決

## 緊急時の対処法

### データベース全体の再作成（開発環境のみ）

```bash
# 警告: 全データが削除されます！
poetry run python backend/scripts/init_schema.py --drop
poetry run python backend/scripts/init_schema.py
```

### 特定のカラムを手動で追加

```sql
-- PostgreSQLで実行
ALTER TABLE property_listings 
ADD COLUMN management_company VARCHAR(200);
```

## チェックリスト

- [ ] models.pyを変更した
- [ ] ローカル環境でスキーマ同期を実行した
- [ ] Docker環境でスキーマ同期を実行した
- [ ] 新しいカラムが正しく追加されたことを確認した
- [ ] APIが正常に動作することを確認した
- [ ] スクレイパーが正常に動作することを確認した