/**
 * ブックマーク機能のAPIサービス
 */

import { Bookmark, BookmarkCreate, BookmarkStatus } from '../types/property';
import { API_CONFIG } from '../config/api';

export class BookmarkService {
  /**
   * 認証ヘッダーを取得
   */
  private static getAuthHeaders(): Record<string, string> {
    const token = localStorage.getItem('userToken');
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    return headers;
  }

  /**
   * 物件をブックマークに追加
   */
  static async addBookmark(propertyId: number): Promise<Bookmark> {
    const response = await fetch(`${API_CONFIG.BASE_URL}${API_CONFIG.PATHS.BOOKMARKS}/`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify({
        master_property_id: propertyId
      }),
    });

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('ログインが必要です');
      }
      if (response.status === 409) {
        throw new Error('既にブックマークされています');
      }
      if (response.status === 404) {
        throw new Error('物件が見つかりません');
      }
      throw new Error('ブックマークの追加に失敗しました');
    }

    return response.json();
  }

  /**
   * 物件をブックマークから削除
   */
  static async removeBookmark(propertyId: number): Promise<void> {
    const response = await fetch(`${API_CONFIG.BASE_URL}${API_CONFIG.PATHS.BOOKMARKS}/${propertyId}`, {
      method: 'DELETE',
      headers: this.getAuthHeaders(),
    });

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('ログインが必要です');
      }
      if (response.status === 404) {
        throw new Error('ブックマークが見つかりません');
      }
      throw new Error('ブックマークの削除に失敗しました');
    }
  }

  /**
   * ブックマーク一覧を取得
   */
  static async getBookmarks(): Promise<Bookmark[]> {
    const response = await fetch(`${API_CONFIG.BASE_URL}${API_CONFIG.PATHS.BOOKMARKS}/`, {
      headers: this.getAuthHeaders(),
    });

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('ログインが必要です');
      }
      throw new Error('ブックマーク一覧の取得に失敗しました');
    }

    return response.json();
  }

  /**
   * 物件のブックマーク状態をチェック
   */
  static async checkBookmarkStatus(propertyId: number): Promise<BookmarkStatus> {
    const response = await fetch(`${API_CONFIG.BASE_URL}${API_CONFIG.PATHS.BOOKMARKS}/check/${propertyId}`, {
      headers: this.getAuthHeaders(),
    });

    if (!response.ok) {
      throw new Error('ブックマーク状態の確認に失敗しました');
    }

    return response.json();
  }

  /**
   * ブックマークのトグル（追加/削除を自動判定）
   */
  static async toggleBookmark(propertyId: number): Promise<{ action: 'added' | 'removed', bookmark?: Bookmark }> {
    try {
      // まず現在の状態をチェック
      const status = await this.checkBookmarkStatus(propertyId);
      
      if (status.is_bookmarked) {
        // ブックマークされている場合は削除
        await this.removeBookmark(propertyId);
        return { action: 'removed' };
      } else {
        // ブックマークされていない場合は追加
        const bookmark = await this.addBookmark(propertyId);
        return { action: 'added', bookmark };
      }
    } catch (error) {
      console.error('ブックマークのトグル操作に失敗:', error);
      throw error;
    }
  }
}