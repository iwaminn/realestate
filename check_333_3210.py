import os
import sys
sys.path.append('/home/ubuntu/realestate')
os.environ['DATABASE_URL'] = 'postgresql://realestate:realestate_pass@localhost:5432/realestate'

from backend.app.database import SessionLocal
from backend.app.models import Building
from backend.app.utils.enhanced_building_matcher import EnhancedBuildingMatcher

db = SessionLocal()

# 建物を取得
building_333 = db.query(Building).filter(Building.id == 333).first()
building_3210 = db.query(Building).filter(Building.id == 3210).first()

if building_333 and building_3210:
    print(f"建物333: {building_333.normalized_name}")
    print(f"  住所: {building_333.address}, 築年: {building_333.built_year}")
    print(f"  総階数: {building_333.total_floors}, 総戸数: {building_333.total_units}")
    print()
    print(f"建物3210: {building_3210.normalized_name}")
    print(f"  住所: {building_3210.address}, 築年: {building_3210.built_year}")
    print(f"  総階数: {building_3210.total_floors}, 総戸数: {building_3210.total_units}")
    print()
    
    # 類似度を計算
    matcher = EnhancedBuildingMatcher()
    similarity = matcher.calculate_comprehensive_similarity(building_333, building_3210, db)
    print(f"類似度: {similarity}")

db.close()
