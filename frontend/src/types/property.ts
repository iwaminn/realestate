// v2 API用の型定義
export interface Building {
  id: number;
  normalized_name: string;
  address: string;
  total_floors?: number;
  basement_floors?: number;
  total_units?: number;
  built_year?: number;
  built_month?: number;
  structure?: string;
  land_rights?: string;
  parking_info?: string;
}

export interface PriceChangeInfo {
  date: string;
  previous_price: number;
  current_price: number;
  change_amount: number;
  change_rate: number;
}

export interface Property {
  id: number;
  building: Building;
  room_number?: string;
  floor_number?: number;
  area?: number;
  balcony_area?: number;
  layout?: string;
  direction?: string;

  is_resale?: boolean;
  resale_property_id?: number;
  current_price?: number;
  listing_count: number;
  source_sites: string[];
  station_info?: string;
  management_fee?: number;
  repair_fund?: number;
  earliest_published_at?: string;
  has_active_listing?: boolean;
  last_confirmed_at?: string;
  delisted_at?: string;
  latest_price_update?: string;
  has_price_change?: boolean;
  sold_at?: string;
  last_sale_price?: number;
  final_price?: number;  // 最終価格（販売終了時の価格）
  is_bookmarked?: boolean;  // ブックマーク状態
  display_building_name?: string;  // 物件レベルの建物名
  price_change_info?: PriceChangeInfo;  // 価格変更情報
  price_per_tsubo?: number;  // 坪単価
  earliest_published_at?: string;  // 売出確認日
}

export interface Listing {
  id: number;
  source_site: string;
  site_property_id: string;
  url: string;
  title: string;
  agency_name?: string;
  agency_tel?: string;
  current_price?: number;
  management_fee?: number;
  repair_fund?: number;
  remarks?: string;
  is_active: boolean;
  first_seen_at: string;
  last_scraped_at: string;
  published_at?: string;
  first_published_at?: string;
}

export interface PropertyDetail {
  master_property: Property;
  listings: Listing[];
  price_histories_by_listing: Record<number, PriceHistory[]>;
  price_timeline?: any;
  price_consistency?: any;
  unified_price_history?: any[];
  price_discrepancies?: any[];
}

export interface PriceHistory {
  price: number;
  management_fee?: number;
  repair_fund?: number;
  recorded_at: string;
}

export interface OtherSource {
  id: number;
  source_site: string;
  price: number;
  url: string;
  last_updated: string;
}

export interface SearchParams {
  min_price?: number;
  max_price?: number;
  min_area?: number;
  max_area?: number;
  layouts?: string[];
  building_name?: string;
  max_building_age?: number;
  wards?: string[];
  sort_by?: string;
  sort_order?: string;
  page?: number;
  per_page?: number;
  include_inactive?: boolean;
}

export interface Area {
  id: number;
  name: string;
  prefecture: string;
  city: string;
  code: string;
  property_count: number;
  is_active: boolean;
}

export interface ApiResponse<T> {
  properties: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface Statistics {
  total_properties: number;
  by_source: Record<string, number>;
  by_price_range: Record<string, number>;
  by_layout: Record<string, number>;
  last_updated: string;
}

// ブックマーク関連の型定義
export interface Bookmark {
  id: number;
  master_property_id: number;
  created_at: string;
  master_property?: Property;
}

export interface BookmarkCreate {
  master_property_id: number;
}

export interface BookmarkStatus {
  is_bookmarked: boolean;
  bookmark_id?: number;
}