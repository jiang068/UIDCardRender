# 战双幻痛囚笼 卡片渲染器 (PIL 重构精简版)

from __future__ import annotations
import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageOps, ImageChops

# 从统一包中导入所有所需函数
from . import (
    F14, F16, F20, F22, F24, F26, F28, F30, F44,
    M14, M16, M20, M22, M24, M26, M28, M30, M44,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask,
    _ty, _draw_rounded_rect, _draw_h_gradient, _draw_v_gradient,
    parse_common_header, draw_common_header, draw_title_bar
)

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2

C_BG_PAGE = (226, 235, 245, 255)
C_PRIMARY = (24, 107, 181, 255)
C_TEXT_DARK = (51, 51, 51, 255)
C_TEXT_GRAY = (102, 102, 102, 255)
C_BG_LIGHT = (240, 246, 250, 255)
C_BORDER = (210, 224, 235, 255)
C_ACCENT_RED = (231, 76, 60, 255)

# --- DOM 解析 ---
def _parse_boss_group(bg: BeautifulSoup) -> dict:
    """提取单个 Boss 组数据的辅助函数"""
    boss = {'weaknesses': [], 'stages': []}
    
    b_avatar = bg.select_one('.boss-avatar img')
    boss['iconB64'] = b_avatar['src'] if b_avatar else ""
    boss['name'] = bg.select_one('.boss-name').get_text(strip=True) if bg.select_one('.boss-name') else ""
    boss['totalPoint'] = bg.select_one('.boss-total-score span').get_text(strip=True) if bg.select_one('.boss-total-score span') else "0"

    for w_row in bg.select('.weakness-row'):
        for w_name, w_icon in zip(w_row.select('.weakness-name'), w_row.select('.weakness-icon')):
            boss['weaknesses'].append({
                'name': w_name.get_text(strip=True),
                'iconB64': w_icon['src'] if w_icon else ""
            })

    for st in bg.select('.stage-item'):
        stage = {'team': []}
        stage['stageName'] = st.select_one('.stage-difficulty').get_text(strip=True) if st.select_one('.stage-difficulty') else ""
        
        s_vals = st.select('.stage-details .val')
        stage['point'] = s_vals[0].get_text(strip=True) if len(s_vals)>0 else "0"
        
        time_text = s_vals[1].parent.get_text(strip=True) if len(s_vals)>1 else ""
        stage['autoFight'] = "自动" in time_text
        stage['fightTime'] = re.sub(r'[^\d]', '', s_vals[1].get_text(strip=True)) if len(s_vals)>1 else "0"

        for av_card in st.select('.avatar-card'):
            c_img = av_card.select_one('img')
            c_grade = av_card.select_one('.avatar-grade')
            is_plus = av_card.select_one('.plus-mark') is not None
            
            grade_class = 'none'
            if c_grade:
                cls = c_grade.get('class', [])
                if 'grade-sss-plus' in cls: grade_class = 'sss-plus'
                elif 'grade-sss' in cls: grade_class = 'sss'
                elif 'grade-ss' in cls: grade_class = 'ss'
            
            stage['team'].append({
                'iconB64': c_img['src'] if c_img else "",
                'gradeDisplay': c_grade.get_text(strip=True).replace("+", "") if c_grade else "",
                'isPlus': is_plus,
                'gradeClass': grade_class
            })
        boss['stages'].append(stage)
    return boss

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    # 1. 抽取基础公共 Header 数据
    data = parse_common_header(soup, html)

    # 2. 抽取幻痛特有数据
    summaries = soup.select('.summary-card')
    bgs = soup.select('.boss-group')

    # 解析主 Summary
    if summaries:
        main_sum = summaries[0]
        a_icon = main_sum.select_one('.area-icon')
        data['areaIconB64'] = a_icon['src'] if a_icon else ""
        data['challengeArea'] = main_sum.select_one('.summary-info h2').get_text(strip=True) if main_sum.select_one('.summary-info h2') else ""
        
        lvl_tag = main_sum.select_one('.summary-info p')
        data['challengeLevel'] = lvl_tag.get_text(strip=True).replace("等级:", "").strip() if lvl_tag else ""
        
        main_stats = main_sum.select('.summary-stats .score-hl')
        data['totalPoint'] = main_stats[0].get_text(strip=True) if len(main_stats)>0 else "0"
        data['totalChallengeTimes'] = main_stats[1].get_text(strip=True) if len(main_stats)>1 else "0"

    # 判断是否有鏖战点 (如果 summary-card 大于 1 个)
    data['hasFightHard'] = len(summaries) > 1
    
    if data['hasFightHard']:
        # 前面的 boss-group 归常规 Boss
        data['bosses'] = [_parse_boss_group(bg) for bg in bgs[:-1]] if len(bgs) > 1 else []
        
        # 最后一个 summary 是鏖战点
        fh_sum = summaries[1]
        fh_icon = fh_sum.select_one('.area-icon')
        data['fhIconB64'] = fh_icon['src'] if fh_icon else ""
        data['fhTitle'] = fh_sum.select_one('.summary-info h2').get_text(strip=True) if fh_sum.select_one('.summary-info h2') else "鏖战点"
        
        fh_stats = fh_sum.select('.summary-stats .score-hl')
        data['fhTotalPoint'] = fh_stats[0].get_text(strip=True) if len(fh_stats)>0 else "0"
        data['fhChallengeTimes'] = fh_stats[1].get_text(strip=True) if len(fh_stats)>1 else "0"
        
        # 最后一个 boss 是鏖战点 Boss
        data['fightHardBoss'] = _parse_boss_group(bgs[-1]) if bgs else None
    else:
        # 没有鏖战点，所有 boss-group 都是常规 Boss
        data['bosses'] = [_parse_boss_group(bg) for bg in bgs]

    return data

# --- 主渲染逻辑 ---
def render(html: str) -> bytes:
    data = parse_html(html)
    
    MAX_H = 8000
    canvas = Image.new("RGBA", (W, MAX_H), C_BG_PAGE)
    if data.get('contentBgB64'):
        try:
            bg_img = _b64_img(data['contentBgB64'])
            bg_img = ImageOps.fit(bg_img, (W, MAX_H), Image.LANCZOS)
            canvas.alpha_composite(bg_img)
        except: pass

    d = ImageDraw.Draw(canvas)
    y = PAD

    # --- 内部复用绘图函数 ---
    def draw_summary_card(start_y, icon_b64, title, level_text, pt, times):
        S_H = 120
        _draw_rounded_rect(canvas, PAD, start_y, PAD + INNER_W, start_y + S_H, 6, C_BG_LIGHT)
        d.rounded_rectangle([PAD, start_y, PAD + INNER_W, start_y + S_H], radius=6, outline=C_BORDER, width=1)
        
        if icon_b64:
            try:
                a_icon = _b64_fit(icon_b64, 60, 70)
                canvas.alpha_composite(a_icon, (PAD + 34, start_y + (S_H - 70)//2))
            except: pass
        
        draw_text_mixed(d, (PAD + 118, start_y + 30), title, cn_font=F30, en_font=M30, fill=C_TEXT_DARK)
        if level_text:
            draw_text_mixed(d, (PAD + 118, start_y + 68), f"等级: {level_text}", cn_font=F20, en_font=M20, fill=C_TEXT_GRAY)

        rw = int(F28.getlength(times))
        draw_text_mixed(d, (PAD + INNER_W - 34 - rw, start_y + 68), times, cn_font=F28, en_font=M28, fill=C_PRIMARY)
        draw_text_mixed(d, (PAD + INNER_W - 34 - rw - 110, start_y + 72), "挑战次数: ", cn_font=F22, en_font=M22, fill=C_TEXT_GRAY)

        rw2 = int(F28.getlength(pt))
        draw_text_mixed(d, (PAD + INNER_W - 34 - rw2, start_y + 26), pt, cn_font=F28, en_font=M28, fill=C_PRIMARY)
        draw_text_mixed(d, (PAD + INNER_W - 34 - rw2 - 110, start_y + 30), "讨伐总值: ", cn_font=F22, en_font=M22, fill=C_TEXT_GRAY)
        return start_y + S_H + 20

    def draw_boss_group(start_y, boss):
        b_img = Image.new("RGBA", (INNER_W, 2000), (0,0,0,0))
        bd = ImageDraw.Draw(b_img)

        # Boss Header
        BH_H = 160
        _draw_rounded_rect(b_img, 0, 0, INNER_W, BH_H, 0, C_BG_LIGHT)
        
        if boss['iconB64']:
            try:
                b_icon = _b64_fit(boss['iconB64'], 306, 160)
                b_img.alpha_composite(b_icon, (0, 0))
                _draw_h_gradient(b_img, 153, 0, 306, 160, (240, 246, 250, 0), (240, 246, 250, 255))
            except: pass
            
        bd.rectangle([0, BH_H - 3, INNER_W, BH_H], fill=C_PRIMARY)

        # 右侧对齐文字排版
        name_w = int(F28.getlength(boss['name']))
        draw_text_mixed(bd, (INNER_W - 24 - name_w, 24), boss['name'], cn_font=F28, en_font=M28, fill=C_TEXT_DARK)
        
        score_w = int(F26.getlength(boss['totalPoint']))
        lbl_w = int(F20.getlength("讨伐总值: "))
        tx = INNER_W - 24 - score_w
        draw_text_mixed(bd, (tx, 66), boss['totalPoint'], cn_font=F26, en_font=M26, fill=C_PRIMARY)
        draw_text_mixed(bd, (tx - lbl_w, 70), "讨伐总值: ", cn_font=F20, en_font=M20, fill=C_TEXT_GRAY)
        
        if boss['weaknesses']:
            w_total_w = 0
            for w in boss['weaknesses']:
                w_total_w += 24 + 6 + int(F16.getlength(w['name'])) + 12
            w_total_w -= 12 
            
            wx = INNER_W - 24 - w_total_w
            for w in boss['weaknesses']:
                if w['iconB64']:
                    try:
                        w_icon = _b64_fit(w['iconB64'], 24, 24)
                        b_img.alpha_composite(w_icon, (wx, 108))
                    except: pass
                draw_text_mixed(bd, (wx + 30, 110), w['name'], cn_font=F16, en_font=M16, fill=C_TEXT_GRAY)
                wx += 24 + 6 + int(F16.getlength(w['name'])) + 12

        by = BH_H
        
        # Stages Items
        for idx, stage in enumerate(boss['stages']):
            ST_H = 142
            _draw_rounded_rect(b_img, 0, by, INNER_W, by + ST_H, 0, (255, 255, 255, 255))
            if idx < len(boss['stages']) - 1:
                bd.line([(0, by + ST_H - 1), (INNER_W, by + ST_H - 1)], fill=(238, 238, 238, 255), width=1)
            
            # 难度方块
            _draw_rounded_rect(b_img, 20, by + 16, 130, by + 126, 4, (93, 103, 115, 255))
            tw = int(F26.getlength(stage['stageName']))
            draw_text_mixed(bd, (20 + (110 - tw)//2, by + 16 + _ty(F26, stage['stageName'], 110)), stage['stageName'], cn_font=F26, en_font=M26, fill=(255, 255, 255, 255))
            
            # 数据详情
            draw_text_mixed(bd, (154, by + 34), "讨伐值: ", cn_font=F24, en_font=M24, fill=C_TEXT_GRAY)
            draw_text_mixed(bd, (154 + int(F24.getlength("讨伐值: ")), by + 30), stage['point'], cn_font=F28, en_font=M28, fill=C_PRIMARY)
            
            draw_text_mixed(bd, (154, by + 76), "耗时: ", cn_font=F24, en_font=M24, fill=C_TEXT_GRAY)
            time_w = int(F28.getlength(f"{stage['fightTime']}S"))
            draw_text_mixed(bd, (154 + int(F24.getlength("耗时: ")), by + 72), f"{stage['fightTime']}S", cn_font=F28, en_font=M28, fill=C_PRIMARY)
            
            if stage['autoFight']:
                draw_text_mixed(bd, (154 + int(F24.getlength("耗时: ")) + time_w + 4, by + 76), " · 自动", cn_font=F24, en_font=M24, fill=C_TEXT_GRAY)

            # 队伍卡片
            tx = INNER_W - 20
            for char in reversed(stage['team']):
                tx -= 140
                _draw_rounded_rect(b_img, tx, by + 16, tx + 140, by + 156, 4, (240, 240, 240, 255))
                if char['iconB64']:
                    try:
                        c_img = _b64_fit(char['iconB64'], 140, 140)
                        c_alpha = c_img.split()[3] if c_img.mode == "RGBA" else Image.new("L", c_img.size, 255)
                        c_img.putalpha(ImageChops.multiply(c_alpha, _round_mask(140, 140, 4)))
                        b_img.alpha_composite(c_img, (tx, by + 16))
                    except: pass
                bd.rounded_rectangle([tx, by + 16, tx + 140, by + 156], radius=4, outline=(224, 229, 235, 255), width=2)
                
                g_col = (255, 255, 255, 255)
                if char['gradeClass'] == 'sss-plus': g_col = (255, 152, 0, 255)
                elif char['gradeClass'] == 'sss': g_col = (230, 194, 90, 255)
                elif char['gradeClass'] == 'ss': g_col = (211, 47, 47, 255)

                draw_text_mixed(bd, (tx + 6, by + 22), char['gradeDisplay'], cn_font=F20, en_font=M20, fill=g_col)
                if char['isPlus']:
                    pw = int(F20.getlength(char['gradeDisplay']))
                    draw_text_mixed(bd, (tx + 6 + pw + 2, by + 18), "+", cn_font=F14, en_font=M14, fill=g_col)
                
                tx -= 10
            
            by += ST_H

        # 合成并应用外边框
        b_final = b_img.crop((0, 0, INNER_W, by))
        _draw_rounded_rect(canvas, PAD, start_y, PAD + INNER_W, start_y + by, 6, (255, 255, 255, 255))
        canvas.paste(b_final, (PAD, start_y), _round_mask(INNER_W, by, 6))
        d.rounded_rectangle([PAD, start_y, PAD + INNER_W, start_y + by], radius=6, outline=C_BORDER, width=1)
        
        return start_y + by + 20


    # --- 开始实际绘制流水线 ---
    y = draw_common_header(canvas, d, data, PAD, INNER_W, y)
    y = draw_title_bar(canvas, d, "幻痛囚笼", data.get('titleBgB64', ''), PAD, INNER_W, y)

    # 1. 常规区域 Summary
    y = draw_summary_card(y, data.get('areaIconB64'), data.get('challengeArea', ''), data.get('challengeLevel', ''), data.get('totalPoint', '0'), data.get('totalChallengeTimes', '0'))

    # 2. 常规区域 Bosses
    for boss in data.get('bosses', []):
        y = draw_boss_group(y, boss)

    # 3. 鏖战点区域 (如果存在)
    if data.get('hasFightHard'):
        # 鏖战点没有 level，所以传空字符串
        y = draw_summary_card(y, data.get('fhIconB64'), data.get('fhTitle', ''), "", data.get('fhTotalPoint', '0'), data.get('fhChallengeTimes', '0'))
        if data.get('fightHardBoss'):
            y = draw_boss_group(y, data['fightHardBoss'])

    # 一刀裁剪，最终输出
    out_rgb = canvas.crop((0, 0, W, y + 20)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()