# 战双角色面板 卡片渲染器 (PIL 重构精简版)

from __future__ import annotations
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageOps, ImageChops

# 从同一包内导入统一资源
from . import (
    F11, F12, F13, F14, F15, F16, F18, F20, F22, F24, F26, F30, F34, F44, F48,
    M11, M12, M13, M14, M15, M16, M18, M20, M22, M24, M26, M30, M34, M44, M48,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask,
    _ty, _draw_rounded_rect, _draw_clipped_rect,
    parse_common_header, draw_common_header, draw_title_bar
)

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2

C_BG_PAGE = (226, 235, 245, 255)
C_HEADER_DARK = (31, 49, 77, 255)
C_BG_LIGHT = (241, 244, 248, 255)
C_TEXT_MAIN = (43, 43, 43, 255)
C_TEXT_GRAY = (140, 147, 157, 255)
C_PRIMARY = (27, 115, 201, 255)
C_ACCENT_RED = (209, 61, 51, 255)
C_BORDER = (220, 227, 235, 255)

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    # 1. 抽取基础公共 Header 数据
    data = parse_common_header(soup, html)

    # 2. 角色头部信息
    c_img = soup.select_one('.char-portrait')
    data['charImgB64'] = c_img['src'] if c_img else ""
    c_name = soup.select_one('.char-name')
    data['charName'] = c_name.get_text(strip=True) if c_name else ""
    
    c_rank = soup.select_one('.char-rank')
    if c_rank:
        cls = c_rank.get('class', [])
        data['gradeDisplay'] = c_rank.get_text(strip=True).replace("+", "")
        data['isPlus'] = soup.select_one('.char-rank .plus-mark') is not None
        if 'grade-sss-plus' in cls: data['gradeClass'] = 'sss-plus'
        elif 'grade-sss' in cls: data['gradeClass'] = 'sss'
        elif 'grade-ss' in cls: data['gradeClass'] = 'ss'
        else: data['gradeClass'] = 'none'
    else:
        data['gradeDisplay'], data['isPlus'], data['gradeClass'] = "", False, "none"

    data['tags'] = [img['src'] for img in soup.select('.char-tag-icon')]
    data['fightAbility'] = soup.select_one('.combat-power-val').get_text(strip=True) if soup.select_one('.combat-power-val') else "0"

    # 3. 装备/辅助机/意识解析
    data['weapon'] = None
    data['partner'] = None
    data['chipResonances'] = []
    data['chipSuits'] = []
    data['chipExDamage'] = ""

    for panel in soup.select('.section-panel'):
        title_el = panel.select_one('.section-title')
        if not title_el: continue
        title_text = title_el.get_text(strip=True)

        if '武器' in title_text:
            wp_img = panel.select_one('.weapon-img-inner img')
            w_stars = panel.select_one('.red-bar-stars')
            w_name = panel.select_one('.item-name')
            weapon = {
                'iconB64': wp_img['src'] if wp_img else "",
                'stars': w_stars.get_text(strip=True) if w_stars else "",
                'name': w_name.get_text(strip=True) if w_name else "",
                'resonances': [], 'suitIconB64': "", 'overRunLevel': ""
            }
            for sf in panel.select('.sub-feature-item'):
                lbl = sf.select_one('.sub-feature-label').get_text(strip=True)
                icn = sf.select_one('.sub-feature-icon img')
                if '谐振' in lbl:
                    weapon['overRunLevel'] = lbl.replace("谐振", "").replace("级", "")
                    weapon['suitIconB64'] = icn['src'] if icn else ""
                else:
                    weapon['resonances'].append({'name': lbl, 'iconB64': icn['src'] if icn else ""})
            data['weapon'] = weapon

        elif '辅助机' in title_text:
            pt_img = panel.select_one('.weapon-img-inner img')
            p_stars = panel.select_one('.red-bar-stars')
            p_name = panel.select_one('.item-name')
            partner = {
                'iconB64': pt_img['src'] if pt_img else "",
                'grade': p_stars.get_text(strip=True) if p_stars else "",
                'name': p_name.get_text(strip=True) if p_name else "",
                'skills': []
            }
            main_skill = panel.select_one('.cub-skills')
            if main_skill:
                si = main_skill.select_one('.cub-skill-icon img')
                sn = main_skill.select_one('.cub-skill-name')
                sl = main_skill.select_one('.cub-skill-level')
                partner['skills'].append({
                    'name': sn.get_text(strip=True) if sn else "",
                    'level': sl.get_text(strip=True) if sl else "",
                    'iconB64': si['src'] if si else ""
                })
            for sub in panel.select('.cub-sub-skill-item'):
                si = sub.select_one('.cub-sub-icon img')
                sl = sub.select_one('.cub-skill-level')
                partner['skills'].append({'name': "", 'level': sl.get_text(strip=True) if sl else "", 'iconB64': si['src'] if si else ""})
            data['partner'] = partner

        elif '意识' in title_text:
            si_node = panel.select_one('.memory-set-info')
            if si_node:
                text = si_node.get_text(strip=True).replace("套装技能", "").replace("▶", "").strip()
                if text:
                    for p in [t.strip() for t in text.split("  ") if t.strip()]:
                        if "|" in p:
                            n, num = p.split("|")
                            data['chipSuits'].append({'name': n.strip(), 'num': num.strip()})
            
            ex_node = panel.select_one('.memory-buff')
            if ex_node:
                data['chipExDamage'] = ex_node.get_text(strip=True).replace("额外伤害加成：", "")

            for m_card in panel.select('.memory-card'):
                cr = {}
                m_num = m_card.select_one('.memory-num')
                cr['site'] = int(m_num.get_text(strip=True)) if m_num else 1
                cr['defend'] = m_card.select_one('.memory-awake') is not None
                
                m_img = m_card.select_one('.memory-portrait-area img')
                cr['chipIconB64'] = m_img['src'] if m_img else ""
                m_name = m_card.select_one('.memory-name')
                cr['chipName'] = m_name.get_text(strip=True) if m_name else ""
                
                slots = m_card.select('.res-slot')
                cr['superIconB64'], cr['superAwake'] = "", False
                if len(slots) > 0:
                    s_img = slots[0].select_one('img')
                    cr['superIconB64'] = s_img['src'] if s_img else ""
                    cr['superAwake'] = slots[0].select_one('.res-placeholder') is not None
                    
                cr['subIconB64'], cr['subAwake'] = "", False
                if len(slots) > 1:
                    s_img = slots[1].select_one('img')
                    cr['subIconB64'] = s_img['src'] if s_img else ""
                    cr['subAwake'] = slots[1].select_one('.res-placeholder') is not None
                    
                data['chipResonances'].append(cr)

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
    y = draw_title_bar(canvas, d, "角色详情", data.get('titleBgB64', ''), PAD, INNER_W, y)

    # --- 1. 角色头部 ---
    CH_H = 340
    _draw_clipped_rect(canvas, PAD, y, INNER_W, CH_H, fill=(255, 255, 255, 255), outline=C_BORDER, clip_size=14)

    if data['charImgB64']:
        try:
            c_img = _b64_img(data['charImgB64'])
            cw, ch = c_img.size
            th = int(CH_H * 1.3)
            tw = int(cw * (th / ch))
            c_img = c_img.resize((tw, th), Image.LANCZOS)
            temp_c = Image.new("RGBA", (INNER_W, CH_H), (0,0,0,0))
            temp_c.alpha_composite(c_img, (INNER_W - 20 - tw, (CH_H - th)//2))
            
            mask_clip = Image.new("L", (INNER_W, CH_H), 0)
            md = ImageDraw.Draw(mask_clip)
            md.polygon([(0, 0), (INNER_W, 0), (INNER_W, CH_H - 14), (INNER_W - 14, CH_H), (0, CH_H)], fill=255)
            
            temp_c.putalpha(ImageChops.multiply(temp_c.getchannel('A'), mask_clip))
            canvas.alpha_composite(temp_c, (PAD, y))
        except: pass

    cy = y + 28
    d.rectangle([PAD + 28, cy, PAD + 33, cy + 30], fill=C_ACCENT_RED)
    draw_text_mixed(d, (PAD + 42, cy), data['charName'], cn_font=F30, en_font=M30, fill=C_TEXT_MAIN)
    cy += 40

    g_col = (255,255,255,255)
    if data['gradeClass'] == 'sss-plus': g_col = (255, 152, 0, 255)
    elif data['gradeClass'] == 'sss': g_col = (230, 194, 90, 255)
    elif data['gradeClass'] == 'ss': g_col = (211, 47, 47, 255)

    draw_text_mixed(d, (PAD + 46, cy), data['gradeDisplay'], cn_font=F34, en_font=M34, fill=g_col)
    if data['isPlus']:
        pw = int(F34.getlength(data['gradeDisplay']))
        draw_text_mixed(d, (PAD + 46 + pw + 2, cy - 4), "+", cn_font=F22, en_font=M22, fill=g_col)
    cy += 44

    tx = PAD + 46
    for tag_b64 in data['tags']:
        try:
            tag_img = _b64_fit(tag_b64, 38, 38)
            _draw_rounded_rect(canvas, tx, cy, tx + 48, cy + 48, 10, (0, 0, 0, 89))
            canvas.alpha_composite(tag_img, (tx + 5, cy + 5))
        except: pass
        tx += 56
    cy += 68

    draw_text_mixed(d, (PAD + 46, cy), "战斗参数", cn_font=F18, en_font=M18, fill=C_TEXT_GRAY)
    cy += 24
    draw_text_mixed(d, (PAD + 46, cy), data['fightAbility'], cn_font=F48, en_font=M48, fill=C_PRIMARY)

    y += CH_H + 20

    # --- 辅助模块绘制（武器 / 辅助机） ---
    def draw_equip_panel(title, eq_data, is_partner=False):
        nonlocal y
        if not eq_data: return
        
        EQ_H = 240
        _draw_clipped_rect(canvas, PAD, y, INNER_W, EQ_H, fill=C_BG_LIGHT, outline=C_BORDER, clip_size=14)
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + 44, 0, C_HEADER_DARK)
        d.rectangle([PAD + 16, y + 12, PAD + 21, y + 32], fill=(59, 142, 237, 255))
        draw_text_mixed(d, (PAD + 31, y + _ty(F20, title, 44)), title, cn_font=F20, en_font=M20, fill=(255,255,255,255))

        ey = y + 60
        bx = PAD + 16
        
        _draw_rounded_rect(canvas, bx, ey, bx + 140, ey + 140, 0, (255,255,255,255))
        d.rectangle([bx, ey, bx + 140, ey + 140], outline=(224, 229, 235, 255), width=2)
        _draw_rounded_rect(canvas, bx + 5, ey + 5, bx + 135, ey + 135, 0, (244, 246, 249, 255))
        
        if eq_data['iconB64']:
            try:
                eq_img = _b64_fit(eq_data['iconB64'], 130, 130)
                canvas.alpha_composite(eq_img, (bx + 5, ey + 5))
            except: pass
            
        sup_col = (226, 43, 55, 255) if not is_partner else (229, 141, 60, 255)
        d.rectangle([bx + 5, ey + 115, bx + 135, ey + 135], fill=sup_col)
        draw_text_mixed(d, (bx + 8, ey + 92), "SUPPLY", cn_font=F18, en_font=M18, fill=sup_col)
        
        sw = int(F15.getlength(eq_data.get('stars') or eq_data.get('grade') or ""))
        draw_text_mixed(d, (bx + 135 - 5 - sw, ey + 116), eq_data.get('stars') or eq_data.get('grade') or "", cn_font=F15, en_font=M15, fill=(255,255,255,255))
        d.rectangle([bx + 10, ey + 121, bx + 15, ey + 129], fill=(255,255,255,255))
        d.rectangle([bx + 17, ey + 121, bx + 18, ey + 129], fill=(255,255,255,255))

        if not is_partner:
            d.polygon([(bx + 135, ey + 5), (bx + 107, ey + 5), (bx + 135, ey + 33)], fill=(38, 91, 164, 255))

        ex = bx + 158
        d.line([(ex, ey + 36), (PAD + INNER_W - 16, ey + 36)], fill=C_BORDER, width=1)
        draw_text_mixed(d, (ex, ey + 4), eq_data['name'], cn_font=F22, en_font=M22, fill=C_TEXT_MAIN)
        type_txt = "WEAPON" if not is_partner else "PARTNER"
        tw = int(F13.getlength(type_txt))
        draw_text_mixed(d, (PAD + INNER_W - 16 - tw, ey + 16), type_txt, cn_font=F13, en_font=M13, fill=(176, 184, 194, 255))

        ey += 44
        
        if not is_partner:
            rx = ex
            for res in eq_data['resonances']:
                _draw_rounded_rect(canvas, rx, ey, rx + 48, ey + 48, 0, (255,255,255,255))
                d.rectangle([rx, ey, rx + 48, ey + 48], outline=(221,221,221,255), width=1)
                if res['iconB64']:
                    try:
                        r_img = _b64_fit(res['iconB64'], 46, 46)
                        canvas.alpha_composite(r_img, (rx + 1, ey + 1))
                    except: pass
                draw_text_mixed(d, (rx + 24 - int(F15.getlength(res['name']))//2, ey + 54), res['name'], cn_font=F15, en_font=M15, fill=C_TEXT_MAIN)
                rx += 66
                
            if eq_data.get('suitIconB64'):
                _draw_rounded_rect(canvas, rx, ey, rx + 48, ey + 48, 0, (255,255,255,255))
                d.rectangle([rx, ey, rx + 48, ey + 48], outline=(221,221,221,255), width=1)
                try:
                    s_img = _b64_fit(eq_data['suitIconB64'], 46, 46)
                    canvas.alpha_composite(s_img, (rx + 1, ey + 1))
                except: pass
                lbl = f"谐振{eq_data['overRunLevel']}级"
                draw_text_mixed(d, (rx + 24 - int(F15.getlength(lbl))//2, ey + 54), lbl, cn_font=F15, en_font=M15, fill=C_TEXT_MAIN)
        
        else:
            if eq_data['skills']:
                s1 = eq_data['skills'][0]
                _draw_rounded_rect(canvas, ex, ey, PAD + INNER_W - 16, ey + 60, 6, (232, 236, 239, 255))
                if s1['iconB64']:
                    try:
                        s_img = _b64_fit(s1['iconB64'], 40, 40)
                        canvas.paste(s_img, (ex + 14, ey + 10), _round_mask(40, 40, 20))
                    except: pass
                draw_text_mixed(d, (ex + 66, ey + 10), s1['name'], cn_font=F16, en_font=M16, fill=C_TEXT_MAIN)
                draw_text_mixed(d, (ex + 66, ey + 34), s1['level'], cn_font=F14, en_font=M14, fill=C_PRIMARY)
                
                if len(eq_data['skills']) > 1:
                    sx = ex + int(F16.getlength(s1['name'])) + 90
                    for sub in eq_data['skills'][1:]:
                        if sub['iconB64']:
                            try:
                                sub_img = _b64_fit(sub['iconB64'], 44, 44)
                                canvas.paste(sub_img, (sx, ey + 8), _round_mask(44, 44, 22))
                            except: pass
                        draw_text_mixed(d, (sx + 48, ey + 22), sub['level'], cn_font=F14, en_font=M14, fill=C_PRIMARY)
                        sx += 90

        y += EQ_H + 20

    draw_equip_panel("武器", data['weapon'], is_partner=False)
    draw_equip_panel("辅助机", data['partner'], is_partner=True)

    # --- 3. 意识 ---
    if data['chipResonances']:
        card_w = (INNER_W - 32 - 5 * 6) // 6
        row_h = card_w + 104
        grid_rows = (len(data['chipResonances']) + 5) // 6 
        MEM_H = 44 + 16 + (30 if data['chipSuits'] else 0) + (24 if data['chipExDamage'] else 0) + grid_rows * row_h + 16
        
        _draw_clipped_rect(canvas, PAD, y, INNER_W, MEM_H, fill=C_BG_LIGHT, outline=C_BORDER, clip_size=14)
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + 44, 0, C_HEADER_DARK)
        d.rectangle([PAD + 16, y + 12, PAD + 21, y + 32], fill=(59, 142, 237, 255))
        draw_text_mixed(d, (PAD + 31, y + _ty(F20, "意识", 44)), "意识", cn_font=F20, en_font=M20, fill=(255,255,255,255))

        my = y + 60
        if data['chipSuits']:
            tx = PAD + 16
            draw_text_mixed(d, (tx, my), "套装技能", cn_font=F18, en_font=M18, fill=C_TEXT_MAIN)
            tx += int(F18.getlength("套装技能")) + 6
            d.polygon([(tx, my+4), (tx+8, my+10), (tx, my+16)], fill=C_TEXT_MAIN)
            tx += 14
            for cs in data['chipSuits']:
                draw_text_mixed(d, (tx, my), f"{cs['name']} | {cs['num']}", cn_font=F18, en_font=M18, fill=C_TEXT_MAIN)
                tx += int(F18.getlength(f"{cs['name']} | {cs['num']}")) + 16
            my += 30
            
        if data['chipExDamage']:
            draw_text_mixed(d, (PAD + 16, my), f"额外伤害加成：{data['chipExDamage']}", cn_font=F16, en_font=M16, fill=C_TEXT_GRAY)
            my += 24

        bx = PAD + 16
        
        for i, cr in enumerate(data['chipResonances']):
            row = i // 6
            col = i % 6
            cx = bx + col * (card_w + 6)
            cy = my + row * row_h
            
            _draw_rounded_rect(canvas, cx, cy, cx + card_w, cy + card_w + 94, 3, (255,255,255,255))
            d.rounded_rectangle([cx, cy, cx + card_w, cy + card_w + 94], radius=3, outline=(208, 215, 224, 255), width=1)
            
            if cr['chipIconB64']:
                try:
                    c_img = _b64_fit(cr['chipIconB64'], card_w, card_w)
                    canvas.alpha_composite(c_img, (cx, cy))
                except: pass
                
            _draw_rounded_rect(canvas, cx + 3, cy + 3, cx + 20, cy + 18, 2, (0,0,0,153))
            draw_text_mixed(d, (cx + 5, cy + 3), f"{cr['site']:02d}", cn_font=F11, en_font=M11, fill=(255,255,255,255))
            
            if cr['defend']:
                d.polygon([(cx + card_w - 3, cy + 3), (cx + card_w - 11, cy + 3), (cx + card_w - 7, cy + 13)], fill=(255, 32, 32, 255))
                
            _draw_rounded_rect(canvas, cx, cy + card_w, cx + card_w, cy + card_w + 94, 0, (248, 250, 252, 255))
            tw = int(F11.getlength(cr['chipName']))
            draw_text_mixed(d, (cx + (card_w - tw)//2, cy + card_w + 4), cr['chipName'], cn_font=F11, en_font=M11, fill=C_TEXT_MAIN)
            
            r_w = (card_w - 8 - 3) // 2
            rx = cx + 4
            ry = cy + card_w + 22
            
            _draw_rounded_rect(canvas, rx, ry, rx + r_w, ry + r_w, 0, (255,255,255,255))
            d.rectangle([rx, ry, rx + r_w, ry + r_w], outline=(238,238,238,255), width=1)
            if cr['superIconB64']:
                try:
                    s_img = _b64_fit(cr['superIconB64'], r_w-4, r_w-4)
                    canvas.alpha_composite(s_img, (rx + 2, ry + 2))
                except: pass
            elif cr['superAwake']:
                draw_text_mixed(d, (rx + r_w//2 - 6, ry + r_w//2 - 6), "✓", cn_font=F12, en_font=M12, fill=C_ACCENT_RED)
                
            rx += r_w + 3
            _draw_rounded_rect(canvas, rx, ry, rx + r_w, ry + r_w, 0, (255,255,255,255))
            d.rectangle([rx, ry, rx + r_w, ry + r_w], outline=(238,238,238,255), width=1)
            if cr['subIconB64']:
                try:
                    s_img = _b64_fit(cr['subIconB64'], r_w-4, r_w-4)
                    canvas.alpha_composite(s_img, (rx + 2, ry + 2))
                except: pass
            elif cr['subAwake']:
                draw_text_mixed(d, (rx + r_w//2 - 6, ry + r_w//2 - 6), "✓", cn_font=F12, en_font=M12, fill=C_ACCENT_RED)

        y += MEM_H + 20

    out_rgb = canvas.crop((0, 0, W, y)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()