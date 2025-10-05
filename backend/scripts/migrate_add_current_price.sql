-- マイグレーション: master_propertiesテーブルにcurrent_priceカラムを追加
-- 実行日: 2025-10-05
-- 目的: 価格フィールドの統一（min_price/max_price/majority_price → current_price）

-- ステップ1: current_priceカラムが既に存在するか確認
-- 以下のコマンドで確認:
-- \d master_properties

-- ステップ2: current_priceカラムを追加（存在しない場合のみ）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'master_properties'
        AND column_name = 'current_price'
    ) THEN
        ALTER TABLE master_properties
        ADD COLUMN current_price INTEGER;

        RAISE NOTICE 'current_priceカラムを追加しました';
    ELSE
        RAISE NOTICE 'current_priceカラムは既に存在します';
    END IF;
END $$;

-- ステップ3: 既存データのcurrent_priceを計算して更新
-- 販売中物件: アクティブな掲載の価格から多数決で決定
-- 販売終了物件: final_priceを使用

-- 一時テーブル: 各物件の多数決価格を計算
CREATE TEMP TABLE temp_majority_prices AS
SELECT
    mp.id as master_property_id,
    CASE
        WHEN mp.sold_at IS NOT NULL THEN mp.final_price
        ELSE (
            SELECT pl.current_price
            FROM property_listings pl
            WHERE pl.master_property_id = mp.id
                AND pl.is_active = TRUE
                AND pl.current_price IS NOT NULL
            GROUP BY pl.current_price
            ORDER BY COUNT(*) DESC, pl.current_price DESC
            LIMIT 1
        )
    END as calculated_price
FROM master_properties mp;

-- current_priceを更新
UPDATE master_properties mp
SET current_price = tmp.calculated_price
FROM temp_majority_prices tmp
WHERE mp.id = tmp.master_property_id
    AND tmp.calculated_price IS NOT NULL;

-- 一時テーブルを削除
DROP TABLE temp_majority_prices;

-- ステップ4: 結果確認
SELECT
    COUNT(*) as total_properties,
    COUNT(current_price) as properties_with_price,
    COUNT(*) - COUNT(current_price) as properties_without_price,
    MIN(current_price) as min_price,
    MAX(current_price) as max_price,
    AVG(current_price)::INTEGER as avg_price
FROM master_properties;

-- ステップ5: サンプルデータ確認（最初の10件）
SELECT
    id,
    building_id,
    room_number,
    current_price,
    sold_at,
    final_price
FROM master_properties
ORDER BY id
LIMIT 10;
