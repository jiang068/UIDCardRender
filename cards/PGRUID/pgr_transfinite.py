# 战双历战映射 卡片渲染器 (PIL 重构精简版)

from __future__ import annotations
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops, ImageOps

# 从统一包中导入所有所需函数与字体
from . import (
    F14, F16, F18, F20, F22, F24, F26, F28, F30, F36, F44,
    M14, M16, M18, M20, M22, M24, M26, M28, M30, M36, M44,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask,
    _ty, _draw_rounded_rect,
    parse_common_header, draw_common_header, draw_title_bar
)

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2

C_BG_PAGE = (12, 14, 19, 255)          # #0c0e13
C_PRIMARY = (24, 107, 181, 255)        # #186bb5
C_TEXT_DARK = (51, 51, 51, 255)        # #333333
C_TEXT_GRAY = (102, 102, 102, 255)     # #666666
C_BG_LIGHT_BLUE = (232, 241, 248, 255) # #e8f1f8
C_BORDER = (201, 221, 236, 255)        # #c9ddec
C_HIGHLIGHT_BLUE = (26, 123, 201, 255) # #1a7bc9

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    # 1. 抽取基础公共 Header 数据
    data = parse_common_header(soup, html)

    # Info Card
    boss_icon = soup.select_one('.boss-icon')
    data['bossIconB64'] = boss_icon['src'] if boss_icon else ""
    data['challengeArea'] = soup.select_one('.info-text h2').get_text(strip=True) if soup.select_one('.info-text h2') else ""
    data['challengeDesc'] = soup.select_one('.info-text p').get_text(strip=True) if soup.select_one('.info-text p') else ""
    
    stat_val_node = soup.select_one('.stat-value')
    if stat_val_node:
        hl_node = stat_val_node.select_one('.hl')
        data['operatorCount'] = hl_node.get_text(strip=True) if hl_node else "0"
        if hl_node: hl_node.extract()
        data['operatorSuffix'] = stat_val_node.get_text(strip=True)
    else:
        data['operatorCount'] = "0"
        data['operatorSuffix'] = "/1500"

    # Data Rows
    data['dataRows'] = []
    for r in soup.select('.data-row'):
        data['dataRows'].append({
            'title': r.select_one('.data-title').get_text(strip=True),
            'val': r.select_one('.data-value').get_text(strip=True)
        })

    # Teams
    data['characters'] = []
    for cw in soup.select('.char-wrap'):
        char = {}
        c_img = cw.select_one('.avatar-card img')
        char['iconB64'] = c_img['src'] if c_img else ""
        
        c_grade = cw.select_one('.avatar-grade')
        char['gradeDisplay'] = c_grade.get_text(strip=True).replace("+", "") if c_grade else ""
        char['isPlus'] = cw.select_one('.plus-mark') is not None
        cls = c_grade.get('class', []) if c_grade else []
        if 'grade-sss-plus' in cls: char['gradeClass'] = 'sss-plus'
        elif 'grade-sss' in cls: char['gradeClass'] = 'sss'
        elif 'grade-ss' in cls: char['gradeClass'] = 'ss'
        else: char['gradeClass'] = 'none'
        
        char['bodyName'] = cw.select_one('.avatar-name').get_text(strip=True) if cw.select_one('.avatar-name') else ""
        data['characters'].append(char)

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
    y = draw_title_bar(canvas, d, "历战映射", data.get('titleBgB64', ''), PAD, INNER_W, y)

    # --- Info Card ---
    I_H = 118
    _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + I_H, 6, C_BG_LIGHT_BLUE, outline=C_BORDER)
    
    # Left
    if data['bossIconB64']:
        try:
            b_img = _b64_fit(data['bossIconB64'], 70, 70)
            b_alpha = b_img.split()[3] if b_img.mode == "RGBA" else Image.new("L", b_img.size, 255)
            b_img.putalpha(ImageChops.multiply(b_alpha, _round_mask(70, 70, 6)))
            canvas.alpha_composite(b_img, (PAD + 30, y + 24))
        except: pass
        
    draw_text_mixed(d, (PAD + 120, y + 28), data['challengeArea'], cn_font=F30, en_font=M30, fill=C_TEXT_DARK)
    draw_text_mixed(d, (PAD + 120, y + 66), data['challengeDesc'], cn_font=F20, en_font=M20, fill=C_TEXT_GRAY)
    
    # Center Divider
    div_x = PAD + INNER_W // 2
    d.line([(div_x, y + 34), (div_x, y + 84)], fill=(180, 200, 216, 255), width=1)
    
    # Right
    rx_center = div_x + INNER_W // 4
    draw_text_mixed(d, (rx_center - int(F22.getlength("算符"))//2, y + 28), "算符", cn_font=F22, en_font=M22, fill=C_TEXT_DARK)
    
    hw = int(F36.getlength(data['operatorCount']))
    sw = int(F20.getlength(data['operatorSuffix']))
    val_w = hw + sw
    vx = rx_center - val_w // 2
    draw_text_mixed(d, (vx, y + 60), data['operatorCount'], cn_font=F36, en_font=M36, fill=C_HIGHLIGHT_BLUE)
    draw_text_mixed(d, (vx + hw, y + 74), data['operatorSuffix'], cn_font=F20, en_font=M20, fill=C_TEXT_GRAY)
    
    y += I_H + 20

    # --- Data Rows ---
    for i, row in enumerate(data['dataRows']):
        R_H = 64
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + R_H, 4, (255,255,255,255))
        
        draw_text_mixed(d, (PAD + 28, y + _ty(F24, row['title'], R_H)), row['title'], cn_font=F24, en_font=M24, fill=C_TEXT_DARK)
        
        vw = int(F28.getlength(row['val']))
        draw_text_mixed(d, (PAD + INNER_W - 28 - vw, y + _ty(F28, row['val'], R_H)), row['val'], cn_font=F28, en_font=M28, fill=C_HIGHLIGHT_BLUE)
        
        y += R_H + 2
    y += 18

    # --- Team Section ---
    if data['characters']:
        TM_H = 230 # padding 28*2 + img 140 + text ~34
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + TM_H, 6, (255,255,255,255), outline=C_BORDER)
        
        cx = PAD + 34
        cy = y + 28
        
        for char in data['characters']:
            _draw_rounded_rect(canvas, cx, cy, cx + 140, cy + 140, 4, (240,240,240,255))
            d.rounded_rectangle([cx, cy, cx + 140, cy + 140], radius=4, outline=(224, 229, 235, 255), width=2)
            
            if char['iconB64']:
                try:
                    c_img = _b64_fit(char['iconB64'], 140, 140)
                    c_alpha = c_img.split()[3] if c_img.mode == "RGBA" else Image.new("L", c_img.size, 255)
                    c_img.putalpha(ImageChops.multiply(c_alpha, _round_mask(140, 140, 4)))
                    canvas.alpha_composite(c_img, (cx, cy))
                except: pass
                
            g_col = (255,255,255,255)
            if char['gradeClass'] == 'sss-plus': g_col = (255, 152, 0, 255)
            elif char['gradeClass'] == 'sss': g_col = (230, 194, 90, 255)
            elif char['gradeClass'] == 'ss': g_col = (211, 47, 47, 255)

            draw_text_mixed(d, (cx + 6, cy + 6), char['gradeDisplay'], cn_font=F20, en_font=M20, fill=g_col)
            if char['isPlus']:
                pw = int(F20.getlength(char['gradeDisplay']))
                draw_text_mixed(d, (cx + 6 + pw + 2, cy + 2), "+", cn_font=F14, en_font=M14, fill=g_col)
                
            nw = int(F22.getlength(char['bodyName']))
            draw_text_mixed(d, (cx + (140 - nw)//2, cy + 140 + 10), char['bodyName'], cn_font=F22, en_font=M22, fill=C_TEXT_DARK)
            
            cx += 140 + 20
            
        y += TM_H + 20

    out_rgb = canvas.crop((0, 0, W, y)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()