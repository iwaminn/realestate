"""
不動産取引価格API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional, Dict
from datetime import datetime
from pydantic import BaseModel

from ..database import get_db
from ..models import TransactionPrice

router = APIRouter(prefix="/api/transaction-prices", tags=["transaction-prices"])


class TransactionPriceResponse(BaseModel):
    """取引価格レスポンス"""
    id: int
    area_name: str
    transaction_price: Optional[int]
    price_per_sqm: Optional[int]
    floor_area: Optional[float]
    transaction_year: Optional[int]
    transaction_quarter: Optional[int]
    nearest_station: Optional[str]
    station_distance: Optional[int]
    built_year: Optional[str]
    layout: Optional[str]


class AreaStatistics(BaseModel):
    """エリア別統計"""
    area_name: str
    avg_price_per_sqm: float
    median_price_per_sqm: float
    transaction_count: int
    avg_transaction_price: float
    min_price: int
    max_price: int


class PriceTrendData(BaseModel):
    """価格推移データ"""
    year: int
    quarter: int
    avg_price_per_sqm: float
    transaction_count: int
    area_name: Optional[str]


@router.get("/areas")
async def get_areas(db: Session = Depends(get_db)) -> List[str]:
    """港区内の全エリアを取得"""
    areas = db.query(TransactionPrice.area_name).distinct().order_by(TransactionPrice.area_name).all()
    return [area[0] for area in areas if area[0]]


@router.get("/transactions")
async def get_transactions(
    area: Optional[str] = Query(None, description="エリア名"),
    year: Optional[int] = Query(None, description="取引年"),
    quarter: Optional[int] = Query(None, description="四半期"),
    min_price: Optional[int] = Query(None, description="最低価格（万円）"),
    max_price: Optional[int] = Query(None, description="最高価格（万円）"),
    db: Session = Depends(get_db)
) -> List[TransactionPriceResponse]:
    """取引価格データを取得"""

    query = db.query(TransactionPrice)

    if area:
        query = query.filter(TransactionPrice.area_name == area)
    if year:
        query = query.filter(TransactionPrice.transaction_year == year)
    if quarter:
        query = query.filter(TransactionPrice.transaction_quarter == quarter)
    if min_price:
        query = query.filter(TransactionPrice.transaction_price >= min_price)
    if max_price:
        query = query.filter(TransactionPrice.transaction_price <= max_price)

    transactions = query.order_by(
        TransactionPrice.transaction_year,
        TransactionPrice.transaction_quarter
    ).limit(10000).all()

    return [
        TransactionPriceResponse(
            id=t.id,
            area_name=t.area_name,
            transaction_price=t.transaction_price,
            price_per_sqm=t.price_per_sqm,
            floor_area=t.floor_area,
            transaction_year=t.transaction_year,
            transaction_quarter=t.transaction_quarter,
            nearest_station=t.nearest_station,
            station_distance=t.station_distance,
            built_year=t.built_year,
            layout=t.layout
        )
        for t in transactions
    ]


@router.get("/statistics/by-area")
async def get_area_statistics(
    year: Optional[int] = Query(None, description="取引年"),
    quarter: Optional[int] = Query(None, description="四半期"),
    db: Session = Depends(get_db)
) -> List[AreaStatistics]:
    """エリア別の統計情報を取得"""

    query = db.query(
        TransactionPrice.area_name,
        func.avg(TransactionPrice.price_per_sqm).label('avg_price_per_sqm'),
        func.percentile_cont(0.5).within_group(TransactionPrice.price_per_sqm).label('median_price_per_sqm'),
        func.count(TransactionPrice.id).label('transaction_count'),
        func.avg(TransactionPrice.transaction_price).label('avg_transaction_price'),
        func.min(TransactionPrice.transaction_price).label('min_price'),
        func.max(TransactionPrice.transaction_price).label('max_price')
    ).filter(
        TransactionPrice.price_per_sqm.isnot(None),
        TransactionPrice.area_name.isnot(None)
    )

    if year:
        query = query.filter(TransactionPrice.transaction_year == year)
    if quarter:
        query = query.filter(TransactionPrice.transaction_quarter == quarter)

    results = query.group_by(TransactionPrice.area_name).all()

    return [
        AreaStatistics(
            area_name=r.area_name,
            avg_price_per_sqm=r.avg_price_per_sqm / 10000 if r.avg_price_per_sqm else 0,  # 円を万円に変換
            median_price_per_sqm=r.median_price_per_sqm / 10000 if r.median_price_per_sqm else 0,
            transaction_count=r.transaction_count,
            avg_transaction_price=r.avg_transaction_price,
            min_price=r.min_price,
            max_price=r.max_price
        )
        for r in results
    ]


@router.get("/trends")
async def get_price_trends(
    area: Optional[str] = Query(None, description="エリア名"),
    db: Session = Depends(get_db)
) -> List[PriceTrendData]:
    """価格推移データを取得"""

    query = db.query(
        TransactionPrice.transaction_year,
        TransactionPrice.transaction_quarter,
        func.avg(TransactionPrice.price_per_sqm).label('avg_price_per_sqm'),
        func.count(TransactionPrice.id).label('transaction_count')
    ).filter(
        TransactionPrice.price_per_sqm.isnot(None)
    )

    if area:
        query = query.filter(TransactionPrice.area_name == area)

    results = query.group_by(
        TransactionPrice.transaction_year,
        TransactionPrice.transaction_quarter
    ).order_by(
        TransactionPrice.transaction_year,
        TransactionPrice.transaction_quarter
    ).all()

    return [
        PriceTrendData(
            year=r.transaction_year,
            quarter=r.transaction_quarter,
            avg_price_per_sqm=r.avg_price_per_sqm / 10000 if r.avg_price_per_sqm else 0,  # 円を万円に変換
            transaction_count=r.transaction_count,
            area_name=area
        )
        for r in results
    ]


@router.get("/trends-by-size")
async def get_trends_by_size(
    db: Session = Depends(get_db)
) -> List[Dict]:
    """広さ別の価格推移データを取得"""

    # 広さカテゴリーを定義
    size_categories = [
        ("20㎡未満", 0, 20),
        ("20-40㎡", 20, 40),
        ("40-60㎡", 40, 60),
        ("60-80㎡", 60, 80),
        ("80-100㎡", 80, 100),
        ("100㎡以上", 100, 999)
    ]

    results = []

    for category_name, min_size, max_size in size_categories:
        query = db.query(
            TransactionPrice.transaction_year,
            TransactionPrice.transaction_quarter,
            func.avg(TransactionPrice.price_per_sqm).label('avg_price_per_sqm'),
            func.count(TransactionPrice.id).label('transaction_count')
        ).filter(
            TransactionPrice.price_per_sqm.isnot(None),
            TransactionPrice.floor_area >= min_size,
            TransactionPrice.floor_area < max_size
        ).group_by(
            TransactionPrice.transaction_year,
            TransactionPrice.transaction_quarter
        ).order_by(
            TransactionPrice.transaction_year,
            TransactionPrice.transaction_quarter
        ).all()

        for r in query:
            results.append({
                "category": category_name,
                "year": r.transaction_year,
                "quarter": r.transaction_quarter,
                "avg_price_per_sqm": float(r.avg_price_per_sqm / 10000) if r.avg_price_per_sqm else 0.0,
                "transaction_count": r.transaction_count
            })

    return results


@router.get("/trends-by-age")
async def get_trends_by_age(
    db: Session = Depends(get_db)
) -> List[Dict]:
    """築年数別の価格推移データを取得"""

    # 築年カテゴリーを定義（取引時点での築年数を計算）
    results = []

    # 築年数カテゴリー
    age_categories = [
        ("築5年以内", 0, 5),
        ("築5-10年", 5, 10),
        ("築10-15年", 10, 15),
        ("築15-20年", 15, 20),
        ("築20年超", 20, 100)
    ]

    # 全データを取得して築年数を計算
    transactions = db.query(TransactionPrice).filter(
        TransactionPrice.price_per_sqm.isnot(None),
        TransactionPrice.built_year.isnot(None),
        TransactionPrice.transaction_year.isnot(None)
    ).all()

    # 築年数別にグループ化
    from collections import defaultdict
    grouped_data = defaultdict(list)

    for t in transactions:
        # 築年を数値に変換
        try:
            if '年' in str(t.built_year):
                built_year_str = str(t.built_year).replace('年', '').replace('築', '')
                # 令和、平成、昭和の処理
                if '令和' in built_year_str:
                    built_year_num = 2018 + int(built_year_str.replace('令和', ''))
                elif '平成' in built_year_str:
                    built_year_num = 1988 + int(built_year_str.replace('平成', ''))
                elif '昭和' in built_year_str:
                    built_year_num = 1925 + int(built_year_str.replace('昭和', ''))
                else:
                    built_year_num = int(built_year_str)
            else:
                built_year_num = int(t.built_year)

            # 築年数を計算
            age = t.transaction_year - built_year_num

            # カテゴリー判定
            category = None
            for cat_name, min_age, max_age in age_categories:
                if min_age <= age < max_age:
                    category = cat_name
                    break

            if category:
                key = (category, t.transaction_year, t.transaction_quarter)
                grouped_data[key].append(t.price_per_sqm)

        except:
            continue

    # 平均を計算
    for (category, year, quarter), prices in grouped_data.items():
        results.append({
            "category": category,
            "year": year,
            "quarter": quarter,
            "avg_price_per_sqm": sum(prices) / len(prices) / 10000 if prices else 0,
            "transaction_count": len(prices)
        })

    return sorted(results, key=lambda x: (x["category"], x["year"], x["quarter"]))


@router.get("/heatmap-data")
async def get_heatmap_data(
    db: Session = Depends(get_db)
) -> Dict:
    """ヒートマップ用のデータを取得（エリア×年の平均価格）"""

    results = db.query(
        TransactionPrice.area_name,
        TransactionPrice.transaction_year,
        func.avg(TransactionPrice.price_per_sqm).label('avg_price')
    ).filter(
        TransactionPrice.price_per_sqm.isnot(None),
        TransactionPrice.area_name.isnot(None)
    ).group_by(
        TransactionPrice.area_name,
        TransactionPrice.transaction_year
    ).all()

    # データを整形
    areas = sorted(set(r.area_name for r in results))
    years = sorted(set(r.transaction_year for r in results))

    # マトリックスデータを作成
    matrix = []
    for area in areas:
        row = []
        for year in years:
            value = next(
                (r.avg_price / 10000 for r in results
                 if r.area_name == area and r.transaction_year == year),
                None
            )
            row.append(value)
        matrix.append(row)

    return {
        "areas": areas,
        "years": years,
        "data": matrix
    }