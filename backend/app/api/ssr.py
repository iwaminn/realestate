"""
Server-Side Rendering (SSR) エンドポイント
Google等の検索エンジン向けに、ページ固有のメタタグを埋め込んだHTMLを返す
"""
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

import os
import re

from ..database import get_db
from ..models import Building, MasterProperty

router = APIRouter()

# フロントエンドのビルド済みindex.htmlのパス
# 本番環境：/app/frontend_dist/index.html（nginx経由でアクセス）
# 開発環境：シンプルなテンプレートを使用（Vite devサーバーが別途動作）
FRONTEND_DIST_PATH = os.getenv("FRONTEND_DIST_PATH", "/app/frontend_dist/index.html")

# デフォルトのHTMLテンプレート（開発環境用）
DEFAULT_HTML_TEMPLATE = """<!doctype html>
<html lang="ja">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />

    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-C985LS1W3F"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());

      gtag('config', 'G-C985LS1W3F');
    </script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"""

# ビルド済みindex.htmlを読み込む（本番環境用）
def load_frontend_html() -> str:
    """
    フロントエンドのビルド済みindex.htmlを読み込む
    
    本番環境：frontendコンテナからHTTPで取得
    開発環境：ローカルファイルまたはデフォルトテンプレート
    """
    import requests
    
    # 本番環境：frontendコンテナからHTMLを取得
    frontend_urls = [
        "http://frontend:3000/",  # 本番環境（docker-compose内部）
        "http://localhost:3001/"   # 開発環境
    ]
    
    for url in frontend_urls:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"Success: フロントエンドのHTMLを取得しました: {url}")
                return response.text
        except Exception as e:
            print(f"Warning: {url}からHTMLを取得できませんでした: {e}")
            continue
    
    # ローカルファイルシステムから試行
    try:
        if os.path.exists(FRONTEND_DIST_PATH):
            with open(FRONTEND_DIST_PATH, 'r', encoding='utf-8') as f:
                print(f"Success: ローカルファイルからHTMLを読み込みました: {FRONTEND_DIST_PATH}")
                return f.read()
    except Exception as e:
        print(f"Warning: ローカルファイルから読み込めませんでした: {e}")
    
    # すべて失敗した場合はデフォルトテンプレート
    print("Warning: フロントエンドのHTMLを取得できませんでした。デフォルトテンプレートを使用します。")
    return DEFAULT_HTML_TEMPLATE


def is_crawler(request: Request) -> bool:
    """
    User-Agentから検索エンジンクローラー（GoogleとBingのみ）かどうかを判定
    
    クローラーの場合のみSSR初期データを埋め込み、
    通常のユーザーには高速なフローを提供する（Dynamic Rendering）
    
    Args:
        request: FastAPIのリクエストオブジェクト
    
    Returns:
        GoogleまたはBingのクローラーの場合True、それ以外False
    """
    user_agent = request.headers.get("user-agent", "").lower()
    
    # GoogleとBingの検索エンジンクローラーのみ対応
    crawlers = [
        "googlebot",              # Google検索
        "google-inspectiontool",  # Google Search Console
        "bingbot",                # Bing検索
    ]
    
    is_bot = any(crawler in user_agent for crawler in crawlers)
    
    if is_bot:
        print(f"INFO: 検索エンジンクローラー検出 - User-Agent: {user_agent[:100]}")
    
    return is_bot


def generate_building_meta_tags(building_id: int, db: Session) -> dict:
    """
    建物ページのメタタグを生成

    Args:
        building_id: 建物ID
        db: データベースセッション

    Returns:
        メタタグの辞書
    """
    # 建物情報を取得
    building = db.query(Building).filter(Building.id == building_id).first()

    if not building:
        # 建物が見つからない場合はデフォルトのメタタグ
        return {
            "title": "都心マンション価格チェッカー",
            "description": "東京都心の中古マンション価格を複数サイトから横断検索",
            "canonical": f"https://mscan.jp/buildings/{building_id}/properties"
        }

    # 建物名を取得（正規化名）
    building_name = building.normalized_name or "マンション"

    # 物件数を取得
    property_count = db.query(MasterProperty).filter(
        MasterProperty.building_id == building_id
    ).count()

    # タイトルと説明を生成
    title = f"{building_name}の物件一覧 - 都心マンション価格チェッカー"
    description = f"{building_name}の販売中マンション{property_count}件を複数サイトから横断検索。価格、間取り、階数を比較できます。"

    return {
        "title": title,
        "description": description,
        "canonical": f"https://mscan.jp/buildings/{building_id}/properties"
    }


def generate_property_meta_tags(property_id: int, db: Session) -> dict:
    """
    物件詳細ページのメタタグを生成

    Args:
        property_id: 物件ID
        db: データベースセッション

    Returns:
        メタタグの辞書
    """
    # 物件情報を取得
    property_obj = db.query(MasterProperty).filter(
        MasterProperty.id == property_id
    ).first()

    if not property_obj:
        # 物件が見つからない場合はデフォルトのメタタグ
        return {
            "title": "都心マンション価格チェッカー",
            "description": "東京都心の中古マンション価格を複数サイトから横断検索",
            "canonical": f"https://mscan.jp/properties/{property_id}"
        }

    # 建物名を取得
    building_name = property_obj.display_building_name or "マンション"

    # タイトルと説明を生成
    layout = property_obj.layout or "間取り不明"
    area = f"{property_obj.area}㎡" if property_obj.area else "面積不明"

    title = f"{building_name} {layout} {area} - 都心マンション価格チェッカー"

    # 価格情報
    price_info = ""
    if property_obj.final_price:
        price_millions = property_obj.final_price / 10000
        price_info = f"価格{price_millions:.0f}万円"

    description = f"{building_name}の{layout} {area}の物件詳細。{price_info}複数サイトの情報を比較できます。"

    return {
        "title": title,
        "description": description,
        "canonical": f"https://mscan.jp/properties/{property_id}"
    }


def generate_properties_list_meta_tags(request: Request) -> dict:
    """
    物件一覧ページのメタタグを生成

    Args:
        request: FastAPIのリクエストオブジェクト

    Returns:
        メタタグの辞書
    """
    # クエリパラメータを取得
    query_params = dict(request.query_params)

    # トラッキングパラメータを除外
    tracking_params = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'fbclid', 'gclid']
    for param in tracking_params:
        query_params.pop(param, None)

    # canonical URLを生成
    if query_params:
        query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
        canonical = f"https://mscan.jp/properties?{query_string}"
    else:
        canonical = "https://mscan.jp/properties"

    # 検索条件に応じたタイトルと説明を生成
    title_parts = []

    if "area" in query_params:
        title_parts.append(query_params["area"])

    if "min_price" in query_params or "max_price" in query_params:
        min_price = query_params.get("min_price", "")
        max_price = query_params.get("max_price", "")
        if min_price and max_price:
            title_parts.append(f"{min_price}万円〜{max_price}万円")
        elif min_price:
            title_parts.append(f"{min_price}万円以上")
        elif max_price:
            title_parts.append(f"{max_price}万円以下")

    if title_parts:
        title = f"{' '.join(title_parts)}の中古マンション - 都心マンション価格チェッカー"
        description = f"{' '.join(title_parts)}の中古マンションを複数サイトから横断検索。価格、間取り、築年数を比較できます。"
    else:
        title = "都心の中古マンション検索 - 都心マンション価格チェッカー"
        description = "東京都心の中古マンション価格を複数サイトから横断検索。SUUMO、HOME'S、三井のリハウス、ノムコムの情報を一括比較。"

    return {
        "title": title,
        "description": description,
        "canonical": canonical
    }


def inject_meta_tags_into_html(html: str, meta_data: dict) -> str:
    """
    既存のHTMLにメタタグを注入する

    Args:
        html: ビルド済みのHTML
        meta_data: メタタグのデータ

    Returns:
        メタタグが注入されたHTML
    """
    # メタタグを生成（titleタグは別途置換するので除外）
    # data-rh="true" を追加してreact-helmetが既存タグとして認識し、重複を防ぐ
    meta_tags = f"""<meta name="description" content="{meta_data['description']}" data-rh="true" />
    <link rel="canonical" href="{meta_data['canonical']}" data-rh="true" />
    <meta property="og:title" content="{meta_data['title']}" data-rh="true" />
    <meta property="og:description" content="{meta_data['description']}" data-rh="true" />
    <meta property="og:url" content="{meta_data['canonical']}" data-rh="true" />
    <meta property="og:type" content="website" data-rh="true" />
    <meta name="twitter:card" content="summary_large_image" data-rh="true" />
    <meta name="twitter:title" content="{meta_data['title']}" data-rh="true" />
    <meta name="twitter:description" content="{meta_data['description']}" data-rh="true" />"""

    # 既存のHTMLに対してメタタグを注入
    # 1. 既存のmeta description、canonical、OGタグ、Twitterタグを削除
    html = re.sub(r'<meta\s+name="description"[^>]*>', '', html)
    html = re.sub(r'<link\s+rel="canonical"[^>]*>', '', html)
    html = re.sub(r'<meta\s+property="og:[^"]*"[^>]*>', '', html)
    html = re.sub(r'<meta\s+name="twitter:[^"]*"[^>]*>', '', html)

    # 2. <title>タグを置換し、その後にメタタグを追加
    # data-rh="true"を追加してreact-helmetが重複作成しないようにする
    title_tag = f'<title data-rh="true">{meta_data["title"]}</title>'
    if re.search(r'<title[^>]*>.*?</title>', html, flags=re.DOTALL):
        html = re.sub(
            r'<title[^>]*>.*?</title>',
            title_tag + '\n    ' + meta_tags,
            html,
            flags=re.DOTALL
        )
    else:
        # <title>がない場合は<head>の直後に追加
        html = re.sub(
            r'(<head[^>]*>)',
            r'\1\n    ' + title_tag + '\n    ' + meta_tags,
            html
        )
    
    return html


@router.api_route("/buildings/{building_id}/properties", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def render_building_page(
    building_id: int,
    request: Request,
    include_inactive: bool = Query(False, description="販売終了物件も含む"),
    db: Session = Depends(get_db)
):
    """
    建物ページのSSRを提供（条件付き初期データ埋め込み対応）
    
    クローラーの場合のみ初期データを埋め込み、
    通常のユーザーには高速なフローを提供する（Dynamic Rendering）
    """
    # フロントエンドのHTMLを読み込む
    frontend_html = load_frontend_html()
    
    # メタタグを生成
    meta_data = generate_building_meta_tags(building_id, db)
    
    # クローラーの場合のみ初期データを取得
    initial_state_script = ""
    if is_crawler(request):
        # 初期データを取得（buildingsエンドポイントの実装を再利用）
        from .buildings import get_building_properties
        try:
            # APIエンドポイントと同じデータを取得
            initial_data = await get_building_properties(building_id, include_inactive, db)
            
            # JavaScriptで安全に扱えるようにJSON文字列化
            import json
            initial_state_json = json.dumps(initial_data, ensure_ascii=False, default=str)
            
            # 初期データをHTMLに埋め込む
            initial_state_script = f'''
    <script>
      window.__INITIAL_STATE__ = {initial_state_json};
      window.__SSR_BUILDING_ID__ = {building_id};
      window.__SSR_INCLUDE_INACTIVE__ = {str(include_inactive).lower()};
    </script>'''
        except Exception as e:
            # データ取得失敗時はスクリプトを埋め込まない（通常のAPI呼び出しにフォールバック）
            print(f"Warning: 初期データ取得失敗: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"INFO: 通常ユーザー - 初期データスキップ（高速モード）")
    
    # メタタグを注入
    html = inject_meta_tags_into_html(frontend_html, meta_data)
    
    # 初期データスクリプトを</head>の直前に挿入（クローラーの場合のみ）
    if initial_state_script:
        html = html.replace('</head>', f'{initial_state_script}\n  </head>')
    
    return HTMLResponse(content=html)


@router.api_route("/properties/{property_id}", methods=["GET", "HEAD"], response_class=HTMLResponse)

async def render_property_page(
    property_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    物件詳細ページのSSRを提供（条件付き初期データ埋め込み対応）
    
    クローラーの場合のみ初期データを埋め込み、
    通常のユーザーには高速なフローを提供する（Dynamic Rendering）
    """
    # フロントエンドのHTMLを読み込む
    frontend_html = load_frontend_html()
    
    # メタタグを生成
    meta_data = generate_property_meta_tags(property_id, db)
    
    # クローラーの場合のみ初期データを取得
    initial_state_script = ""
    if is_crawler(request):
        # 初期データを取得（propertiesエンドポイントの実装を再利用）
        from .properties import get_property_details
        try:
            # APIエンドポイントと同じデータを取得
            initial_data = await get_property_details(property_id, db)
            
            # JavaScriptで安全に扱えるようにJSON文字列化
            import json
            # Pydantic modelの場合はdict()を使用
            data_dict = initial_data.dict() if hasattr(initial_data, 'dict') else initial_data
            initial_state_json = json.dumps(data_dict, ensure_ascii=False, default=str)
            
            # 初期データをHTMLに埋め込む
            initial_state_script = f'''
    <script>
      window.__INITIAL_STATE__ = {initial_state_json};
      window.__SSR_PROPERTY_ID__ = {property_id};
    </script>'''
        except Exception as e:
            # データ取得失敗時はスクリプトを埋め込まない（通常のAPI呼び出しにフォールバック）
            print(f"Warning: 初期データ取得失敗: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"INFO: 通常ユーザー - 初期データスキップ（高速モード）")
    
    # メタタグを注入
    html = inject_meta_tags_into_html(frontend_html, meta_data)
    
    # 初期データスクリプトを</head>の直前に挿入（クローラーの場合のみ）
    if initial_state_script:
        html = html.replace('</head>', f'{initial_state_script}\n  </head>')
    
    return HTMLResponse(content=html)


@router.api_route("/properties", methods=["GET", "HEAD"], response_class=HTMLResponse)

async def render_properties_list_page(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    物件一覧ページのSSRを提供（条件付き初期データ埋め込み対応）
    
    クローラーの場合のみ初期データを埋め込み、
    通常のユーザーには高速なフローを提供する（Dynamic Rendering）
    """
    # フロントエンドのHTMLを読み込む
    frontend_html = load_frontend_html()
    
    # メタタグを生成
    meta_data = generate_properties_list_meta_tags(request)
    
    # クローラーの場合のみ初期データを取得
    initial_state_script = ""
    if is_crawler(request):
        # 初期データを取得（propertiesエンドポイントの実装を再利用）
        from .properties import get_properties
        try:
            # クエリパラメータを取得
            min_price = request.query_params.get('min_price')
            max_price = request.query_params.get('max_price')
            min_area = request.query_params.get('min_area')
            max_area = request.query_params.get('max_area')
            layouts = request.query_params.getlist('layouts') if 'layouts' in request.query_params else None
            building_name = request.query_params.get('building_name')
            max_building_age = request.query_params.get('max_building_age')
            wards = request.query_params.getlist('wards') if 'wards' in request.query_params else None
            include_inactive = request.query_params.get('include_inactive', 'false').lower() == 'true'
            page = int(request.query_params.get('page', 1))
            per_page = int(request.query_params.get('per_page', 30))
            sort_by = request.query_params.get('sort_by', 'updated_at')
            sort_order = request.query_params.get('sort_order', 'desc')
            
            # int/floatに変換
            min_price = int(min_price) if min_price else None
            max_price = int(max_price) if max_price else None
            min_area = float(min_area) if min_area else None
            max_area = float(max_area) if max_area else None
            max_building_age = int(max_building_age) if max_building_age else None
            
            # APIエンドポイントと同じデータを取得
            initial_data = await get_properties(
                min_price=min_price,
                max_price=max_price,
                min_area=min_area,
                max_area=max_area,
                layouts=layouts,
                building_name=building_name,
                max_building_age=max_building_age,
                wards=wards,
                include_inactive=include_inactive,
                page=page,
                per_page=per_page,
                sort_by=sort_by,
                sort_order=sort_order,
                db=db
            )
            
            # JavaScriptで安全に扱えるようにJSON文字列化
            import json
            initial_state_json = json.dumps(initial_data, ensure_ascii=False, default=str)
            
            # 初期データとクエリパラメータをHTMLに埋め込む
            initial_state_script = f'''
    <script>
      window.__INITIAL_STATE__ = {initial_state_json};
      window.__SSR_QUERY_PARAMS__ = {{
        min_price: {json.dumps(min_price)},
        max_price: {json.dumps(max_price)},
        min_area: {json.dumps(min_area)},
        max_area: {json.dumps(max_area)},
        layouts: {json.dumps(layouts)},
        building_name: {json.dumps(building_name)},
        max_building_age: {json.dumps(max_building_age)},
        wards: {json.dumps(wards)},
        include_inactive: {str(include_inactive).lower()},
        page: {page},
        per_page: {per_page},
        sort_by: {json.dumps(sort_by)},
        sort_order: {json.dumps(sort_order)}
      }};
    </script>'''
        except Exception as e:
            # データ取得失敗時はスクリプトを埋め込まない（通常のAPI呼び出しにフォールバック）
            print(f"Warning: 初期データ取得失敗: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"INFO: 通常ユーザー - 初期データスキップ（高速モード）")
    
    # メタタグを注入
    html = inject_meta_tags_into_html(frontend_html, meta_data)
    
    # 初期データスクリプトを</head>の直前に挿入（クローラーの場合のみ）
    if initial_state_script:
        html = html.replace('</head>', f'{initial_state_script}\n  </head>')
    
    return HTMLResponse(content=html)


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def render_home_page(
    request: Request
):
    """
    トップページのSSRを提供
    """
    # フロントエンドのHTMLを読み込む
    frontend_html = load_frontend_html()
    
    # メタタグを生成
    meta_data = {
        "title": "都心マンション価格チェッカー - 複数サイト横断検索",
        "description": "東京都心の中古マンション価格を複数サイトから横断検索。SUUMO、HOME'S、三井のリハウス、ノムコムの情報を一括比較。",
        "canonical": "https://mscan.jp/"
    }
    
    # メタタグを注入
    html = inject_meta_tags_into_html(frontend_html, meta_data)
    
    return HTMLResponse(content=html)
