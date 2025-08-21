import os
import sys
sys.path.append('/home/ubuntu/realestate')
os.environ['DATABASE_URL'] = 'postgresql://realestate:realestate_pass@localhost:5432/realestate'

from backend.app.database import SessionLocal
from backend.app.models import Building, MasterProperty
from sqlalchemy import func

db = SessionLocal()

# base_groupsクエリを実行
base_groups = db.query(
    func.substring(Building.normalized_address, 1, 10).label('address_prefix'),
    Building.total_floors,
    Building.total_units,
    func.array_agg(Building.id).label('building_ids'),
    func.array_agg(Building.built_year).label('built_years'),
    func.count(Building.id).label('group_count')
).filter(
    Building.id.in_(
        db.query(MasterProperty.building_id).distinct()
    ),
    Building.total_floors.isnot(None),
    Building.total_units.isnot(None)
).group_by(
    func.substring(Building.normalized_address, 1, 10),
    Building.total_floors,
    Building.total_units
).having(
    func.count(Building.id) > 1
).limit(50).all()

# 白金ザ・スカイのグループを探す
for group in base_groups:
    building_ids = group.building_ids if group.building_ids else []
    if any(bid in [333, 3210] for bid in building_ids):
        print(f"Found group with 白金ザ・スカイ:")
        print(f"  address_prefix: {group.address_prefix}")
        print(f"  total_floors: {group.total_floors}")
        print(f"  total_units: {group.total_units}")
        print(f"  building_ids: {building_ids}")
        print(f"  built_years: {group.built_years}")
        print(f"  Type of building_ids: {type(building_ids)}")
        print(f"  Type of element: {type(building_ids[0]) if building_ids else 'N/A'}")
        print()
        
        # 築年の差をチェック
        built_years = group.built_years if group.built_years else []
        for i in range(len(built_years)):
            for j in range(i + 1, len(built_years)):
                if built_years[i] and built_years[j]:
                    diff = abs(built_years[i] - built_years[j])
                    print(f"  Year difference between {built_years[i]} and {built_years[j]}: {diff}")

db.close()
