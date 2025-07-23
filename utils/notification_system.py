#!/usr/bin/env python3
"""
通知システム
価格変動・新着物件・エラー等の通知を送信
"""

import smtplib
import requests
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from typing import Dict, List, Optional
import os

class NotificationSystem:
    def __init__(self, config_file='notification_config.json'):
        self.config_file = config_file
        self.config = self.load_config()
        
        # ログ設定
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # データベース
        self.db_path = 'realestate.db'
    
    def load_config(self) -> Dict:
        """通知設定を読み込み"""
        default_config = {
            'email': {
                'enabled': False,
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'username': '',
                'password': '',
                'from_address': '',
                'to_addresses': []
            },
            'webhook': {
                'enabled': False,
                'url': '',
                'headers': {
                    'Content-Type': 'application/json'
                }
            },
            'slack': {
                'enabled': False,
                'webhook_url': '',
                'channel': '#real-estate',
                'username': 'Real Estate Bot'
            },
            'discord': {
                'enabled': False,
                'webhook_url': ''
            },
            'notifications': {
                'price_drops': {
                    'enabled': True,
                    'threshold_percent': 5.0,
                    'check_interval_hours': 24
                },
                'new_properties': {
                    'enabled': True,
                    'check_interval_hours': 6
                },
                'system_errors': {
                    'enabled': True
                },
                'daily_summary': {
                    'enabled': True,
                    'time': '18:00'
                }
            }
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    self.merge_config(default_config, user_config)
            except Exception as e:
                self.logger.error(f"設定ファイル読み込みエラー: {e}")
        else:
            self.save_config(default_config)
        
        return default_config
    
    def merge_config(self, default: Dict, user: Dict):
        """設定をマージ"""
        for key, value in user.items():
            if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                self.merge_config(default[key], value)
            else:
                default[key] = value
    
    def save_config(self, config: Dict):
        """設定ファイルを保存"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"設定ファイル保存エラー: {e}")
    
    def send_email(self, subject: str, body: str, is_html: bool = False) -> bool:
        """メール送信"""
        if not self.config['email']['enabled']:
            return False
        
        try:
            msg = MimeMultipart()
            msg['From'] = self.config['email']['from_address']
            msg['To'] = ', '.join(self.config['email']['to_addresses'])
            msg['Subject'] = subject
            
            msg.attach(MimeText(body, 'html' if is_html else 'plain', 'utf-8'))
            
            server = smtplib.SMTP(self.config['email']['smtp_server'], self.config['email']['smtp_port'])
            server.starttls()
            server.login(self.config['email']['username'], self.config['email']['password'])
            
            text = msg.as_string()
            server.sendmail(self.config['email']['from_address'], self.config['email']['to_addresses'], text)
            server.quit()
            
            self.logger.info(f"📧 メール送信成功: {subject}")
            return True
            
        except Exception as e:
            self.logger.error(f"📧 メール送信エラー: {e}")
            return False
    
    def send_webhook(self, data: Dict) -> bool:
        """Webhook通知送信"""
        if not self.config['webhook']['enabled']:
            return False
        
        try:
            response = requests.post(
                self.config['webhook']['url'],
                json=data,
                headers=self.config['webhook']['headers'],
                timeout=30
            )
            response.raise_for_status()
            
            self.logger.info(f"🔗 Webhook送信成功")
            return True
            
        except Exception as e:
            self.logger.error(f"🔗 Webhook送信エラー: {e}")
            return False
    
    def send_slack(self, message: str, channel: str = None) -> bool:
        """Slack通知送信"""
        if not self.config['slack']['enabled']:
            return False
        
        try:
            payload = {
                'text': message,
                'channel': channel or self.config['slack']['channel'],
                'username': self.config['slack']['username'],
                'icon_emoji': ':house:'
            }
            
            response = requests.post(
                self.config['slack']['webhook_url'],
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            self.logger.info(f"💬 Slack送信成功")
            return True
            
        except Exception as e:
            self.logger.error(f"💬 Slack送信エラー: {e}")
            return False
    
    def send_discord(self, message: str) -> bool:
        """Discord通知送信"""
        if not self.config['discord']['enabled']:
            return False
        
        try:
            payload = {
                'content': message,
                'username': 'Real Estate Bot',
                'avatar_url': 'https://example.com/bot-avatar.png'
            }
            
            response = requests.post(
                self.config['discord']['webhook_url'],
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            self.logger.info(f"🎮 Discord送信成功")
            return True
            
        except Exception as e:
            self.logger.error(f"🎮 Discord送信エラー: {e}")
            return False
    
    def send_notification(self, title: str, message: str, notification_type: str = 'info') -> bool:
        """統合通知送信"""
        success = False
        
        # 通知レベルに応じたアイコン
        icons = {
            'info': 'ℹ️',
            'success': '✅',
            'warning': '⚠️',
            'error': '❌',
            'price_drop': '📉',
            'new_property': '🏠'
        }
        
        icon = icons.get(notification_type, 'ℹ️')
        formatted_message = f"{icon} {title}\n\n{message}"
        
        # メール送信
        if self.send_email(f"[不動産通知] {title}", formatted_message):
            success = True
        
        # Slack送信
        if self.send_slack(formatted_message):
            success = True
        
        # Discord送信
        if self.send_discord(formatted_message):
            success = True
        
        # Webhook送信
        webhook_data = {
            'title': title,
            'message': message,
            'type': notification_type,
            'timestamp': datetime.now().isoformat()
        }
        if self.send_webhook(webhook_data):
            success = True
        
        return success
    
    def check_price_drops(self) -> List[Dict]:
        """価格下落物件をチェック"""
        if not self.config['notifications']['price_drops']['enabled']:
            return []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            threshold = self.config['notifications']['price_drops']['threshold_percent']
            
            # 価格下落物件を検索
            cursor.execute('''
                SELECT p.id, p.address, p.room_layout, p.current_price,
                       ph1.price as previous_price, ph1.updated_at
                FROM properties p
                JOIN price_history ph1 ON p.id = ph1.property_id
                WHERE ph1.updated_at > datetime('now', '-24 hours')
                  AND ((p.current_price - ph1.price) / ph1.price * 100) <= ?
            ''', (-threshold,))
            
            price_drops = cursor.fetchall()
            
            results = []
            for drop in price_drops:
                prop_id, address, layout, current_price, previous_price, updated_at = drop
                drop_percent = ((current_price - previous_price) / previous_price) * 100
                
                results.append({
                    'property_id': prop_id,
                    'address': address,
                    'room_layout': layout,
                    'current_price': current_price,
                    'previous_price': previous_price,
                    'drop_percent': drop_percent,
                    'updated_at': updated_at
                })
            
            return results
            
        except Exception as e:
            self.logger.error(f"価格下落チェックエラー: {e}")
            return []
        finally:
            conn.close()
    
    def check_new_properties(self) -> List[Dict]:
        """新着物件をチェック"""
        if not self.config['notifications']['new_properties']['enabled']:
            return []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            hours = self.config['notifications']['new_properties']['check_interval_hours']
            
            cursor.execute('''
                SELECT id, address, room_layout, floor_area, current_price, created_at
                FROM properties
                WHERE created_at > datetime('now', '-{} hours')
                ORDER BY created_at DESC
            '''.format(hours))
            
            new_properties = cursor.fetchall()
            
            results = []
            for prop in new_properties:
                prop_id, address, layout, area, price, created_at = prop
                
                results.append({
                    'property_id': prop_id,
                    'address': address,
                    'room_layout': layout,
                    'floor_area': area,
                    'current_price': price,
                    'created_at': created_at
                })
            
            return results
            
        except Exception as e:
            self.logger.error(f"新着物件チェックエラー: {e}")
            return []
        finally:
            conn.close()
    
    def send_price_drop_notification(self, price_drops: List[Dict]):
        """価格下落通知を送信"""
        if not price_drops:
            return
        
        title = f"価格下落物件 {len(price_drops)} 件"
        
        message_parts = []
        for drop in price_drops[:5]:  # 最大5件
            message_parts.append(
                f"📍 {drop['address']}\n"
                f"   間取り: {drop['room_layout']}\n"
                f"   価格: {drop['previous_price']:,}円 → {drop['current_price']:,}円\n"
                f"   変動: {drop['drop_percent']:.1f}%\n"
            )
        
        if len(price_drops) > 5:
            message_parts.append(f"...他 {len(price_drops) - 5} 件")
        
        message = "\n".join(message_parts)
        
        self.send_notification(title, message, 'price_drop')
    
    def send_new_property_notification(self, new_properties: List[Dict]):
        """新着物件通知を送信"""
        if not new_properties:
            return
        
        title = f"新着物件 {len(new_properties)} 件"
        
        message_parts = []
        for prop in new_properties[:5]:  # 最大5件
            message_parts.append(
                f"🏠 {prop['address']}\n"
                f"   間取り: {prop['room_layout']}\n"
                f"   面積: {prop['floor_area']}㎡\n"
                f"   価格: {prop['current_price']:,}円\n"
            )
        
        if len(new_properties) > 5:
            message_parts.append(f"...他 {len(new_properties) - 5} 件")
        
        message = "\n".join(message_parts)
        
        self.send_notification(title, message, 'new_property')
    
    def send_daily_summary(self):
        """日次サマリー通知を送信"""
        if not self.config['notifications']['daily_summary']['enabled']:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 今日の統計
            cursor.execute('''
                SELECT COUNT(*) FROM properties
                WHERE created_at > datetime('now', '-24 hours')
            ''')
            new_properties_count = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT COUNT(*) FROM price_history
                WHERE updated_at > datetime('now', '-24 hours')
            ''')
            price_changes_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM properties')
            total_properties = cursor.fetchone()[0]
            
            cursor.execute('SELECT AVG(current_price) FROM properties')
            avg_price = cursor.fetchone()[0]
            
            title = "不動産データ 日次サマリー"
            message = f"""
今日の活動概要:
• 新着物件: {new_properties_count} 件
• 価格変動: {price_changes_count} 件
• 総物件数: {total_properties} 件
• 平均価格: {avg_price:,.0f}円

更新時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """.strip()
            
            self.send_notification(title, message, 'info')
            
        except Exception as e:
            self.logger.error(f"日次サマリー作成エラー: {e}")
        finally:
            conn.close()
    
    def run_periodic_checks(self):
        """定期チェックを実行"""
        self.logger.info("🔔 定期通知チェック開始")
        
        # 価格下落チェック
        price_drops = self.check_price_drops()
        if price_drops:
            self.send_price_drop_notification(price_drops)
        
        # 新着物件チェック
        new_properties = self.check_new_properties()
        if new_properties:
            self.send_new_property_notification(new_properties)
        
        self.logger.info("🔔 定期通知チェック完了")
    
    def test_notifications(self):
        """通知テスト"""
        test_message = f"通知システムテスト - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        print("🧪 通知システムテスト開始")
        
        # 各通知方法をテスト
        methods = ['email', 'slack', 'discord', 'webhook']
        for method in methods:
            if self.config[method]['enabled']:
                print(f"  {method}: テスト中...")
                success = self.send_notification(f"[テスト] {method.upper()}", test_message, 'info')
                print(f"  {method}: {'✅ 成功' if success else '❌ 失敗'}")
            else:
                print(f"  {method}: 無効")
        
        print("🧪 通知システムテスト完了")

def main():
    """メイン実行関数"""
    import sys
    
    notification = NotificationSystem()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'test':
            notification.test_notifications()
        elif command == 'check':
            notification.run_periodic_checks()
        elif command == 'summary':
            notification.send_daily_summary()
        elif command == 'price-drops':
            drops = notification.check_price_drops()
            if drops:
                notification.send_price_drop_notification(drops)
            else:
                print("価格下落物件はありません")
        elif command == 'new-properties':
            new_props = notification.check_new_properties()
            if new_props:
                notification.send_new_property_notification(new_props)
            else:
                print("新着物件はありません")
        else:
            print("不明なコマンド")
    else:
        print("🔔 不動産通知システム")
        print("=" * 30)
        print("使用方法:")
        print("  python3 notification_system.py test           # 通知テスト")
        print("  python3 notification_system.py check          # 定期チェック実行")
        print("  python3 notification_system.py summary        # 日次サマリー送信")
        print("  python3 notification_system.py price-drops    # 価格下落通知")
        print("  python3 notification_system.py new-properties # 新着物件通知")
        
        print("\n⚙️  設定ファイル: notification_config.json")
        print("📧 メール・Slack・Discord・Webhook に対応")

if __name__ == '__main__':
    main()