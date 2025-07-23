#!/usr/bin/env python3
"""
簡単なWebフロントエンド
スクレイピングデータを見やすく表示
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import sqlite3
from urllib.parse import urlparse, parse_qs
import html

def build_property_url(source_site, source_property_id):
    """物件IDからURLを構築"""
    if not source_property_id:
        return None
    
    if source_site == 'suumo':
        return f"https://suumo.jp/ms/chuko/tokyo/sc_minato/{source_property_id}/"
    elif source_site == 'athome':
        return f"https://athome.jp/mansions/{source_property_id}/"
    elif source_site == 'homes':
        return f"https://homes.co.jp/chuko/{source_property_id}/"
    
    return None

def get_site_display_name(source_site):
    """サイト名の表示用名称を取得"""
    site_names = {
        'suumo': 'SUUMO',
        'athome': 'アットホーム',
        'homes': 'ホームズ',
        'rakumachi': '楽待'
    }
    return site_names.get(source_site, source_site.upper())

class WebFrontendHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)
        
        if path == '/':
            self.serve_property_list()
        elif path == '/property':
            property_id = query_params.get('id', [None])[0]
            if property_id:
                self.serve_property_detail(int(property_id))
            else:
                self.serve_property_list()
        elif path == '/stats':
            self.serve_stats()
        elif path.startswith('/static/'):
            self.serve_static()
        else:
            self.send_error(404)
    
    def serve_property_list(self):
        """物件一覧ページ"""
        # パラメータを取得
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        page = int(query_params.get('page', ['1'])[0])
        sort = query_params.get('sort', ['price'])[0]
        order = query_params.get('order', ['desc'])[0]
        per_page = 20  # 1ページあたりの表示件数
        
        conn = sqlite3.connect('realestate.db')
        cursor = conn.cursor()
        
        # 総件数を取得
        cursor.execute('SELECT COUNT(*) FROM properties')
        total_count = cursor.fetchone()[0]
        total_pages = (total_count + per_page - 1) // per_page
        
        # ページ番号の検証
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page
        
        # ソート条件を設定
        sort_column = {
            'price': 'p.current_price',
            'area': 'p.floor_area',
            'age': 'p.building_age'
        }.get(sort, 'p.current_price')
        
        order_direction = 'ASC' if order == 'asc' else 'DESC'
        
        cursor.execute(f'''
            SELECT p.id, p.address, p.room_layout, p.floor_area, p.current_price, 
                   p.building_age, p.building_name, p.created_at
            FROM properties p
            ORDER BY {sort_column} {order_direction}
            LIMIT ? OFFSET ?
        ''', (per_page, offset))
        
        properties = cursor.fetchall()
        conn.close()
        
        html_content = self.generate_property_list_html(properties, page, total_pages, total_count, sort, order)
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))
    
    def serve_property_detail(self, property_id):
        """物件詳細ページ"""
        conn = sqlite3.connect('realestate.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT p.*, a.prefecture_name, a.ward_name
            FROM properties p
            JOIN areas a ON p.area_id = a.id
            WHERE p.id = ?
        ''', (property_id,))
        
        property_data = cursor.fetchone()
        
        if not property_data:
            self.send_error(404)
            return
        
        # リスティング情報を取得
        cursor.execute('''
            SELECT source_site, agent_company, listed_price, scraped_at, source_property_id
            FROM property_listings
            WHERE property_id = ? AND is_active = 1
        ''', (property_id,))
        
        listings = cursor.fetchall()
        conn.close()
        
        html_content = self.generate_property_detail_html(property_data, listings)
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))
    
    def serve_stats(self):
        """統計情報ページ"""
        conn = sqlite3.connect('realestate.db')
        cursor = conn.cursor()
        
        # 基本統計
        cursor.execute('SELECT COUNT(*) FROM properties')
        total_properties = cursor.fetchone()[0]
        
        cursor.execute('SELECT AVG(current_price) FROM properties')
        avg_price = cursor.fetchone()[0]
        
        cursor.execute('SELECT MIN(current_price), MAX(current_price) FROM properties')
        min_price, max_price = cursor.fetchone()
        
        # 間取り別統計
        cursor.execute('''
            SELECT room_layout, COUNT(*) as count, AVG(current_price) as avg_price
            FROM properties
            GROUP BY room_layout
            ORDER BY count DESC
        ''')
        layout_stats = cursor.fetchall()
        
        conn.close()
        
        html_content = self.generate_stats_html(total_properties, avg_price, min_price, max_price, layout_stats)
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))
    
    def serve_static(self):
        """CSS等の静的ファイル"""
        css_content = """
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
        .property-card { border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; background: #fafafa; }
        .property-card:hover { background: #f0f8ff; }
        .price { font-size: 1.2em; font-weight: bold; color: #e74c3c; }
        .address { font-size: 1.1em; color: #2c3e50; margin: 5px 0; }
        .details { color: #7f8c8d; margin: 5px 0; }
        .nav { background: #34495e; padding: 10px; margin: -20px -20px 20px -20px; border-radius: 8px 8px 0 0; }
        .nav a { color: white; text-decoration: none; margin: 0 15px; padding: 5px 10px; border-radius: 3px; }
        .nav a:hover { background: #2c3e50; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 20px 0; }
        .stat-card { background: #ecf0f1; padding: 20px; border-radius: 5px; text-align: center; }
        .stat-number { font-size: 2em; font-weight: bold; color: #3498db; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #f8f9fa; }
        .source-link { display: inline-block; padding: 8px 16px; margin: 5px; background: #3498db; color: white; text-decoration: none; border-radius: 4px; }
        .source-link:hover { background: #2980b9; }
        .pagination { display: flex; justify-content: center; align-items: center; margin: 20px 0; gap: 10px; flex-wrap: wrap; }
        .pagination a { padding: 8px 12px; background: #3498db; color: white; text-decoration: none; border-radius: 4px; transition: background 0.3s; }
        .pagination a:hover { background: #2980b9; }
        .pagination a.current { background: #e74c3c; font-weight: bold; }
        .pagination a.disabled { background: #95a5a6; cursor: not-allowed; pointer-events: none; }
        .pagination span { color: #7f8c8d; }
        .sort-buttons { display: flex; justify-content: center; gap: 10px; margin: 20px 0; flex-wrap: wrap; }
        .sort-button { display: inline-flex; align-items: center; gap: 5px; padding: 8px 16px; background: #ecf0f1; color: #2c3e50; text-decoration: none; border-radius: 4px; transition: all 0.3s; }
        .sort-button:hover { background: #bdc3c7; }
        .sort-button.active { background: #3498db; color: white; font-weight: bold; }
        .sort-arrow { font-size: 0.8em; }
        """
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/css')
        self.end_headers()
        self.wfile.write(css_content.encode('utf-8'))
    
    def generate_property_list_html(self, properties, current_page, total_pages, total_count, sort, order):
        """物件一覧HTMLを生成"""
        property_cards = []
        for prop in properties:
            prop_id, address, layout, area, price, age, building_name, created_at = prop
            age_str = f"築{age}年" if age else "築年数不明"
            building_str = f"({building_name})" if building_name else ""
            
            card = f"""
            <div class="property-card">
                <div class="address">
                    <a href="/property?id={prop_id}" style="text-decoration: none; color: inherit;">
                        {html.escape(address)} {html.escape(building_str)}
                    </a>
                </div>
                <div class="price">💰 {price:,}円</div>
                <div class="details">
                    🏠 {html.escape(layout)} | 📏 {area}㎡ | 🏗️ {age_str} | 📅 {created_at[:10] if created_at else '不明'}
                </div>
            </div>
            """
            property_cards.append(card)
        
        return f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>港区 中古不動産物件一覧</title>
            <link rel="stylesheet" href="/static/style.css">
        </head>
        <body>
            <div class="container">
                <nav class="nav">
                    <a href="/">🏠 物件一覧</a>
                    <a href="/stats">📊 統計情報</a>
                    <a href="http://localhost:8000/api/v1/properties" target="_blank">🔌 API</a>
                </nav>
                
                <h1>🏠 港区 中古不動産物件一覧</h1>
                <p>📍 対象エリア: 東京都港区 | 📊 総物件数: {total_count} 件 | 📄 ページ {current_page}/{total_pages}</p>
                
                {self.generate_sort_buttons(sort, order)}
                
                {self.generate_pagination_html(current_page, total_pages, sort, order)}
                
                {''.join(property_cards)}
                
                {self.generate_pagination_html(current_page, total_pages, sort, order)}
                
                <div style="margin-top: 30px; padding: 20px; background: #e8f4f8; border-radius: 5px;">
                    <h3>📋 利用可能なAPI</h3>
                    <ul>
                        <li><a href="http://localhost:8000/api/v1/properties" target="_blank">GET /api/v1/properties</a> - 物件一覧</li>
                        <li><a href="http://localhost:8000/api/v1/stats" target="_blank">GET /api/v1/stats</a> - 統計情報</li>
                        <li><a href="http://localhost:8000/api/v1/areas" target="_blank">GET /api/v1/areas</a> - エリア一覧</li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """
    
    def generate_sort_buttons(self, current_sort, current_order):
        """ソートボタンHTMLを生成"""
        buttons = ['<div class="sort-buttons">']
        
        sort_options = [
            ('price', '💰 価格'),
            ('area', '📏 平米数'),
            ('age', '🏗️ 築年数')
        ]
        
        for sort_key, label in sort_options:
            is_active = current_sort == sort_key
            new_order = 'desc' if is_active and current_order == 'asc' else 'asc'
            arrow = '▲' if is_active and current_order == 'asc' else '▼'
            
            if is_active:
                buttons.append(f'''
                    <a href="/?sort={sort_key}&order={new_order}" class="sort-button active">
                        {label} <span class="sort-arrow">{arrow}</span>
                    </a>
                ''')
            else:
                buttons.append(f'''
                    <a href="/?sort={sort_key}&order=desc" class="sort-button">
                        {label}
                    </a>
                ''')
        
        buttons.append('</div>')
        return '\n'.join(buttons)
    
    def generate_pagination_html(self, current_page, total_pages, sort='price', order='desc'):
        """ページネーションHTMLを生成"""
        if total_pages <= 1:
            return ""
        
        links = ['<div class="pagination">']
        
        # URLパラメータを保持
        def build_url(page):
            return f"/?page={page}&sort={sort}&order={order}"
        
        # 最初のページへ
        if current_page > 1:
            links.append(f'<a href="{build_url(1)}">« 最初</a>')
            links.append(f'<a href="{build_url(current_page-1)}">‹ 前へ</a>')
        else:
            links.append('<a class="disabled">« 最初</a>')
            links.append('<a class="disabled">‹ 前へ</a>')
        
        # ページ番号
        start_page = max(1, current_page - 2)
        end_page = min(total_pages, current_page + 2)
        
        if start_page > 1:
            links.append('<span>...</span>')
        
        for page in range(start_page, end_page + 1):
            if page == current_page:
                links.append(f'<a class="current">{page}</a>')
            else:
                links.append(f'<a href="{build_url(page)}">{page}</a>')
        
        if end_page < total_pages:
            links.append('<span>...</span>')
        
        # 最後のページへ
        if current_page < total_pages:
            links.append(f'<a href="{build_url(current_page+1)}">次へ ›</a>')
            links.append(f'<a href="{build_url(total_pages)}">最後 »</a>')
        else:
            links.append('<a class="disabled">次へ ›</a>')
            links.append('<a class="disabled">最後 »</a>')
        
        links.append('</div>')
        return '\n'.join(links)
    
    def generate_property_detail_html(self, property_data, listings):
        """物件詳細HTMLを生成"""
        prop_id, area_id, address, layout, area, price, first_listed, building_name, age, hash_val, created_at, updated_at, construction_year, construction_month, construction_date, prefecture, ward = property_data
        
        age_str = f"築{age}年" if age else "築年数不明"
        building_str = building_name if building_name else "建物名不明"
        
        listing_rows = []
        source_links = []
        for listing in listings:
            site, agent, listed_price, scraped_at, source_property_id = listing
            
            # 元サイトへのリンクを生成
            source_url = build_property_url(site, source_property_id)
            site_display_name = get_site_display_name(site)
            
            if source_url:
                site_link = f'<a href="{source_url}" target="_blank">{html.escape(site_display_name)}</a>'
                source_links.append(f'<a href="{source_url}" target="_blank" class="source-link">📋 {site_display_name}で詳細を見る</a>')
            else:
                site_link = html.escape(site_display_name)
            
            listing_rows.append(f"""
            <tr>
                <td>{site_link}</td>
                <td>{html.escape(agent)}</td>
                <td>{listed_price:,}円</td>
                <td>{scraped_at[:16] if scraped_at else '不明'}</td>
            </tr>
            """)
        
        # 元サイトへのリンクセクション
        source_links_html = ""
        if source_links:
            source_links_html = f"""
            <div style="margin: 20px 0; padding: 15px; background: #f0f8ff; border-radius: 5px; border-left: 4px solid #3498db;">
                <h3>🔗 元サイトで詳細を確認</h3>
                <div style="margin-top: 10px;">
                    {' | '.join(source_links)}
                </div>
            </div>
            """
        
        return f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>物件詳細 - {address}</title>
            <link rel="stylesheet" href="/static/style.css">
        </head>
        <body>
            <div class="container">
                <nav class="nav">
                    <a href="/">🏠 物件一覧</a>
                    <a href="/stats">📊 統計情報</a>
                    <a href="http://localhost:8000/api/v1/properties/{prop_id}" target="_blank">🔌 API</a>
                </nav>
                
                <h1>🏠 物件詳細</h1>
                
                <div class="property-card" style="margin: 20px 0;">
                    <div class="address">{html.escape(address)}</div>
                    <div class="price">💰 {price:,}円</div>
                    <div class="details">
                        🏠 {html.escape(layout)} | 📏 {area}㎡ | 🏗️ {age_str}<br>
                        🏢 {html.escape(building_str)} | 📅 初回掲載: {first_listed}
                    </div>
                </div>
                
                <h2>📋 掲載情報</h2>
                <table>
                    <thead>
                        <tr>
                            <th>サイト</th>
                            <th>業者</th>
                            <th>掲載価格</th>
                            <th>取得日時</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(listing_rows)}
                    </tbody>
                </table>
                
                {source_links_html}
                
                <div style="margin-top: 20px;">
                    <a href="/" style="display: inline-block; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">← 物件一覧に戻る</a>
                </div>
            </div>
        </body>
        </html>
        """
    
    def generate_stats_html(self, total_properties, avg_price, min_price, max_price, layout_stats):
        """統計情報HTMLを生成"""
        layout_rows = []
        for layout, count, avg_price_layout in layout_stats:
            layout_rows.append(f"""
            <tr>
                <td>{html.escape(layout)}</td>
                <td>{count} 件</td>
                <td>{avg_price_layout:,.0f}円</td>
            </tr>
            """)
        
        return f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>統計情報 - 港区不動産</title>
            <link rel="stylesheet" href="/static/style.css">
        </head>
        <body>
            <div class="container">
                <nav class="nav">
                    <a href="/">🏠 物件一覧</a>
                    <a href="/stats">📊 統計情報</a>
                    <a href="http://localhost:8000/api/v1/stats" target="_blank">🔌 API</a>
                </nav>
                
                <h1>📊 統計情報</h1>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-number">{total_properties}</div>
                        <div>総物件数</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{avg_price:,.0f}円</div>
                        <div>平均価格</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{min_price:,.0f}円</div>
                        <div>最低価格</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{max_price:,.0f}円</div>
                        <div>最高価格</div>
                    </div>
                </div>
                
                <h2>🏠 間取り別統計</h2>
                <table>
                    <thead>
                        <tr>
                            <th>間取り</th>
                            <th>件数</th>
                            <th>平均価格</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(layout_rows)}
                    </tbody>
                </table>
                
                <div style="margin-top: 20px;">
                    <a href="/" style="display: inline-block; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">← 物件一覧に戻る</a>
                </div>
            </div>
        </body>
        </html>
        """

def run_web_frontend():
    """Webフロントエンドサーバーを起動"""
    server_address = ('', 8001)
    httpd = HTTPServer(server_address, WebFrontendHandler)
    print("🌐 Webフロントエンドを起動中...")
    print("📍 http://localhost:8001 でアクセス可能")
    print("🏠 物件一覧: http://localhost:8001/")
    print("📊 統計情報: http://localhost:8001/stats")
    print("サーバーを停止するには Ctrl+C を押してください")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Webフロントエンドを停止しています...")
        httpd.server_close()

if __name__ == '__main__':
    run_web_frontend()