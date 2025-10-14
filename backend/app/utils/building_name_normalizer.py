"""
建物名正規化の共通モジュール
base_scraper.pyから正規化ロジックを抽出して共通化
"""

import re
import jaconv


"""
建物名の正規化のための汎用関数群

このファイルは建物名の正規化のための標準的な関数を提供します。
スクレイパー、API、その他のユーティリティで広く使用されています。

主な関数:
- normalize_building_name: 表示用の建物名正規化（中点は保持）
- canonicalize_building_name: 検索用の建物名正規化（中点を削除）
- extract_room_number: 建物名から部屋番号を抽出
"""

def remove_ad_text_from_building_name(ad_text: str) -> str:
    """
    広告テキストから建物名を抽出する（広告文除去）
    純粋に広告文除去処理のみを実行し、判定は行わない
    
    Args:
        ad_text: 広告文を含む可能性のある建物名テキスト
        
    Returns:
        広告文を除去した建物名
    """
    import unicodedata
    
    if not ad_text:
        return ad_text

    original_text = ad_text.strip()
    if not original_text:
        return ""

    # 統一された広告文除去処理
    if not original_text or not original_text.strip():
        return ""

    current_text = original_text.strip()

    # Step 0: 全角英数記号を半角に統一（パターンマッチングの簡略化のため）
    current_text = unicodedata.normalize('NFKC', current_text)

    # Step 1: 全文レベルでの階数・方角情報除去
    WING_NAMES = r'[A-Z東西南北本新旧]'

    # 棟名保持パターン（棟名を保持して階数のみ除去）
    BUILDING_WING_PATTERN = rf'({WING_NAMES}棟)\s*\d+階'
    current_text = re.sub(BUILDING_WING_PATTERN, r'\1', current_text)

    # Step 1.5: パーセンテージ表記を削除（記号削除前に実行）
    percentage_pattern = r'[0-9]+\.?[0-9]*%'
    current_text = re.sub(percentage_pattern, ' ', current_text)

    # Step 1.5.5: スラッシュと&の処理
    # 建物名に使われる可能性があるため、スペース変換はせず、
    # 後続の is_word_ad 関数内で分割して判定する

    # Step 1.5.6: 連続した広告文パターンを前処理で削除（ワード分割前）
    # 「の中古物件情報」など、助詞で連結されているため単語分割で処理できないパターン
    current_text = re.sub(r'の中古物件情報$', '', current_text).strip()

    # 広告文+の+広告文のパターンを削除（例：「高層階の南西角部屋」）
    floor_ad_pattern = r'(高層階|低層階|最上階|角部屋|角住戸|[南北東西]{1,2}向き|(南西|南東|北西|北東|東南|西南|東北|西北)角(部屋|住戸))'
    current_text = re.sub(rf'{floor_ad_pattern}の{floor_ad_pattern}', '', current_text)
    
    # 広告文パターンの定義
    base_ad_patterns = [
        # 内見・見学関連
        '内見可能?', '内覧可能?', '見学可能?', '見学予約可', '予約可',
        '予約制内覧会.*', '内覧会実施.*',
        'ネット見学.*', 'オンライン見学.*',
        'プレゼント.*', 'キャンペーン.*',
        # 状態・品質
        'リノベーション済み?', 'リフォーム済み?', 'リノベ.*',
        'フルリフォーム済み?', 'フルリノベーション済み?',
        'フルリノベ',  # 「フルリノベ」単体
        r'\d{4}年[リフォームリノベ].*',  # 「2022年フルリフォーム済」など
        '新築未入居', '新築物件', '新築住戸', '新築', '中古', '築浅', 'リフォーム中古',
        '美品', '内装リフォーム済',
        '売主.*',
        # 物件タイプ・状態の接頭辞
        r'(OC|投資|オーナー.*チェンジ)\s*物件',  # OC物件、投資物件、オーナーチェンジ物件（スペース対応）
        'OC',  # OC単体（オーナーチェンジの略語）
        '物件',  # 物件単体
        'の中古物件情報',  # 「〜の中古物件情報」パターン
        '旧称',  # 旧称
        # 築年数・年号
        r'築\d+年', r'\d{4}年築', r'令和\d+年築', r'\d{4}年', r'\d+年築',
        # 日付パターン
        r'\d+/\d+.*', r'\d+月\d+日.*', r'\d+/\d+', r'\d+月\d+日',
        # 手数料・価格
        '仲介手数料無料', '手数料無料', '手数料.*', '仲介料.*',
        '諸費用.*', '企画.*',
        '弊社限定公開', '限定公開', '独占公開', '新規物件', '新価格',
        '弊社.*', '当社.*', '払う.*', '勿体無い.*', '勿体ない.*', 'お得.*',
        # 価格情報
        r'\d+億\d+万円', r'\d+億円', r'\d+万円', r'\d+円',
        r'\d+億\d+千\d+百万円', r'\d+千\d+百万円', r'\d+億\d+千万円',
        r'\d+\.\d+億円', r'\d+\.\d+万円',
        r'\d+億\d+万円~\d+億\d+万円', r'\d+万円~\d+万円', r'\d+億円~\d+億円',
        '価格相談', '値下げ', '価格改定', 'お買い得',
        # 駅・アクセス
        r'駅近',
        r'徒歩\d+分',  # 単独の「徒歩〜分」
        r'駅\d+分',  # 「駅8分」「駅10分」など（徒歩なし）
        r'[ぁ-んァ-ヶ一-龥々ー\d]+駅\d+分',  # 「西新宿5丁目駅4分」など（駅名+駅+数字+分）
        r'[ぁ-んァ-ヶ一-龥々ー]+駅\s*(から|まで)?\s*徒歩\s*\d+分',  # 「〜駅(から|まで)?徒歩〜分」を厳密に
        r'[ぁ-んァ-ヶ一-龥々ー]+徒歩圏内',  # 「〜徒歩圏内」
        r'[ぁ-んァ-ヶ一-龥々ー]+\d+分',  # 「渋谷11分」「田町10分」など（地名+数字+分）
        r'\d+分',  # 「10分」など（数字+分単体）
        # 路線名パターン（主要鉄道会社を統合）
        r'(JR|東京メトロ|都営|東急|小田急|京王|西武|東武|京急|相鉄|京成)[ぁ-んァ-ヶ一-龥]+線(利用可)?',  # 主要路線名
        r'(つくばエクスプレス|りんかい線|ゆりかもめ)(利用可)?',  # 特殊な路線名
        r'[ぁ-んァ-ヶ一-龥]+線',  # 路線名単体（「山手線」など）
        r'\d+路線\d+駅.*',  # 「15路線5駅利用可」「6路線3駅」など
        r'\d+路線利用可?',  # 「3路線利用」など
        r'\d+駅利用可?',  # 「5駅利用可」など
        # アピール文言
        'オススメ', 'おすすめ', '可能',
        '好立地', '好条件', '良好', '管理良好', '立地良好',
        '都内.*', '近郊.*',
        '新規.*',  # 「新規リフォーム」「新規リノベーション」「新規物件」など
        '新耐震.*',  # 「新耐震基準」「新耐震基準適合」など
        '共用部.*', '共用設備.*',  # 「共用部充実」「共用設備充実」など
        '再開発.*',  # 「再開発が進む」「再開発計画エリア」など
        'エリア.*',  # 「エリア近郊」など
        # 建物タイプの説明文（過度に広範なパターンは削除）
        '駅直結型.*',
        # ペット・設備
        'ペット可', 'ペット相談可', '楽器可', '事務所利用可', 'SOHO可',
        '無償.*', '有償.*',
        'エアコン.*', '新品.*', 'TVモニター.*', 'インターフォン.*',
        '浴室乾燥機.*',
        '家具.*',  # 「家具付き」「家具・〜プレゼント」など
        # 部屋特徴・眺望・日当たり
        '角部屋', '角住戸', '住戸', '角', '最上階', '低層階', '高層階',
        # 階数+広告文の組み合わせ、方角+角部屋/角住戸の組み合わせ
        r'\d+階(高層階|低層階|最上階|角部屋|角住戸|[南北東西]{1,2}向き|(南西|南東|北西|北東|東南|西南|東北|西北)角(部屋|住戸))',
        r'(南西|南東|北西|北東|東南|西南|東北|西北)角(部屋|住戸)',
        # 眺望・階数関連
        '眺望.*', '陽当.*', '日当.*', '眺望良好', '海を望む.*', '上階なし',
        '開放感.*',
        '室内.*', '内装.*',
        # 建物規模
        '大規模.*',
        # 企画・リフォーム
        '特別企画', 'リフォーム',
        # 面積情報
        r'\d+平米', r'\d+㎡', r'\d+[mM]2', r'\d+\.\d+平米',
        r'\d+\.\d+㎡', r'\d+\.\d+[mM]2',
        r'[約およそ]?\d+\.?\d*平米[超以上以下約程度]?', r'[約およそ]?\d+\.?\d*㎡[超以上以下約程度]?', r'[約およそ]?\d+\.?\d*[mM]2[超以上以下約程度]?',  # 修飾語付き
        r'(専有)?面積\d+\.?\d*[平米㎡]?', r'(専有)?面積\d+\.?\d*[mM]2?',  # 「専有面積80平米超」などに対応
        # 畳・帖情報
        r'\d+\.?\d*帖', r'\d+\.?\d*畳',  # 「26.6帖」「8畳」など
        r'[ぁ-んァ-ヶ一-龥]+\d+\.?\d*帖', r'[ぁ-んァ-ヶ一-龥]+\d+\.?\d*畳',  # 「リビング26.6帖」「和室8畳」など
        # 設備詳細
        '床暖房', 'コンシェルジュサービス.*', 'コンシェルジュ付.*',
        'バレー.*サービス.*',
        # 間取り・設備
        r'\d+(R|LDK|LK|DK|K).*',  # 間取り（範囲指定や付帯情報含む）
        r'\d+S',  # Sタイプ
        r'([A-Z\d]+|メゾネット)タイプ',  # 各種タイプ
        'メゾネット',  # メゾネット単体（建物タイプであり建物名ではない）
        'タウンハウス', 'テラスハウス',  # その他の建物タイプ
        r'(\d+|ワン)ルーム(\+[A-Z]+)?',  # ルーム（オプション付き）
        r'(WIC|SIC|TR)(付き?|×\d+)?',  # WIC/SIC関連
        r'\d+(WIC|SIC|TR)',  # 「2WIC」など（数字+WIC）
        '納戸', 'サービスルーム', 'S室', 'N室',  # その他設備
        'システムキッチン', 'オートロック', '宅配.*',  # 「宅配ボックス」「宅配BOX」など
        r'バルコニー付', '専用庭付.*', r'ルーフバルコニー付',
        r'ルーフバルコニー×\d+',
        'バルコニー.*', 'ルーフバルコニー.*',
        'エレベーター付', '駐車場付', '駐輪場付',
        # 階数・部屋番号情報
        r'\d+階', r'\d+F', '階部分', r'\d+th',
        r'\d+階部分', '部分', r'\d+階.*向き.*', r'\d+階.*角.*',
        r'\d+階の.*', r'\d+階/.*', r'\d+号室',
        # 方角・方向情報（方角向き+角部屋/角住戸も含む）
        '(南|北|東|西|南東|南西|北東|北西|東南|西南|東北|西北)向き(角部屋|角住戸)?',
        r'\d+方向.*',
        # 入居・契約
        '即入居可', '空室', '賃貸中', '未入居', '内覧.*', '空室.*',
        r'空室に付',  # 「空室に付〜」などに対応
        # ゴミ出し・設備サービス
        '24時間.*', 'ゴミ出し.*', 'ゴミ置場.*',  # 「24時間ゴミ出し可」など
        'ゲストルーム.*', 'パーティールーム.*',  # 「ゲストルーム完備」など
        # その他広告文言
        'シリーズ', 'エクセルシリーズ', 'プレミアムシリーズ', 'グランドシリーズ',
        '(システムキッチン|オートロック|宅配ボックス)(付|完備)?',
        '(エクセル|プレミアム|グランド)シリーズ',
        '(納戸|サービスルーム|S室|N室)付?',
        '(バルコニー|専用庭|ルーフバルコニー|エレベーター|駐車場|駐輪場)付',
    ]

    ad_patterns = base_ad_patterns

    # 建物名として保護するキーワード（ブランド名のみ）
    building_name_keywords = [
        'パークハウス', 'オープンレジデンシア', 'プラウド', 'シティハウス',
        'グランドメゾン', 'パークコート', 'ピアース', 'パークホームズ',
        'ブランズ', 'グランスイート', 'スカーラ', 'シティタワー',
        'ディアナコート', 'ホームズ', 'ジェイパーク', 'シャンボール',
        'プレミスト', 'パークタワー', 'セザール', 'アトラス', 'クレヴィア',
        'ダイアパレス', 'ジオ', 'サンクタス', 'クリオ', 'サンウッド',
        'ファミール', 'イトーピア', 'ガーデンヒルズ', 'デュオ',
        'パークマンション', 'セブンスター', 'インペリアル', 'クオリア',
        'リビオレゾン', 'ルジェンテ',
        'BRILLIA', 'HARUMI', 'CLEARE', 'FAMILLE', 'DUET', 'DUO', 'SCALA',
        'DOEL', 'ALLES', 'CLEO', 'GALA',
        'EAST', 'WEST', 'NORTH', 'SOUTH', 'CENTER',
        'ウエスト', 'ウェスト', 'イースト', 'ノース', 'サウス', 'セントラル',
        'エスト', 'Est', 'Terrazza',
    ]
    
    # Step 1.7: 中点処理は_trim_ad_text_from_ends内で行う
    # （中点を含む広告文パターンのマッチングと、中点分割後の処理を統合）

    # 前後の広告文をトリミングする共通関数
    def _trim_ad_text_from_ends(text, symbols_pattern):
        trimmed = re.sub(symbols_pattern, ' ', text)
        trimmed = re.sub(r'\s+', ' ', trimmed.strip())
        words = trimmed.split()
        if not words:
            return ""

        removal_patterns = [f'^{pat}$' for pat in base_ad_patterns]
        escaped_keywords = [re.escape(kw) for kw in building_name_keywords]
        keywords_pattern = '|'.join(escaped_keywords)
        station_exclusion_pattern = (
            f'^(?!.*({keywords_pattern})).*駅(\\s*徒歩[0-9０-９]+分)?$'
        )
        removal_patterns.append(station_exclusion_pattern)
        
        def is_word_ad(word):
            """単語が広告文かどうかを判定（中点処理を含む）"""
            if not word.strip():
                return False
            if any(keyword in word for keyword in building_name_keywords):
                return False
            if re.match(BUILDING_WING_PATTERN + '$', word):
                return False
            
            # まず中点を含めた状態でパターンマッチ
            for pattern in removal_patterns:
                if re.match(pattern, word):
                    return True
            
            # マッチしなければ、分割記号（・、&、/）で分割してすべての部分が広告文かチェック
            if any(sep in word for sep in ['・', '&', '/']):
                # 複数の分割記号で分割
                parts = re.split(r'[・&/]', word)
                all_parts_ad = True
                for part in parts:
                    if not part.strip():
                        continue
                    # 建物名キーワードを含む場合は広告文でない
                    if any(keyword in part for keyword in building_name_keywords):
                        all_parts_ad = False
                        break
                    # パターンマッチ
                    part_is_ad = False
                    for pattern in removal_patterns:
                        if re.match(pattern, part):
                            part_is_ad = True
                            break
                    if not part_is_ad:
                        all_parts_ad = False
                        break
                if all_parts_ad:
                    return True
            
            return False

        # スラッシュで区切られた単語を前後からトリミング
        # 例: "ザ・タワーズ台場EAST棟/85.20m2/2LDK+WIC+納戸/北東角住戸" → "ザ・タワーズ台場EAST棟"
        processed_words = []
        for word in words:
            if '/' in word:
                # 日付パターン（数字/数字...）の場合は全体を削除
                if re.match(r'^\d+/\d+', word):
                    # 日付パターンなので削除（何も追加しない）
                    continue

                # スラッシュで分割
                parts = word.split('/')
                # 各部分を評価し、広告文でない部分のみを収集
                non_ad_parts = []
                for part in parts:
                    part = part.strip()
                    if part and not is_word_ad(part):
                        non_ad_parts.append(part)

                # 広告文でない部分がある場合、最初の部分のみを残す
                # （建物名は通常最初に来るため）
                if non_ad_parts:
                    processed_words.append(non_ad_parts[0])
                # すべてが広告文の場合は何も追加しない（削除）
            else:
                processed_words.append(word)

        words = processed_words

        # 前方からトリミング
        start_index = 0
        for i, word in enumerate(words):
            if is_word_ad(word):
                start_index = i + 1
            else:
                start_index = i
                break

        # 後方からトリミング
        end_index = len(words) - 1
        for i in range(len(words) - 1, start_index - 1, -1):
            word = words[i]
            if is_word_ad(word):
                end_index = i - 1
            else:
                end_index = i
                break

        if start_index <= end_index:
            result_words = words[start_index:end_index + 1]
            return ' '.join(result_words).strip()
        else:
            return ""

    # 括弧パターンを検出して処理
    bracket_patterns = [
        (r'^(.*?)\((.+?)\)(.*)$', '(', ')'),
        (r'^(.*?)【(.+?)】(.*)$', '【', '】'),
        (r'^(.*?)\[(.+?)\](.*)$', '[', ']'),
        (r'^(.*?)≪(.+?)≫(.*)$', '≪', '≫'),  # 数学記号の括弧
    ]

    def trim_candidate(text):
        symbols_pattern = (
            r'[☆★◆◇■□▲△▼▽◎○●◯※＊！？：；♪｜～〜、。→←↑↓⇒⇐⇑⇓]'
        )
        return _trim_ad_text_from_ends(text, symbols_pattern)

    # 最大10回まで括弧処理を繰り返す
    for _ in range(10):
        found_bracket = False
        for pattern, _open_br, _close_br in bracket_patterns:
            match = re.match(pattern, current_text)
            if match:
                outside_before = match.group(1).strip()
                inside = match.group(2).strip()
                outside_after = match.group(3).strip()

                if any(bracket in inside for bracket in [
                    '（', '）', '(', ')', '【', '】', '[', ']'
                ]):
                    continue

                # 候補を生成
                candidates = []
                if inside and inside.strip():
                    candidates.append(('inside', inside))
                if outside_before and outside_before.strip():
                    candidates.append(('before', outside_before))
                if outside_after and outside_after.strip():
                    candidates.append(('after', outside_after))
                combined = (outside_before + ' ' + outside_after).strip()
                if combined and combined != outside_before and (
                    combined != outside_after
                ):
                    candidates.append(('combined', combined))

                # 各候補をトリミング
                trimmed_candidates = []
                for candidate_type, candidate_text in candidates:
                    trimmed_text = trim_candidate(candidate_text)
                    if trimmed_text:
                        trimmed_candidates.append((
                            candidate_type, candidate_text, trimmed_text
                        ))

                # 有効な候補を選択
                valid_candidates = []
                for _candidate_type, _original_text, trimmed_text in (
                    trimmed_candidates
                ):
                    is_ad = any(
                        re.search(pat, trimmed_text, re.IGNORECASE)
                        for pat in ad_patterns
                    )
                    if is_ad:
                        continue
                    has_keyword = any(
                        kw in trimmed_text for kw in building_name_keywords
                    )
                    valid_candidates.append((trimmed_text, has_keyword))

                # 優先順位で候補を選択
                best_candidate = None
                if valid_candidates:
                    candidates_with_keyword = [
                        text for text, has_kw in valid_candidates if has_kw
                    ]
                    if candidates_with_keyword:
                        best_candidate = max(candidates_with_keyword, key=len)
                    else:
                        best_candidate = max(
                            [text for text, _has_kw in valid_candidates],
                            key=len
                        )

                if best_candidate:
                    current_text = best_candidate
                    found_bracket = True
                    break
        if not found_bracket:
            break

    # 前後の広告文をトリミング
    # 注意: /と&は建物名に使われる可能性があるため除外（is_word_ad関数内で処理）
    symbols_pattern = (
        r'[☆★◆◇■□▲△▼▽◎○●◯※＊！？：；♪｜～〜~、。→←↑↓⇒⇐⇑⇓'
        r'\[\]「」『』（）()\【】〔〕〈〉《》!?@#$%^*×]'
    )
    result = _trim_ad_text_from_ends(current_text, symbols_pattern)

    # 記号だけが残った場合は無効
    if result and re.match(
        r'^[^a-zA-Z0-9ぁ-んァ-ヶー一-龥Ａ-Ｚａ-ｚ０-９]+$', result
    ):
        return ""

    # 路線名だけの場合は無効
    railway_patterns = [
        r'^.*線$', r'^JR.*$', r'^東京メトロ.*$', r'^都営.*線$',
        r'^東急.*線$', r'^小田急.*線$', r'^京王.*線$', r'^西武.*線$',
        r'^東武.*線$', r'^京急.*線$', r'^相鉄.*線$', r'^京成.*線$',
        r'^つくばエクスプレス$', r'^りんかい線$', r'^ゆりかもめ$',
    ]
    for pattern in railway_patterns:
        if re.match(pattern, result):
            return ""

    return result

def normalize_building_name_with_ad_removal(building_name: str) -> str:
    """
    建物名を正規化する（広告文削除付き）
    
    スクレイピング時など、広告文が含まれている可能性がある場合に使用
    
    Args:
        building_name: 正規化する建物名（広告文が含まれる可能性あり）
        
    Returns:
        広告文を削除して正規化された建物名
    """
    if not building_name:
        return ""
    
    # まず広告文を削除（棟名や番号は保持）
    cleaned_name = remove_ad_text_from_building_name(building_name)
    
    # その後、通常の正規化を適用
    return normalize_building_name(cleaned_name)


def normalize_building_name(building_name: str) -> str:
    """
    建物名を正規化する共通メソッド
    
    Args:
        building_name: 正規化する建物名
        
    Returns:
        正規化された建物名
    """
    if not building_name:
        return ""
        
    # 1. 全角英数字と記号を半角に変換
    normalized = jaconv.z2h(building_name, kana=False, ascii=True, digit=True)
    
    # 2. ローマ数字の正規化を先に実行（フィルタリング前に変換）
    # 全角ローマ数字を半角に変換
    roman_map = {
        'Ⅰ': 'I', 'Ⅱ': 'II', 'Ⅲ': 'III', 'Ⅳ': 'IV', 'Ⅴ': 'V',
        'Ⅵ': 'VI', 'Ⅶ': 'VII', 'Ⅷ': 'VIII', 'Ⅸ': 'IX', 'Ⅹ': 'X',
        'Ⅺ': 'XI', 'Ⅻ': 'XII',
        # 小文字版も追加
        'ⅰ': 'I', 'ⅱ': 'II', 'ⅲ': 'III', 'ⅳ': 'IV', 'ⅴ': 'V',
        'ⅵ': 'VI', 'ⅶ': 'VII', 'ⅷ': 'VIII', 'ⅸ': 'IX', 'ⅹ': 'X',
        'ⅺ': 'XI', 'ⅻ': 'XII'
    }
    for full_width, half_width in roman_map.items():
        normalized = normalized.replace(full_width, half_width)
    
    # 3. 記号類の処理
    # 意味のある記号（・、&、-、~）は保持、装飾記号はスペースに変換
    
    # 各種ダッシュをハイフンに統一
    for dash_char in ['\u2010', '\u2011', '\u2012', '\u2013', '\u2014', '\u2015']:
        normalized = normalized.replace(dash_char, '-')
    
    # 波ダッシュをチルダに統一
    normalized = normalized.replace('\u301c', '~').replace('\uff5e', '~')
    
    # 装飾記号をスペースに変換（●■★◆▲◇□◎○△▽♪など）
    # 保持する記号: 英数字、日本語、・（中点）、&、-、~、括弧、スペース
    import string
    allowed_chars = set(string.ascii_letters + string.digits + '・&-~()[] 　々')  # 々を追加
    # 日本語文字の範囲を追加（ひらがな、カタカナ、漢字）
    result = []
    for char in normalized:
        if char in allowed_chars:
            result.append(char)
        elif '\u3000' <= char <= '\u9fff':  # 日本語文字の範囲（U+3000から開始して々を含む）
            result.append(char)
        elif '\uff00' <= char <= '\uffef':  # 全角記号の一部（全角英数字など）
            result.append(char)
        else:
            # その他の記号はスペースに変換
            result.append(' ')
    normalized = ''.join(result)
    
    # 4. 単位の正規化（㎡とm2を統一）
    normalized = normalized.replace('㎡', 'm2').replace('m²', 'm2')
    
    # 5. 英字を大文字に統一（表記ゆれ吸収のため）
    # 日本語（ひらがな・カタカナ・漢字）は影響を受けない
    normalized = normalized.upper()
    
    # 6. スペースの正規化
    # 全角スペースも半角スペースに変換
    normalized = normalized.replace('　', ' ')
    # 連続するスペースを1つの半角スペースに統一
    import re
    normalized = re.sub(r'\s+', ' ', normalized)
    # 前後の空白を除去
    normalized = normalized.strip()
    
    return normalized


def convert_japanese_numbers_to_arabic(text: str) -> str:
    """漢数字を算用数字に変換（検索用）
    
    Args:
        text: 変換対象のテキスト
    
    Returns:
        漢数字を算用数字に変換したテキスト
    """
    if not text:
        return text
    
    # 基本的な漢数字マップ
    basic_map = {
        '〇': '0', '○': '0', '零': '0',
        '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
        '六': '6', '七': '7', '八': '8', '九': '9',
        '壱': '1', '弐': '2', '参': '3',  # 旧字体
    }
    
    result = text
    
    # パターン1: 第X棟、X号館などの単純な置換
    for pattern in [r'第([一二三四五六七八九十]+)([棟館号])', 
                   r'([一二三四五六七八九十]+)([棟館号])']:
        def replace_func(match):
            num_str = match.group(1)
            suffix = match.group(2) if len(match.groups()) > 1 else ''
            prefix = '第' if '第' in match.group(0) else ''
            
            # 「十」を含む場合の処理
            if '十' in num_str:
                if num_str == '十':
                    converted = '10'
                elif num_str.startswith('十'):
                    rest = num_str[1:]
                    if rest in basic_map:
                        converted = '1' + basic_map[rest]
                    else:
                        converted = num_str
                elif num_str.endswith('十'):
                    first = num_str[:-1]
                    if first in basic_map:
                        converted = basic_map[first] + '0'
                    else:
                        converted = num_str
                elif len(num_str) == 3 and num_str[1] == '十':
                    first = num_str[0]
                    last = num_str[2]
                    if first in basic_map and last in basic_map:
                        converted = basic_map[first] + basic_map[last]
                    else:
                        converted = num_str
                else:
                    converted = num_str
            else:
                # 単純な置換
                converted = num_str
                for kanji, num in basic_map.items():
                    converted = converted.replace(kanji, num)
            
            return prefix + converted + suffix
        
        result = re.sub(pattern, replace_func, result)
    
    # パターン2: 残った独立した漢数字を処理
    def convert_compound_number(match):
        text = match.group(0)
        # 十の位と一の位を処理
        if '十' in text:
            parts = text.split('十')
            if len(parts) == 2:
                tens = basic_map.get(parts[0], parts[0]) if parts[0] else '1'
                ones = basic_map.get(parts[1], '0') if parts[1] else '0'
                if tens.isdigit() and ones.isdigit():
                    return str(int(tens) * 10 + int(ones))
            elif text == '十':
                return '10'
        # 単純な一桁の数字
        return basic_map.get(text, text)
    
    # 漢数字のパターンにマッチする部分を変換
    result = re.sub(r'[一二三四五六七八九十]+', convert_compound_number, result)
    
    return result


def convert_roman_numerals_to_arabic(text: str) -> str:
    """ローマ数字を算用数字に変換（検索用）
    
    Args:
        text: 変換対象のテキスト
    
    Returns:
        ローマ数字を算用数字に変換したテキスト
    """
    if not text:
        return text
    
    # 全角ローマ数字の変換マップ
    roman_map = {
        # 大文字
        'Ⅰ': '1', 'Ⅱ': '2', 'Ⅲ': '3', 'Ⅳ': '4', 'Ⅴ': '5',
        'Ⅵ': '6', 'Ⅶ': '7', 'Ⅷ': '8', 'Ⅸ': '9', 'Ⅹ': '10',
        'Ⅺ': '11', 'Ⅻ': '12',
        # 小文字
        'ⅰ': '1', 'ⅱ': '2', 'ⅲ': '3', 'ⅳ': '4', 'ⅴ': '5',
        'ⅵ': '6', 'ⅶ': '7', 'ⅷ': '8', 'ⅸ': '9', 'ⅹ': '10',
        'ⅺ': '11', 'ⅻ': '12'
    }
    
    result = text
    
    # 全角ローマ数字を変換
    for roman, num in roman_map.items():
        result = result.replace(roman, num)
    
    # 半角ローマ数字パターン（汎用的な変換）
    import re
    
    def replace_roman(match):
        """ローマ数字を算用数字に変換する関数"""
        roman = match.group(1).upper() if match.lastindex else match.group(0).upper()  # グループ1があれば使用、なければグループ0
        
        # ローマ数字と算用数字の対応表（1-30まで対応）
        roman_to_arabic = {
            'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
            'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
            'XI': 11, 'XII': 12, 'XIII': 13, 'XIV': 14, 'XV': 15,
            'XVI': 16, 'XVII': 17, 'XVIII': 18, 'XIX': 19, 'XX': 20,
            'XXI': 21, 'XXII': 22, 'XXIII': 23, 'XXIV': 24, 'XXV': 25,
            'XXVI': 26, 'XXVII': 27, 'XXVIII': 28, 'XXIX': 29, 'XXX': 30
        }
        
        # 大文字に統一して検索
        if roman in roman_to_arabic:
            return str(roman_to_arabic[roman])
        
        # 見つからない場合はそのまま返す
        return match.group(0)
    
    # 半角ローマ数字のパターン（より汎用的）
    # 前後が英字でない場合にマッチ（日本語文字や数字、記号の前後はOK）
    # (?<![A-Za-z]) : 前に英字がない
    # (roman_numeral) : ローマ数字をキャプチャグループ1として取得
    # (?![A-Za-z]) : 後に英字がない
    roman_pattern = r'(?<![A-Za-z])((?:XXX|XX[IXV]|XX|X[IXV]|IX|IV|V?I{1,3}|X{1,2}))(?![A-Za-z])'
    
    # ローマ数字を変換（大文字小文字を問わない）
    result = re.sub(roman_pattern, replace_roman, result, flags=re.IGNORECASE)
    
    return result


def canonicalize_building_name(building_name: str) -> str:
    """
    建物名を正規化して検索用キーを生成
    
    処理内容：
    1. normalize_building_nameで基本的な正規化
    2. 漢数字を算用数字に変換
    3. ローマ数字を算用数字に変換
    4. ひらがなをカタカナに変換
    5. 英数字と日本語文字以外を削除（中点・も削除）
    6. 小文字化
    
    注意：棟表記（東棟、西棟など）は除去しません。
    異なる棟は別々の建物として扱われます。
    
    Args:
        building_name: 正規化する建物名
        
    Returns:
        検索用に完全に正規化された建物名
    """
    if not building_name:
        return ""
    
    # まず標準的な正規化を適用
    normalized = normalize_building_name(building_name)
    
    # 漢数字を算用数字に変換（検索精度向上）
    normalized = convert_japanese_numbers_to_arabic(normalized)
    
    # ローマ数字を算用数字に変換（検索精度向上）
    normalized = convert_roman_numerals_to_arabic(normalized)
    
    # ひらがなをカタカナに変換
    canonical = ''
    for char in normalized:
        # ひらがなの範囲（U+3040〜U+309F）をカタカナ（U+30A0〜U+30FF）に変換
        if '\u3040' <= char <= '\u309f':
            canonical += chr(ord(char) + 0x60)
        else:
            canonical += char
    
    # 英数字と日本語文字以外をすべて削除
    import string
    result = []
    for char in canonical:
        if char in string.ascii_letters + string.digits:
            result.append(char)
        # 中点（・）は除外して、日本語文字のみを残す
        elif char == '・':
            continue  # 中点は削除
        elif char == '々':  # 繰り返し記号は保持
            result.append(char)
        elif '\u3000' <= char <= '\u9fff':  # 日本語文字の範囲（U+3000から開始）
            result.append(char)
        # それ以外の文字（記号、スペース等）は削除
    
    # 小文字化
    return ''.join(result).lower()


def extract_room_number(building_name: str) -> tuple[str, str]:
    """
    建物名から部屋番号を抽出する
    
    Args:
        building_name: 部屋番号を含む可能性のある建物名
        
    Returns:
        (部屋番号を除いた建物名, 抽出された部屋番号)
    """
    if not building_name:
        return "", None
    
    # 部屋番号のパターン（末尾の数字）
    # 例: "パークハウス101" -> ("パークハウス", "101")
    # 例: "東京タワー 2003号" -> ("東京タワー", "2003")
    
    # パターン1: 末尾の3-4桁の数字（号や号室を含む）
    pattern1 = re.compile(r'(.+?)\s*(\d{3,4})\s*(?:号|号室)?$')
    match = pattern1.match(building_name)
    if match:
        return match.group(1).strip(), match.group(2)
    
    # パターン2: 末尾に「○階」がある場合（これは部屋番号ではない）
    if re.search(r'\d+階$', building_name):
        return building_name, None
    
    # パターン3: 建物名の後に明確に区切られた数字
    # 例: "ビル名 101"
    pattern3 = re.compile(r'(.+?)\s+(\d{3,4})$')
    match = pattern3.match(building_name)
    if match:
        clean_name = match.group(1).strip()
        # 建物名っぽい場合のみ分離
        if len(clean_name) >= 2:  # 最低2文字以上
            return clean_name, match.group(2)
    
    return building_name, None