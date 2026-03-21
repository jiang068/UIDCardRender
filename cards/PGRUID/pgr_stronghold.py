# 战双诺曼复兴战 卡片渲染器 (PIL 重构精简版)

from __future__ import annotations
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops, ImageOps

# 从统一包中导入所有所需函数与滤镜
from . import (
    F14, F16, F18, F20, F22, F24, F26, F28, F30, F44,
    M14, M16, M18, M20, M22, M24, M26, M28, M30, M44,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask,
    _ty, _draw_rounded_rect, _invert_rgba_image,
    parse_common_header, draw_common_header, draw_title_bar
)

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2

C_BG_PAGE = (226, 235, 245, 255)
C_TEXT_DARK = (51, 51, 51, 255)
C_TEXT_GRAY = (102, 102, 102, 255)
C_BG_LIGHT_BLUE = (232, 241, 248, 255)
C_BORDER = (201, 221, 236, 255)
C_CLEAR_BLUE = (26, 123, 201, 255)

def _draw_lock_icon(canvas: Image.Image, x: int, y: int):
    """纯代码绘制 SVG 锁图标"""
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle([x + 3, y + 11, x + 21, y + 22], radius=2, outline=(153, 153, 153, 255), width=2)
    d.arc([x + 7, y + 2, x + 17, y + 12], start=180, end=0, fill=(153, 153, 153, 255), width=2)
    d.line([(x + 7, y + 7), (x + 7, y + 11)], fill=(153, 153, 153, 255), width=2)
    d.line([(x + 17, y + 7), (x + 17, y + 11)], fill=(153, 153, 153, 255), width=2)

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    # 1. 抽取基础公共 Header 数据
    data = parse_common_header(soup, html)

    # 2. Summary
    lvl_icon = soup.select_one('.level-icon')
    data['levelIconB64'] = lvl_icon['src'] if lvl_icon else ""
    data['challengeArea'] = soup.select_one('.summary-info h2').get_text(strip=True) if soup.select_one('.summary-info h2') else ""
    data['challengeLevel'] = soup.select_one('.summary-info p').get_text(strip=True).replace("等级:", "").strip() if soup.select_one('.summary-info p') else ""

    # 3. Mines
    data['mines'] = []
    for m_row in soup.select('.mine-row'):
        m_name = m_row.select_one('.mine-name')
        name_text = m_name.get_text(strip=True).replace("Clear", "").strip() if m_name else ""
        
        is_unlock = m_row.select_one('.mine-lock') is None
        is_pass = m_row.select_one('.mine-status') is not None
        
        buffs = []
        for bd in m_row.select('.buff-dot'):
            b_img = bd.select_one('img')
            buffs.append({
                'iconB64': b_img['src'] if b_img else "",
                'isComplete': bd.select_one('.buff-complete-mark') is not None
            })
            
        data['mines'].append({
            'groupName': name_text,
            'isUnlock': is_unlock,
            'pass': is_pass,
            'buffs': buffs
        })

    # 4. Teams
    data['teams'] = []
    for tc in soup.select('.team-card'):
        team = {}
        t_group = tc.select_one('.team-name-group')
        e_icon = t_group.select_one('.element-icon-sm') if t_group else None
        team['elementIconB64'] = e_icon['src'] if e_icon else ""
        team['elementName'] = t_group.get_text(strip=True).split('梯队')[0].strip() if t_group else ""
        
        b_icon = tc.select_one('.battery-icon')
        data['batteryIconB64'] = b_icon['src'] if b_icon else "" # 电池图标公共提取
        e_cost = tc.select_one('.energy-cost')
        team['electricNum'] = e_cost.get_text(strip=True) if e_cost else "0"

        r_group = tc.select_one('.rune-group')
        r_text = r_group.get_text(strip=True) if r_group else ""
        r_parts = r_text.split('·')
        team['runeName'] = r_parts[0].strip() if len(r_parts) > 0 else ""
        team['subRuneName'] = r_parts[1].strip() if len(r_parts) > 1 else ""
        
        r_icons = tc.select('.rune-icon-sm')
        team['runeIconB64'] = r_icons[0]['src'] if len(r_icons) > 0 else ""
        team['subRuneIconB64'] = r_icons[1]['src'] if len(r_icons) > 1 else ""

        team['characters'] = []
        for av in tc.select('.avatar-card'):
            char = {}
            c_img = av.select_one('img')
            char['iconB64'] = c_img['src'] if c_img else ""
            
            c_grade = av.select_one('.avatar-grade')
            char['gradeDisplay'] = c_grade.get_text(strip=True).replace("+", "") if c_grade else ""
            char['isPlus'] = av.select_one('.plus-mark') is not None
            cls = c_grade.get('class', []) if c_grade else []
            if 'grade-sss-plus' in cls: char['gradeClass'] = 'sss-plus'
            elif 'grade-sss' in cls: char['gradeClass'] = 'sss'
            elif 'grade-ss' in cls: char['gradeClass'] = 'ss'
            else: char['gradeClass'] = 'none'
            
            bp = av.select_one('.bp-bar')
            char['fightAbility'] = bp.get_text(strip=True) if bp else ""
            team['characters'].append(char)
            
        data['teams'].append(team)

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

    # --- Header 组件化调用 ---
    y = draw_common_header(canvas, d, data, PAD, INNER_W, y)

    # --- Summary ---
    y = draw_title_bar(canvas, d, "诺曼复兴战", data.get('titleBgB64', ''), PAD, INNER_W, y)
    
    S_H = 120
    _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + S_H, 6, C_BG_LIGHT_BLUE)
    d.rounded_rectangle([PAD, y, PAD + INNER_W, y + S_H], radius=6, outline=C_BORDER, width=1)
    
    if data['levelIconB64']:
        try:
            a_icon = _b64_fit(data['levelIconB64'], 60, 70)
            canvas.alpha_composite(a_icon, (PAD + 34, y + (S_H - 70)//2))
        except: pass
    
    draw_text_mixed(d, (PAD + 118, y + 30), data['challengeArea'], cn_font=F30, en_font=M30, fill=C_TEXT_DARK)
    draw_text_mixed(d, (PAD + 118, y + 68), f"等级: {data['challengeLevel']}", cn_font=F20, en_font=M20, fill=C_TEXT_GRAY)
    y += S_H + 20

    # --- Mine Grid ---
    y = draw_title_bar(canvas, d, "矿区进度", data.get('titleBgB64', ''), PAD, INNER_W, y)
    
    col_w = (INNER_W - 14) // 2
    row_count = (len(data['mines']) + 1) // 2
    mine_h = row_count * (54 + 4) + 8
    
    col1_x, col2_x = PAD, PAD + col_w + 14
    _draw_rounded_rect(canvas, col1_x, y, col1_x + col_w, y + mine_h, 6, C_BG_LIGHT_BLUE, outline=C_BORDER)
    _draw_rounded_rect(canvas, col2_x, y, col2_x + col_w, y + mine_h, 6, C_BG_LIGHT_BLUE, outline=C_BORDER)

    cy1, cy2 = y + 6, y + 6
    for i, mine in enumerate(data['mines']):
        is_col1 = (i < row_count)
        cx = col1_x if is_col1 else col2_x
        cy = cy1 if is_col1 else cy2
        
        _draw_rounded_rect(canvas, cx + 6, cy, cx + col_w - 6, cy + 54, 4, (255,255,255,255))
        draw_text_mixed(d, (cx + 20, cy + _ty(F20, mine['groupName'], 54)), mine['groupName'], cn_font=F20, en_font=M20, fill=C_TEXT_DARK)
        name_w = int(F20.getlength(mine['groupName']))
        
        if not mine['isUnlock']:
            _draw_lock_icon(canvas, cx + 20 + name_w + 10, cy + 14)
        elif mine['pass']:
            draw_text_mixed(d, (cx + 20 + name_w + 10, cy + _ty(F18, "Clear", 54)), "Clear", cn_font=F18, en_font=M18, fill=C_CLEAR_BLUE)
            
        bx = cx + col_w - 6 - 14
        for buff in reversed(mine['buffs']):
            bx -= 36
            if buff['iconB64']:
                try:
                    b_img = _b64_fit(buff['iconB64'], 36, 36)
                    b_img = _invert_rgba_image(b_img) # 直接调用包内工具函数反转黑白
                    canvas.paste(b_img, (bx, cy + 9), _round_mask(36, 36, 18))
                except: pass
            
            if buff['isComplete']:
                d.ellipse([bx, cy + 9, bx + 36, cy + 45], outline=(76, 175, 80, 255), width=2)
                d.line([(bx + 6, cy + 39), (bx + 30, cy + 15)], fill=(76, 175, 80, 255), width=2)
            bx -= 6
            
        if is_col1: cy1 += 58
        else: cy2 += 58

    y += mine_h + 20

    # --- Teams ---
    if data['teams']:
        y = draw_title_bar(canvas, d, "预设队伍", data.get('titleBgB64', ''), PAD, INNER_W, y)
        
        for team in data['teams']:
            TM_H = 224
            _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + TM_H, 6, C_BG_LIGHT_BLUE, outline=C_BORDER)
            
            th_y = y + 16
            tx = PAD + 20
            if team['elementIconB64']:
                try:
                    el_img = _b64_fit(team['elementIconB64'], 36, 36)
                    canvas.alpha_composite(el_img, (tx, th_y))
                except: pass
                tx += 46
                
            t_name = f"{team['elementName']}梯队"
            draw_text_mixed(d, (tx, th_y + _ty(F22, t_name, 36)), t_name, cn_font=F22, en_font=M22, fill=(56, 81, 112, 255))
            tx += int(F22.getlength(t_name)) + 16
            
            if data.get('batteryIconB64'):
                try:
                    bat_img = _b64_fit(data['batteryIconB64'], 24, 34)
                    canvas.alpha_composite(bat_img, (tx, th_y + 1))
                except: pass
                tx += 32
                
            draw_text_mixed(d, (tx, th_y + _ty(F24, team['electricNum'], 36)), team['electricNum'], cn_font=F24, en_font=M24, fill=C_CLEAR_BLUE)
            
            rx = PAD + INNER_W - 20
            if team['subRuneIconB64']:
                rx -= 30
                _draw_rounded_rect(canvas, rx, th_y + 3, rx + 30, th_y + 33, 6, (26, 123, 201, 38))
                try:
                    r_img = _b64_fit(team['subRuneIconB64'], 24, 24)
                    canvas.alpha_composite(r_img, (rx + 3, th_y + 6))
                except: pass
                rx -= 8
                
            if team['runeIconB64']:
                rx -= 30
                _draw_rounded_rect(canvas, rx, th_y + 3, rx + 30, th_y + 33, 6, (26, 123, 201, 38))
                try:
                    r_img = _b64_fit(team['runeIconB64'], 24, 24)
                    canvas.alpha_composite(r_img, (rx + 3, th_y + 6))
                except: pass
                rx -= 8
                
            r_name = team['runeName']
            if team['subRuneName']: r_name += f" · {team['subRuneName']}"
            r_w = int(F22.getlength(r_name))
            rx -= r_w
            draw_text_mixed(d, (rx, th_y + _ty(F22, r_name, 36)), r_name, cn_font=F22, en_font=M22, fill=C_TEXT_DARK)
            
            d.line([(PAD + 20, th_y + 48), (PAD + INNER_W - 20, th_y + 48)], fill=C_BORDER, width=1)
            
            ax, ay = PAD + 20, th_y + 48 + 14
            for char in team['characters']:
                _draw_rounded_rect(canvas, ax, ay, ax + 140, ay + 140, 4, (240,240,240,255))
                d.rounded_rectangle([ax, ay, ax + 140, ay + 140], radius=4, outline=(224, 229, 235, 255), width=2)
                
                if char['iconB64']:
                    try:
                        c_img = _b64_fit(char['iconB64'], 140, 140)
                        c_alpha = c_img.split()[3] if c_img.mode == "RGBA" else Image.new("L", c_img.size, 255)
                        c_img.putalpha(ImageChops.multiply(c_alpha, _round_mask(140, 140, 4)))
                        canvas.alpha_composite(c_img, (ax, ay))
                    except: pass
                    
                g_col = (255,255,255,255)
                if char['gradeClass'] == 'sss-plus': g_col = (255, 152, 0, 255)
                elif char['gradeClass'] == 'sss': g_col = (230, 194, 90, 255)
                elif char['gradeClass'] == 'ss': g_col = (211, 47, 47, 255)

                draw_text_mixed(d, (ax + 6, ay + 6), char['gradeDisplay'], cn_font=F20, en_font=M20, fill=g_col)
                if char['isPlus']:
                    pw = int(F20.getlength(char['gradeDisplay']))
                    draw_text_mixed(d, (ax + 6 + pw + 2, ay + 2), "+", cn_font=F14, en_font=M14, fill=g_col)
                    
                if char['fightAbility']:
                    bp_h = 30
                    _draw_rounded_rect(canvas, ax, ay + 140 - bp_h, ax + 140, ay + 140, 0, (30,30,30,191))
                    bp_w = int(F20.getlength(char['fightAbility']))
                    draw_text_mixed(d, (ax + (140 - bp_w)//2, ay + 140 - bp_h + _ty(F20, char['fightAbility'], bp_h)), char['fightAbility'], cn_font=F20, en_font=M20, fill=(255,255,255,255))
                
                ax += 152
            y += TM_H + 18

    out_rgb = canvas.crop((0, 0, W, y + 2)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()