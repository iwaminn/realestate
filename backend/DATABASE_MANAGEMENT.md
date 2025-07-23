# データベース管理ガイド

## 概要
このプロジェクトではPostgreSQLを使用し、Alembicでデータベースマイグレーションを管理します。

## データベース接続

### 重要: データベース名の統一
**プロジェクト全体で使用するデータベース名: `realestate`**

以前、`realestate`と`realestate_db`の2つのデータベースが混在していた問題がありました。
現在は`realestate`に統一されています。

```bash
# Docker環境（docker-compose.yml で定義）
DATABASE_URL=postgresql://realestate:realestate_pass@postgres:5432/realestate

# ローカル開発環境（ホストから接続）
export DATABASE_URL="postgresql://realestate:realestate_pass@localhost:5432/realestate"

# コンテナ内から接続
docker exec -it realestate-postgres psql -U realestate -d realestate
```

## データベース定義ファイルの場所

### 重要なファイル
1. **モデル定義（正式な定義）**: `backend/app/models.py`
   - SQLAlchemyのORMモデル定義
   - **これが唯一の正式なスキーマ定義ソース**
   
2. **マイグレーション履歴**: `backend/alembic/versions/`
   - 各変更の履歴が時系列で保存
   
3. **初期スキーマのバックアップ**: `backend/migrations/001_initial_schema.sql`
   - 参考用のSQLダンプ（自動更新されない）

## スキーマ管理

### 1. Alembicの使用方法

```bash
# 環境変数を設定
export DATABASE_URL="postgresql://realestate:realestate_pass@localhost:5432/realestate_db"

# 新しいマイグレーションを作成（自動生成）
poetry run alembic revision --autogenerate -m "Add new column"

# マイグレーションを実行
poetry run alembic upgrade head

# 現在のリビジョンを確認
poetry run alembic current

# 履歴を確認
poetry run alembic history
```

### 2. モデルの変更手順

#### 開発段階（現在）

リリース前の開発段階では、シンプルな手順でスキーマを更新できます：

1. **モデルの変更**: `backend/app/models.py` でモデルを変更
   ```python
   # 例: 新しいカラムを追加
   class PropertyListing(Base):
       # ... 既存のカラム ...
       new_column = Column(String(255))  # 新しいカラム
   ```

2. **データベースを再作成**:
   ```bash
   # 既存のテーブルを削除して再作成
   export DATABASE_URL="postgresql://realestate:realestate_pass@localhost:5432/realestate"
   poetry run python backend/scripts/init_v2_schema.py --drop  # 既存テーブル削除
   poetry run python backend/scripts/init_v2_schema.py        # テーブル再作成
   ```

3. **初期スキーマを更新**（オプション）:
   ```bash
   # 最新のスキーマをダンプ
   docker exec realestate-postgres pg_dump -U realestate -d realestate --schema-only > \
     backend/migrations/001_initial_schema.sql
   ```

#### 本番リリース後

本番環境にデプロイ後は、データを保持するためにAlembicマイグレーションを使用します：

1. モデルを変更
2. `poetry run alembic revision --autogenerate -m "変更内容"`
3. `poetry run alembic upgrade head`

### ⚠️ 注意事項
- **開発段階でも models.py が正式な定義ソース**
- データベースを直接変更した場合は、必ず models.py を同期させること
- 重要なテストデータがある場合は、削除前にバックアップを取ること

### 3. データベーススキーマ

現在のスキーマは以下のテーブルで構成されています：

#### 建物関連
- `buildings` - 建物マスター
- `building_aliases` - 建物名のエイリアス
- `building_external_ids` - 外部サイトの建物ID

#### 物件関連
- `master_properties` - 物件マスター（重複排除済み）
- `property_listings` - 各サイトの掲載情報
- `listing_price_history` - 価格変更履歴
- `property_images` - 物件画像

## トラブルシューティング

### カラムが存在しないエラー
モデルとデータベースのスキーマが不一致の場合：

```bash
# 手動でカラムを追加（緊急対応）
docker exec realestate-postgres psql -U realestate -d realestate -c "
ALTER TABLE property_listings 
ADD COLUMN IF NOT EXISTS last_fetched_at TIMESTAMP DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS last_confirmed_at TIMESTAMP DEFAULT NOW();
"

# その後、Alembicで正式にマイグレーションを作成
poetry run alembic revision --autogenerate -m "Add missing columns"
poetry run alembic upgrade head
```

### トランザクションエラー
`InFailedSqlTransaction` エラーが発生した場合は、データベース接続をリセット：

```python
# base_scraper.py などで
self.session.rollback()  # トランザクションをロールバック
```

## バックアップとリストア

```bash
# バックアップ
docker exec realestate-postgres pg_dump -U realestate -d realestate > backup_$(date +%Y%m%d_%H%M%S).sql

# リストア
docker exec -i realestate-postgres psql -U realestate -d realestate < backup.sql
```

## 開発環境のセットアップ

```bash
# 初回セットアップ
cd backend
poetry install
export DATABASE_URL="postgresql://realestate:realestate_pass@localhost:5432/realestate"

# データベースの初期化
poetry run python scripts/init_v2_schema.py

# Alembicの初期化（済み）
poetry run alembic stamp head
```