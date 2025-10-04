import axios from '../utils/axiosConfig';
import type { Property, PropertyDetail, SearchParams, ApiResponse, Area, Statistics } from '../types/property';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  // 配列パラメータを正しく送信するための設定
  paramsSerializer: (params) => {
    const searchParams = new URLSearchParams();
    Object.keys(params).forEach(key => {
      const value = params[key];
      if (value === undefined || value === null || value === '') {
        return;
      }
      if (Array.isArray(value)) {
        // 配列の場合、各要素を同じキー名で追加
        value.forEach(item => {
          searchParams.append(key, item);
        });
      } else {
        searchParams.append(key, String(value));
      }
    });
    return searchParams.toString();
  },
});

// 認証情報を含めるためのインターセプター
api.interceptors.request.use(
  (config) => {
    const authHeader = localStorage.getItem('adminAuth');
    if (authHeader && config.headers) {
      config.headers['Authorization'] = authHeader;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

export interface RecentUpdate {
  id: number;
  building_name: string;
  room_number: string | null;
  floor_number: number | null;
  area: number | null;
  layout: string | null;
  direction: string | null;
  price: number;
  previous_price?: number;  // 前回価格
  price_diff?: number;       // 価格変動幅（万円）
  price_diff_rate?: number;  // 価格変動率（%）
  title: string;
  url: string;
  source_site: string;
  changed_at?: string;
  created_at?: string;
  address: string | null;
  built_year?: number | null;
  built_month?: number | null;
  days_on_market?: number | null;
}

export interface WardUpdates {
  ward: string;
  price_changes: RecentUpdate[];
  new_listings: RecentUpdate[];
}

export interface RecentUpdatesResponse {
  period_hours: number;
  cutoff_time: string;
  total_price_changes: number;
  total_new_listings: number;
  updates_by_ward: WardUpdates[];
  last_scraper_completed_at: string | null;
}

export const propertyApi = {
  // 物件一覧検索
  searchProperties: async (params: SearchParams): Promise<ApiResponse<Property>> => {
    const response = await api.get('/properties', { params });
    return response.data;
  },

  // 物件詳細取得
  getPropertyDetail: async (id: number): Promise<PropertyDetail> => {
    const response = await api.get(`/properties/${id}`);
    return response.data;
  },

  // 統計情報取得
  getStatistics: async (): Promise<Statistics> => {
    const response = await api.get('/stats');
    return response.data;
  },

  // エリア一覧取得
  getAreas: async (): Promise<Area[]> => {
    const response = await api.get('/areas');
    return response.data;
  },

  // 建物一覧取得
  searchBuildings: async (params: {
    wards?: string[];
    search?: string;
    min_price?: number;
    max_price?: number;
    max_building_age?: number;
    min_total_floors?: number;
    page?: number;
    per_page?: number;
    sort_by?: string;
    sort_order?: string;
  }): Promise<{
    buildings: Array<{
      id: number;
      normalized_name: string;
      address: string | null;
      total_floors: number | null;
      built_year: number | null;
      built_month: number | null;
      construction_type: string | null;
      station_info: string | null;
      property_count: number;
      active_listings: number;
      price_range: {
        min: number | null;
        max: number | null;
        avg: number | null;
      };
      building_age: number | null;
    }>;
    total: number;
    page: number;
    per_page: number;
    total_pages: number;
  }> => {
    const response = await api.get('/buildings', { params });
    return response.data;
  },

  // 建物別物件一覧取得
  getBuildingProperties: async (buildingId: number, includeInactive: boolean = false): Promise<{
    building: any;
    properties: Property[];
    total: number;
  }> => {
    const response = await api.get(`/buildings/${buildingId}/properties`, {
      params: { include_inactive: includeInactive }
    });
    return response.data;
  },

  // 建物名サジェスト取得（エイリアス対応）
  suggestBuildings: async (query: string, limit: number = 10): Promise<Array<string | { value: string; label: string }>> => {
    const response = await api.get('/buildings/suggest', {
      params: { q: query, limit }
    });
    return response.data;
  },

  // 管理者機能
  getDuplicateBuildings: async (params?: {
    search?: string;
    min_similarity?: number;
    limit?: number;
  }): Promise<{
    duplicate_groups: Array<{
      primary: {
        id: number;
        normalized_name: string;
        address: string;
        property_count: number;
      };
      candidates: Array<{
        id: number;
        normalized_name: string;
        address: string;
        property_count: number;
        similarity: number;
      }>;
    }>;
    total_groups: number;
  }> => {
    const response = await api.get('/admin/duplicate-buildings', { params });
    return response.data;
  },

  mergeBuildings: async (primaryId: number, secondaryIds: number[]): Promise<{
    success: boolean;
    merged_count: number;
    moved_properties: number;
    primary_building: any;
  }> => {
    const response = await api.post('/admin/merge-buildings', {
      primary_id: primaryId,
      secondary_ids: secondaryIds
    });
    return response.data;
  },

  excludeBuildings: async (building1Id: number, building2Id: number, reason?: string): Promise<{
    success: boolean;
    exclusion_id?: number;
    message?: string;
  }> => {
    const response = await api.post('/admin/exclude-buildings', {
      building1_id: building1Id,
      building2_id: building2Id,
      reason
    });
    return response.data;
  },

  removeExclusion: async (exclusionId: number): Promise<{
    success: boolean;
  }> => {
    const response = await api.delete(`/admin/exclude-buildings/${exclusionId}`);
    return response.data;
  },

  getMergeHistory: async (params?: {
    limit?: number;
    offset?: number;
    include_reverted?: boolean;
  }): Promise<{
    histories: Array<{
      id: number;
      primary_building: {
        id: number;
        normalized_name: string;
      };
      secondary_building?: {
        id: number;
        normalized_name: string;
        properties_moved: number | null;
      };
      moved_properties: number;
      merge_details: any;
      created_at: string;
    }>;
    total: number;
  }> => {
    const response = await api.get('/admin/building-merge-history', { params });
    return response.data;
  },

  revertMerge: async (historyId: number): Promise<{
    success: boolean;
    message: string;
  }> => {
    const response = await api.post(`/admin/revert-property-merge/${historyId}`);
    return response.data;
  },

  // 建物統合を取り消し
  revertBuildingMerge: async (historyId: number): Promise<{
    success: boolean;
    message: string;
  }> => {
    const response = await api.post(`/admin/revert-building-merge/${historyId}`);
    return response.data;
  },

  // 建物統合履歴を削除（履歴のみ削除、統合は維持）
  deleteBuildingMergeHistory: async (historyId: number): Promise<{
    success: boolean;
    message: string;
  }> => {
    const response = await api.delete(`/admin/building-merge-history/${historyId}`);
    return response.data;
  },

  // 物件統合履歴を削除（履歴のみ削除、統合は維持）
  deletePropertyMergeHistory: async (historyId: number): Promise<{
    success: boolean;
    message: string;
  }> => {
    const response = await api.delete(`/admin/property-merge-history/${historyId}`);
    return response.data;
  },

  // 建物統合履歴を一括削除
  bulkDeleteBuildingMergeHistory: async (): Promise<{
    success: boolean;
    message: string;
    deleted_count: number;
  }> => {
    const response = await api.delete(`/admin/building-merge-history/bulk`);
    return response.data;
  },

  // 物件統合履歴を一括削除
  bulkDeletePropertyMergeHistory: async (): Promise<{
    success: boolean;
    message: string;
    deleted_count: number;
  }> => {
    const response = await api.delete(`/admin/property-merge-history/bulk`);
    return response.data;
  },

  // 建物除外履歴を一括削除
  bulkDeleteBuildingExclusions: async (): Promise<{
    success: boolean;
    message: string;
    deleted_count: number;
  }> => {
    const response = await api.delete(`/admin/building-exclusions/bulk`);
    return response.data;
  },

  // 物件除外履歴を一括削除
  bulkDeletePropertyExclusions: async (): Promise<{
    success: boolean;
    message: string;
    deleted_count: number;
  }> => {
    const response = await api.delete(`/admin/property-exclusions/bulk`);
    return response.data;
  },

  // 建物検索（統合用）
  searchBuildingsForMerge: async (query: string, limit: number = 20): Promise<{
    buildings: Array<{
      id: number;
      normalized_name: string;
      address: string;
      total_floors: number | null;
      property_count: number;
    }>;
    total: number;
  }> => {
    const response = await api.get('/admin/buildings/search', { 
      params: { query, limit } 
    });
    return response.data;
  },

  // 物件検索（統合用）
  searchPropertiesForMerge: async (query: string, limit: number = 20): Promise<{
    properties: Array<{
      id: number;
      building_id: number;
      building_name: string;
      room_number: string | null;
      floor_number: number | null;
      area: number | null;
      layout: string | null;
      direction: string | null;
      current_price: number | null;
      listing_count: number;
    }>;
    total: number;
  }> => {
    const response = await api.get('/admin/properties/search', { 
      params: { query, limit } 
    });
    return response.data;
  },

  // 物件統合
  mergeProperties: async (primaryId: number, secondaryId: number): Promise<{
    success: boolean;
    message: string;
  }> => {
    const response = await api.post('/admin/merge-properties', {
      primary_property_id: primaryId,
      secondary_property_id: secondaryId
    });
    return response.data;
  },

  // 建物除外履歴取得
  getBuildingExclusions: async (params?: {
    limit?: number;
    offset?: number;
  }): Promise<{
    exclusions: Array<{
      id: number;
      building1: {
        id: number;
        normalized_name: string;
        address: string;
        property_count: number;
      };
      building2: {
        id: number;
        normalized_name: string;
        address: string;
        property_count: number;
      };
      reason: string;
      excluded_by: string;
      created_at: string;
    }>;
    total: number;
  }> => {
    const response = await api.get('/admin/building-exclusions', { params });
    return response.data;
  },

  // 直近の価格改定・新着物件を取得
  getRecentUpdates: async (hours: number = 24): Promise<RecentUpdatesResponse> => {
    const response = await api.get('/properties/recent-updates', {
      params: { hours }
    });
    return response.data;
  },

  // 直近の価格改定・新着物件の件数のみを高速取得
  getRecentUpdatesCount: async (hours: number = 24): Promise<{
    total_price_changes: number;
    total_new_listings: number;
    hours: number;
    updated_at: string;
  }> => {
    const response = await api.get('/recent-updates-count', {
      params: { hours }
    });
    return response.data;
  },
};