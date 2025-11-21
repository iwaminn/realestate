/**
 * 住所から座標を取得するユーティリティ
 * バックエンドAPIを経由して座標を取得（サーバー側でキャッシュ）
 */

import axios from './axiosConfig';

/**
 * 建物IDから座標を取得（バックエンドAPI経由）
 * @param buildingId 建物ID
 * @returns 緯度・経度のオブジェクト、または取得失敗時はnull
 */
export async function getCoordinatesFromBuilding(buildingId: number): Promise<{ lat: number; lng: number } | null> {
  try {
    const response = await axios.get(`/geocoding/building/${buildingId}`);
    const data = response.data;
    
    if (data && data.latitude !== undefined && data.longitude !== undefined) {
      return { lat: data.latitude, lng: data.longitude };
    }
    return null;
  } catch (error) {
    return null;
  }
}

/**
 * 住所から座標を取得（バックエンドAPI経由）
 * @param address 住所文字列
 * @returns 緯度・経度のオブジェクト、または取得失敗時はnull
 */
export async function getCoordinatesFromAddress(address: string): Promise<{ lat: number; lng: number } | null> {
  try {
    const response = await axios.post('/geocoding/geocode', { address });
    const data = response.data;
    
    if (data && data.latitude !== undefined && data.longitude !== undefined) {
      return { lat: data.latitude, lng: data.longitude };
    }
    return null;
  } catch (error) {
    return null;
  }
}

/**
 * ハザードマップのURLを生成（建物ID使用）
 * @param buildingId 建物ID
 * @returns ハザードマップのURL
 */
export async function getHazardMapUrlFromBuilding(buildingId: number): Promise<string> {
  // まず建物の座標を取得
  let coords = await getCoordinatesFromBuilding(buildingId);
  
  // 座標が取得できない場合、住所からジオコーディングを試みる
  if (!coords) {
    try {
      const response = await axios.get(`/buildings/${buildingId}`);
      if (response.data && response.data.address) {
        coords = await getCoordinatesFromAddress(response.data.address);
      }
    } catch (error) {
    }
  }
  
  if (coords) {
    // 座標が取得できた場合は、その位置を中心としたハザードマップURLを生成
    // ズームレベル15で表示（地域全体が見える適度な詳細度）
    // 重要なハザード情報レイヤーを有効化：
    // - disid_kouzui: 洪水浸水想定区域（最大規模）
    // - disid_takashio: 高潮浸水想定区域
    // - disid_doseki: 土砂災害警戒区域
    // - disid_tsunami: 津波浸水想定区域
    const hazardMapUrl = `https://disaportal.gsi.go.jp/maps/index.html?ll=${coords.lat},${coords.lng}&z=15&base=pale&ls=disid_kouzui%2C0.8%7Cdisid_takashio%2C0.8%7Cdisid_doseki%2C0.8%7Cdisid_tsunami%2C0.8&disp=11111&lcd=disid_kouzui&vs=c1j0h0k0l0u0t0z0r0s0m0f1&d=l`;
    return hazardMapUrl;
  }

  // 座標が取得できない場合は、デフォルトのハザードマップURLを返す
  // 注: 国土地理院のハザードマップポータルサイトは #address= 形式をサポートしていないため
  return 'https://disaportal.gsi.go.jp/maps/index.html?base=pale&ls=disid_kouzui%2C0.8%7Cdisid_takashio%2C0.8%7Cdisid_doseki%2C0.8%7Cdisid_tsunami%2C0.8&disp=11111&lcd=disid_kouzui&vs=c1j0h0k0l0u0t0z0r0s0m0f1&d=l';
}

/**
 * ハザードマップのURLを生成（住所使用）
 * @param address 住所文字列
 * @returns ハザードマップのURL
 */
export async function getHazardMapUrl(address: string): Promise<string> {
  // 座標取得を試みる
  try {
    const coords = await getCoordinatesFromAddress(address);

    if (coords) {
      // 座標が取得できた場合は、その位置を中心としたハザードマップURLを生成
      const hazardMapUrl = `https://disaportal.gsi.go.jp/maps/index.html?ll=${coords.lat},${coords.lng}&z=15&base=pale&ls=disid_kouzui%2C0.8%7Cdisid_takashio%2C0.8%7Cdisid_doseki%2C0.8%7Cdisid_tsunami%2C0.8&disp=11111&lcd=disid_kouzui&vs=c1j0h0k0l0u0t0z0r0s0m0f1&d=l`;
      return hazardMapUrl;
    }
  } catch (error) {
    // 座標取得エラーは無視してデフォルトURLにフォールバック
  }

  // 座標が取得できない場合は、デフォルトのハザードマップURLを返す
  // 注: 国土地理院のハザードマップポータルサイトは #address= 形式をサポートしていないため
  return 'https://disaportal.gsi.go.jp/maps/index.html?base=pale&ls=disid_kouzui%2C0.8%7Cdisid_takashio%2C0.8%7Cdisid_doseki%2C0.8%7Cdisid_tsunami%2C0.8&disp=11111&lcd=disid_kouzui&vs=c1j0h0k0l0u0t0z0r0s0m0f1&d=l';
}