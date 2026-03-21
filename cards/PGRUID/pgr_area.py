# 战双纷争战区 卡片渲染器 (PIL 版)

from __future__ import annotations

import base64
import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 从同一包内导入统一资源
from . import (
    F14, F20, F22, F24, F26, F28, F30, F44,
    M14, M20, M22, M24, M26, M28, M30, M44,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask
)

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2  # 920

C_BG_PAGE = (226, 235, 245, 255)    # #e2ebf5
C_PRIMARY = (24, 107, 181, 255)     # #186bb5
C_TEXT_DARK = (51, 51, 51, 255)     # #333333
C_TEXT_GRAY = (102, 102, 102, 255)  # #666666
C_BG_LIGHT = (240, 246, 250, 255)   # #f0f6fa
C_BORDER = (210, 224, 235, 255)     # #d2e0eb

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1

def _draw_rounded_rect(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, r: int, fill: tuple):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill)
    canvas.alpha_composite(block, (x0, y0))

def _draw_h_gradient(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, left_rgba: tuple, right_rgba: tuple, r: int = 0):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    grad_1d = Image.new("RGBA", (w, 1))
    for xi in range(w):
        t = xi / max(w - 1, 1)
        color = tuple(int(left_rgba[i] + (right_rgba[i] - left_rgba[i]) * t) for i in range(4))
        grad_1d.putpixel((xi, 0), color)
    grad = grad_1d.resize((w, h), Image.NEAREST)
    if r > 0:
        mask = _round_mask(w, h, r)
        new_a = ImageChops.multiply(grad.split()[3], mask)
        grad.putalpha(new_a)
    canvas.alpha_composite(grad, (x0, y0))

def _draw_v_gradient(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, top_rgba: tuple, bottom_rgba: tuple, r: int = 0):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    grad_1d = Image.new("RGBA", (1, h))
    for yi in range(h):
        t = yi / max(h - 1, 1)
        color = tuple(int(top_rgba[i] + (bottom_rgba[i] - top_rgba[i]) * t) for i in range(4))
        grad_1d.putpixel((0, yi), color)
    grad = grad_1d.resize((w, h), Image.NEAREST)
    if r > 0:
        mask = _round_mask(w, h, r)
        new_a = ImageChops.multiply(grad.split()[3], mask)
        grad.putalpha(new_a)
    canvas.alpha_composite(grad, (x0, y0))

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    data = {'zones': []}

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
    
    bottom_spans = soup.select('.header-row-bottom span')
    data['serverName'] = bottom_spans[0].get_text(strip=True) if len(bottom_spans)>0 else ""
    
    # 修复：防止双重 ID
    raw_id = bottom_spans[-1].get_text(strip=True) if len(bottom_spans)>2 else ""
    data['roleId'] = raw_id.replace("ID:", "").replace("ID", "").strip()

    t_bg = soup.select_one('.section-title-bar img')
    data['titleBgB64'] = t_bg['src'] if t_bg else ""

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
            rmask = _round_mask(INNER_W, H_H, 8)
            h_img.paste(hbg, (0,0), rmask)
        except: pass

    av_w, av_h = 170, 170
    av_x, av_y = 30, (H_H - av_h)//2
    
    # 1. 先画头像框 (底层 z-index: 1)
    if data['avatarBoxB64']:
        try:
            abox = _b64_fit(data['avatarBoxB64'], av_w, av_h)
            h_img.alpha_composite(abox, (av_x, av_y))
        except: pass

    # 2. 再画头像 (顶层 z-index: 2)
    if data['avatarB64']:
        try:
            aimg = _b64_fit(data['avatarB64'], 120, 120)
            cmask = Image.new("L", (120, 120), 0)
            ImageDraw.Draw(cmask).ellipse([0,0,119,119], fill=255)
            h_img.paste(aimg, (av_x + 25, av_y + 25), cmask)
        except: pass

    info_x = av_x + av_w + 20
    draw_text_mixed(hd, (info_x, av_y + 20), data['roleName'], cn_font=F44, en_font=M44, fill=(255,255,255,255))
    name_w = F44.getlength(data['roleName'])
    
    # 修复：动态计算“勋阶”框的宽度，防止 None 等长字符溢出
    rank_x = info_x + name_w + 16
    rank_val = data['rank']
    val_w = int(F22.getlength(rank_val))
    # 宽度计算：左侧边距(14) + "勋阶"(44) + 间距(6) + 值宽度(val_w) + 右侧边距(14)
    box_w = 64 + val_w + 14 
    
    _draw_rounded_rect(h_img, rank_x, av_y + 30, rank_x + box_w, av_y + 65, 4, (25,30,40,204))
    hd.rounded_rectangle([rank_x, av_y + 30, rank_x + box_w, av_y + 65], radius=4, outline=(80,100,120,153), width=1)
    draw_text_mixed(hd, (rank_x + 14, av_y + 30 + _ty(F22, "勋阶", 35)), "勋阶", cn_font=F22, en_font=M22, fill=(155,174,194,255))
    draw_text_mixed(hd, (rank_x + 64, av_y + 30 + _ty(F22, rank_val, 35)), rank_val, cn_font=F22, en_font=M22, fill=(229,141,60,255))

    bottom_y = av_y + 100
    draw_text_mixed(hd, (info_x, bottom_y), data['serverName'], cn_font=F24, en_font=M24, fill=(140,158,181,255))
    sw = F24.getlength(data['serverName'])
    draw_text_mixed(hd, (info_x + sw + 4, bottom_y), "|", cn_font=F24, en_font=M24, fill=(74,90,117,255))
    draw_text_mixed(hd, (info_x + sw + 20, bottom_y), f"ID:{data['roleId']}", cn_font=F24, en_font=M24, fill=(140,158,181,255))

    canvas.alpha_composite(h_img, (PAD, y))
    y += H_H + 20

    # --- Title Bar ---
    T_H = 60
    _draw_v_gradient(canvas, PAD, y, PAD + INNER_W, y + T_H, (24, 45, 75, 255), (15, 25, 45, 255), r=6)
    if data['titleBgB64']:
        try:
            tbg = _b64_fit(data['titleBgB64'], INNER_W, T_H)
            canvas.paste(tbg, (PAD, y), _round_mask(INNER_W, T_H, 6))
        except: pass
    draw_text_mixed(d, (PAD + 24, y + _ty(F26, "纷争战区", T_H)), "纷争战区", cn_font=F26, en_font=M26, fill=(255,255,255,255))
    y += T_H + 20

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