"""
Server-Side Rendering (SSR) エンドポイント
Google等の検索エンジン向けに、ページ固有のメタタグを埋め込んだHTMLを返す
"""
from fastapi import APIRouter, Depends, Request
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
    読み込めない場合はデフォルトテンプレートを使用
    """
    try:
        if os.path.exists(FRONTEND_DIST_PATH):
            with open(FRONTEND_DIST_PATH, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        print(f"Warning: フロントエンドのindex.htmlを読み込めませんでした: {e}")
    
    return DEFAULT_HTML_TEMPLATE


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
    # メタタグを生成
    meta_tags = f"""<title>{meta_data['title']}</title>
    <meta name="description" content="{meta_data['description']}" />
    <link rel="canonical" href="{meta_data['canonical']}" />
    <meta property="og:title" content="{meta_data['title']}" />
    <meta property="og:description" content="{meta_data['description']}" />
    <meta property="og:url" content="{meta_data['canonical']}" />
    <meta property="og:type" content="website" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{meta_data['title']}" />
    <meta name="twitter:description" content="{meta_data['description']}" />"""

    # 既存のHTMLに対してメタタグを注入
    # 1. <title>タグを置換
    html = re.sub(r'<title>.*?</title>', f'<title>{meta_data["title"]}</title>', html, flags=re.DOTALL)
    
    # 2. <head>の終了タグの前にメタタグを追加（既存のtitleタグの後）
    # まず既存のmeta descriptionとcanonicalがあれば削除
    html = re.sub(r'<meta\s+name="description"[^>]*>', '', html)
    html = re.sub(r'<link\s+rel="canonical"[^>]*>', '', html)
    html = re.sub(r'<meta\s+property="og:[^"]*"[^>]*>', '', html)
    html = re.sub(r'<meta\s+name="twitter:[^"]*"[^>]*>', '', html)
    
    # <title>タグの後に新しいメタタグを追加
    if '<title>' in html:
        html = re.sub(
            r'(<title>.*?</title>)',
            r'\1\n    ' + meta_tags,
            html,
            flags=re.DOTALL
        )
    else:
        # <title>がない場合は<head>の直後に追加
        html = re.sub(
            r'(<head[^>]*>)',
            r'\1\n    ' + meta_tags,
            html
        )
    
    return html


@router.get("/buildings/{building_id}/properties", response_class=HTMLResponse)
async def render_building_page(
    building_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    建物ページのSSRを提供
    """
    # フロントエンドのHTMLを読み込む
    frontend_html = load_frontend_html()
    
    # メタタグを生成
    meta_data = generate_building_meta_tags(building_id, db)
    
    # メタタグを注入
    html = inject_meta_tags_into_html(frontend_html, meta_data)
    
    return HTMLResponse(content=html)


@router.get("/properties/{property_id}", response_class=HTMLResponse)
async def render_property_page(
    property_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    物件詳細ページのSSRを提供
    """
    # フロントエンドのHTMLを読み込む
    frontend_html = load_frontend_html()
    
    # メタタグを生成
    meta_data = generate_property_meta_tags(property_id, db)
    
    # メタタグを注入
    html = inject_meta_tags_into_html(frontend_html, meta_data)
    
    return HTMLResponse(content=html)


@router.get("/properties", response_class=HTMLResponse)
async def render_properties_list_page(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    物件一覧ページのSSRを提供
    """
    # フロントエンドのHTMLを読み込む
    frontend_html = load_frontend_html()
    
    # メタタグを生成
    meta_data = generate_properties_list_meta_tags(request)
    
    # メタタグを注入
    html = inject_meta_tags_into_html(frontend_html, meta_data)
    
    return HTMLResponse(content=html)


@router.get("/", response_class=HTMLResponse)
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
