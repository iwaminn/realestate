#!/usr/bin/env python3
"""
BuildingListingNameManagerのテストコード
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.models import Base, Building, MasterProperty, PropertyListing, BuildingListingName
from backend.app.utils.building_listing_name_manager import BuildingListingNameManager

# テスト用のデータベース設定
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture
def db_session():
    """テスト用のデータベースセッションを作成"""
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_data(db_session):
    """テスト用のサンプルデータを作成"""
    # 建物を作成
    building1 = Building(
        id=1,
        normalized_name="パークハウス渋谷",
        address="東京都渋谷区"
    )
    building2 = Building(
        id=2,
        normalized_name="タワーマンション新宿",
        address="東京都新宿区"
    )
    db_session.add_all([building1, building2])
    
    # 物件を作成
    property1 = MasterProperty(
        id=1,
        building_id=1,
        room_number="101",
        floor_number=1,
        area=65.5,
        layout="2LDK"
    )
    property2 = MasterProperty(
        id=2,
        building_id=1,
        room_number="202",
        floor_number=2,
        area=70.0,
        layout="3LDK"
    )
    property3 = MasterProperty(
        id=3,
        building_id=2,
        room_number="301",
        floor_number=3,
        area=80.0,
        layout="3LDK"
    )
    db_session.add_all([property1, property2, property3])
    
    # 掲載情報を作成
    listing1 = PropertyListing(
        id=1,
        master_property_id=1,
        source_site="SUUMO",
        site_property_id="suumo_001",
        url="https://suumo.jp/1",
        listing_building_name="パークハウス渋谷",
        current_price=5000
    )
    listing2 = PropertyListing(
        id=2,
        master_property_id=1,
        source_site="HOMES",
        site_property_id="homes_001",
        url="https://homes.co.jp/1",
        listing_building_name="PARK HOUSE 渋谷",  # 異なる表記
        current_price=5100
    )
    listing3 = PropertyListing(
        id=3,
        master_property_id=2,
        source_site="SUUMO",
        site_property_id="suumo_002",
        url="https://suumo.jp/2",
        listing_building_name="パークハウス渋谷",
        current_price=5500
    )
    listing4 = PropertyListing(
        id=4,
        master_property_id=3,
        source_site="SUUMO",
        site_property_id="suumo_003",
        url="https://suumo.jp/3",
        listing_building_name="タワーマンション新宿",
        current_price=6000
    )
    db_session.add_all([listing1, listing2, listing3, listing4])
    
    db_session.commit()
    
    return {
        "buildings": [building1, building2],
        "properties": [property1, property2, property3],
        "listings": [listing1, listing2, listing3, listing4]
    }


def test_update_from_listing(db_session, sample_data):
    """掲載情報からの更新テスト"""
    manager = BuildingListingNameManager(db_session)
    
    # 新しい掲載情報を作成
    new_listing = PropertyListing(
        id=5,
        master_property_id=1,
        source_site="REHOUSE",
        site_property_id="rehouse_001",
        url="https://rehouse.jp/1",
        listing_building_name="パークハウス渋谷 中古",  # 新しい表記
        current_price=5200
    )
    db_session.add(new_listing)
    db_session.commit()
    
    # 更新を実行
    manager.update_from_listing(new_listing)
    db_session.commit()
    
    # 結果を確認
    listing_names = db_session.query(BuildingListingName).filter(
        BuildingListingName.building_id == 1
    ).all()
    
    # 新しい建物名が追加されているか確認
    names = [ln.normalized_name for ln in listing_names]
    assert "パークハウス渋谷 中古" in names
    
    # サイト情報が正しく記録されているか確認
    new_entry = next((ln for ln in listing_names if ln.normalized_name == "パークハウス渋谷 中古"), None)
    assert new_entry is not None
    assert "REHOUSE" in new_entry.source_sites


def test_update_from_property_merge(db_session, sample_data):
    """物件統合時の更新テスト"""
    manager = BuildingListingNameManager(db_session)
    
    # 初期データを設定（建物1と建物2に掲載名を登録）
    manager.refresh_building_names(1)
    manager.refresh_building_names(2)
    db_session.commit()
    
    # 物件3を物件1に統合（異なる建物間の統合）
    manager.update_from_property_merge(
        primary_property_id=1,
        secondary_property_id=3
    )
    db_session.commit()
    
    # 建物2の掲載名が建物1に移動されているか確認
    building1_names = db_session.query(BuildingListingName).filter(
        BuildingListingName.building_id == 1
    ).all()
    
    names = [ln.normalized_name for ln in building1_names]
    assert "タワーマンション新宿" in names


def test_update_from_building_merge(db_session, sample_data):
    """建物統合時の更新テスト"""
    manager = BuildingListingNameManager(db_session)
    
    # 初期データを設定
    manager.refresh_building_names(1)
    manager.refresh_building_names(2)
    db_session.commit()
    
    initial_building1_count = db_session.query(BuildingListingName).filter(
        BuildingListingName.building_id == 1
    ).count()
    
    initial_building2_count = db_session.query(BuildingListingName).filter(
        BuildingListingName.building_id == 2
    ).count()
    
    # 建物2を建物1に統合
    manager.update_from_building_merge(
        primary_building_id=1,
        secondary_building_id=2
    )
    db_session.commit()
    
    # 建物2の掲載名が建物1に移動されているか確認
    building1_names = db_session.query(BuildingListingName).filter(
        BuildingListingName.building_id == 1
    ).all()
    
    building2_names = db_session.query(BuildingListingName).filter(
        BuildingListingName.building_id == 2
    ).all()
    
    # 建物1の掲載名が増えているか確認
    assert len(building1_names) > initial_building1_count
    
    # 建物2の掲載名が削除されているか確認
    assert len(building2_names) == 0
    
    # タワーマンション新宿の名前が建物1に移動されているか確認
    names = [ln.normalized_name for ln in building1_names]
    assert "タワーマンション新宿" in names


def test_refresh_building_names(db_session, sample_data):
    """建物名の再集計テスト"""
    manager = BuildingListingNameManager(db_session)
    
    # 建物1の掲載名を再集計
    manager.refresh_building_names(1)
    db_session.commit()
    
    # 結果を確認
    listing_names = db_session.query(BuildingListingName).filter(
        BuildingListingName.building_id == 1
    ).all()
    
    # 期待される建物名が登録されているか確認
    names = [ln.normalized_name for ln in listing_names]
    assert "パークハウス渋谷" in names
    assert "PARK HOUSE 渋谷" in names
    
    # 出現回数が正しく集計されているか確認
    park_house = next((ln for ln in listing_names if ln.normalized_name == "パークハウス渋谷"), None)
    assert park_house is not None
    assert park_house.occurrence_count == 2  # listing1とlisting3
    
    # サイト情報が正しく集計されているか確認
    assert "SUUMO" in park_house.source_sites


def test_search_buildings_by_name(db_session, sample_data):
    """建物名検索のテスト"""
    manager = BuildingListingNameManager(db_session)
    
    # 初期データを設定
    manager.refresh_building_names(1)
    manager.refresh_building_names(2)
    db_session.commit()
    
    # "パーク"で検索
    building_ids = manager.search_buildings_by_name("パーク")
    assert 1 in building_ids
    
    # "新宿"で検索
    building_ids = manager.search_buildings_by_name("新宿")
    assert 2 in building_ids
    
    # 英語表記でも検索できるか確認
    building_ids = manager.search_buildings_by_name("PARK")
    assert 1 in building_ids


def test_get_building_names(db_session, sample_data):
    """建物名一覧取得のテスト"""
    manager = BuildingListingNameManager(db_session)
    
    # 初期データを設定
    manager.refresh_building_names(1)
    db_session.commit()
    
    # 建物1の掲載名一覧を取得
    names = manager.get_building_names(1)
    
    # 結果を確認
    assert len(names) > 0
    
    # 出現回数の多い順にソートされているか確認
    if len(names) > 1:
        assert names[0]["occurrence_count"] >= names[1]["occurrence_count"]
    
    # 必要な情報が含まれているか確認
    for name_info in names:
        assert "normalized_name" in name_info
        assert "canonical_name" in name_info
        assert "source_sites" in name_info
        assert "occurrence_count" in name_info


def test_property_split(db_session, sample_data):
    """物件分離時の更新テスト"""
    manager = BuildingListingNameManager(db_session)
    
    # 初期データを設定
    manager.refresh_building_names(1)
    db_session.commit()
    
    # 新しい建物を作成
    new_building = Building(
        id=3,
        normalized_name="新パークハウス渋谷",
        address="東京都渋谷区"
    )
    db_session.add(new_building)
    
    # 物件2を新しい建物に分離
    property2 = sample_data["properties"][1]
    property2.building_id = 3
    db_session.commit()
    
    # 分離処理を実行
    manager.update_from_property_split(
        original_property_id=1,
        new_property_id=2,
        new_building_id=3
    )
    db_session.commit()
    
    # 新しい建物にも掲載名がコピーされているか確認
    building3_names = db_session.query(BuildingListingName).filter(
        BuildingListingName.building_id == 3
    ).all()
    
    assert len(building3_names) > 0
    names = [ln.normalized_name for ln in building3_names]
    assert "パークハウス渋谷" in names


def test_building_split(db_session, sample_data):
    """建物分離時の更新テスト"""
    manager = BuildingListingNameManager(db_session)
    
    # 初期データを設定
    manager.refresh_building_names(1)
    db_session.commit()
    
    # 新しい建物を作成
    new_building = Building(
        id=3,
        normalized_name="パークハウス渋谷 別棟",
        address="東京都渋谷区"
    )
    db_session.add(new_building)
    db_session.commit()
    
    # 物件2を新しい建物に移動
    property2 = sample_data["properties"][1]
    property2.building_id = 3
    db_session.commit()
    
    # 建物分離処理を実行
    manager.update_from_building_split(
        original_building_id=1,
        new_building_id=3,
        property_ids_to_move=[2]
    )
    db_session.commit()
    
    # 新しい建物に掲載名が登録されているか確認
    building3_names = db_session.query(BuildingListingName).filter(
        BuildingListingName.building_id == 3
    ).all()
    
    assert len(building3_names) > 0
    names = [ln.normalized_name for ln in building3_names]
    assert "パークハウス渋谷" in names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])