/**
 * ブックマーク機能のAPIサービス（Cookie認証）
 */

import { Bookmark, BookmarkCreate, BookmarkStatus } from '../types/property';
import axios from '../utils/axiosConfig';

export class BookmarkService {
  /**
   * 物件をブックマークに追加
   */
  static async addBookmark(propertyId: number): Promise<Bookmark> {
    const response = await axios.post('/bookmarks/', {
      master_property_id: propertyId
    });
    return response.data;
  }

  /**
   * 物件をブックマークから削除
   */
  static async removeBookmark(propertyId: number): Promise<void> {
    await axios.delete(`/bookmarks/${propertyId}`);
  }

  /**
   * ブックマーク一覧を取得
   */
  static async getBookmarks(groupBy?: 'ward' | 'building'): Promise<any> {
    const params = groupBy ? { group_by: groupBy } : {};
    const response = await axios.get('/bookmarks/', { params });
    return response.data;
  }

  /**
   * 物件のブックマーク状態をチェック
   */
  static async checkBookmarkStatus(propertyId: number): Promise<BookmarkStatus> {
    const response = await axios.get(`/bookmarks/check/${propertyId}`);
    return response.data;
  }

  /**
   * 複数物件のブックマーク状態を一括チェック
   */
  static async checkBookmarkStatusBulk(propertyIds: number[]): Promise<{ bookmarks: { [key: string]: boolean }, requires_login: boolean }> {
    const response = await axios.post('/bookmarks/check-bulk', propertyIds);
    return response.data;
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
