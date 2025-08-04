#!/usr/bin/env python3
"""
自動重複検出スクリプト

ファジーマッチングと高度なアルゴリズムを使用して、
物件と建物の重複を自動的に検出し、統合候補を提案します。
"""

import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging
from typing import List, Dict, Any, Tuple

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import Building, MasterProperty, PropertyListing
from app.utils.fuzzy_property_matcher import FuzzyPropertyMatcher
from app.utils.advanced_building_matcher import AdvancedBuildingMatcher

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# データベース接続
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


class DuplicateDetector:
    """重複検出クラス"""
    
    def __init__(self, session):
        self.session = session
        self.property_matcher = FuzzyPropertyMatcher()
        self.building_matcher = AdvancedBuildingMatcher()
        self.detected_duplicates = {
            'properties': [],
            'buildings': []
        }
    
    def detect_duplicate_properties(self, limit: int = None) -> List[Dict[str, Any]]:
        """重複物件を検出"""
        logger.info("重複物件の検出を開始します...")
        
        # 除外済みペアを取得
        excluded_pairs = self._get_excluded_property_pairs()
        
        # 同じ建物内の物件を取得
        query = """
        SELECT 
            mp.id,
            mp.building_id,
            mp.room_number,
            mp.floor_number,
            mp.area,
            mp.layout,
            mp.direction,
            mp.balcony_area,
            b.normalized_name as building_name
        FROM master_properties mp
        JOIN buildings b ON mp.building_id = b.id
        WHERE mp.id NOT IN (
            SELECT primary_property_id FROM property_merge_history
        )
        ORDER BY mp.building_id, mp.floor_number, mp.area
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        properties = self.session.execute(text(query)).fetchall()
        
        # 建物ごとにグループ化
        buildings_map = {}
        for prop in properties:
            building_id = prop.building_id
            if building_id not in buildings_map:
                buildings_map[building_id] = []
            buildings_map[building_id].append(dict(prop._mapping))
        
        duplicate_groups = []
        processed_ids = set()
        
        # 各建物内で重複をチェック
        for building_id, props in buildings_map.items():
            if len(props) < 2:
                continue
            
            for i, prop1 in enumerate(props):
                if prop1['id'] in processed_ids:
                    continue
                
                # 重複候補を検索
                candidates = self.property_matcher.find_duplicate_candidates(
                    prop1,
                    props[i+1:],
                    confidence_level='medium'
                )
                
                if candidates:
                    group = {
                        'primary': prop1,
                        'duplicates': []
                    }
                    
                    for candidate, score, features in candidates:
                        # 除外済みペアはスキップ
                        pair_key = tuple(sorted([prop1['id'], candidate['id']]))
                        if pair_key in excluded_pairs:
                            continue
                        
                        # 推奨度を取得
                        recommendation = self.property_matcher.get_merge_recommendation(
                            score, features
                        )
                        
                        if recommendation['should_merge']:
                            group['duplicates'].append({
                                'property': candidate,
                                'score': score,
                                'features': features,
                                'recommendation': recommendation
                            })
                            processed_ids.add(candidate['id'])
                    
                    if group['duplicates']:
                        duplicate_groups.append(group)
                        processed_ids.add(prop1['id'])
        
        self.detected_duplicates['properties'] = duplicate_groups
        logger.info(f"重複物件グループを{len(duplicate_groups)}件検出しました")
        
        return duplicate_groups
    
    def detect_duplicate_buildings(self, limit: int = None) -> List[Dict[str, Any]]:
        """重複建物を検出"""
        logger.info("重複建物の検出を開始します...")
        
        # 除外済みペアを取得
        excluded_pairs = self._get_excluded_building_pairs()
        
        # 建物を取得
        query = """
        SELECT 
            b.id,
            b.normalized_name,
            b.address,
            b.built_year,
            b.total_floors,
            COUNT(mp.id) as property_count
        FROM buildings b
        LEFT JOIN master_properties mp ON b.id = mp.building_id
        WHERE b.id NOT IN (
            SELECT merged_building_id FROM building_merge_history
        )
        GROUP BY b.id, b.normalized_name, b.address, b.built_year, b.total_floors
        HAVING COUNT(mp.id) > 0
        ORDER BY b.normalized_name
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        buildings = self.session.execute(text(query)).fetchall()
        building_list = [dict(b._mapping) for b in buildings]
        
        duplicate_groups = []
        processed_ids = set()
        
        for i, building1 in enumerate(building_list):
            if building1['id'] in processed_ids:
                continue
            
            # 重複候補を検索
            candidates = self.building_matcher.find_duplicate_buildings(
                building1,
                building_list[i+1:],
                min_confidence='medium'
            )
            
            if candidates:
                group = {
                    'primary': building1,
                    'duplicates': []
                }
                
                for candidate, score, details in candidates:
                    # 除外済みペアはスキップ
                    pair_key = tuple(sorted([building1['id'], candidate['id']]))
                    if pair_key in excluded_pairs:
                        continue
                    
                    # 推奨度を取得
                    recommendation = self.building_matcher.get_merge_recommendation(
                        score, details
                    )
                    
                    if recommendation['should_merge']:
                        group['duplicates'].append({
                            'building': candidate,
                            'score': score,
                            'details': details,
                            'recommendation': recommendation
                        })
                        processed_ids.add(candidate['id'])
                
                if group['duplicates']:
                    duplicate_groups.append(group)
                    processed_ids.add(building1['id'])
        
        self.detected_duplicates['buildings'] = duplicate_groups
        logger.info(f"重複建物グループを{len(duplicate_groups)}件検出しました")
        
        return duplicate_groups
    
    def _get_excluded_property_pairs(self) -> set:
        """除外済みの物件ペアを取得"""
        query = """
        SELECT property1_id, property2_id
        FROM property_merge_exclusions
        """
        
        result = self.session.execute(text(query)).fetchall()
        return {tuple(sorted([row[0], row[1]])) for row in result}
    
    def _get_excluded_building_pairs(self) -> set:
        """除外済みの建物ペアを取得"""
        query = """
        SELECT building1_id, building2_id
        FROM building_merge_exclusions
        """
        
        result = self.session.execute(text(query)).fetchall()
        return {tuple(sorted([row[0], row[1]])) for row in result}
    
    def generate_report(self, output_file: str = None):
        """検出結果のレポートを生成"""
        report = []
        report.append("=" * 80)
        report.append("自動重複検出レポート")
        report.append(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 80)
        report.append("")
        
        # 物件の重複
        report.append("## 重複物件候補")
        report.append(f"検出グループ数: {len(self.detected_duplicates['properties'])}")
        report.append("")
        
        for i, group in enumerate(self.detected_duplicates['properties'], 1):
            primary = group['primary']
            report.append(f"### グループ {i}")
            report.append(f"メイン物件: ID={primary['id']}, "
                         f"{primary['building_name']} {primary['floor_number']}階 "
                         f"{primary['area']}㎡ {primary['layout']}")
            report.append("")
            
            for dup in group['duplicates']:
                prop = dup['property']
                rec = dup['recommendation']
                report.append(f"  - 候補: ID={prop['id']}, "
                             f"{prop['floor_number']}階 {prop['area']}㎡ {prop['layout']}")
                report.append(f"    類似度: {dup['score']:.1%} ({rec['confidence']})")
                report.append(f"    理由: {rec['reason']}")
                report.append(f"    一致特徴: {', '.join(dup['features'])}")
                report.append("")
        
        # 建物の重複
        report.append("")
        report.append("## 重複建物候補")
        report.append(f"検出グループ数: {len(self.detected_duplicates['buildings'])}")
        report.append("")
        
        for i, group in enumerate(self.detected_duplicates['buildings'], 1):
            primary = group['primary']
            report.append(f"### グループ {i}")
            report.append(f"メイン建物: ID={primary['id']}, {primary['normalized_name']}")
            report.append(f"住所: {primary['address']}")
            report.append(f"物件数: {primary['property_count']}")
            report.append("")
            
            for dup in group['duplicates']:
                building = dup['building']
                rec = dup['recommendation']
                report.append(f"  - 候補: ID={building['id']}, {building['normalized_name']}")
                report.append(f"    住所: {building['address']}")
                report.append(f"    物件数: {building['property_count']}")
                report.append(f"    類似度: {dup['score']:.1%} ({rec['confidence']})")
                report.append(f"    理由: {rec['reason']}")
                if rec.get('warnings'):
                    report.append(f"    警告: {', '.join(rec['warnings'])}")
                report.append("")
        
        # 統計情報
        report.append("")
        report.append("## 統計情報")
        
        # 物件の統計
        total_property_duplicates = sum(
            len(g['duplicates']) for g in self.detected_duplicates['properties']
        )
        report.append(f"- 重複物件候補総数: {total_property_duplicates}")
        
        # 信頼度別の集計
        confidence_counts = {'high': 0, 'medium': 0, 'low': 0}
        for group in self.detected_duplicates['properties']:
            for dup in group['duplicates']:
                confidence = dup['recommendation']['confidence']
                confidence_counts[confidence] += 1
        
        report.append(f"  - 高信頼度: {confidence_counts['high']}")
        report.append(f"  - 中信頼度: {confidence_counts['medium']}")
        report.append(f"  - 低信頼度: {confidence_counts['low']}")
        
        # 建物の統計
        total_building_duplicates = sum(
            len(g['duplicates']) for g in self.detected_duplicates['buildings']
        )
        report.append(f"- 重複建物候補総数: {total_building_duplicates}")
        
        # レポートを出力
        report_text = "\n".join(report)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
            logger.info(f"レポートを {output_file} に保存しました")
        else:
            print(report_text)
    
    def generate_merge_sql(self, output_file: str = None):
        """統合用のSQLを生成"""
        sql_commands = []
        
        # ヘッダー
        sql_commands.append("-- 自動生成された重複統合SQL")
        sql_commands.append(f"-- 生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        sql_commands.append("-- 注意: 実行前に必ずバックアップを取ってください")
        sql_commands.append("")
        sql_commands.append("BEGIN;")
        sql_commands.append("")
        
        # 物件の統合SQL
        sql_commands.append("-- 物件の統合")
        for group in self.detected_duplicates['properties']:
            primary_id = group['primary']['id']
            
            for dup in group['duplicates']:
                if dup['recommendation']['confidence'] == 'high':
                    dup_id = dup['property']['id']
                    sql_commands.append(f"-- 物件 {dup_id} を {primary_id} に統合")
                    sql_commands.append(f"CALL merge_properties({primary_id}, {dup_id}, 'auto_detector');")
                    sql_commands.append("")
        
        # 建物の統合SQL
        sql_commands.append("")
        sql_commands.append("-- 建物の統合")
        for group in self.detected_duplicates['buildings']:
            primary_id = group['primary']['id']
            
            for dup in group['duplicates']:
                if dup['recommendation']['confidence'] == 'high':
                    dup_id = dup['building']['id']
                    sql_commands.append(f"-- 建物 {dup_id} を {primary_id} に統合")
                    sql_commands.append(f"CALL merge_buildings({primary_id}, {dup_id}, 'auto_detector');")
                    sql_commands.append("")
        
        sql_commands.append("")
        sql_commands.append("-- COMMIT; -- 確認後にコメントを外して実行")
        sql_commands.append("ROLLBACK; -- 安全のためデフォルトはロールバック")
        
        # SQLを出力
        sql_text = "\n".join(sql_commands)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(sql_text)
            logger.info(f"SQLを {output_file} に保存しました")
        else:
            print(sql_text)


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='自動重複検出スクリプト')
    parser.add_argument('--limit', type=int, help='検査する件数の上限')
    parser.add_argument('--properties-only', action='store_true', help='物件のみ検査')
    parser.add_argument('--buildings-only', action='store_true', help='建物のみ検査')
    parser.add_argument('--report', type=str, help='レポートの出力ファイル')
    parser.add_argument('--sql', type=str, help='統合SQLの出力ファイル')
    parser.add_argument('--auto-merge', action='store_true', help='高信頼度の重複を自動統合')
    
    args = parser.parse_args()
    
    session = Session()
    
    try:
        detector = DuplicateDetector(session)
        
        # 検出実行
        if not args.buildings_only:
            detector.detect_duplicate_properties(limit=args.limit)
        
        if not args.properties_only:
            detector.detect_duplicate_buildings(limit=args.limit)
        
        # レポート生成
        if args.report:
            detector.generate_report(args.report)
        else:
            detector.generate_report()
        
        # SQL生成
        if args.sql:
            detector.generate_merge_sql(args.sql)
        
        # 自動統合
        if args.auto_merge:
            logger.warning("自動統合は未実装です。生成されたSQLを手動で実行してください。")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}", exc_info=True)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()