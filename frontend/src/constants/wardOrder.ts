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

// 対象エリア（都心8区を扱う）
export const TARGET_WARDS = [
  { name: '千代田区', id: 'chiyoda' },
  { name: '港区', id: 'minato' },
  { name: '中央区', id: 'chuo' },
  { name: '渋谷区', id: 'shibuya' },
  { name: '新宿区', id: 'shinjuku' },
  { name: '文京区', id: 'bunkyo' },
  { name: '目黒区', id: 'meguro' },
  { name: '品川区', id: 'shinagawa' },
];

// 東京23区のリスト（現在は対象8区）
export const TOKYO_WARDS = TARGET_WARDS;

// 都心8区すべてを取得（人気エリア・その他の区別なし）
export const getAllTargetWards = () => {
  return TARGET_WARDS;
};

// 後方互換性のため維持（すべての対象エリアを返す）
export const getPopularWards = () => {
  return TARGET_WARDS;
};

// 後方互換性のため維持（空配列を返す）
export const getOtherWards = () => {
  return [];
};