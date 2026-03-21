# 战双我的资料/角色信息 卡片渲染器 (PIL 重构精简版)

from __future__ import annotations
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageOps

# 从统一包中导入所有所需函数与字体 (F36, M36 已在 __init__ 预置)
from . import (
    F13, F14, F16, F18, F20, F22, F24, F26, F28, F30, F36, F44,
    M13, M14, M16, M18, M20, M22, M24, M26, M28, M30, M36, M44,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask,
    _ty, _draw_rounded_rect, truncate_text,
    parse_common_header, draw_common_header, draw_title_bar
)

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2

C_BG_PAGE = (226, 235, 245, 255)
C_STAT_VAL = (0, 102, 179, 255)
C_STAT_LBL = (85, 85, 85, 255)

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    # 1. 抽取基础公共 Header 数据
    data = parse_common_header(soup, html)

    # 2. 资料卡片
    data['stats'] = []
    for sc in soup.select('.stat-card'):
        bg = sc.select_one('.stat-card-bg')
        val = sc.select_one('.stat-value')
        lbl = sc.select_one('.stat-label')
        data['stats'].append({
            'bgB64': bg['src'] if bg else "",
            'value': val.get_text(strip=True) if val else "",
            'label': lbl.get_text(strip=True) if lbl else ""
        })

    # 提取公共的角色底图
    r_bg = soup.select_one('.char-role-bg')
    data['roleBgB64'] = r_bg['src'] if r_bg else ""

    data['charTitle'] = "角色信息"
    for tb in soup.select('.section-title-bar span'):
        t = tb.get_text(strip=True)
        if "角色信息" in t:
            data['charTitle'] = t

    # 角色列表
    data['characters'] = []
    for cc in soup.select('.char-card'):
        char = {}
        c_img = cc.select_one('.char-icon')
        char['iconB64'] = c_img['src'] if c_img else ""
        
        c_grade = cc.select_one('.char-grade-badge')
        char['gradeDisplay'] = c_grade.get_text(strip=True).replace("+", "") if c_grade else ""
        char['isPlus'] = cc.select_one('.plus-mark') is not None
        cls = c_grade.get('class', []) if c_grade else []
        if 'grade-sss-plus' in cls: char['gradeClass'] = 'sss-plus'
        elif 'grade-sss' in cls: char['gradeClass'] = 'sss'
        elif 'grade-ss' in cls: char['gradeClass'] = 'ss'
        else: char['gradeClass'] = 'none'

        c_fight = cc.select_one('.char-fight')
        char['fightAbility'] = c_fight.get_text(strip=True) if c_fight else "0"
        
        c_name = cc.select_one('.char-name')
        char['bodyName'] = c_name.get_text(strip=True) if c_name else ""
        
        char['elements'] = []
        for el in cc.select('.char-element-icon'):
            char['elements'].append({'iconB64': el['src'], 'name': el.get('title', '')})

        data['characters'].append(char)

    return data


# --- 主渲染逻辑 ---
def render(html: str) -> bytes:
    data = parse_html(html)
    
    stat_rows = (len(data['stats']) + 3) // 4
    char_rows = (len(data['characters']) + 4) // 5
    MAX_H = PAD + 200 + 20 + 80 + stat_rows * 112 + 80 + char_rows * 226 + PAD + 100
    
    canvas = Image.new("RGBA", (W, MAX_H), C_BG_PAGE)
    if data.get('contentBgB64'):
        try:
            bg_img = _b64_img(data['contentBgB64'])
            bg_img = ImageOps.fit(bg_img, (W, MAX_H), Image.LANCZOS)
            canvas.alpha_composite(bg_img)
        except: pass

    d = ImageDraw.Draw(canvas)
    y = PAD

    # --- Header 组件化调用 ---
    y = draw_common_header(canvas, d, data, PAD, INNER_W, y)

    # --- 我的资料 (Stats Grid) ---
    y = draw_title_bar(canvas, d, "我的资料", data.get('titleBgB64', ''), PAD, INNER_W, y)
    
    s_w = (INNER_W - 3 * 12) // 4
    s_h = 100
    for i, stat in enumerate(data['stats']):
        col = i % 4
        row = i // 4
        sx = PAD + col * (s_w + 12)
        sy = y + row * (s_h + 12)
        
        _draw_rounded_rect(canvas, sx, sy, sx + s_w, sy + s_h, 12, (255,255,255,255))
        if stat['bgB64']:
            try:
                s_img = _b64_fit(stat['bgB64'], s_w, s_h)
                canvas.paste(s_img, (sx, sy), _round_mask(s_w, s_h, 12))
            except: pass
            
        draw_text_mixed(d, (sx + 18, sy + 21), stat['value'], cn_font=F36, en_font=M36, fill=C_STAT_VAL)
        draw_text_mixed(d, (sx + 18, sy + 61), stat['label'], cn_font=F18, en_font=M18, fill=C_STAT_LBL)
        
    s_rows = (len(data['stats']) + 3) // 4
    if s_rows > 0:
        y += s_rows * s_h + (s_rows - 1) * 12 + 30

    # --- 角色信息 (Char Grid) ---
    y = draw_title_bar(canvas, d, data['charTitle'], data.get('titleBgB64', ''), PAD, INNER_W, y)

    shared_role_bg = None
    cw = (INNER_W - 4 * 10) // 5  # 176
    if data['roleBgB64']:
        try:
            shared_role_bg = _b64_fit(data['roleBgB64'], cw, cw)
        except: pass

    ch_img_h, ch_info_h, ch_border = cw, 36, 4
    ch_total_h = ch_img_h + ch_info_h + ch_border # 216

    for i, char in enumerate(data['characters']):
        col = i % 5
        row = i // 5
        cx = PAD + col * (cw + 10)
        cy = y + row * (ch_total_h + 10)
        
        c_card = Image.new("RGBA", (cw, ch_total_h), (255,255,255,0))
        cd = ImageDraw.Draw(c_card)
        
        if shared_role_bg:
            c_card.paste(shared_role_bg, (0, 0))
        else:
            cd.rectangle([0, 0, cw, ch_img_h], fill=(40,45,55,255))
            
        if char['iconB64']:
            try:
                icon_img = _b64_fit(char['iconB64'], cw, ch_img_h)
                c_card.alpha_composite(icon_img, (0, 0))
            except: pass
            
        g_col = (255,255,255,255)
        if char['gradeClass'] == 'sss-plus': g_col = (255, 152, 0, 255)
        elif char['gradeClass'] == 'sss': g_col = (230, 194, 90, 255)
        elif char['gradeClass'] == 'ss': g_col = (211, 47, 47, 255)
        
        draw_text_mixed(cd, (6, 12), char['gradeDisplay'], cn_font=F26, en_font=M26, fill=g_col)
        if char['isPlus']:
            gw = int(F26.getlength(char['gradeDisplay']))
            draw_text_mixed(cd, (6 + gw + 2, 8), "+", cn_font=F16, en_font=M16, fill=g_col)
            
        fw = int(M13.getlength(char['fightAbility'])) + 12
        cd.rounded_rectangle([cw - fw - 4, ch_img_h - 22, cw - 4, ch_img_h - 4], radius=4, fill=(0,0,0,140))
        draw_text_mixed(cd, (cw - fw + 2, ch_img_h - 20), char['fightAbility'], cn_font=F13, en_font=M13, fill=(255,255,255,255))
        
        cd.rectangle([0, ch_img_h, cw, ch_img_h + ch_info_h], fill=(27, 32, 40, 255))
        cd.rectangle([0, ch_img_h + ch_info_h, cw, ch_total_h], fill=(231, 92, 36, 255))
        
        ex = 6
        ey = ch_img_h + (ch_info_h - 24) // 2
        for el in char['elements']:
            if el['iconB64']:
                try:
                    el_img = _b64_fit(el['iconB64'], 24, 24)
                    c_card.alpha_composite(el_img, (ex, ey))
                except: pass
            ex += 28
            
        nw = cw - ex - 6
        short_name = truncate_text(char['bodyName'], F16, nw)
        draw_text_mixed(cd, (ex, ch_img_h + _ty(F16, short_name, ch_info_h)), short_name, cn_font=F16, en_font=M16, fill=(255,255,255,255))
        
        canvas.paste(c_card, (cx, cy), _round_mask(cw, ch_total_h, 4))

    c_rows = (len(data['characters']) + 4) // 5
    if c_rows > 0:
        y += c_rows * ch_total_h + (c_rows - 1) * 10
        
    out_rgb = canvas.crop((0, 0, W, y + PAD)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()