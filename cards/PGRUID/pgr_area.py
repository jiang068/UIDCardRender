# 战双纷争战区 卡片渲染器 (PIL 重构精简版)

from __future__ import annotations
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageOps

# 从统一包中导入所有所需函数
from . import (
    F14, F20, F22, F24, F26, F28, F30, F44,
    M14, M20, M22, M24, M26, M28, M30, M44,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask,
    _ty, _draw_rounded_rect, _draw_h_gradient, _draw_v_gradient,
    parse_common_header, draw_common_header, draw_title_bar
)

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2  # 920

C_BG_PAGE = (226, 235, 245, 255)
C_PRIMARY = (24, 107, 181, 255)
C_TEXT_DARK = (51, 51, 51, 255)
C_TEXT_GRAY = (102, 102, 102, 255)
C_BG_LIGHT = (240, 246, 250, 255)
C_BORDER = (210, 224, 235, 255)

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    # 1. 抽取基础公共 Header 数据
    data = parse_common_header(soup, html)
    data['zones'] = []

    # 2. 抽取战区特有数据
    a_icon = soup.select_one('.area-icon')
    data['areaIconB64'] = a_icon['src'] if a_icon else ""
    data['groupName'] = soup.select_one('.summary-info h2').get_text(strip=True) if soup.select_one('.summary-info h2') else ""
    data['groupLevel'] = soup.select_one('.summary-info p').get_text(strip=True).replace("等级:", "").strip() if soup.select_one('.summary-info p') else ""
    
    stats = soup.select('.summary-stats .score-hl')
    data['totalPoint'] = stats[0].get_text(strip=True) if len(stats)>0 else "0"
    data['totalChallengeTimes'] = stats[1].get_text(strip=True) if len(stats)>1 else "0"

    for zc in soup.select('.zone-card'):
        zone = {'buffFights': []}
        zi = zc.select_one('.zone-icon')
        zone['stageIconB64'] = zi['src'] if zi else ""
        zone['stageName'] = zc.select_one('.zone-title').get_text(strip=True) if zc.select_one('.zone-title') else ""
        
        zstats = zc.select('.zone-stats .val')
        zone['point'] = zstats[0].get_text(strip=True) if len(zstats)>0 else "0"
        zone['totalNum'] = zstats[1].get_text(strip=True) if len(zstats)>1 else "0"

        for zb in zc.select('.zone-body'):
            bf = {'supportBuffs': [], 'team': []}
            for bi in zb.select('.buff-item'):
                bimg = bi.select_one('.buff-icon-img')
                bf['supportBuffs'].append({
                    'iconB64': bimg['src'] if bimg else "",
                    'name': bi.select_one('.buff-name').get_text(strip=True) if bi.select_one('.buff-name') else ""
                })
            
            bf_stats = zb.select('.zone-details .val')
            bf['point'] = bf_stats[0].get_text(strip=True) if len(bf_stats)>0 else "0"
            bf['fightTime'] = bf_stats[1].get_text(strip=True).replace("S", "") if len(bf_stats)>1 else "0"

            for av_card in zb.select('.avatar-card'):
                c_img = av_card.select_one('img')
                c_grade = av_card.select_one('.avatar-grade')
                is_plus = av_card.select_one('.plus-mark') is not None
                
                grade_class = 'none'
                if c_grade:
                    cls = c_grade.get('class', [])
                    if 'grade-sss-plus' in cls: grade_class = 'sss-plus'
                    elif 'grade-sss' in cls: grade_class = 'sss'
                    elif 'grade-ss' in cls: grade_class = 'ss'
                
                bf['team'].append({
                    'iconB64': c_img['src'] if c_img else "",
                    'gradeDisplay': c_grade.get_text(strip=True).replace("+", "") if c_grade else "",
                    'isPlus': is_plus,
                    'gradeClass': grade_class
                })
            zone['buffFights'].append(bf)
        data['zones'].append(zone)

    return data

# --- 主渲染逻辑 ---
def render(html: str) -> bytes:
    data = parse_html(html)
    
    MAX_H = 6000
    canvas = Image.new("RGBA", (W, MAX_H), C_BG_PAGE)
    if data.get('contentBgB64'):
        try:
            bg_img = _b64_img(data['contentBgB64'])
            bg_img = ImageOps.fit(bg_img, (W, MAX_H), Image.LANCZOS)
            canvas.alpha_composite(bg_img)
        except: pass

    d = ImageDraw.Draw(canvas)
    y = PAD

    # --- Header & Title Bar 组件式调用 ---
    y = draw_common_header(canvas, d, data, PAD, INNER_W, y)
    y = draw_title_bar(canvas, d, "纷争战区", data.get('titleBgB64', ''), PAD, INNER_W, y)

    # --- Summary ---
    S_H = 120
    _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + S_H, 6, C_BG_LIGHT)
    d.rounded_rectangle([PAD, y, PAD + INNER_W, y + S_H], radius=6, outline=C_BORDER, width=1)
    
    if data['areaIconB64']:
        try:
            a_icon = _b64_fit(data['areaIconB64'], 60, 70)
            canvas.alpha_composite(a_icon, (PAD + 34, y + (S_H - 70)//2))
        except: pass
    
    draw_text_mixed(d, (PAD + 118, y + 30), data['groupName'], cn_font=F30, en_font=M30, fill=C_TEXT_DARK)
    draw_text_mixed(d, (PAD + 118, y + 68), f"等级: {data['groupLevel']}", cn_font=F20, en_font=M20, fill=C_TEXT_GRAY)

    rw = F28.getlength(data['totalChallengeTimes'])
    draw_text_mixed(d, (PAD + INNER_W - 34 - rw, y + 68), data['totalChallengeTimes'], cn_font=F28, en_font=M28, fill=C_PRIMARY)
    draw_text_mixed(d, (PAD + INNER_W - 34 - rw - 110, y + 72), "挑战次数: ", cn_font=F22, en_font=M22, fill=C_TEXT_GRAY)

    rw2 = F28.getlength(data['totalPoint'])
    draw_text_mixed(d, (PAD + INNER_W - 34 - rw2, y + 26), data['totalPoint'], cn_font=F28, en_font=M28, fill=C_PRIMARY)
    draw_text_mixed(d, (PAD + INNER_W - 34 - rw2 - 110, y + 30), "积分总值: ", cn_font=F22, en_font=M22, fill=C_TEXT_GRAY)
    y += S_H + 20

    # --- Zones ---
    for zone in data['zones']:
        z_start_y = y
        z_img = Image.new("RGBA", (INNER_W, 2000), (0,0,0,0))
        zd = ImageDraw.Draw(z_img)

        # Zone Header
        ZH_H = 86
        _draw_h_gradient(z_img, 0, 0, INNER_W, ZH_H, (244, 248, 251, 255), (255, 255, 255, 255))
        zd.line([(0, ZH_H-1), (INNER_W, ZH_H-1)], fill=(238,238,238,255), width=1)
        
        if zone['stageIconB64']:
            try:
                z_icon = _b64_fit(zone['stageIconB64'], 50, 50)
                z_img.alpha_composite(z_icon, (24, (ZH_H - 50)//2))
            except: pass
        
        draw_text_mixed(zd, (90, 26), zone['stageName'], cn_font=F28, en_font=M28, fill=C_TEXT_DARK)
        
        sw = F26.getlength(zone['totalNum'])
        draw_text_mixed(zd, (INNER_W - 24 - sw, 28), zone['totalNum'], cn_font=F26, en_font=M26, fill=C_PRIMARY)
        draw_text_mixed(zd, (INNER_W - 24 - sw - 60, 31), "波次: ", cn_font=F22, en_font=M22, fill=C_TEXT_GRAY)
        
        pw = F26.getlength(zone['point'])
        draw_text_mixed(zd, (INNER_W - 24 - sw - 60 - 30 - pw, 28), zone['point'], cn_font=F26, en_font=M26, fill=C_PRIMARY)
        draw_text_mixed(zd, (INNER_W - 24 - sw - 60 - 30 - pw - 60, 31), "积分: ", cn_font=F22, en_font=M22, fill=C_TEXT_GRAY)

        zy = ZH_H
        
        # Zone Body (Buffs & Team)
        for idx, bf in enumerate(zone['buffFights']):
            BODY_H = 172
            _draw_rounded_rect(z_img, 0, zy, INNER_W, zy + BODY_H, 0, (255,255,255,255))
            if idx < len(zone['buffFights']) - 1:
                zd.line([(0, zy + BODY_H - 1), (INNER_W, zy + BODY_H - 1)], fill=(240,240,240,255), width=1)
            
            bx = 24
            by = zy + (BODY_H - 80) // 2
            for sb in bf['supportBuffs']:
                _draw_rounded_rect(z_img, bx, by, bx + 80, by + 80, 4, (85, 98, 112, 255))
                if sb['iconB64']:
                    try:
                        b_icon = _b64_fit(sb['iconB64'], 34, 34)
                        z_img.alpha_composite(b_icon, (bx + 23, by + 12))
                    except: pass
                
                tw = F14.getlength(sb['name'])
                draw_text_mixed(zd, (bx + 40 - tw//2, by + 54), sb['name'], cn_font=F14, en_font=M14, fill=(255,255,255,255))
                bx += 90

            # Details
            draw_text_mixed(zd, (bx + 16, zy + 40), "积分: ", cn_font=F24, en_font=M24, fill=C_TEXT_GRAY)
            draw_text_mixed(zd, (bx + 16 + 60, zy + 36), bf['point'], cn_font=F28, en_font=M28, fill=C_PRIMARY)
            
            draw_text_mixed(zd, (bx + 16, zy + 88), "耗时: ", cn_font=F24, en_font=M24, fill=C_TEXT_GRAY)
            draw_text_mixed(zd, (bx + 16 + 60, zy + 84), f"{bf['fightTime']}S", cn_font=F28, en_font=M28, fill=C_PRIMARY)

            # Team Avatars
            tx = INNER_W - 24
            for char in reversed(bf['team']):
                tx -= 140
                _draw_rounded_rect(z_img, tx, zy + 16, tx + 140, zy + 156, 4, (240,240,240,255))
                if char['iconB64']:
                    try:
                        c_img = _b64_fit(char['iconB64'], 140, 140)
                        z_img.paste(c_img, (tx, zy + 16), _round_mask(140, 140, 4))
                    except: pass
                zd.rounded_rectangle([tx, zy + 16, tx + 140, zy + 156], radius=4, outline=(224, 229, 235, 255), width=2)
                
                g_col = (255,255,255,255)
                if char['gradeClass'] == 'sss-plus': g_col = (255, 152, 0, 255)
                elif char['gradeClass'] == 'sss': g_col = (230, 194, 90, 255)
                elif char['gradeClass'] == 'ss': g_col = (211, 47, 47, 255)

                draw_text_mixed(zd, (tx + 6, zy + 22), char['gradeDisplay'], cn_font=F20, en_font=M20, fill=g_col)
                if char['isPlus']:
                    pw = F20.getlength(char['gradeDisplay'])
                    draw_text_mixed(zd, (tx + 6 + pw + 2, zy + 18), "+", cn_font=F14, en_font=M14, fill=g_col)
                
                tx -= 10
            
            zy += BODY_H

        z_final = z_img.crop((0, 0, INNER_W, zy))
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + zy, 6, (255,255,255,255))
        canvas.alpha_composite(z_final, (PAD, y))
        d.rounded_rectangle([PAD, y, PAD + INNER_W, y + zy], radius=6, outline=C_BORDER, width=1)
        y += zy + 20

    out_rgb = canvas.crop((0, 0, W, y + 20)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()