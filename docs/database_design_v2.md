# 不動産検索システム データベース設計 v2.0

## 概要
同一物件の重複を排除し、複数サイトの掲載情報を統合管理するための設計

## テーブル構成

### 1. buildings (建物マスター)
標準化された建物情報を管理
```sql
CREATE TABLE buildings (
    id SERIAL PRIMARY KEY,
    normalized_name VARCHAR(255) NOT NULL,  -- 標準化された建物名
    address VARCHAR(500),                   -- 標準化された住所
    total_floors INTEGER,                   -- 総階数
    built_year INTEGER,                     -- 築年
    structure VARCHAR(100),                 -- 構造（RC造など）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_buildings_normalized_name ON buildings(normalized_name);
CREATE INDEX idx_buildings_address ON buildings(address);
```

### 2. building_aliases (建物名エイリアス)
建物名の表記ゆれを管理
```sql
CREATE TABLE building_aliases (
    id SERIAL PRIMARY KEY,
    building_id INTEGER REFERENCES buildings(id),
    alias_name VARCHAR(255) NOT NULL,       -- 実際に使われている建物名
    source VARCHAR(50),                     -- どのサイトで使われているか
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_building_aliases_alias_name ON building_aliases(alias_name);
CREATE INDEX idx_building_aliases_building_id ON building_aliases(building_id);
```

### 3. master_properties (物件マスター)
重複を排除した物件の基本情報
```sql
CREATE TABLE master_properties (
    id SERIAL PRIMARY KEY,
    building_id INTEGER REFERENCES buildings(id),
    room_number VARCHAR(50),                -- 部屋番号
    floor_number INTEGER,                   -- 階数
    area FLOAT,                             -- 専有面積
    layout VARCHAR(50),                     -- 間取り
    direction VARCHAR(50),                  -- 方角
    property_hash VARCHAR(255) UNIQUE,      -- 建物ID+部屋番号のハッシュ
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_master_properties_building_id ON master_properties(building_id);
CREATE INDEX idx_master_properties_property_hash ON master_properties(property_hash);
```

### 4. property_listings (物件掲載情報)
各サイトの掲載情報
```sql
CREATE TABLE property_listings (
    id SERIAL PRIMARY KEY,
    master_property_id INTEGER REFERENCES master_properties(id),
    source_site VARCHAR(50) NOT NULL,       -- SUUMO, AtHome, HOMES
    site_property_id VARCHAR(255),          -- サイト内の物件ID
    url VARCHAR(1000) NOT NULL,             -- 掲載URL
    title VARCHAR(500),                     -- 掲載タイトル
    description TEXT,                       -- 物件説明
    
    -- 掲載元情報
    agency_name VARCHAR(255),               -- 仲介業者名
    agency_tel VARCHAR(50),                 -- 問い合わせ電話番号
    
    -- 価格情報（最新）
    current_price INTEGER,                  -- 現在の価格（万円）
    management_fee INTEGER,                 -- 管理費
    repair_fund INTEGER,                    -- 修繕積立金
    
    -- その他の情報
    station_info TEXT,                      -- 最寄り駅情報
    features TEXT,                          -- 物件特徴
    
    -- 掲載状態
    is_active BOOLEAN DEFAULT TRUE,         -- 掲載中かどうか
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delisted_at TIMESTAMP,                  -- 掲載終了日時
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_property_listings_master_property_id ON property_listings(master_property_id);
CREATE INDEX idx_property_listings_source_site ON property_listings(source_site);
CREATE INDEX idx_property_listings_is_active ON property_listings(is_active);
CREATE UNIQUE INDEX idx_property_listings_url ON property_listings(url);
```

### 5. listing_price_history (掲載価格履歴)
掲載ごとの価格変動を記録
```sql
CREATE TABLE listing_price_history (
    id SERIAL PRIMARY KEY,
    property_listing_id INTEGER REFERENCES property_listings(id),
    price INTEGER NOT NULL,                 -- 価格（万円）
    management_fee INTEGER,                 -- 管理費
    repair_fund INTEGER,                    -- 修繕積立金
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_listing_price_history_property_listing_id ON listing_price_history(property_listing_id);
CREATE INDEX idx_listing_price_history_recorded_at ON listing_price_history(recorded_at);
```

### 6. property_images (物件画像)
物件の画像情報
```sql
CREATE TABLE property_images (
    id SERIAL PRIMARY KEY,
    property_listing_id INTEGER REFERENCES property_listings(id),
    image_url VARCHAR(1000),
    image_type VARCHAR(50),                 -- 外観、間取り図、室内など
    display_order INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_property_images_property_listing_id ON property_images(property_listing_id);
```

## データフロー

### 1. スクレイピング時の処理
1. 物件情報を取得
2. 建物名を標準化処理
   - building_aliasesをチェック
   - なければ新規buildingとして登録
3. master_propertiesに物件が存在するかチェック
   - property_hash（建物ID+部屋番号）で判定
4. property_listingsに掲載情報を追加/更新
5. 価格が変更されていればlisting_price_historyに記録

### 2. 一覧表示時の処理
```sql
-- 最新価格と掲載数を含む物件一覧
SELECT 
    mp.*,
    b.normalized_name as building_name,
    b.address,
    MIN(pl.current_price) as min_price,
    MAX(pl.current_price) as max_price,
    COUNT(DISTINCT pl.source_site) as source_count,
    COUNT(pl.id) as listing_count
FROM master_properties mp
JOIN buildings b ON mp.building_id = b.id
JOIN property_listings pl ON mp.id = pl.master_property_id
WHERE pl.is_active = TRUE
GROUP BY mp.id, b.id;
```

### 3. 詳細表示時の処理
```sql
-- 物件の全掲載情報を取得
SELECT 
    pl.*,
    mp.*,
    b.*
FROM property_listings pl
JOIN master_properties mp ON pl.master_property_id = mp.id
JOIN buildings b ON mp.building_id = b.id
WHERE mp.id = ?
ORDER BY pl.source_site, pl.current_price;
```

## 建物名標準化ロジック

1. **前処理**
   - 全角英数字を半角に変換
   - スペースの正規化
   - 「マンション」「ビル」などの接尾辞を統一

2. **類似度判定**
   - レーベンシュタイン距離
   - 住所の一致度
   - 総階数の一致

3. **標準名の決定**
   - 最も出現頻度の高い表記を採用
   - または最も詳細な表記を採用

## メリット

1. **重複排除**: 同一物件は1レコードとして管理
2. **価格追跡**: 掲載単位で詳細な価格履歴を保持
3. **柔軟性**: 同一サイトの複数掲載にも対応
4. **標準化**: 建物名の表記ゆれを吸収
5. **パフォーマンス**: 適切なインデックスで高速検索

## 移行計画

1. 新テーブルの作成
2. 既存データの分析と建物名標準化
3. master_propertiesへのデータ移行
4. property_listingsへのデータ移行
5. APIの更新
6. フロントエンドの更新