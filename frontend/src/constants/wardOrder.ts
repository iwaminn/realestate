/**
 * 東京23区の地価順序定義
 * 2024年の公示地価を基準に高い順に配列
 */

// 地価の高い順（左から右へ）
export const WARD_ORDER = [
  '千代田区',
  '港区',
  '中央区',
  '渋谷区',
  '新宿区',
  '文京区',
  '目黒区',
  '品川区',
  '世田谷区',
  '豊島区',
  '台東区',
  '中野区',
  '杉並区',
  '大田区',
  '江東区',
  '北区',
  '墨田区',
  '板橋区',
  '練馬区',
  '荒川区',
  '江戸川区',
  '足立区',
  '葛飾区',
] as const;

// 区名から順序インデックスを取得
export const getWardOrder = (wardName: string): number => {
  const index = WARD_ORDER.indexOf(wardName as any);
  return index === -1 ? 999 : index; // 見つからない場合は最後尾
};

// 区名配列を地価順でソート
export const sortWardsByLandPrice = <T extends { ward: string }>(wards: T[]): T[] => {
  return [...wards].sort((a, b) => {
    return getWardOrder(a.ward) - getWardOrder(b.ward);
  });
};

// 区名文字列配列を地価順でソート
export const sortWardNamesByLandPrice = (wardNames: string[]): string[] => {
  return [...wardNames].sort((a, b) => {
    return getWardOrder(a) - getWardOrder(b);
  });
};

// 東京23区のリスト（UIで使用）
export const TOKYO_WARDS = [
  { name: '千代田区', id: 'chiyoda', popular: true },
  { name: '港区', id: 'minato', popular: true },
  { name: '中央区', id: 'chuo', popular: true },
  { name: '渋谷区', id: 'shibuya', popular: true },
  { name: '新宿区', id: 'shinjuku', popular: true },
  { name: '文京区', id: 'bunkyo', popular: true },
  { name: '目黒区', id: 'meguro', popular: true },
  { name: '品川区', id: 'shinagawa', popular: true },
  { name: '世田谷区', id: 'setagaya', popular: true },
  { name: '豊島区', id: 'toshima' },
  { name: '台東区', id: 'taito' },
  { name: '中野区', id: 'nakano' },
  { name: '杉並区', id: 'suginami' },
  { name: '大田区', id: 'ota' },
  { name: '江東区', id: 'koto' },
  { name: '北区', id: 'kita' },
  { name: '墨田区', id: 'sumida' },
  { name: '板橋区', id: 'itabashi' },
  { name: '練馬区', id: 'nerima' },
  { name: '荒川区', id: 'arakawa' },
  { name: '江戸川区', id: 'edogawa' },
  { name: '足立区', id: 'adachi' },
  { name: '葛飾区', id: 'katsushika' },
];

// 人気エリア（地価上位エリア）
export const getPopularWards = () => {
  return TOKYO_WARDS.filter(ward => ward.popular);
};

// その他のエリア
export const getOtherWards = () => {
  return TOKYO_WARDS.filter(ward => !ward.popular);
};