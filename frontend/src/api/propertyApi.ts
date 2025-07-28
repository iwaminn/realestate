import axios from 'axios';
import type { Property, PropertyDetail, SearchParams, ApiResponse, Area, Statistics } from '../types/property';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const propertyApi = {
  // 物件一覧検索
  searchProperties: async (params: SearchParams): Promise<ApiResponse<Property>> => {
    const response = await api.get('/v2/properties', { params });
    return response.data;
  },

  // 物件詳細取得
  getPropertyDetail: async (id: number): Promise<PropertyDetail> => {
    const response = await api.get(`/v2/properties/${id}`);
    return response.data;
  },

  // 統計情報取得
  getStatistics: async (): Promise<Statistics> => {
    const response = await api.get('/v2/stats');
    return response.data;
  },

  // エリア一覧取得
  getAreas: async (): Promise<{ areas: Area[] }> => {
    const response = await api.get('/v2/areas');
    return response.data;
  },

  // 建物別物件一覧取得
  getBuildingProperties: async (buildingId: number, includeInactive: boolean = false): Promise<{
    building: any;
    properties: Property[];
    total: number;
  }> => {
    console.log('[propertyApi] getBuildingProperties called with:', {
      buildingId,
      includeInactive,
      params: { include_inactive: includeInactive }
    });
    const response = await api.get(`/v2/buildings/${buildingId}/properties`, {
      params: { include_inactive: includeInactive }
    });
    console.log('[propertyApi] Response properties count:', response.data.properties?.length);
    return response.data;
  },

  // 建物名サジェスト取得
  suggestBuildings: async (query: string, limit: number = 10): Promise<string[]> => {
    const response = await api.get('/v2/buildings/suggest', {
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
    include_reverted?: boolean;
  }): Promise<{
    histories: Array<{
      id: number;
      primary_building: {
        id: number;
        normalized_name: string;
      };
      merged_building_ids: number[];
      moved_properties: number;
      merge_details: any;
      created_at: string;
      reverted_at: string | null;
      reverted_by: string | null;
    }>;
    total: number;
  }> => {
    const response = await api.get('/admin/merge-history', { params });
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
};