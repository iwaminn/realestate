import axios from 'axios';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface ListingListParams {
  source_site?: string;
  building_name?: string;
  is_active?: boolean;
  has_detail?: boolean;
  min_price?: number;
  max_price?: number;
  ward?: string;
  page?: number;
  per_page?: number;
  sort_by?: string;
  sort_order?: string;
}

export interface ListingListResponse {
  listings: any[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  stats: {
    total_listings: number;
    unique_properties: number;
    active_listings: number;
    with_details: number;
  };
}

export interface ListingStatsResponse {
  by_source: Array<{
    source_site: string;
    total_listings: number;
    unique_properties: number;
    active_listings: number;
    with_details: number;
    avg_price?: number;
    earliest_listing?: string;
    latest_update?: string;
  }>;
  total: {
    total_listings: number;
    unique_properties: number;
    source_sites: number;
  };
}

export const listingApi = {
  // 掲載情報一覧を取得
  getListings: async (params: ListingListParams): Promise<ListingListResponse> => {
    const response = await api.get('/admin/listings', { params });
    return response.data;
  },

  // 掲載情報の詳細を取得
  getListingDetail: async (listingId: number): Promise<any> => {
    const response = await api.get(`/admin/listings/${listingId}`);
    return response.data;
  },

  // サイト別統計を取得
  getListingStats: async (): Promise<ListingStatsResponse> => {
    const response = await api.get('/admin/listings/stats/by-source');
    return response.data;
  },

  // 掲載情報の詳細を再取得
  refreshListingDetail: async (listingId: number): Promise<{
    success: boolean;
    message: string;
    listing_id: number;
    url: string;
    source_site: string;
  }> => {
    const response = await api.post(`/admin/listings/${listingId}/refresh-detail`);
    return response.data;
  },

  // 掲載情報を削除（非アクティブ化）
  deleteListing: async (listingId: number): Promise<{
    success: boolean;
    message: string;
    listing_id: number;
  }> => {
    const response = await api.delete(`/admin/listings/${listingId}`);
    return response.data;
  },
};