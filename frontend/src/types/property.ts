// v2 API用の型定義
export interface Building {
  id: number;
  normalized_name: string;
  address: string;
  total_floors?: number;
  basement_floors?: number;
  total_units?: number;
  built_year?: number;
  structure?: string;
  land_rights?: string;
  parking_info?: string;
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
  summary_remarks?: string;
  is_resale?: boolean;
  resale_property_id?: number;
  min_price?: number;
  max_price?: number;
  listing_count: number;
  source_sites: string[];
  station_info?: string;
  earliest_published_at?: string;
  has_active_listing?: boolean;
  last_confirmed_at?: string;
  delisted_at?: string;
  latest_price_update?: string;
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
  layout?: string;
  building_name?: string;
  max_building_age?: number;
  sort_by?: string;
  sort_order?: string;
  page?: number;
  per_page?: number;
}

export interface ApiResponse<T> {
  properties: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface Area {
  id: number;
  prefecture: string;
  city: string;
  code: string;
  is_active: boolean;
}

export interface Statistics {
  total_properties: number;
  by_source: Record<string, number>;
  by_price_range: Record<string, number>;
  by_layout: Record<string, number>;
  last_updated: string;
}