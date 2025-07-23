#!/usr/bin/env python3
"""
高精度重複排除エンジン
物件の重複を検出し、統合処理を実行する
"""

import sqlite3
import hashlib
import re
from datetime import datetime
from difflib import SequenceMatcher
import logging

class DeduplicationEngine:
    def __init__(self, db_path='realestate.db'):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)
        
        # 重複判定の閾値
        self.thresholds = {
            'address_similarity': 0.8,    # 住所の類似度
            'area_tolerance': 3.0,        # 面積の許容差（㎡）
            'age_tolerance': 1,           # 築年数の許容差（年）
            'price_tolerance': 0.15,      # 価格の許容差（15%）
            'overall_threshold': 0.75     # 総合判定の閾値
        }
    
    def get_db_connection(self):
        """データベース接続を取得"""
        return sqlite3.connect(self.db_path)
    
    def normalize_address(self, address):
        """住所の正規化"""
        if not address:
            return ""
        
        # 正規化ルール
        normalized = address
        
        # 数字の表記統一
        normalized = re.sub(r'([0-9]+)丁目', r'\1-', normalized)
        normalized = re.sub(r'([0-9]+)番地?', r'\1-', normalized)
        normalized = re.sub(r'([0-9]+)号', r'\1', normalized)
        
        # 空白・記号の除去
        normalized = re.sub(r'[\s\-ー−－]+', '-', normalized)
        normalized = re.sub(r'[\.．。]', '', normalized)
        
        # 建物名の除去（住所部分のみ抽出）
        # 例: "東京都港区赤坂1-1-1 赤坂マンション" → "東京都港区赤坂1-1-1"
        parts = normalized.split()
        if len(parts) > 1:
            # 最初の部分（住所）のみ使用
            normalized = parts[0]
        
        return normalized.strip()
    
    def calculate_address_similarity(self, addr1, addr2):
        """住所の類似度を計算"""
        norm1 = self.normalize_address(addr1)
        norm2 = self.normalize_address(addr2)
        
        if not norm1 or not norm2:
            return 0.0
        
        # 完全一致
        if norm1 == norm2:
            return 1.0
        
        # 文字列の類似度
        similarity = SequenceMatcher(None, norm1, norm2).ratio()
        
        # 住所の重要部分（区まで）が一致している場合はボーナス
        if self.extract_ward(norm1) == self.extract_ward(norm2):
            similarity += 0.1
        
        return min(similarity, 1.0)
    
    def extract_ward(self, address):
        """住所から区名を抽出"""
        match = re.search(r'(.*?[区市町村])', address)
        if match:
            return match.group(1)
        return address
    
    def calculate_area_similarity(self, area1, area2):
        """面積の類似度を計算"""
        if area1 is None or area2 is None:
            return 0.5  # 不明な場合は中間値
        
        diff = abs(area1 - area2)
        if diff <= self.thresholds['area_tolerance']:
            return 1.0
        
        # 差が大きいほど類似度が低下
        return max(0.0, 1.0 - (diff / 20.0))
    
    def calculate_age_similarity(self, age1, age2):
        """築年数の類似度を計算"""
        if age1 is None or age2 is None:
            return 0.5  # 不明な場合は中間値
        
        diff = abs(age1 - age2)
        if diff <= self.thresholds['age_tolerance']:
            return 1.0
        
        # 差が大きいほど類似度が低下
        return max(0.0, 1.0 - (diff / 10.0))
    
    def calculate_price_similarity(self, price1, price2):
        """価格の類似度を計算"""
        if price1 is None or price2 is None or price1 == 0 or price2 == 0:
            return 0.5  # 不明な場合は中間値
        
        diff_ratio = abs(price1 - price2) / max(price1, price2)
        if diff_ratio <= self.thresholds['price_tolerance']:
            return 1.0
        
        # 差が大きいほど類似度が低下
        return max(0.0, 1.0 - (diff_ratio * 2))
    
    def calculate_layout_similarity(self, layout1, layout2):
        """間取りの類似度を計算"""
        if not layout1 or not layout2:
            return 0.5
        
        # 完全一致
        if layout1 == layout2:
            return 1.0
        
        # 部分一致（例：3LDK と 3LDK+S）
        if layout1 in layout2 or layout2 in layout1:
            return 0.8
        
        # 数字部分の比較（例：3LDK と 3DK）
        num1 = re.findall(r'\d+', layout1)
        num2 = re.findall(r'\d+', layout2)
        
        if num1 and num2 and num1[0] == num2[0]:
            return 0.6
        
        return 0.0
    
    def calculate_similarity_score(self, prop1, prop2):
        """2つの物件の類似度スコアを計算"""
        # 各要素の類似度を計算
        address_sim = self.calculate_address_similarity(prop1['address'], prop2['address'])
        area_sim = self.calculate_area_similarity(prop1['floor_area'], prop2['floor_area'])
        age_sim = self.calculate_age_similarity(prop1['building_age'], prop2['building_age'])
        price_sim = self.calculate_price_similarity(prop1['current_price'], prop2['current_price'])
        layout_sim = self.calculate_layout_similarity(prop1['room_layout'], prop2['room_layout'])
        
        # 重み付け平均
        weights = {
            'address': 0.35,
            'area': 0.25,
            'layout': 0.20,
            'age': 0.10,
            'price': 0.10
        }
        
        total_score = (
            address_sim * weights['address'] +
            area_sim * weights['area'] +
            layout_sim * weights['layout'] +
            age_sim * weights['age'] +
            price_sim * weights['price']
        )
        
        return {
            'total_score': total_score,
            'address_similarity': address_sim,
            'area_similarity': area_sim,
            'age_similarity': age_sim,
            'price_similarity': price_sim,
            'layout_similarity': layout_sim
        }
    
    def find_duplicate_candidates(self):
        """重複候補の物件を検出"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # 全物件を取得
        cursor.execute('''
            SELECT id, address, room_layout, floor_area, building_age, current_price, building_name
            FROM properties
            ORDER BY id
        ''')
        
        properties = cursor.fetchall()
        conn.close()
        
        # 物件を辞書形式に変換
        prop_list = []
        for prop in properties:
            prop_dict = {
                'id': prop[0],
                'address': prop[1],
                'room_layout': prop[2],
                'floor_area': prop[3],
                'building_age': prop[4],
                'current_price': prop[5],
                'building_name': prop[6]
            }
            prop_list.append(prop_dict)
        
        # 重複候補を検出
        duplicates = []
        
        for i in range(len(prop_list)):
            for j in range(i + 1, len(prop_list)):
                prop1 = prop_list[i]
                prop2 = prop_list[j]
                
                similarity = self.calculate_similarity_score(prop1, prop2)
                
                if similarity['total_score'] >= self.thresholds['overall_threshold']:
                    duplicates.append({
                        'property1': prop1,
                        'property2': prop2,
                        'similarity': similarity
                    })
        
        return duplicates
    
    def merge_duplicate_properties(self, prop1_id, prop2_id, keep_id=None):
        """重複する物件を統合"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # 統合後に残す物件を決定
            if keep_id is None:
                # より古い物件ID（先に登録された物件）を残す
                keep_id = min(prop1_id, prop2_id)
            
            remove_id = prop2_id if keep_id == prop1_id else prop1_id
            
            # 削除対象物件の情報を取得
            cursor.execute('SELECT * FROM properties WHERE id = ?', (remove_id,))
            remove_prop = cursor.fetchone()
            
            cursor.execute('SELECT * FROM properties WHERE id = ?', (keep_id,))
            keep_prop = cursor.fetchone()
            
            if not remove_prop or not keep_prop:
                self.logger.error(f"物件が見つかりません: {prop1_id}, {prop2_id}")
                return False
            
            # 統合対象物件のリスティング情報を移動
            cursor.execute('''
                UPDATE property_listings 
                SET property_id = ? 
                WHERE property_id = ?
            ''', (keep_id, remove_id))
            
            # 価格履歴があれば移動
            cursor.execute('''
                UPDATE price_history 
                SET property_id = ? 
                WHERE property_id = ?
            ''', (keep_id, remove_id))
            
            # 残す物件の情報を更新（より良い情報があれば）
            update_fields = []
            update_values = []
            
            # 建物名が不明な場合は補完
            if not keep_prop[7] and remove_prop[7]:  # building_name
                update_fields.append('building_name = ?')
                update_values.append(remove_prop[7])
            
            # 築年数が不明な場合は補完
            if not keep_prop[8] and remove_prop[8]:  # building_age
                update_fields.append('building_age = ?')
                update_values.append(remove_prop[8])
            
            # 更新が必要な場合
            if update_fields:
                update_values.append(keep_id)
                cursor.execute(f'''
                    UPDATE properties 
                    SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', update_values)
            
            # 重複物件を削除
            cursor.execute('DELETE FROM properties WHERE id = ?', (remove_id,))
            
            conn.commit()
            
            self.logger.info(f"物件統合完了: {remove_id} → {keep_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"物件統合エラー: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def run_deduplication(self, auto_merge=False):
        """重複排除処理を実行"""
        self.logger.info("🔄 重複排除処理を開始します...")
        
        # 重複候補を検出
        duplicates = self.find_duplicate_candidates()
        
        if not duplicates:
            self.logger.info("✅ 重複する物件は見つかりませんでした")
            return 0
        
        self.logger.info(f"📊 {len(duplicates)} 件の重複候補を検出しました")
        
        merged_count = 0
        
        for i, dup in enumerate(duplicates):
            prop1 = dup['property1']
            prop2 = dup['property2']
            similarity = dup['similarity']
            
            print(f"\n--- 重複候補 {i+1}/{len(duplicates)} ---")
            print(f"物件1 (ID:{prop1['id']}): {prop1['address']} {prop1['room_layout']} {prop1['floor_area']}㎡")
            print(f"物件2 (ID:{prop2['id']}): {prop2['address']} {prop2['room_layout']} {prop2['floor_area']}㎡")
            print(f"類似度: {similarity['total_score']:.3f}")
            print(f"  - 住所: {similarity['address_similarity']:.3f}")
            print(f"  - 面積: {similarity['area_similarity']:.3f}")
            print(f"  - 間取り: {similarity['layout_similarity']:.3f}")
            
            if auto_merge or similarity['total_score'] >= 0.9:
                # 自動統合または高い類似度の場合
                if self.merge_duplicate_properties(prop1['id'], prop2['id']):
                    merged_count += 1
                    print("✅ 自動統合しました")
                else:
                    print("❌ 統合に失敗しました")
            else:
                # 手動確認
                while True:
                    choice = input("統合しますか？ (y/n/s=skip): ").lower()
                    if choice == 'y':
                        if self.merge_duplicate_properties(prop1['id'], prop2['id']):
                            merged_count += 1
                            print("✅ 統合しました")
                        break
                    elif choice == 'n':
                        print("⏭️  統合をスキップしました")
                        break
                    elif choice == 's':
                        print("⏭️  スキップしました")
                        break
        
        self.logger.info(f"🎉 重複排除完了: {merged_count} 件の物件を統合しました")
        return merged_count
    
    def show_statistics(self):
        """重複排除の統計情報を表示"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM properties')
        total_props = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM property_listings')
        total_listings = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) 
            FROM properties 
            WHERE master_property_hash IS NOT NULL
        ''')
        hashed_props = cursor.fetchone()[0]
        
        print("\n📊 重複排除統計:")
        print(f"総物件数: {total_props}")
        print(f"総リスティング数: {total_listings}")
        print(f"ハッシュ化済み物件: {hashed_props}")
        print(f"平均リスティング数/物件: {total_listings/total_props:.2f}")
        
        conn.close()

def main():
    """メイン実行関数"""
    engine = DeduplicationEngine()
    
    print("🔧 重複排除エンジン")
    print("=" * 40)
    
    while True:
        print("\n選択してください:")
        print("1. 重複候補を検出")
        print("2. 重複排除を実行（手動確認）")
        print("3. 重複排除を実行（自動統合）")
        print("4. 統計情報を表示")
        print("5. 終了")
        
        choice = input("選択 (1-5): ")
        
        if choice == '1':
            duplicates = engine.find_duplicate_candidates()
            if duplicates:
                print(f"\n📊 {len(duplicates)} 件の重複候補を検出:")
                for i, dup in enumerate(duplicates):
                    prop1 = dup['property1']
                    prop2 = dup['property2']
                    sim = dup['similarity']
                    print(f"{i+1}. 類似度 {sim['total_score']:.3f}")
                    print(f"   {prop1['address']} ⟷ {prop2['address']}")
            else:
                print("✅ 重複候補は見つかりませんでした")
        
        elif choice == '2':
            engine.run_deduplication(auto_merge=False)
        
        elif choice == '3':
            engine.run_deduplication(auto_merge=True)
        
        elif choice == '4':
            engine.show_statistics()
        
        elif choice == '5':
            print("👋 終了します")
            break
        
        else:
            print("❌ 無効な選択です")

if __name__ == '__main__':
    main()