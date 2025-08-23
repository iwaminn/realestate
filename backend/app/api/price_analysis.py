"""
価格分析用のヘルパー関数
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date
from collections import defaultdict


def create_unified_price_timeline(price_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    統合価格タイムラインを作成
    
    Returns:
        {
            "timeline": [
                {
                    "date": "2024-01-01",
                    "price": 5000,  # その日の代表価格（最頻値または平均）
                    "sources": {
                        "SUUMO": 5000,
                        "HOMES": 5100
                    },
                    "has_discrepancy": true
                }
            ],
            "price_changes": [  # 価格変更があった日付のみ
                {
                    "date": "2024-01-15",
                    "old_price": 5000,
                    "new_price": 4900,
                    "change_amount": -100,
                    "change_percentage": -2.0
                }
            ]
        }
    """
    
    if not price_records:
        return {"timeline": [], "price_changes": []}
    
    # 各掲載の価格履歴と開始日を整理
    listing_price_history = defaultdict(lambda: {'history': [], 'start_date': None, 'source': None})
    for record in price_records:
        if record.get('is_active', True) and record.get('price'):
            date_key = record['recorded_at'].date() if isinstance(record['recorded_at'], datetime) else record['recorded_at']
            listing_id = record.get('listing_id')
            source = record['source_site']
            price = record['price']
            
            if listing_id:
                # 価格履歴を追加
                listing_price_history[listing_id]['history'].append((date_key, price))
                listing_price_history[listing_id]['source'] = source
                
                # 掲載開始日を記録
                if 'listing_start_date' in record and record['listing_start_date']:
                    start_date = record['listing_start_date']
                    if isinstance(start_date, datetime):
                        start_date = start_date.date()
                    listing_price_history[listing_id]['start_date'] = start_date
    
    # 各掲載の履歴を日付順にソート
    for listing_id in listing_price_history:
        listing_price_history[listing_id]['history'].sort(key=lambda x: x[0])
    
    # 全日付の範囲を取得
    all_dates = set()
    for listing_data in listing_price_history.values():
        # 価格履歴の日付を追加
        all_dates.update([d for d, _ in listing_data['history']])
        # 掲載開始日も追加
        if listing_data['start_date']:
            all_dates.add(listing_data['start_date'])
    
    if not all_dates:
        return {"timeline": [], "price_changes": []}
    
    sorted_dates = sorted(all_dates)
    min_date = sorted_dates[0]
    max_date = sorted_dates[-1]
    
    # 日付ごとに各掲載の価格を集約（価格を持ち越し）
    daily_prices = {}
    
    for date_key in sorted_dates:
        daily_prices[date_key] = {}
        
        # 各掲載の価格を確認
        for listing_id, listing_data in listing_price_history.items():
            source = listing_data['source']
            start_date = listing_data['start_date']
            
            # 掲載開始日以降のみ価格を記録
            if start_date and date_key >= start_date:
                # その日以前の最新価格を取得
                price_for_date = None
                for hist_date, hist_price in listing_data['history']:
                    if hist_date <= date_key:
                        price_for_date = hist_price
                    else:
                        break
                
                # 価格履歴がない場合は、その掲載の価格を含めない（持ち越さない）
                # 重要: 掲載開始日以降でも、実際に価格記録がある日のみカウント
                has_price_on_date = any(hist_date == date_key for hist_date, _ in listing_data['history'])
                
                if price_for_date is not None and has_price_on_date:
                    # 掲載ごとにユニークなキーを作成（同じソースでも複数掲載がある場合）
                    key = f"{source}_{listing_id}"
                    daily_prices[date_key][key] = price_for_date
    
    # タイムラインを作成
    timeline = []
    sorted_dates = sorted(daily_prices.keys())
    
    for date_key in sorted_dates:
        sources = daily_prices[date_key]
        
        # その日の価格を集計
        all_prices = list(sources.values())
        unique_prices = set(all_prices)
        
        # ソース別に価格を集約（表示用）
        source_prices = {}
        for key, price in sources.items():
            source_name = key.split('_')[0]  # listing_idを除去
            if source_name not in source_prices:
                source_prices[source_name] = price
            # 同じソースで複数の価格がある場合は最小値を採用
            elif price < source_prices[source_name]:
                source_prices[source_name] = price
        
        # 代表価格を決定（最頻値、同数の場合は最小値）
        if all_prices:
            price_counts = {p: all_prices.count(p) for p in unique_prices}
            max_count = max(price_counts.values())
            most_common_prices = [p for p, c in price_counts.items() if c == max_count]
            representative_price = min(most_common_prices)
        else:
            continue  # 価格データがない日はスキップ
        
        timeline.append({
            "date": str(date_key),
            "price": representative_price,
            "sources": source_prices,  # ソース別に集約した価格
            "has_discrepancy": len(unique_prices) > 1
        })
    
    # 価格変更を検出
    price_changes = []
    prev_price = None
    
    for i, entry in enumerate(timeline):
        current_price = entry['price']
        
        if prev_price is not None and current_price != prev_price:
            change_amount = current_price - prev_price
            change_percentage = (change_amount / prev_price) * 100
            
            price_changes.append({
                "date": entry['date'],
                "old_price": prev_price,
                "new_price": current_price,
                "change_amount": change_amount,
                "change_percentage": round(change_percentage, 2)
            })
        
        prev_price = current_price
    
    # 現在価格を計算（property_listingsのcurrent_priceから直接取得）
    # price_recordsに含まれるcurrent_price情報を使用（各掲載ごと）
    current_prices_from_listings = {}
    for record in price_records:
        if record.get('is_active', True):
            listing_id = record.get('listing_id')
            # current_priceが含まれている場合は使用
            if 'current_price' in record and record['current_price']:
                # 各掲載IDごとに価格を保存（ソースごとではなく）
                if listing_id and listing_id not in current_prices_from_listings:
                    current_prices_from_listings[listing_id] = record['current_price']
    
    # current_priceが取得できない場合は、最新の履歴から計算
    if not current_prices_from_listings:
        current_prices = {}
        for record in price_records:
            if record.get('is_active', True) and record.get('price'):
                source = record['source_site']
                # 各ソースの最新価格を保持
                if source not in current_prices or record['recorded_at'] > current_prices[source]['recorded_at']:
                    current_prices[source] = {
                        'price': record['price'],
                        'recorded_at': record['recorded_at']
                    }
        
        if current_prices:
            active_prices = [p['price'] for p in current_prices.values()]
            price_counts = {p: active_prices.count(p) for p in set(active_prices)}
            max_count = max(price_counts.values())
            most_common_prices = [p for p, c in price_counts.items() if c == max_count]
            current_price = min(most_common_prices)  # 同数の場合は最小値
        else:
            current_price = timeline[-1]['price'] if timeline else None
    else:
        # property_listingsのcurrent_priceから多数決（各掲載ごとに1票）
        active_prices = list(current_prices_from_listings.values())
        price_counts = {p: active_prices.count(p) for p in set(active_prices)}
        max_count = max(price_counts.values())
        most_common_prices = [p for p, c in price_counts.items() if c == max_count]
        current_price = min(most_common_prices)  # 同数の場合は最小値

    return {
        "timeline": timeline,
        "price_changes": price_changes,
        "summary": {
            "initial_price": timeline[0]['price'] if timeline else None,
            "current_price": current_price,
            "lowest_price": min(entry['price'] for entry in timeline) if timeline else None,
            "highest_price": max(entry['price'] for entry in timeline) if timeline else None,
            "total_change": current_price - timeline[0]['price'] if timeline and current_price else 0,
            "discrepancy_count": sum(1 for entry in timeline if entry['has_discrepancy'])
        }
    }


def analyze_source_price_consistency(price_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    ソース間の価格一貫性を分析
    
    Returns:
        {
            "consistency_score": 0.95,  # 0-1の一貫性スコア
            "discrepancies": [
                {
                    "date": "2024-01-01",
                    "sources": {"SUUMO": 5000, "HOMES": 5100},
                    "max_difference": 100,
                    "max_difference_percentage": 2.0
                }
            ],
            "source_statistics": {
                "SUUMO": {
                    "avg_price": 5000,
                    "price_changes": 3,
                    "last_update": "2024-03-01"
                }
            }
        }
    """
    
    # 日付ごとにソース別価格を収集
    daily_source_prices = defaultdict(dict)
    source_stats = defaultdict(lambda: {
        "prices": [],
        "updates": [],
        "price_changes": 0,
        "last_price": None
    })
    
    for record in price_records:
        if not record.get('is_active', True):
            continue
            
        date_key = record['recorded_at'].date() if isinstance(record['recorded_at'], datetime) else record['recorded_at']
        source = record['source_site']
        price = record['price']
        
        daily_source_prices[date_key][source] = price
        
        # ソース別統計
        stats = source_stats[source]
        stats['prices'].append(price)
        stats['updates'].append(date_key)
        
        if stats['last_price'] and stats['last_price'] != price:
            stats['price_changes'] += 1
        stats['last_price'] = price
    
    # 価格差異を分析
    discrepancies = []
    total_days = 0
    consistent_days = 0
    
    for date_key, sources in daily_source_prices.items():
        if len(sources) > 1:
            total_days += 1
            prices = list(sources.values())
            min_price = min(prices)
            max_price = max(prices)
            
            if min_price == max_price:
                consistent_days += 1
            else:
                max_diff_pct = ((max_price - min_price) / min_price) * 100
                discrepancies.append({
                    "date": str(date_key),
                    "sources": dict(sources),
                    "max_difference": max_price - min_price,
                    "max_difference_percentage": round(max_diff_pct, 2)
                })
    
    # 一貫性スコアを計算
    consistency_score = consistent_days / total_days if total_days > 0 else 1.0
    
    # ソース別統計を集計
    source_statistics = {}
    for source, stats in source_stats.items():
        if stats['prices']:
            source_statistics[source] = {
                "avg_price": round(sum(stats['prices']) / len(stats['prices'])),
                "price_changes": stats['price_changes'],
                "last_update": str(max(stats['updates'])) if stats['updates'] else None,
                "total_updates": len(stats['updates'])
            }
    
    return {
        "consistency_score": round(consistency_score, 3),
        "discrepancies": sorted(discrepancies, key=lambda x: x['max_difference_percentage'], reverse=True),
        "source_statistics": source_statistics
    }