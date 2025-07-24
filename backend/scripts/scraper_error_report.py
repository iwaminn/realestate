#!/usr/bin/env python3
"""
スクレイパーエラーレポート生成スクリプト
エラーログを分析して人間が読みやすいレポートを生成
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import argparse


def load_error_logs(log_path: str = "logs/scraper_errors.json"):
    """エラーログを読み込む"""
    path = Path(log_path)
    if not path.exists():
        print(f"エラーログファイルが見つかりません: {log_path}")
        return []
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"エラーログの読み込みに失敗しました: {e}")
        return []


def analyze_errors(errors, hours=24):
    """エラーを分析してレポートを生成"""
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    # 最近のエラーのみをフィルタ
    recent_errors = [
        e for e in errors
        if datetime.fromisoformat(e['timestamp']) > cutoff_time
    ]
    
    if not recent_errors:
        return None
    
    # スクレイパー別の集計
    scraper_stats = defaultdict(lambda: {
        'total': 0,
        'by_type': defaultdict(int),
        'by_phase': defaultdict(int),
        'unique_urls': set(),
        'unique_buildings': set()
    })
    
    # エラーパターンの集計
    error_patterns = defaultdict(list)
    validation_errors_count = defaultdict(int)
    missing_selectors_count = defaultdict(int)
    
    for error in recent_errors:
        scraper = error.get('scraper', 'unknown')
        error_type = error.get('error_type', 'unknown')
        phase = error.get('phase', 'unknown')
        
        # 基本統計
        scraper_stats[scraper]['total'] += 1
        scraper_stats[scraper]['by_type'][error_type] += 1
        scraper_stats[scraper]['by_phase'][phase] += 1
        
        # URLと建物名を記録
        if error.get('url'):
            scraper_stats[scraper]['unique_urls'].add(error['url'])
        if error.get('building_name'):
            scraper_stats[scraper]['unique_buildings'].add(error['building_name'])
        
        # エラーメッセージでグループ化
        if error.get('error_message'):
            error_patterns[error['error_message'][:100]].append(error)
        
        # バリデーションエラーの詳細
        if error_type == 'validation' and error.get('validation_errors'):
            for val_error in error['validation_errors']:
                validation_errors_count[val_error] += 1
        
        # パースエラーのセレクタ
        if error_type == 'parsing' and error.get('missing_selectors'):
            for selector in error['missing_selectors']:
                missing_selectors_count[selector] += 1
    
    return {
        'period': {
            'hours': hours,
            'start': cutoff_time.isoformat(),
            'end': datetime.now().isoformat()
        },
        'total_errors': len(recent_errors),
        'scraper_stats': dict(scraper_stats),
        'error_patterns': dict(error_patterns),
        'validation_errors': dict(validation_errors_count),
        'missing_selectors': dict(missing_selectors_count)
    }


def generate_report(analysis):
    """分析結果から人間が読みやすいレポートを生成"""
    if not analysis:
        return "指定期間内にエラーはありませんでした。"
    
    report = []
    report.append("=" * 60)
    report.append("スクレイパーエラーレポート")
    report.append("=" * 60)
    report.append(f"期間: {analysis['period']['hours']}時間")
    report.append(f"総エラー数: {analysis['total_errors']}")
    report.append("")
    
    # スクレイパー別のサマリー
    report.append("【スクレイパー別サマリー】")
    for scraper, stats in analysis['scraper_stats'].items():
        report.append(f"\n{scraper}:")
        report.append(f"  総エラー数: {stats['total']}")
        report.append(f"  影響を受けたURL数: {len(stats['unique_urls'])}")
        report.append(f"  影響を受けた建物数: {len(stats['unique_buildings'])}")
        
        # エラータイプ別
        report.append("  エラータイプ:")
        for error_type, count in sorted(stats['by_type'].items(), key=lambda x: x[1], reverse=True):
            report.append(f"    - {error_type}: {count}件")
        
        # フェーズ別
        report.append("  処理フェーズ:")
        for phase, count in sorted(stats['by_phase'].items(), key=lambda x: x[1], reverse=True):
            report.append(f"    - {phase}: {count}件")
    
    # バリデーションエラーの詳細
    if analysis['validation_errors']:
        report.append("\n【バリデーションエラー詳細】")
        for error, count in sorted(analysis['validation_errors'].items(), key=lambda x: x[1], reverse=True):
            report.append(f"  - {error}: {count}件")
    
    # HTMLセレクタの問題
    if analysis['missing_selectors']:
        report.append("\n【HTMLセレクタの問題】")
        report.append("以下のセレクタが見つかりませんでした（サイト構造が変更された可能性があります）:")
        for selector, count in sorted(analysis['missing_selectors'].items(), key=lambda x: x[1], reverse=True)[:10]:
            report.append(f"  - {selector}: {count}件")
    
    # 頻出エラーパターン
    report.append("\n【頻出エラーパターン】")
    sorted_patterns = sorted(analysis['error_patterns'].items(), key=lambda x: len(x[1]), reverse=True)[:5]
    for i, (pattern, errors) in enumerate(sorted_patterns, 1):
        report.append(f"{i}. {pattern}... ({len(errors)}件)")
        # 最初の例を表示
        if errors:
            example = errors[0]
            if example.get('url'):
                report.append(f"   例: {example['url']}")
    
    return "\n".join(report)


def export_problem_urls(errors, output_file="problem_urls.txt", hours=24):
    """問題のあるURLをエクスポート"""
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    recent_errors = [
        e for e in errors
        if datetime.fromisoformat(e['timestamp']) > cutoff_time
    ]
    
    # URLごとにエラーを集計
    url_errors = defaultdict(list)
    for error in recent_errors:
        if error.get('url'):
            url_errors[error['url']].append(error)
    
    # エラーが多い順にソート
    sorted_urls = sorted(url_errors.items(), key=lambda x: len(x[1]), reverse=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"問題のあるURL一覧（過去{hours}時間）\n")
        f.write("=" * 60 + "\n\n")
        
        for url, errors in sorted_urls:
            f.write(f"URL: {url}\n")
            f.write(f"エラー数: {len(errors)}\n")
            
            # エラータイプの集計
            error_types = defaultdict(int)
            for error in errors:
                error_types[error.get('error_type', 'unknown')] += 1
            
            f.write("エラータイプ: ")
            f.write(", ".join([f"{t}({c})" for t, c in error_types.items()]))
            f.write("\n")
            
            # 最新のエラーメッセージ
            latest_error = max(errors, key=lambda x: x['timestamp'])
            if latest_error.get('error_message'):
                f.write(f"最新エラー: {latest_error['error_message']}\n")
            
            f.write("\n")
    
    print(f"問題のあるURLを {output_file} にエクスポートしました。")


def main():
    parser = argparse.ArgumentParser(description='スクレイパーエラーレポートを生成')
    parser.add_argument('--hours', type=int, default=24, help='分析対象の時間範囲（デフォルト: 24時間）')
    parser.add_argument('--export-urls', action='store_true', help='問題のあるURLをファイルにエクスポート')
    parser.add_argument('--json', action='store_true', help='JSON形式でレポートを出力')
    
    args = parser.parse_args()
    
    # エラーログを読み込む
    errors = load_error_logs()
    
    if not errors:
        print("エラーログが見つかりません。")
        return
    
    # エラーを分析
    analysis = analyze_errors(errors, hours=args.hours)
    
    if args.json:
        # JSON形式で出力
        print(json.dumps(analysis, ensure_ascii=False, indent=2, default=str))
    else:
        # 人間が読みやすい形式で出力
        report = generate_report(analysis)
        print(report)
    
    # URLのエクスポート
    if args.export_urls:
        export_problem_urls(errors, hours=args.hours)
    
    # 推奨事項
    if analysis and analysis['missing_selectors']:
        print("\n【推奨事項】")
        print("HTMLセレクタが頻繁に見つからない場合は、サイトの構造が変更された可能性があります。")
        print("該当するスクレイパーのセレクタを確認・更新してください。")


if __name__ == "__main__":
    main()