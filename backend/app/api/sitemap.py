"""sitemap.xmlとrobots.txtを生成するAPIエンドポイント"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import List
import xml.etree.ElementTree as ET

from ..database import get_db
from ..models import MasterProperty, Building

router = APIRouter(tags=["seo"])

BASE_URL = "https://mscan.jp"

@router.get("/sitemap.xml")
async def get_sitemap(db: Session = Depends(get_db)):
    """
    sitemap.xmlを動的に生成
    全物件、全建物、静的ページのURLを含める
    """
    # XML namespaceの定義
    urlset = ET.Element("urlset")
    urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")

    # 静的ページを追加
    static_pages = [
        {"loc": f"{BASE_URL}/", "priority": "1.0", "changefreq": "daily"},
        {"loc": f"{BASE_URL}/transaction-prices", "priority": "0.8", "changefreq": "weekly"},
    ]

    for page in static_pages:
        url_elem = ET.SubElement(urlset, "url")
        loc = ET.SubElement(url_elem, "loc")
        loc.text = page["loc"]
        priority = ET.SubElement(url_elem, "priority")
        priority.text = page["priority"]
        changefreq = ET.SubElement(url_elem, "changefreq")
        changefreq.text = page["changefreq"]

    # 全建物のIDを取得（販売中物件がある建物のみ）
    active_building_ids = db.query(
        Building.id
    ).join(
        Building.properties
    ).join(
        MasterProperty.listings
    ).filter(
        MasterProperty.listings.any(is_active=True)
    ).distinct().limit(10000).all()  # 最大10,000件

    for (building_id,) in active_building_ids:
        url_elem = ET.SubElement(urlset, "url")
        loc = ET.SubElement(url_elem, "loc")
        loc.text = f"{BASE_URL}/buildings/{building_id}/properties"
        priority = ET.SubElement(url_elem, "priority")
        priority.text = "0.6"
        changefreq = ET.SubElement(url_elem, "changefreq")
        changefreq.text = "weekly"

    # XMLを文字列に変換
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_str += ET.tostring(urlset, encoding="unicode", method="xml")

    return Response(content=xml_str, media_type="application/xml")


@router.get("/robots.txt")

async def get_robots():
    """
    robots.txtを生成
    GoogleとBingのみを許可し、他の検索エンジンbotは拒否
    """
    robots_content = f"""# Google検索bot（許可）
User-agent: Googlebot
Allow: /
Disallow: /admin
Disallow: /api/

# Google画像検索bot（許可）
User-agent: Googlebot-Image
Allow: /

# Google Search Console検証ツール（許可）
User-agent: Google-InspectionTool
Allow: /

# Bingbot（許可）
User-agent: Bingbot
Allow: /
Disallow: /admin
Disallow: /api/

# その他すべてのbot（拒否）
User-agent: *
Disallow: /

# Sitemap
Sitemap: {BASE_URL}/sitemap.xml
"""

    return Response(content=robots_content, media_type="text/plain")
