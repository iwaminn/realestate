-- データベースの全テーブルをクリアするSQL
-- 外部キー制約を一時的に無効化
SET session_replication_role = 'replica';

-- 削除（依存関係順）
DELETE FROM listing_price_history;
DELETE FROM property_merge_exclusions;
DELETE FROM property_merge_history;
DELETE FROM price_mismatch_history;
DELETE FROM property_listings;
DELETE FROM master_properties;
DELETE FROM building_merge_exclusions;
DELETE FROM building_merge_history;
DELETE FROM building_external_ids;
DELETE FROM building_aliases;
DELETE FROM buildings;
DELETE FROM url_404_retries;
DELETE FROM scraper_alerts;
DELETE FROM scraping_task_progress;
DELETE FROM scraping_tasks;

-- 外部キー制約を再度有効化
SET session_replication_role = 'origin';

-- シーケンスのリセット
ALTER SEQUENCE IF EXISTS buildings_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS building_aliases_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS master_properties_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS property_listings_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS listing_price_history_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS building_external_ids_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS building_merge_history_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS building_merge_exclusions_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS property_merge_history_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS property_merge_exclusions_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS url_404_retries_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS scraper_alerts_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS price_mismatch_history_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS scraping_tasks_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS scraping_task_progress_id_seq RESTART WITH 1;

-- 削除結果の確認
SELECT 'buildings' as table_name, COUNT(*) as count FROM buildings
UNION ALL SELECT 'master_properties', COUNT(*) FROM master_properties
UNION ALL SELECT 'property_listings', COUNT(*) FROM property_listings
UNION ALL SELECT 'scraping_tasks', COUNT(*) FROM scraping_tasks
UNION ALL SELECT 'scraper_alerts', COUNT(*) FROM scraper_alerts
ORDER BY table_name;