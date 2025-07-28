#!/usr/bin/env python3
"""
サイトマスターテーブルを作成し、source_siteを数値IDに移行
"""
import os
import sys
from sqlalchemy import create_engine, text, Column, Integer, String, DateTime, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# データベース接続
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()


# サイトマスターテーブルの定義
class SiteMaster(Base):
    __tablename__ = "site_master"
    
    id = Column(Integer, primary_key=True)
    site_code = Column(String(50), unique=True, nullable=False)  # suumo, homes等
    site_name = Column(String(100), nullable=False)  # SUUMO, LIFULL HOME'S等
    base_url = Column(String(500))  # https://suumo.jp等
    is_active = Column(Integer, default=1)  # 1: 有効, 0: 無効
    display_order = Column(Integer)  # 表示順
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


def create_site_master_table():
    """サイトマスターテーブルを作成"""
    print("=== サイトマスターテーブルの作成 ===\n")
    
    # テーブル作成
    Base.metadata.create_all(engine)
    print("✓ site_masterテーブルを作成しました")
    
    # 初期データを投入
    sites = [
        (1, 'suumo', 'SUUMO', 'https://suumo.jp', 1, 1),
        (2, 'homes', 'LIFULL HOME\'S', 'https://www.homes.co.jp', 1, 2),
        (3, 'nomu', 'ノムコム', 'https://www.nomu.com', 1, 3),
        (4, 'rehouse', '三井のリハウス', 'https://www.rehouse.co.jp', 1, 4),
        (5, 'livable', '東急リバブル', 'https://www.livable.co.jp', 1, 5),
        (6, 'athome', 'AtHome', 'https://www.athome.co.jp', 0, 6),  # 無効化
    ]
    
    for site_id, code, name, url, active, order in sites:
        session.execute(text("""
            INSERT INTO site_master (id, site_code, site_name, base_url, is_active, display_order)
            VALUES (:id, :code, :name, :url, :active, :order)
            ON CONFLICT (site_code) DO NOTHING
        """), {
            "id": site_id,
            "code": code,
            "name": name,
            "url": url,
            "active": active,
            "order": order
        })
    
    session.commit()
    print("✓ 初期データを投入しました")


def add_source_site_id_column():
    """property_listingsテーブルにsource_site_idカラムを追加"""
    print("\n=== source_site_idカラムの追加 ===\n")
    
    # カラムを追加
    session.execute(text("""
        ALTER TABLE property_listings 
        ADD COLUMN IF NOT EXISTS source_site_id INTEGER
    """))
    session.commit()
    print("✓ source_site_idカラムを追加しました")
    
    # 既存データを更新
    print("\n既存データのsource_site_idを設定中...")
    
    # 大文字小文字を統一してから更新
    updates = [
        ('suumo', 'SUUMO'),
        ('homes', 'HOMES'),
        ('nomu', 'NOMU'),
    ]
    
    for lower, upper in updates:
        session.execute(text("""
            UPDATE property_listings
            SET source_site = :lower
            WHERE source_site = :upper
        """), {"lower": lower, "upper": upper})
    
    # source_site_idを設定
    session.execute(text("""
        UPDATE property_listings pl
        SET source_site_id = sm.id
        FROM site_master sm
        WHERE LOWER(pl.source_site) = sm.site_code
    """))
    
    session.commit()
    
    # 結果を確認
    result = session.execute(text("""
        SELECT 
            source_site,
            source_site_id,
            COUNT(*) as count
        FROM property_listings
        GROUP BY source_site, source_site_id
        ORDER BY source_site_id, source_site
    """)).fetchall()
    
    print("\n更新結果:")
    for row in result:
        print(f"  source_site: '{row.source_site}' → source_site_id: {row.source_site_id} ({row.count}件)")


def add_foreign_key_constraint():
    """外部キー制約を追加"""
    print("\n=== 外部キー制約の追加 ===\n")
    
    # 外部キー制約を追加
    session.execute(text("""
        ALTER TABLE property_listings
        ADD CONSTRAINT fk_property_listings_source_site
        FOREIGN KEY (source_site_id) REFERENCES site_master(id)
    """))
    
    # インデックスを追加
    session.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_property_listings_source_site_id
        ON property_listings(source_site_id)
    """))
    
    session.commit()
    print("✓ 外部キー制約とインデックスを追加しました")


def show_migration_plan():
    """移行計画を表示"""
    print("\n=== 今後の移行計画 ===\n")
    print("1. BuildingExternalIdテーブルのsource_siteも同様に移行")
    print("2. models.pyを更新:")
    print("   - SiteMasterモデルを追加")
    print("   - PropertyListingにsource_site_id外部キーを追加")
    print("   - source_siteカラムは後方互換性のため一時的に保持")
    print("3. スクレイパーを更新:")
    print("   - source_site文字列の代わりにsite_idを使用")
    print("4. 最終的にsource_siteカラムを削除")


if __name__ == "__main__":
    try:
        print("サイトマスターテーブルを作成し、source_siteを数値IDに移行します。\n")
        
        # 実行確認
        confirm = input("続行しますか？ (y/N): ")
        if confirm.lower() != 'y':
            print("キャンセルしました。")
            sys.exit(0)
        
        create_site_master_table()
        add_source_site_id_column()
        add_foreign_key_constraint()
        show_migration_plan()
        
        print("\n✓ 移行が完了しました！")
        
    except Exception as e:
        session.rollback()
        print(f"\n✗ エラーが発生しました: {e}")
        raise
    finally:
        session.close()