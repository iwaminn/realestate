# データベースマイグレーション管理

このディレクトリには、データベーススキーマのバックアップとマイグレーション関連ファイルが保存されています。

## ファイル構成

- `001_initial_schema.sql` - 初期スキーマのダンプ
- `YYYYMMDD_HHMMSS_*.sql` - 各時点でのスキーマスナップショット

## 重要な注意事項

**これらのSQLファイルは参考用です。正式なスキーマ定義は以下のファイルです：**

1. **`backend/app/models.py`** - SQLAlchemy ORMモデル（正式な定義）
2. **`backend/alembic/versions/`** - Alembicマイグレーション履歴

## スキーマ変更時の手順

1. `backend/app/models.py` を編集
2. Alembicでマイグレーションを作成
3. マイグレーションを実行
4. 必要に応じてスキーマをダンプ（オプション）

詳細は `backend/DATABASE_MANAGEMENT.md` を参照してください。