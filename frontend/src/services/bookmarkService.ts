/**
 * ブックマーク機能のAPIサービス（Cookie認証）
 */

import { Bookmark, BookmarkCreate, BookmarkStatus } from '../types/property';
import { API_CONFIG } from '../config/api';

export class BookmarkService {
  /**
   * Cookie認証でfetchリクエストを送信
   */
  private static async fetchWithCredentials(url: string, options: RequestInit = {}): Promise<Response> {
    return fetch(url, {
      ...options,
      credentials: 'include',  // Cookieを自動送信
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });
  }

  /**
   * 物件をブックマークに追加
   */
  static async addBookmark(propertyId: number): Promise<Bookmark> {
    const response = await this.fetchWithCredentials(`${API_CONFIG.BASE_URL}${API_CONFIG.PATHS.BOOKMARKS}/`, {
      method: 'POST',
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
    const response = await this.fetchWithCredentials(`${API_CONFIG.BASE_URL}${API_CONFIG.PATHS.BOOKMARKS}/${propertyId}`, {
      method: 'DELETE',
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
    const response = await this.fetchWithCredentials(`${API_CONFIG.BASE_URL}${API_CONFIG.PATHS.BOOKMARKS}/`);

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
    const response = await this.fetchWithCredentials(`${API_CONFIG.BASE_URL}${API_CONFIG.PATHS.BOOKMARKS}/check/${propertyId}`);

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
      throw error;
    }
  }
}
