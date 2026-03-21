# 战双诺曼复兴战 卡片渲染器 (PIL 极致性能版)

from __future__ import annotations

import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops, ImageOps

# 从同一包内导入统一资源
from . import (
    F14, F16, F18, F20, F22, F24, F26, F28, F30, F44,
    M14, M16, M18, M20, M22, M24, M26, M28, M30, M44,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask
)

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2  # 920

C_BG_PAGE = (226, 235, 245, 255)    # #e2ebf5 (要求指定)
C_PRIMARY = (24, 107, 181, 255)     # #186bb5
C_TEXT_DARK = (51, 51, 51, 255)     # #333333
C_TEXT_GRAY = (102, 102, 102, 255)  # #666666
C_BG_LIGHT_BLUE = (232, 241, 248, 255) # #e8f1f8
C_BORDER = (201, 221, 236, 255)     # #c9ddec
C_CLEAR_BLUE = (26, 123, 201, 255)  # #1a7bc9

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1

def _draw_rounded_rect(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, r: int, fill: tuple, outline: tuple=None):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(block)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill)
    if outline:
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, outline=outline, width=1)
    canvas.alpha_composite(block, (x0, y0))

def _draw_v_gradient(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, top_rgba: tuple, bottom_rgba: tuple, r: int = 0):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    base = Image.new("RGBA", (1, 2))
    base.putpixel((0, 0), top_rgba)
    base.putpixel((0, 1), bottom_rgba)
    grad = base.resize((w, h), Image.BILINEAR)
    if r > 0:
        mask = _round_mask(w, h, r)
        grad.putalpha(ImageChops.multiply(grad.getchannel('A'), mask))
    canvas.alpha_composite(grad, (x0, y0))

def _invert_rgba_image(img: Image.Image) -> Image.Image:
    """模拟 CSS 的 filter: invert(1)，仅反转 RGB 通道，保留 Alpha 通道"""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    r, g, b, a = img.split()
    r = ImageOps.invert(r)
    g = ImageOps.invert(g)
    b = ImageOps.invert(b)
    return Image.merge("RGBA", (r, g, b, a))

def _draw_lock_icon(canvas: Image.Image, x: int, y: int):
    """纯代码绘制 SVG 锁图标"""
    d = ImageDraw.Draw(canvas)
    # 锁身
    d.rounded_rectangle([x + 3, y + 11, x + 21, y + 22], radius=2, outline=(153, 153, 153, 255), width=2)
    # 锁梁
    d.arc([x + 7, y + 2, x + 17, y + 12], start=180, end=0, fill=(153, 153, 153, 255), width=2)
    d.line([(x + 7, y + 7), (x + 7, y + 11)], fill=(153, 153, 153, 255), width=2)
    d.line([(x + 17, y + 7), (x + 17, y + 11)], fill=(153, 153, 153, 255), width=2)

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    data = {}

    bg_match = re.search(r"background-image:\s*url\(['\"]?(data:[^'\"]+)['\"]?\)", html)
    data['contentBgB64'] = bg_match.group(1) if bg_match else ""

    h_bg = soup.select_one('.header-bg')
    data['headerBgB64'] = h_bg['src'] if h_bg and h_bg.has_attr('src') else ""
    av = soup.select_one('.avatar-img')
    data['avatarB64'] = av['src'] if av else ""
    av_box = soup.select_one('.avatar-box')
    data['avatarBoxB64'] = av_box['src'] if av_box else ""
    
    data['roleName'] = soup.select_one('.header-name').get_text(strip=True) if soup.select_one('.header-name') else ""
    data['rank'] = soup.select_one('.level-val').get_text(strip=True) if soup.select_one('.level-val') else "0"
    
    server_node = soup.select_one('.header-server') or soup.select_one('.header-row-bottom span')
    data['serverName'] = server_node.get_text(strip=True) if server_node else ""
    uid_node = soup.select_one('.header-uid')
    raw_id = uid_node.get_text(strip=True) if uid_node else ""
    data['roleId'] = raw_id.replace("ID:", "").replace("ID", "").strip()

    t_bg = soup.select_one('.section-title-bar img')
    data['titleBgB64'] = t_bg['src'] if t_bg else ""

    # Summary
    lvl_icon = soup.select_one('.level-icon')
    data['levelIconB64'] = lvl_icon['src'] if lvl_icon else ""
    data['challengeArea'] = soup.select_one('.summary-info h2').get_text(strip=True) if soup.select_one('.summary-info h2') else ""
    data['challengeLevel'] = soup.select_one('.summary-info p').get_text(strip=True).replace("等级:", "").strip() if soup.select_one('.summary-info p') else ""

    # Mines
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

    # Teams
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
    if data['contentBgB64']:
        try:
            bg_img = _b64_img(data['contentBgB64'])
            bg_img = ImageOps.fit(bg_img, (W, MAX_H), Image.LANCZOS)
            canvas.alpha_composite(bg_img)
        except: pass

    d = ImageDraw.Draw(canvas)
    y = PAD

    # --- Header ---
    H_H = 200
    h_img = Image.new("RGBA", (INNER_W, H_H), (0,0,0,0))
    hd = ImageDraw.Draw(h_img)
    
    _draw_rounded_rect(h_img, 0, 0, INNER_W, H_H, 8, (20,25,35,255))
    if data['headerBgB64']:
        try:
            hbg = _b64_fit(data['headerBgB64'], INNER_W, H_H)
            h_img.paste(hbg, (0,0), _round_mask(INNER_W, H_H, 8))
        except: pass

    av_w, av_h = 170, 170
    av_x, av_y = 30, (H_H - av_h)//2
    
    if data['avatarBoxB64']:
        try:
            abox = _b64_fit(data['avatarBoxB64'], av_w, av_h)
            h_img.alpha_composite(abox, (av_x, av_y))
        except: pass

    if data['avatarB64']:
        try:
            aimg = _b64_fit(data['avatarB64'], 120, 120)
            cmask = Image.new("L", (120, 120), 0)
            ImageDraw.Draw(cmask).ellipse([0,0,119,119], fill=255)
            h_img.paste(aimg, (av_x + 25, av_y + 25), cmask)
        except: pass

    info_x = av_x + av_w + 20
    draw_text_mixed(hd, (info_x, av_y + 20), data['roleName'], cn_font=F44, en_font=M44, fill=(255,255,255,255))
    name_w = int(F44.getlength(data['roleName']))
    
    rank_x = info_x + name_w + 16
    rank_val = data['rank']
    val_w = int(F22.getlength(rank_val))
    box_w = 64 + val_w + 14 
    
    _draw_rounded_rect(h_img, rank_x, av_y + 30, rank_x + box_w, av_y + 65, 4, (25,30,40,204))
    hd.rounded_rectangle([rank_x, av_y + 30, rank_x + box_w, av_y + 65], radius=4, outline=(80,100,120,153), width=1)
    draw_text_mixed(hd, (rank_x + 14, av_y + 30 + _ty(F22, "勋阶", 35)), "勋阶", cn_font=F22, en_font=M22, fill=(155,174,194,255))
    draw_text_mixed(hd, (rank_x + 64, av_y + 30 + _ty(F22, rank_val, 35)), rank_val, cn_font=F22, en_font=M22, fill=(229,141,60,255))

    bottom_y = av_y + 100
    if data['serverName']:
        draw_text_mixed(hd, (info_x, bottom_y), data['serverName'], cn_font=F24, en_font=M24, fill=(140,158,181,255))
        sw = int(F24.getlength(data['serverName']))
        draw_text_mixed(hd, (info_x + sw + 4, bottom_y), "|", cn_font=F24, en_font=M24, fill=(74,90,117,255))
        draw_text_mixed(hd, (info_x + sw + 20, bottom_y), f"ID:{data['roleId']}", cn_font=F24, en_font=M24, fill=(140,158,181,255))
    else:
        draw_text_mixed(hd, (info_x, bottom_y), f"ID:{data['roleId']}", cn_font=F24, en_font=M24, fill=(140,158,181,255))

    canvas.alpha_composite(h_img, (PAD, y))
    y += H_H + 20

    def draw_title_bar(title):
        nonlocal y
        T_H = 60
        _draw_v_gradient(canvas, PAD, y, PAD + INNER_W, y + T_H, (24, 45, 75, 255), (15, 25, 45, 255), r=6)
        if data['titleBgB64']:
            try:
                tbg = _b64_fit(data['titleBgB64'], INNER_W, T_H)
                canvas.paste(tbg, (PAD, y), _round_mask(INNER_W, T_H, 6))
            except: pass
        draw_text_mixed(d, (PAD + 24, y + _ty(F26, title, T_H)), title, cn_font=F26, en_font=M26, fill=(255,255,255,255))
        y += T_H + 20

    # --- Summary ---
    draw_title_bar("诺曼复兴战")
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
    draw_title_bar("矿区进度")
    
    col_w = (INNER_W - 14) // 2
    row_count = (len(data['mines']) + 1) // 2
    mine_h = row_count * (54 + 4) + 8  # 预估矿区栏高度
    
    col1_x, col2_x = PAD, PAD + col_w + 14
    
    _draw_rounded_rect(canvas, col1_x, y, col1_x + col_w, y + mine_h, 6, C_BG_LIGHT_BLUE, outline=C_BORDER)
    _draw_rounded_rect(canvas, col2_x, y, col2_x + col_w, y + mine_h, 6, C_BG_LIGHT_BLUE, outline=C_BORDER)

    cy1, cy2 = y + 6, y + 6
    for i, mine in enumerate(data['mines']):
        is_col1 = (i < row_count)
        cx = col1_x if is_col1 else col2_x
        cy = cy1 if is_col1 else cy2
        
        # Mine Row
        _draw_rounded_rect(canvas, cx + 6, cy, cx + col_w - 6, cy + 54, 4, (255,255,255,255))
        
        # 矿区名
        draw_text_mixed(d, (cx + 20, cy + _ty(F20, mine['groupName'], 54)), mine['groupName'], cn_font=F20, en_font=M20, fill=C_TEXT_DARK)
        name_w = int(F20.getlength(mine['groupName']))
        
        # 状态标
        if not mine['isUnlock']:
            _draw_lock_icon(canvas, cx + 20 + name_w + 10, cy + 14)
        elif mine['pass']:
            draw_text_mixed(d, (cx + 20 + name_w + 10, cy + _ty(F18, "Clear", 54)), "Clear", cn_font=F18, en_font=M18, fill=C_CLEAR_BLUE)
            
        # 靠右 Buffs
        bx = cx + col_w - 6 - 14
        for buff in reversed(mine['buffs']):
            bx -= 36
            if buff['iconB64']:
                try:
                    b_img = _b64_fit(buff['iconB64'], 36, 36)
                    b_img = _invert_rgba_image(b_img) # 核心：原生 PIL 反转黑白滤镜
                    canvas.paste(b_img, (bx, cy + 9), _round_mask(36, 36, 18))
                except: pass
            
            if buff['isComplete']:
                # 绿色完成圆圈与划线
                d.ellipse([bx, cy + 9, bx + 36, cy + 45], outline=(76, 175, 80, 255), width=2)
                d.line([(bx + 6, cy + 39), (bx + 30, cy + 15)], fill=(76, 175, 80, 255), width=2)
            
            bx -= 6
            
        if is_col1: cy1 += 58
        else: cy2 += 58

    y += mine_h + 20

    # --- Teams ---
    if data['teams']:
        draw_title_bar("预设队伍")
        
        for team in data['teams']:
            TM_H = 224
            _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + TM_H, 6, C_BG_LIGHT_BLUE, outline=C_BORDER)
            
            # Team Header
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
            
            # Runes (Right aligned)
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
            
            # Avatars
            ax = PAD + 20
            ay = th_y + 48 + 14
            
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