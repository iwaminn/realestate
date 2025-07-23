#!/usr/bin/env python3
"""
価格履歴追跡システム
物件の価格変動を記録・分析する機能
"""

import sqlite3
import json
from datetime import datetime, date, timedelta
import logging
import statistics
from typing import List, Dict, Optional
import matplotlib.pyplot as plt
import io
import base64

class PriceHistoryTracker:
    def __init__(self, db_path='realestate.db'):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)
    
    def get_db_connection(self):
        """データベース接続を取得"""
        return sqlite3.connect(self.db_path)
    
    def record_price_change(self, property_id: int, new_price: int, source_site: str, agent_company: str = None):
        """価格変動を記録"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # 現在の価格を取得
            cursor.execute('SELECT current_price FROM properties WHERE id = ?', (property_id,))
            current_data = cursor.fetchone()
            
            if not current_data:
                self.logger.error(f"物件ID {property_id} が見つかりません")
                return False
            
            current_price = current_data[0]
            
            # 価格変動があった場合のみ記録
            if current_price != new_price:
                # 価格履歴に記録
                cursor.execute('''
                    INSERT INTO price_history 
                    (property_id, price, source_site, agent_company, updated_at, first_listed_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 
                            (SELECT first_listed_at FROM properties WHERE id = ?))
                ''', (property_id, new_price, source_site, agent_company or '', property_id))
                
                # 物件テーブルの価格を更新
                cursor.execute('''
                    UPDATE properties 
                    SET current_price = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (new_price, property_id))
                
                conn.commit()
                
                change_amount = new_price - current_price
                change_percent = (change_amount / current_price) * 100
                
                self.logger.info(f"価格変動記録: 物件ID {property_id}, {current_price:,}円 → {new_price:,}円 ({change_percent:+.1f}%)")
                return True
            
            return False  # 価格変動なし
            
        except Exception as e:
            self.logger.error(f"価格変動記録エラー: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def update_all_price_history(self):
        """全物件の価格履歴を更新"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # 全物件の現在価格を取得
            cursor.execute('''
                SELECT p.id, p.current_price, pl.source_site, pl.agent_company, pl.listed_price
                FROM properties p
                JOIN property_listings pl ON p.id = pl.property_id
                WHERE pl.is_active = 1
            ''')
            
            listings = cursor.fetchall()
            updated_count = 0
            
            for listing in listings:
                prop_id, current_price, source_site, agent_company, listed_price = listing
                
                if self.record_price_change(prop_id, listed_price, source_site, agent_company):
                    updated_count += 1
            
            self.logger.info(f"価格履歴更新完了: {updated_count} 件の価格変動を記録")
            return updated_count
            
        except Exception as e:
            self.logger.error(f"価格履歴更新エラー: {e}")
            return 0
        finally:
            conn.close()
    
    def get_price_history(self, property_id: int) -> List[Dict]:
        """特定物件の価格履歴を取得"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT price, source_site, agent_company, updated_at
                FROM price_history
                WHERE property_id = ?
                ORDER BY updated_at ASC
            ''', (property_id,))
            
            history = cursor.fetchall()
            
            result = []
            for record in history:
                result.append({
                    'price': record[0],
                    'source_site': record[1],
                    'agent_company': record[2],
                    'updated_at': record[3]
                })
            
            return result
            
        except Exception as e:
            self.logger.error(f"価格履歴取得エラー: {e}")
            return []
        finally:
            conn.close()
    
    def analyze_price_trends(self, property_id: int) -> Dict:
        """価格トレンドを分析"""
        history = self.get_price_history(property_id)
        
        if len(history) < 2:
            return {'trend': 'insufficient_data', 'change_count': len(history)}
        
        prices = [h['price'] for h in history]
        dates = [datetime.fromisoformat(h['updated_at']) for h in history]
        
        # 価格変動の統計
        price_changes = []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            price_changes.append(change)
        
        # トレンド分析
        first_price = prices[0]
        last_price = prices[-1]
        total_change = last_price - first_price
        total_change_percent = (total_change / first_price) * 100
        
        # 期間計算
        duration = (dates[-1] - dates[0]).days
        
        # トレンド判定
        if total_change_percent > 5:
            trend = 'increasing'
        elif total_change_percent < -5:
            trend = 'decreasing'
        else:
            trend = 'stable'
        
        return {
            'trend': trend,
            'first_price': first_price,
            'last_price': last_price,
            'total_change': total_change,
            'total_change_percent': total_change_percent,
            'change_count': len(price_changes),
            'avg_change': statistics.mean(price_changes) if price_changes else 0,
            'duration_days': duration,
            'min_price': min(prices),
            'max_price': max(prices),
            'price_volatility': statistics.stdev(prices) if len(prices) > 1 else 0
        }
    
    def find_price_drops(self, min_drop_percent: float = 5.0) -> List[Dict]:
        """価格下落物件を検出"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT p.id, p.address, p.room_layout, p.floor_area, p.current_price
                FROM properties p
                WHERE p.id IN (
                    SELECT property_id FROM price_history
                    GROUP BY property_id
                    HAVING COUNT(*) >= 2
                )
            ''')
            
            properties = cursor.fetchall()
            price_drops = []
            
            for prop in properties:
                prop_id, address, layout, area, current_price = prop
                trends = self.analyze_price_trends(prop_id)
                
                if (trends['trend'] == 'decreasing' and 
                    abs(trends['total_change_percent']) >= min_drop_percent):
                    
                    price_drops.append({
                        'property_id': prop_id,
                        'address': address,
                        'room_layout': layout,
                        'floor_area': area,
                        'current_price': current_price,
                        'price_drop_percent': trends['total_change_percent'],
                        'price_drop_amount': trends['total_change'],
                        'change_count': trends['change_count']
                    })
            
            # 価格下落率でソート
            price_drops.sort(key=lambda x: x['price_drop_percent'])
            
            return price_drops
            
        except Exception as e:
            self.logger.error(f"価格下落検出エラー: {e}")
            return []
        finally:
            conn.close()
    
    def get_market_trends(self) -> Dict:
        """市場全体のトレンドを分析"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # 価格帯別の物件数
            cursor.execute('''
                SELECT 
                    CASE 
                        WHEN current_price < 50000000 THEN 'under_50m'
                        WHEN current_price < 100000000 THEN '50m_to_100m'
                        WHEN current_price < 150000000 THEN '100m_to_150m'
                        ELSE 'over_150m'
                    END as price_range,
                    COUNT(*) as count,
                    AVG(current_price) as avg_price
                FROM properties
                GROUP BY price_range
            ''')
            
            price_ranges = cursor.fetchall()
            
            # 最近の価格変動統計
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_changes,
                    AVG(price) as avg_price,
                    MIN(price) as min_price,
                    MAX(price) as max_price
                FROM price_history
                WHERE updated_at > datetime('now', '-30 days')
            ''')
            
            recent_stats = cursor.fetchone()
            
            # 間取り別の価格統計
            cursor.execute('''
                SELECT 
                    room_layout,
                    COUNT(*) as count,
                    AVG(current_price) as avg_price,
                    MIN(current_price) as min_price,
                    MAX(current_price) as max_price
                FROM properties
                GROUP BY room_layout
                ORDER BY count DESC
            ''')
            
            layout_stats = cursor.fetchall()
            
            return {
                'price_ranges': [
                    {
                        'range': pr[0],
                        'count': pr[1],
                        'avg_price': pr[2]
                    } for pr in price_ranges
                ],
                'recent_changes': {
                    'total_changes': recent_stats[0],
                    'avg_price': recent_stats[1],
                    'min_price': recent_stats[2],
                    'max_price': recent_stats[3]
                },
                'layout_stats': [
                    {
                        'layout': ls[0],
                        'count': ls[1],
                        'avg_price': ls[2],
                        'min_price': ls[3],
                        'max_price': ls[4]
                    } for ls in layout_stats
                ]
            }
            
        except Exception as e:
            self.logger.error(f"市場トレンド分析エラー: {e}")
            return {}
        finally:
            conn.close()
    
    def export_price_history(self, property_id: int, format: str = 'json') -> str:
        """価格履歴をエクスポート"""
        history = self.get_price_history(property_id)
        trends = self.analyze_price_trends(property_id)
        
        export_data = {
            'property_id': property_id,
            'analysis': trends,
            'history': history,
            'exported_at': datetime.now().isoformat()
        }
        
        if format == 'json':
            return json.dumps(export_data, indent=2, ensure_ascii=False)
        elif format == 'csv':
            lines = ['date,price,source_site,agent_company']
            for h in history:
                lines.append(f"{h['updated_at']},{h['price']},{h['source_site']},{h['agent_company']}")
            return '\n'.join(lines)
        else:
            return str(export_data)
    
    def show_price_history_summary(self):
        """価格履歴の概要を表示"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # 基本統計
        cursor.execute('''
            SELECT 
                COUNT(DISTINCT property_id) as properties_with_history,
                COUNT(*) as total_price_records,
                AVG(price) as avg_price,
                MIN(price) as min_price,
                MAX(price) as max_price
            FROM price_history
        ''')
        
        stats = cursor.fetchone()
        
        print("📊 価格履歴統計:")
        print(f"履歴のある物件数: {stats[0]}")
        print(f"価格記録総数: {stats[1]}")
        print(f"平均価格: {stats[2]:,.0f}円" if stats[2] else "平均価格: N/A")
        print(f"最低価格: {stats[3]:,}円" if stats[3] else "最低価格: N/A")
        print(f"最高価格: {stats[4]:,}円" if stats[4] else "最高価格: N/A")
        
        # 価格下落物件
        price_drops = self.find_price_drops()
        if price_drops:
            print(f"\n📉 価格下落物件 (Top 5):")
            for drop in price_drops[:5]:
                print(f"  {drop['address'][:30]:30s} | {drop['room_layout']:5s} | {drop['price_drop_percent']:+6.1f}% | {drop['price_drop_amount']:+,}円")
        
        # 市場トレンド
        market_trends = self.get_market_trends()
        if market_trends.get('layout_stats'):
            print(f"\n🏠 間取り別価格統計:")
            for layout in market_trends['layout_stats'][:5]:
                print(f"  {layout['layout']:5s} | {layout['count']:3d}件 | 平均 {layout['avg_price']:,.0f}円")
        
        conn.close()

def main():
    """メイン実行関数"""
    tracker = PriceHistoryTracker()
    
    print("📈 価格履歴追跡システム")
    print("=" * 40)
    
    while True:
        print("\n選択してください:")
        print("1. 価格履歴を更新")
        print("2. 特定物件の価格履歴を表示")
        print("3. 価格下落物件を検出")
        print("4. 市場トレンドを分析")
        print("5. 価格履歴統計を表示")
        print("6. 終了")
        
        choice = input("選択 (1-6): ")
        
        if choice == '1':
            updated = tracker.update_all_price_history()
            print(f"✅ {updated} 件の価格変動を記録しました")
        
        elif choice == '2':
            try:
                prop_id = int(input("物件ID: "))
                history = tracker.get_price_history(prop_id)
                trends = tracker.analyze_price_trends(prop_id)
                
                if history:
                    print(f"\n📊 物件ID {prop_id} の価格履歴:")
                    for h in history:
                        print(f"  {h['updated_at'][:16]} | {h['price']:,}円 | {h['source_site']} | {h['agent_company']}")
                    
                    print(f"\n📈 トレンド分析:")
                    print(f"  トレンド: {trends['trend']}")
                    print(f"  価格変動: {trends['total_change']:+,}円 ({trends['total_change_percent']:+.1f}%)")
                    print(f"  期間: {trends['duration_days']} 日")
                else:
                    print("❌ 価格履歴が見つかりません")
            except ValueError:
                print("❌ 有効な物件IDを入力してください")
        
        elif choice == '3':
            price_drops = tracker.find_price_drops()
            if price_drops:
                print(f"\n📉 価格下落物件 ({len(price_drops)} 件):")
                for drop in price_drops:
                    print(f"  ID:{drop['property_id']:2d} | {drop['address'][:30]:30s} | {drop['room_layout']:5s} | {drop['price_drop_percent']:+6.1f}% | {drop['current_price']:,}円")
            else:
                print("✅ 価格下落物件は見つかりませんでした")
        
        elif choice == '4':
            trends = tracker.get_market_trends()
            if trends:
                print("\n📊 市場トレンド:")
                
                print("価格帯別分布:")
                for pr in trends['price_ranges']:
                    print(f"  {pr['range']:12s}: {pr['count']:3d}件 (平均 {pr['avg_price']:,.0f}円)")
                
                if trends['recent_changes']['total_changes']:
                    print(f"\n最近30日の価格変動:")
                    print(f"  変動回数: {trends['recent_changes']['total_changes']} 回")
                    print(f"  平均価格: {trends['recent_changes']['avg_price']:,.0f}円")
            else:
                print("❌ 市場トレンドデータが不足しています")
        
        elif choice == '5':
            tracker.show_price_history_summary()
        
        elif choice == '6':
            print("👋 終了します")
            break
        
        else:
            print("❌ 無効な選択です")

if __name__ == '__main__':
    main()