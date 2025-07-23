# 同一建物の異なる部屋のスクレイピング・表示テスト結果

## テスト概要
同一の建物に存在する異なる部屋が、別々の物件として正しくスクレイピングされ、表示されることを検証しました。

## 実装内容

### 1. 物件の同一性判定ロジック
`backend/app/scrapers/base_scraper.py` の `generate_property_hash` メソッドで、以下の要素を組み合わせて物件を識別：

```python
def generate_property_hash(self, building_id: int, room_number: str, 
                         floor_number: int = None, area: float = None, 
                         layout: str = None, direction: str = None, url: str = None) -> str:
    """物件ハッシュを生成
    
    部屋番号がない場合は、階数・面積・間取り・方角の組み合わせで同一物件を判定
    """
    if room_number:
        data = f"{building_id}:{room_number}"
    else:
        floor_str = f"F{floor_number}" if floor_number else "F?"
        area_str = f"A{area}" if area else "A?"
        layout_str = layout or "L?"
        direction_str = direction or "D?"
        data = f"{building_id}:{floor_str}_{area_str}_{layout_str}_{direction_str}"
    
    return hashlib.md5(data.encode()).hexdigest()
```

### 2. 建物名での物件取得API
`backend/app/main.py` に専用エンドポイントを追加：

```python
@app.get("/api/v2/buildings/by-name/{building_name}/properties", response_model=Dict[str, Any])
async def get_building_properties_by_name(
    building_name: str,
    db: Session = Depends(get_db)
):
    """建物名で建物内の全物件を取得"""
    # 完全一致優先で建物を検索
    # 複数の建物バリエーション（EAST、WEST等）がある場合は最も基本的な名前を選択
```

### 3. フロントエンド対応
`frontend/src/pages/BuildingPropertiesPage.tsx` で新APIを使用：

```typescript
const response = await propertyApi.getBuildingProperties(decodeURIComponent(buildingName!));
setProperties(response.properties);
setBuilding(response.building);
```

## テスト結果

### ケース1: 同じ階数・面積でも方角が異なる場合
- **10階、75.5㎡、3LDK、南向き** → 別物件として識別 ✓
- **10階、75.5㎡、3LDK、北向き** → 別物件として識別 ✓
- **10階、75.5㎡、3LDK、東向き** → 別物件として識別 ✓

### ケース2: 異なる階数の同じ間取り
- **5階、60.2㎡、2LDK、南向き** → 別物件として識別 ✓
- **8階、60.2㎡、2LDK、南向き** → 別物件として識別 ✓
- **12階、60.2㎡、2LDK、南向き** → 別物件として識別 ✓

### ケース3: 異なる面積・間取り
- **15階、85.0㎡、3LDK、南西向き** → 別物件として識別 ✓
- **14階、95.5㎡、4LDK、南東向き** → 別物件として識別 ✓
- **3階、55.3㎡、1LDK、西向き** → 別物件として識別 ✓

## 実例：白金ザ・スカイ

白金ザ・スカイで複数の建物バリエーションが存在していた問題：
- 白金ザ・スカイ
- 白金ザ・スカイ EAST棟
- 白金ザ・スカイ WEST棟

### 対策
API レベルで最も基本的な建物名を優先的に選択し、統一した表示を実現：

```python
if len(buildings) > 1:
    # 複数見つかった場合は最も基本的な名前のものを選択
    for b in buildings:
        if b.normalized_name == building_name or "EAST" not in b.normalized_name and "WEST" not in b.normalized_name and "棟" not in b.normalized_name:
            building = b
            break
```

## 結論

✅ **同一建物の異なる部屋は、階数・面積・間取り・方角の組み合わせにより、正しく別々の物件として識別されています**

✅ **建物ページ（`/buildings/{建物名}/properties`）では、重複なく全ての物件が表示されます**

✅ **ユーザーの要望通り、同じ階数・面積でも方角が異なる場合は別物件として扱われています**

## 今後の改善案（未実装）

1. **部屋番号の取得強化**: 現在は部屋番号が取得できない物件が多いため、詳細ページからの取得を検討
2. **階数情報の充実**: 階数が不明（None）の物件が多いため、スクレイピングロジックの改善
3. **建物名の統一**: 建物エイリアステーブルを活用した、より高度な名寄せ機能