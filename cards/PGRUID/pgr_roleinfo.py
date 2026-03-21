# 战双我的资料/角色信息 卡片渲染器 (PIL 极致性能版)

from __future__ import annotations

import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 从同一包内导入统一资源
from . import (
    F13, F14, F16, F18, F20, F22, F24, F26, F28, F30, F44, get_font,
    M13, M14, M16, M18, M20, M22, M24, M26, M28, M30, M44,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask
)

# 补充特调大字号
F36 = get_font(36, family='cn')
M36 = get_font(36, family='mono')

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2  # 920

C_BG_PAGE = (226, 235, 245, 255)    # #e2ebf5
C_PRIMARY = (24, 107, 181, 255)     # #186bb5
C_TEXT_MAIN = (43, 43, 43, 255)     # #2b2b2b
C_TEXT_GRAY = (140, 147, 157, 255)  # #8c939d
C_STAT_VAL = (0, 102, 179, 255)     # #0066b3
C_STAT_LBL = (85, 85, 85, 255)      # #555555

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

def truncate_text(text: str, font, max_w: int) -> str:
    if font.getlength(text) <= max_w:
        return text
    while text and font.getlength(text + '...') > max_w:
        text = text[:-1]
    return text + '...'

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    data = {}

    # 背景
    bg_match = re.search(r"background-image:\s*url\(['\"]?(data:[^'\"]+)['\"]?\)", html)
    data['contentBgB64'] = bg_match.group(1) if bg_match else ""

    # Header
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

    # 资料卡片
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

    # 提取公共的角色底图，避免每个角色解一次
    r_bg = soup.select_one('.char-role-bg')
    data['roleBgB64'] = r_bg['src'] if r_bg else ""

    # 解析角色数量文本
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
    
    # 动态计算所需高度，防止大数量角色越界
    stat_rows = (len(data['stats']) + 3) // 4
    char_rows = (len(data['characters']) + 4) // 5
    MAX_H = PAD + 200 + 20 + 80 + stat_rows * 112 + 80 + char_rows * 226 + PAD + 100
    
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
    H_H = 242
    h_img = Image.new("RGBA", (INNER_W, H_H), (0,0,0,0))
    hd = ImageDraw.Draw(h_img)
    
    _draw_rounded_rect(h_img, 0, 0, INNER_W, H_H, 8, (20,25,35,255))
    if data['headerBgB64']:
        try:
            hbg = _b64_fit(data['headerBgB64'], INNER_W, H_H)
            h_img.paste(hbg, (0,0), _round_mask(INNER_W, H_H, 8))
        except: pass

    av_w, av_h = 170, 170
    av_x, av_y = 36, (H_H - av_h)//2
    
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

    info_x = av_x + av_w + 30
    draw_text_mixed(hd, (info_x, av_y + 22), data['roleName'], cn_font=F44, en_font=M44, fill=(255,255,255,255))
    name_w = int(F44.getlength(data['roleName']))
    
    rank_x = info_x + name_w + 16
    rank_val = data['rank']
    val_w = int(F22.getlength(rank_val))
    box_w = 64 + val_w + 14 
    
    _draw_rounded_rect(h_img, rank_x, av_y + 32, rank_x + box_w, av_y + 67, 4, (25,30,40,204))
    hd.rounded_rectangle([rank_x, av_y + 32, rank_x + box_w, av_y + 67], radius=4, outline=(80,100,120,153), width=1)
    draw_text_mixed(hd, (rank_x + 14, av_y + 32 + _ty(F22, "勋阶", 35)), "勋阶", cn_font=F22, en_font=M22, fill=(155,174,194,255))
    draw_text_mixed(hd, (rank_x + 64, av_y + 32 + _ty(F22, rank_val, 35)), rank_val, cn_font=F22, en_font=M22, fill=(229,141,60,255))

    bottom_y = av_y + 104
    if data['serverName']:
        draw_text_mixed(hd, (info_x, bottom_y), data['serverName'], cn_font=F24, en_font=M24, fill=(140,158,181,255))
        sw = int(F24.getlength(data['serverName']))
        draw_text_mixed(hd, (info_x + sw + 4, bottom_y), "|", cn_font=F24, en_font=M24, fill=(74,90,117,255))
        draw_text_mixed(hd, (info_x + sw + 20, bottom_y), f"ID:{data['roleId']}", cn_font=F24, en_font=M24, fill=(140,158,181,255))
    else:
        draw_text_mixed(hd, (info_x, bottom_y), f"ID:{data['roleId']}", cn_font=F24, en_font=M24, fill=(140,158,181,255))

    canvas.alpha_composite(h_img, (PAD, y))
    y += H_H + 30

    # --- 渲染标题条通用函数 ---
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

    # --- 我的资料 (Stats Grid) ---
    draw_title_bar("我的资料")
    
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
            
        # 居中对齐内容
        draw_text_mixed(d, (sx + 18, sy + 21), stat['value'], cn_font=F36, en_font=M36, fill=C_STAT_VAL)
        draw_text_mixed(d, (sx + 18, sy + 61), stat['label'], cn_font=F18, en_font=M18, fill=C_STAT_LBL)
        
    s_rows = (len(data['stats']) + 3) // 4
    if s_rows > 0:
        y += s_rows * s_h + (s_rows - 1) * 12 + 30

    # --- 角色信息 (Char Grid) ---
    draw_title_bar(data['charTitle'])

    # 预加载角色底图
    shared_role_bg = None
    cw = (INNER_W - 4 * 10) // 5  # 176
    if data['roleBgB64']:
        try:
            shared_role_bg = _b64_fit(data['roleBgB64'], cw, cw)
        except: pass

    ch_img_h = cw
    ch_info_h = 36
    ch_border = 4
    ch_total_h = ch_img_h + ch_info_h + ch_border # 216

    for i, char in enumerate(data['characters']):
        col = i % 5
        row = i // 5
        cx = PAD + col * (cw + 10)
        cy = y + row * (ch_total_h + 10)
        
        c_card = Image.new("RGBA", (cw, ch_total_h), (255,255,255,0))
        cd = ImageDraw.Draw(c_card)
        
        # 1. 角色底图与图标
        if shared_role_bg:
            c_card.paste(shared_role_bg, (0, 0))
        else:
            cd.rectangle([0, 0, cw, ch_img_h], fill=(40,45,55,255))
            
        if char['iconB64']:
            try:
                icon_img = _b64_fit(char['iconB64'], cw, ch_img_h)
                c_card.alpha_composite(icon_img, (0, 0))
            except: pass
            
        # 2. 品阶渐变字
        g_col = (255,255,255,255)
        if char['gradeClass'] == 'sss-plus': g_col = (255, 152, 0, 255)
        elif char['gradeClass'] == 'sss': g_col = (230, 194, 90, 255)
        elif char['gradeClass'] == 'ss': g_col = (211, 47, 47, 255)
        
        draw_text_mixed(cd, (6, 12), char['gradeDisplay'], cn_font=F26, en_font=M26, fill=g_col)
        if char['isPlus']:
            gw = int(F26.getlength(char['gradeDisplay']))
            draw_text_mixed(cd, (6 + gw + 2, 8), "+", cn_font=F16, en_font=M16, fill=g_col)
            
        # 3. 右下角战力小黑标
        fw = int(M13.getlength(char['fightAbility'])) + 12
        cd.rounded_rectangle([cw - fw - 4, ch_img_h - 22, cw - 4, ch_img_h - 4], radius=4, fill=(0,0,0,140))
        draw_text_mixed(cd, (cw - fw + 2, ch_img_h - 20), char['fightAbility'], cn_font=F13, en_font=M13, fill=(255,255,255,255))
        
        # 4. 底部信息栏
        cd.rectangle([0, ch_img_h, cw, ch_img_h + ch_info_h], fill=(27, 32, 40, 255))
        cd.rectangle([0, ch_img_h + ch_info_h, cw, ch_total_h], fill=(231, 92, 36, 255))
        
        # 5. 元素图标 + 角色名
        ex = 6
        ey = ch_img_h + (ch_info_h - 24) // 2
        for el in char['elements']:
            if el['iconB64']:
                try:
                    el_img = _b64_fit(el['iconB64'], 24, 24)
                    c_card.alpha_composite(el_img, (ex, ey))
                except: pass
            ex += 28
            
        # 智能截断文本，防止超长
        nw = cw - ex - 6
        short_name = truncate_text(char['bodyName'], F16, nw)
        draw_text_mixed(cd, (ex, ch_img_h + _ty(F16, short_name, ch_info_h)), short_name, cn_font=F16, en_font=M16, fill=(255,255,255,255))
        
        # 将完成的角色卡片贴到主画布并进行切角
        canvas.paste(c_card, (cx, cy), _round_mask(cw, ch_total_h, 4))

    c_rows = (len(data['characters']) + 4) // 5
    if c_rows > 0:
        y += c_rows * ch_total_h + (c_rows - 1) * 10
        
    out_rgb = canvas.crop((0, 0, W, y + PAD)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()