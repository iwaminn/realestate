/**
 * スクレイパー関連の定数定義
 * 全てのコンポーネントで統一して使用する
 */

// スクレイパー名の日本語マッピング
export const SCRAPER_DISPLAY_NAMES: Record<string, string> = {
  suumo: 'SUUMO',
  homes: 'LIFULL HOME\'S',
  rehouse: '三井のリハウス',
  nomu: 'ノムコム',
  livable: '東急リバブル',
};

// 利用可能なスクレイパーのリスト
export const AVAILABLE_SCRAPERS = ['suumo', 'homes', 'rehouse', 'nomu', 'livable'] as const;

// スクレイパーの型定義
export type ScraperType = typeof AVAILABLE_SCRAPERS[number];

// スクレイパーの表示名を取得する関数
export const getScraperDisplayName = (scraper: string): string => {
  return SCRAPER_DISPLAY_NAMES[scraper] || scraper;
};

// スクレイパーのステータスカラー
export const SCRAPER_STATUS_COLORS: Record<string, 'default' | 'primary' | 'secondary' | 'error' | 'warning' | 'info' | 'success'> = {
  pending: 'default',
  running: 'primary',
  paused: 'warning',
  completed: 'success',
  failed: 'error',
  cancelled: 'default',
};

// エリアコードと名前のマッピング
export const AREA_NAMES: Record<string, string> = {
  '13101': '千代田区',
  '13102': '中央区',
  '13103': '港区',
  '13104': '新宿区',
  '13105': '文京区',
  '13106': '台東区',
  '13107': '墨田区',
  '13108': '江東区',
  '13109': '品川区',
  '13110': '目黒区',
  '13111': '大田区',
  '13112': '世田谷区',
  '13113': '渋谷区',
  '13114': '中野区',
  '13115': '杉並区',
  '13116': '豊島区',
  '13117': '北区',
  '13118': '荒川区',
  '13119': '板橋区',
  '13120': '練馬区',
  '13121': '足立区',
  '13122': '葛飾区',
  '13123': '江戸川区',
};

// 利用可能なエリアのリスト（順序付き）
export const AVAILABLE_AREAS = [
  { code: '13101', name: '千代田区' },
  { code: '13103', name: '港区' },
  { code: '13102', name: '中央区' },
  { code: '13113', name: '渋谷区' },
  { code: '13104', name: '新宿区' },
  { code: '13105', name: '文京区' },
  { code: '13110', name: '目黒区' },
  { code: '13109', name: '品川区' },
  { code: '13112', name: '世田谷区' },
  { code: '13116', name: '豊島区' },
  { code: '13106', name: '台東区' },
  { code: '13114', name: '中野区' },
  { code: '13115', name: '杉並区' },
  { code: '13108', name: '江東区' },
];

// 最大物件数の選択肢
export const AVAILABLE_MAX_PROPERTIES = [100, 200, 300, 400, 500, 1000, 2000, 3000, 4000, 5000, 10000];