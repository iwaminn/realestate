# 建物名管理システムの実装計画

## 1. 即座に実施すべき対応

### 1.1 重複建物の統合
```sql
-- 白金ザスカイE棟の重複を統合
-- ID: 361（最も多くの物件を持つ）を主建物とする
-- ID: 1665, 2326 を統合

-- 白金ザスカイ全体の整理も必要
-- ID: 1701 (白金ザスカイ) と ID: 687 (白金ザ・スカイ) の関係を確認
```

### 1.2 不適切な建物名の修正
- 「東京メトロ南北線 白金高輪駅 徒歩10分(港区)の中古マンション」のような建物名を修正
- これらはHOMESから取得した際に建物名が取得できなかった物件

## 2. 短期的な改善（1-2週間）

### 2.1 スクレイパーの改善

```python
# backend/app/scrapers/base_scraper.py の修正

def get_or_create_building(self, building_name: str, address: str = None, **kwargs):
    """建物を取得または作成（改善版）"""
    if not building_name:
        return None, None
    
    # 元の建物名を保存
    original_building_name = building_name
    
    # 比較用の正規化（最小限）
    search_key = self.get_search_key(building_name)
    
    # 既存の建物を検索
    building = self.find_existing_building(search_key, address)
    
    if not building:
        # 新規作成時は元の名前を使用
        building = Building(
            normalized_name=original_building_name,  # 元の名前を保存
            address=address,
            **kwargs
        )
        self.session.add(building)
        self.session.flush()
    
    # エイリアスとして記録（重複チェック付き）
    self.add_building_alias(
        building_id=building.id,
        alias_name=original_building_name,
        source=self.source_site
    )
    
    return building, None

def get_search_key(self, building_name: str) -> str:
    """建物検索用のキーを生成（最小限の正規化）"""
    # 全角英数字→半角
    key = jaconv.z2h(building_name, kana=False, ascii=True, digit=True)
    # スペースと記号の正規化
    key = re.sub(r'[\s　・－―]+', '', key)
    # 大文字統一
    key = key.upper()
    # 末尾の棟表記を除去（検索時のみ）
    key = re.sub(r'(E|W|N|S|東|西|南|北)?棟$', '', key)
    return key
```

### 2.2 多数決による建物名更新の強化

```python
# backend/app/utils/majority_vote_updater.py の拡張

def update_building_name_by_majority(building_id: int):
    """建物名を関連する全ての情報から多数決で決定"""
    
    # 1. BuildingAliasから集計
    alias_votes = get_alias_votes(building_id)
    
    # 2. PropertyListingのtitleからも集計（オプション）
    listing_votes = get_listing_title_votes(building_id)
    
    # 3. 重み付け投票
    weighted_votes = {}
    
    # エイリアスの投票（高い重み）
    for name, count in alias_votes.items():
        weighted_votes[name] = weighted_votes.get(name, 0) + count * 2
    
    # リスティングタイトルの投票（低い重み）
    for name, count in listing_votes.items():
        weighted_votes[name] = weighted_votes.get(name, 0) + count
    
    # 4. 最も票を集めた名前を採用
    if weighted_votes:
        best_name = max(weighted_votes.items(), key=lambda x: x[1])[0]
        
        # 5. 更新
        building = session.query(Building).filter_by(id=building_id).first()
        if building and building.normalized_name != best_name:
            logger.info(f"建物名更新: '{building.normalized_name}' → '{best_name}'")
            building.normalized_name = best_name
            session.commit()
```

## 3. 中期的な改善（1-2ヶ月）

### 3.1 データベーススキーマの拡張

```sql
-- buildingsテーブルに検索用カラムを追加
ALTER TABLE buildings ADD COLUMN search_key VARCHAR(255);
CREATE INDEX idx_buildings_search_key ON buildings(search_key);

-- building_aliasesテーブルに統計情報を追加
ALTER TABLE building_aliases ADD COLUMN occurrence_count INTEGER DEFAULT 1;
ALTER TABLE building_aliases ADD COLUMN last_seen_at TIMESTAMP DEFAULT NOW();
```

### 3.2 建物名の品質管理システム

```python
class BuildingNameQualityChecker:
    """建物名の品質をチェック"""
    
    def is_valid_building_name(self, name: str) -> bool:
        """有効な建物名かチェック"""
        # 駅名や徒歩分数が含まれていないか
        if re.search(r'(駅|徒歩\d+分)', name):
            return False
        
        # 「の中古マンション」で終わっていないか
        if name.endswith('の中古マンション'):
            return False
        
        # 最低文字数チェック
        if len(name) < 3:
            return False
        
        return True
    
    def extract_building_name_from_title(self, title: str) -> str:
        """物件タイトルから建物名を抽出"""
        # 価格情報を除去
        title = re.sub(r'\d+万円.*$', '', title)
        # 間取り情報を除去
        title = re.sub(r'\d+[LDK]+.*$', '', title)
        # 前後の空白を除去
        return title.strip()
```

## 4. 実装の優先順位

1. **最優先**: 重複建物の統合（手動またはスクリプト）
2. **高**: スクレイパーの改善（元の建物名を保持）
3. **中**: 多数決システムの強化
4. **低**: データベーススキーマの拡張

## 5. 移行時の注意点

1. **既存データの保護**
   - 手動で修正された建物名は保護する
   - 統合履歴を必ず記録する

2. **段階的な移行**
   - まず新規データから適用
   - 既存データは慎重に移行

3. **モニタリング**
   - 建物名の変更ログを記録
   - 異常な統合を検知する仕組み