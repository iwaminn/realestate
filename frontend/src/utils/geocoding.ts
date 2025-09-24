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
    const response = await axios.get(`/api/geocoding/building/${buildingId}`);
    const data = response.data;
    
    if (data && data.latitude !== undefined && data.longitude !== undefined) {
      console.log(`座標取得成功 (${data.cached ? 'キャッシュ' : 'API'}): 建物ID ${buildingId} -> lat: ${data.latitude}, lng: ${data.longitude}`);
      return { lat: data.latitude, lng: data.longitude };
    }
    
    console.warn('建物の座標を取得できませんでした:', buildingId);
    return null;
  } catch (error) {
    console.error('座標取得エラー:', error);
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
    console.log('ジオコーディング開始:', address);
    const response = await axios.post('/api/geocoding/geocode', { address });
    const data = response.data;
    
    console.log('APIレスポンス:', data);
    
    if (data && data.latitude !== undefined && data.longitude !== undefined) {
      console.log(`座標取得成功: ${address} -> lat: ${data.latitude}, lng: ${data.longitude}`);
      return { lat: data.latitude, lng: data.longitude };
    }
    
    console.warn('住所から座標を取得できませんでした:', address, data);
    return null;
  } catch (error) {
    console.error('ジオコーディングエラー:', error);
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
      const response = await axios.get(`/api/buildings/${buildingId}`);
      if (response.data && response.data.address) {
        console.log(`建物ID ${buildingId} の座標がないため、住所からジオコーディング: ${response.data.address}`);
        coords = await getCoordinatesFromAddress(response.data.address);
      }
    } catch (error) {
      console.error('建物情報の取得エラー:', error);
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
    console.log(`ハザードマップURL生成: ${hazardMapUrl}`);
    return hazardMapUrl;
  }
  
  // 座標が取得できない場合は、デフォルトのハザードマップURLを返す
  console.warn('座標が取得できなかったため、デフォルトURLを使用');
  return 'https://disaportal.gsi.go.jp/hazardmap/maps/index.html';
}

/**
 * ハザードマップのURLを生成（住所使用）
 * @param address 住所文字列
 * @returns ハザードマップのURL
 */
export async function getHazardMapUrl(address: string): Promise<string> {
  const coords = await getCoordinatesFromAddress(address);
  
  if (coords) {
    // 座標が取得できた場合は、その位置を中心としたハザードマップURLを生成
    const hazardMapUrl = `https://disaportal.gsi.go.jp/maps/index.html?ll=${coords.lat},${coords.lng}&z=15&base=pale&ls=disid_kouzui%2C0.8%7Cdisid_takashio%2C0.8%7Cdisid_doseki%2C0.8%7Cdisid_tsunami%2C0.8&disp=11111&lcd=disid_kouzui&vs=c1j0h0k0l0u0t0z0r0s0m0f1&d=l`;
    console.log(`ハザードマップURL生成: ${hazardMapUrl}`);
    return hazardMapUrl;
  }
  
  // 座標が取得できない場合は、デフォルトのハザードマップURLを返す
  console.warn('座標が取得できなかったため、デフォルトURLを使用');
  return 'https://disaportal.gsi.go.jp/hazardmap/maps/index.html';
}