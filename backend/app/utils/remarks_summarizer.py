"""
物件備考の要約機能
各サイトの備考を集約して要約を作成
"""

from typing import List, Optional
import re


class RemarksSummarizer:
    """物件備考の要約クラス"""
    
    @staticmethod
    def summarize_remarks(remarks_list: List[str]) -> Optional[str]:
        """
        複数の備考を要約
        
        Args:
            remarks_list: 各サイトからの備考リスト
            
        Returns:
            要約された備考文字列
        """
        if not remarks_list:
            return None
        
        # 空文字列を除外
        remarks = [r.strip() for r in remarks_list if r and r.strip()]
        if not remarks:
            return None
        
        # 重複する情報を統合
        unified_info = {}
        
        # よくある項目を抽出
        patterns = {
            'ペット': r'ペット(飼育)?(可|不可|相談|OK|NG)',
            '楽器': r'楽器(演奏)?(可|不可|相談|OK|NG)',
            '事務所利用': r'事務所(利用|使用)?(可|不可|相談|OK|NG)',
            'SOHO': r'SOHO(利用|使用)?(可|不可|相談|OK|NG)',
            '駐車場': r'駐車場(有|無|空き有|空き無|要確認)',
            '駐輪場': r'駐輪場(有|無|空き有|空き無|要確認)',
            'バイク置場': r'バイク置場(有|無|空き有|空き無|要確認)',
            '宅配ボックス': r'宅配ボックス(有|無|設置)',
            'オートロック': r'オートロック(有|無)',
            '管理人': r'管理人(常駐|日勤|巡回|無)',
            'エレベーター': r'エレベーター(有|無|(\d+)基)',
        }
        
        # 各備考から情報を抽出
        for remark in remarks:
            for key, pattern in patterns.items():
                match = re.search(pattern, remark, re.IGNORECASE)
                if match:
                    # 同じ項目で異なる値がある場合は「要確認」とする
                    if key in unified_info and unified_info[key] != match.group(0):
                        unified_info[key] = f"{key}要確認"
                    else:
                        unified_info[key] = match.group(0)
        
        # その他の重要な情報を抽出（パターンにマッチしない情報）
        other_info = []
        for remark in remarks:
            # パターンにマッチしない部分を抽出
            remaining = remark
            for pattern in patterns.values():
                remaining = re.sub(pattern, '', remaining, flags=re.IGNORECASE)
            
            # 残った情報で重要そうなものを追加
            remaining = remaining.strip()
            if remaining and len(remaining) > 10:  # 短すぎる情報は除外
                # 重複チェック
                is_duplicate = False
                for info in other_info:
                    if remaining in info or info in remaining:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    other_info.append(remaining)
        
        # 要約を構築
        summary_parts = []
        
        # 統合された情報を追加
        if unified_info:
            summary_parts.extend(unified_info.values())
        
        # その他の情報を追加（最大3つまで）
        if other_info:
            summary_parts.extend(other_info[:3])
        
        # 要約を結合
        if summary_parts:
            return '。'.join(summary_parts) + '。'
        
        # 要約できない場合は最初の備考を返す
        return remarks[0] if remarks else None
    
    @staticmethod
    def merge_remarks(existing_summary: Optional[str], new_remark: str) -> str:
        """
        既存の要約に新しい備考を追加
        
        Args:
            existing_summary: 既存の要約
            new_remark: 新しい備考
            
        Returns:
            更新された要約
        """
        if not existing_summary:
            return new_remark
        
        if not new_remark:
            return existing_summary
        
        # 既存の要約と新しい備考を結合して再要約
        return RemarksSummarizer.summarize_remarks([existing_summary, new_remark])