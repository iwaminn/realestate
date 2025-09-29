"""
成約価格情報API
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
    """成約価格レスポンス"""
    id: int
    area_name: str
    transaction_price: Optional[int]
    price_per_sqm: Optional[int]
    floor_area: Optional[float]
    transaction_year: Optional[int]
    transaction_quarter: Optional[int]
    built_year: Optional[int]
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
    """全エリアを取得"""
    areas = db.query(TransactionPrice.area_name).distinct().order_by(TransactionPrice.area_name).all()
    return [area[0] for area in areas if area[0]]


@router.get("/areas-by-district")
async def get_areas_by_district(db: Session = Depends(get_db)) -> Dict[str, List[str]]:
    """区ごとにグループ化されたエリア一覧を取得"""

    # 区とエリアのマッピング定義
    district_mapping = {
        "千代田区": ["一番町", "二番町", "三番町", "五番町", "六番町", "九段北", "九段南", "内神田", "内幸町",
                  "北の丸公園", "外神田", "大手町", "岩本町", "平河町", "日比谷公園", "有楽町", "東神田",
                  "永田町", "神田神保町", "神田佐久間町", "神田司町", "神田和泉町", "神田多町", "神田小川町",
                  "神田岩本町", "神田東松下町", "神田東紺屋町", "神田淡路町", "神田相生町", "神田紺屋町",
                  "神田美倉町", "神田美土代町", "神田花岡町", "神田西福田町", "神田錦町", "神田須田町",
                  "神田駿河台", "神田鍛冶町", "紀尾井町", "西神田", "隼町", "霞が関", "飯田橋", "鍛冶町",
                  "麹町", "丸の内"],
        "中央区": ["京橋", "佃", "入船", "八丁堀", "勝どき", "新富", "新川", "日本橋", "日本橋中洲",
                  "日本橋人形町", "日本橋兜町", "日本橋大伝馬町", "日本橋室町", "日本橋小伝馬町",
                  "日本橋小網町", "日本橋小舟町", "日本橋本町", "日本橋本石町", "日本橋東", "日本橋浜町",
                  "日本橋箱崎町", "日本橋蛎殻町", "日本橋茅場町", "日本橋馬喰町", "明石町", "月島", "東日本橋",
                  "晴海", "浜離宮庭園", "湊", "築地", "銀座", "豊海町"],
        "港区": ["三田", "元赤坂", "元麻布", "六本木", "北青山", "南青山", "南麻布", "台場", "東新橋",
                 "東麻布", "海岸", "港南", "浜松町", "白金", "白金台", "芝", "芝公園", "芝大門", "芝浦",
                 "虎ノ門", "西新橋", "西麻布", "赤坂", "高輪", "麻布十番", "麻布台", "麻布永坂町",
                 "麻布狸穴町", "新橋"],
        "新宿区": ["上落合", "下宮比町", "下落合", "中井", "中町", "中落合", "中里町", "二十騎町", "余丁町",
                  "住吉町", "信濃町", "内藤町", "北山伏町", "北新宿", "北町", "南元町", "南山伏町", "南榎町",
                  "南町", "原町", "喜久井町", "四谷", "四谷坂町", "四谷本塩町", "坂町", "大京町", "天神町",
                  "富久町", "左門町", "市谷", "市谷仲之町", "市谷八幡町", "市谷加賀町", "市谷台町",
                  "市谷左内町", "市谷本村町", "市谷柳町", "市谷田町", "市谷甲良町", "市谷砂土原町",
                  "市谷船河原町", "市谷薬王寺町", "市谷長延寺町", "市谷鷹匠町", "弁天町", "戸塚町", "戸山",
                  "払方町", "揚場町", "改代町", "新宿", "新小川町", "早稲田", "早稲田南町", "早稲田鶴巻町",
                  "東五軒町", "東榎町", "歌舞伎町", "河田町", "津久戸町", "片町", "牛込中央通り", "神楽坂",
                  "神楽河岸", "白銀町", "百人町", "矢来町", "箪笥町", "納戸町", "細工町", "若宮町", "若松町",
                  "若葉", "荒木町", "舟町", "西五軒町", "西早稲田", "西新宿", "西落合", "赤城下町", "赤城元町",
                  "袋町", "霞ケ丘町", "高田馬場", "鶴巻町"],
        "文京区": ["千石", "千駄木", "向丘", "大塚", "小日向", "小石川", "弥生", "後楽", "春日", "本郷",
                  "本駒込", "根津", "水道", "湯島", "白山", "目白台", "西片", "関口", "音羽"],
        "台東区": ["三ノ輪", "三筋", "上野", "上野公園", "上野桜木", "下谷", "今戸", "元浅草", "入谷",
                  "千束", "台東", "寿", "小島", "日本堤", "東上野", "東浅草", "松が谷", "根岸", "柳橋",
                  "池之端", "浅草", "浅草橋", "清川", "秋葉原", "竜泉", "蔵前", "西浅草", "谷中", "雷門",
                  "駒形", "鳥越"],
        "墨田区": ["両国", "亀沢", "京島", "八広", "千歳", "吾妻橋", "向島", "墨田", "太平", "堤通",
                  "東向島", "東墨田", "東駒形", "業平", "横川", "横網", "江東橋", "石原", "立川", "立花",
                  "緑", "菊川", "錦糸", "押上"],
        "江東区": ["三好", "亀戸", "住吉", "佐賀", "冬木", "北砂", "千田", "千石", "南砂", "古石場",
                  "塩浜", "大島", "富岡", "平野", "常盤", "扇橋", "新大橋", "新木場", "新砂", "木場",
                  "東砂", "東陽", "東雲", "枝川", "森下", "永代", "毛利", "海辺", "深川", "清澄", "潮見",
                  "牡丹", "猿江", "白河", "石島", "福住", "越中島", "辰巳", "門前仲町", "高橋"],
        "品川区": ["上大崎", "中延", "二葉", "五反田", "北品川", "南品川", "南大井", "勝島", "大井", "大崎",
                  "小山", "小山台", "平塚", "広町", "戸越", "旗の台", "東中延", "東五反田", "東八潮",
                  "東品川", "東大井", "荏原", "西中延", "西五反田", "西品川", "西大井", "豊町"],
        "目黒区": ["三田", "上目黒", "下目黒", "中央町", "中根", "中町", "中目黒", "五本木", "八雲",
                  "南", "原町", "大岡山", "大橋", "平町", "柿の木坂", "洗足", "目黒", "目黒本町",
                  "碑文谷", "祐天寺", "緑が丘", "自由が丘", "鷹番", "駒場", "青葉台"],
        "大田区": ["上池台", "下丸子", "中央", "中馬込", "久が原", "仲六郷", "仲池上", "北千束", "北嶺町",
                  "北糀谷", "北馬込", "千鳥", "南千束", "南六郷", "南蒲田", "南馬込", "南雪谷", "大森中",
                  "大森北", "大森南", "大森本町", "大森東", "大森西", "山王", "平和島", "平和の森公園",
                  "新蒲田", "東六郷", "東嶺町", "東海", "東矢口", "東糀谷", "東蒲田", "東雪谷", "東馬込",
                  "池上", "田園調布", "田園調布南", "田園調布本町", "石川町", "矢口", "羽田", "羽田旭町",
                  "羽田空港", "萩中", "蒲田", "蒲田本町", "西六郷", "西嶺町", "西糀谷", "西蒲田", "西馬込",
                  "雪谷大塚町", "鵜の木"],
        "世田谷区": ["三宿", "三軒茶屋", "上北沢", "上用賀", "上祖師谷", "上野毛", "上馬", "下馬", "世田谷",
                    "中町", "代沢", "代田", "八幡山", "北沢", "北烏山", "千歳台", "南烏山", "喜多見",
                    "大原", "大蔵", "太子堂", "奥沢", "宇奈根", "宮坂", "尾山台", "岡本", "弦巻", "成城",
                    "新町", "東玉川", "松原", "桜", "桜上水", "桜丘", "桜新町", "梅丘", "池尻", "深沢",
                    "瀬田", "玉堤", "玉川", "玉川台", "玉川田園調布", "用賀", "砧", "砧公園", "祖師谷",
                    "等々力", "粕谷", "経堂", "給田", "船橋", "若林", "豪徳寺", "赤堤", "野毛", "野沢",
                    "鎌田", "駒沢", "駒沢公園"],
        "渋谷区": ["上原", "代々木", "代官山町", "元代々木町", "初台", "円山町", "千駄ケ谷", "南平台町",
                  "恵比寿", "恵比寿南", "恵比寿西", "幡ケ谷", "広尾", "本町", "東", "松濤", "桜丘町",
                  "渋谷", "神南", "神宮前", "神山町", "神泉町", "笹塚", "西原", "道玄坂", "鉢山町",
                  "鶯谷町", "富ヶ谷"],
        "中野区": ["上高田", "上鷺宮", "中央", "中野", "丸山", "南台", "大和町", "弥生町", "新井", "本町",
                  "東中野", "松が丘", "江原町", "江古田", "沼袋", "白鷺", "若宮", "野方", "鷺宮"],
        "杉並区": ["上井草", "上荻", "上高井戸", "下井草", "下高井戸", "久我山", "井草", "今川", "南荻窪",
                  "和泉", "和田", "善福寺", "堀ノ内", "大宮", "天沼", "宮前", "成田東", "成田西", "方南",
                  "本天沼", "松庵", "松ノ木", "桃井", "梅里", "永福", "浜田山", "清水", "西荻北", "西荻南",
                  "阿佐谷北", "阿佐谷南", "高井戸東", "高井戸西", "高円寺北", "高円寺南", "荻窪"],
        "豊島区": ["上池袋", "北大塚", "千川", "千早", "南大塚", "南池袋", "南長崎", "巣鴨", "東池袋",
                  "池袋", "池袋本町", "目白", "西巣鴨", "西池袋", "要町", "豊島", "長崎", "雑司が谷",
                  "駒込", "高松", "高田"],
        "北区": ["上中里", "上十条", "中十条", "中里", "十条仲原", "十条台", "堀船", "岩淵町", "岸町",
                "志茂", "昭和町", "東十条", "東田端", "栄町", "桐ケ丘", "浮間", "滝野川", "王子",
                "王子本町", "田端", "田端新町", "神谷", "西が丘", "西ケ原", "豊島", "赤羽", "赤羽北",
                "赤羽南", "赤羽台", "赤羽西"],
        "荒川区": ["南千住", "東尾久", "東日暮里", "町屋", "荒川", "西尾久", "西日暮里"],
        "板橋区": ["三園", "上板橋", "中丸町", "中台", "中板橋", "仲宿", "仲町", "前野町", "加賀", "南町",
                  "双葉町", "向原", "坂下", "大原町", "大和町", "大山東町", "大山町", "大山西町", "大山金井町",
                  "大谷口", "大谷口上町", "大谷口北町", "大門", "宮本町", "小茂根", "小豆沢", "山中町",
                  "常盤台", "幸町", "弥生町", "徳丸", "志村", "成増", "新河岸", "東坂下", "東山町", "東新町",
                  "板橋", "栄町", "桜川", "氷川町", "泉町", "清水町", "熊野町", "相生町", "稲荷台", "舟渡",
                  "若木", "蓮根", "蓮沼町", "西台", "赤塚", "赤塚新町", "高島平"],
        "練馬区": ["三原台", "上石神井", "上石神井南町", "下石神井", "中村", "中村北", "中村南", "光が丘",
                  "北町", "南大泉", "南田中", "向山", "土支田", "大泉学園町", "大泉町", "富士見台", "小竹町",
                  "平和台", "春日町", "早宮", "旭丘", "旭町", "東大泉", "栄町", "桜台", "氷川台", "田柄",
                  "石神井台", "石神井町", "立野町", "練馬", "羽沢", "西大泉", "西大泉町", "豊玉上", "豊玉中",
                  "豊玉北", "豊玉南", "貫井", "錦", "関町北", "関町南", "関町東", "高松", "高野台"],
        "足立区": ["一ツ家", "中央本町", "中川", "伊興", "佐野", "保塚町", "保木間", "入谷", "入谷町",
                  "六月", "六木", "六町", "加平", "加賀", "北加平町", "千住", "千住中居町", "千住仲町",
                  "千住元町", "千住大川町", "千住寿町", "千住宮元町", "千住曙町", "千住東", "千住柳町",
                  "千住桜木", "千住橋戸町", "千住河原町", "千住緑町", "千住関屋町", "千住龍田町", "南花畑",
                  "古千谷", "古千谷本町", "堀之内", "大谷田", "宮城", "小台", "島根", "平野", "弘道",
                  "新田", "日ノ出町", "東伊興", "東保木間", "東六月町", "東和", "東綾瀬", "栗原", "梅島",
                  "梅田", "椿", "江北", "神明", "神明南", "竹の塚", "綾瀬", "舎人", "舎人公園", "花畑",
                  "西伊興", "西伊興町", "西保木間", "西加平", "西新井", "西新井本町", "西新井栄町", "西竹の塚",
                  "西綾瀬", "谷中", "谷在家", "足立", "辰沼", "青井", "鹿浜"],
        "葛飾区": ["お花茶屋", "亀有", "四つ木", "堀切", "奥戸", "宝町", "小菅", "新宿", "新小岩",
                  "東四つ木", "東堀切", "東新小岩", "東水元", "東立石", "東金町", "柴又", "水元", "水元公園",
                  "白鳥", "立石", "細田", "西亀有", "西新小岩", "西水元", "金町", "金町浄水場", "青戸", "鎌倉",
                  "高砂"],
        "江戸川区": ["一之江", "一之江町", "上一色", "上篠崎", "中央", "中葛西", "二之江町", "北小岩",
                   "北葛西", "南小岩", "南篠崎町", "南葛西", "大杉", "宇喜田町", "小松川", "平井", "新堀",
                   "春江町", "東小岩", "東小松川", "東松本", "東瑞江", "東篠崎", "東篠崎町", "東葛西",
                   "松島", "松本", "松江", "江戸川", "清新町", "瑞江", "篠崎町", "船堀", "興宮町", "臨海町",
                   "西一之江", "西小岩", "西小松川町", "西瑞江", "西篠崎", "西葛西", "谷河内", "鹿骨",
                   "鹿骨町"]
    }

    # データベースから全エリアを取得
    all_areas = db.query(TransactionPrice.area_name).distinct().all()
    all_areas_set = {area[0] for area in all_areas if area[0]}

    # 実際にデータが存在するエリアのみを返す
    result = {}
    for district, area_list in district_mapping.items():
        existing_areas = [area for area in area_list if area in all_areas_set]
        if existing_areas:
            result[district] = sorted(existing_areas)

    # マッピングされていないエリアを「その他」として追加
    mapped_areas = set()
    for area_list in district_mapping.values():
        mapped_areas.update(area_list)

    other_areas = sorted(list(all_areas_set - mapped_areas))
    if other_areas:
        result["その他"] = other_areas

    return result


@router.get("/transactions")
async def get_transactions(
    area: Optional[str] = Query(None, description="エリア名"),
    year: Optional[int] = Query(None, description="取引年"),
    quarter: Optional[int] = Query(None, description="四半期"),
    min_price: Optional[int] = Query(None, description="最低価格（万円）"),
    max_price: Optional[int] = Query(None, description="最高価格（万円）"),
    db: Session = Depends(get_db)
) -> List[TransactionPriceResponse]:
    """成約価格データを取得"""

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

    # 上限を撤廃（パフォーマンス注意）
    transactions = query.order_by(
        TransactionPrice.transaction_year.desc(),
        TransactionPrice.transaction_quarter.desc()
    ).all()

    return [
        TransactionPriceResponse(
            id=t.id,
            area_name=t.area_name,
            transaction_price=t.transaction_price,
            price_per_sqm=t.price_per_sqm,
            floor_area=t.floor_area,
            transaction_year=t.transaction_year,
            transaction_quarter=t.transaction_quarter,
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