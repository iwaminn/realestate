-- 認証関連テーブルのマイグレーション
-- 本番環境で実行: docker exec realestate-postgres psql -U realestate -d realestate -f /app/backend/scripts/migrate_auth_tables.sql

-- パスワード設定リクエストテーブル
CREATE TABLE IF NOT EXISTS pending_password_sets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    new_password_hash VARCHAR(255) NOT NULL,
    verification_token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pending_password_sets_user ON pending_password_sets(user_id);
CREATE INDEX IF NOT EXISTS idx_pending_password_sets_token ON pending_password_sets(verification_token);

-- パスワードリセットリクエストテーブル
CREATE TABLE IF NOT EXISTS pending_password_resets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reset_token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pending_password_resets_user ON pending_password_resets(user_id);
CREATE INDEX IF NOT EXISTS idx_pending_password_resets_token ON pending_password_resets(reset_token);

-- メールアドレス変更リクエストテーブル
CREATE TABLE IF NOT EXISTS pending_email_changes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    new_email VARCHAR(255) NOT NULL,
    verification_token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pending_email_changes_user ON pending_email_changes(user_id);
CREATE INDEX IF NOT EXISTS idx_pending_email_changes_token ON pending_email_changes(verification_token);

-- テーブル作成確認
\dt pending_*
