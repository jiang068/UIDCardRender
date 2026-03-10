# 明日方舟：终末地 武器图鉴卡片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 避免循环导入，直接引入工具函数并局部生成字体
from . import get_font, draw_text_mixed, _b64_img, _b64_fit

F12 = get_font(12, family='cn')
F14 = get_font(14, family='cn')
F15 = get_font(15, family='cn')
F16 = get_font(16, family='cn')
F18 = get_font(18, family='cn')
F64 = get_font(64, family='cn')

M12 = get_font(12, family='mono')
M14 = get_font(14, family='mono')
M16 = get_font(16, family='mono')
M20 = get_font(20, family='mono')

O14 = get_font(14, family='oswald')
O16 = get_font(16, family='oswald')
O32 = get_font(32, family='oswald')

# 画布基础属性
W = 1000
PAD = 50
INNER_W = W - PAD * 2

# 颜色定义
C_BG = (15, 16, 20, 255)
C_ACCENT = (255, 230, 0, 255)
C_TEXT = (255, 255, 255, 255)
C_SUBTEXT = (139, 139, 139, 255)
C_CARD_BG = (20, 21, 24, 230)


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg": "", 
        "end_logo": "",
        "name": "未知武器",
        "rarity": 0,
        "type_tag": "",
        "desc": "",
        "acquisition": "",
        "passive": None,
        "weapon_img": "",
        "stats": []
    }

    # 背景与 Logo
    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg"] = bg_el.get("src", "")
    logo_el = soup.select_one(".footer-logo")
    if logo_el: data["end_logo"] = logo_el.get("src", "")

    # Header
    name_el = soup.select_one(".weapon-name")
    if name_el: data["name"] = name_el.get_text(strip=True)
    
    data["rarity"] = len(soup.select(".rarity-star"))
    
    type_el = soup.select_one(".type-tag span")
    if type_el: data["type_tag"] = type_el.get_text(strip=True)
        
    # Top Row
    desc_el = soup.select_one(".top-row .desc-text")
    if desc_el: data["desc"] = desc_el.get_text(strip=True)
        
    acq_el = soup.select_one(".top-row div[style*='font-size:13px']")
    if acq_el: data["acquisition"] = acq_el.get_text(strip=True).replace("[获取方式]", "").strip()
        
    pb_el = soup.select_one(".passive-block")
    if pb_el:
        p_name = pb_el.select_one(".passive-name").get_text(strip=True) if pb_el.select_one(".passive-name") else ""
        p_desc = pb_el.select_one(".desc-text").get_text(strip=True) if pb_el.select_one(".desc-text") else ""
        data["passive"] = {"name": p_name, "desc": p_desc}
        
    img_el = soup.select_one(".weapon-img-small")
    if img_el: data["weapon_img"] = img_el.get("src", "")
        
    # Stats
    for st in soup.select(".stats-grid .stat-item"):
        lbl = st.select_one(".stat-label").get_text(strip=True) if st.select_one(".stat-label") else ""
        main_val = st.select_one(".stat-main").get_text(strip=True) if st.select_one(".stat-main") else ""
        sub_el = st.select_one(".stat-sub")
        sub_val = sub_el.get_text(strip=True).replace("MAX:", "").strip() if sub_el else ""
        
        is_full = "full-width" in st.get("class", [])
        data["stats"].append({
            "label": lbl, "main": main_val, "max": sub_val, "full": is_full
        })

    return data


def draw_bg(canvas: Image.Image, w: int, h: int, bg_src: str):
    sw, sh = w // 10, h // 10
    cx, cy = int(sw * 0.5), int(sh * 0.3)
    grad = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    max_dist = math.hypot(max(cx, sw - cx), max(cy, sh - cy))
    
    for y in range(sh):
        for x in range(sw):
            dist = math.hypot(x - cx, y - cy)
            ratio = min(dist / max_dist, 1.0)
            r = int(30 + (15 - 30) * ratio)
            g = int(31 + (16 - 31) * ratio)
            b = int(36 + (20 - 36) * ratio)
            grad.putpixel((x, y), (r, g, b, 255))
            
    canvas.alpha_composite(grad.resize((w, h), Image.Resampling.LANCZOS))
    
    if bg_src:
        try:
            bg_img = _b64_fit(bg_src, w, h).convert("RGBA")
            bg_img.putalpha(Image.new("L", (w, h), 38)) # opacity 0.15
            canvas.alpha_composite(bg_img)
        except Exception: pass

    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    grid_c = (255, 255, 255, 8) 
    for x in range(0, w, 50): gd.line([(x, 0), (x, h)], fill=grid_c, width=1)
    for y in range(0, h, 50): gd.line([(0, y), (w, y)], fill=grid_c, width=1)
    
    mask = Image.new("L", (w, h), 255)
    md = ImageDraw.Draw(mask)
    fade_h = int(h * 0.4)
    for y in range(fade_h, h):
        alpha = int(255 * (1 - min((y - fade_h) / (h * 0.6), 1.0)))
        md.line([(0, y), (w, y)], fill=alpha)
    grid.putalpha(mask)
    canvas.alpha_composite(grid)


def wrap_text(text: str, font, max_width: int) -> list[str]:
    lines = []
    line = ""
    for char in text:
        if font.getlength(line + char) <= max_width:
            line += char
        else:
            lines.append(line)
            line = char
    if line:
        lines.append(line)
    return lines


def draw_section_title(d: ImageDraw.ImageDraw, x: int, y: int, title_cn: str, title_en: str, width: int):
    draw_text_mixed(d, (x, y), title_cn, cn_font=F18, en_font=F18, fill=C_ACCENT)
    d.line([(x, y + 25), (x + width, y + 25)], fill=(255, 255, 255, 25), width=1)
    # Right align EN text
    en_w = int(M12.getlength(title_en))
    draw_text_mixed(d, (x + width - en_w, y + 4), title_en, cn_font=M12, en_font=M12, fill=C_SUBTEXT)
    return y + 40


def render(html: str) -> bytes:
    data = parse_html(html)
    
    # ---------------- 1. 高度预计算 ----------------
    cur_y = PAD
    
    # Header
    cur_y += 30 + 66 + 30 + 20 # stars + name + tag + border/padding
    
    # Top Row
    top_w = INNER_W - 280 - 30 # Data card width
    text_w = top_w - 50 # Inner text width
    
    data_h = 25 * 2 + 40 # padding + section_title
    
    desc_lines = wrap_text(data["desc"], F15, text_w)
    data_h += len(desc_lines) * 24
    
    if data["acquisition"]:
        data_h += 10 + 20 # mt + text height
        
    if data["passive"]:
        data_h += 15 + 30 + 25 # mt + pad + title
        p_lines = wrap_text(data["passive"]["desc"], F14, text_w - 30)
        data_h += len(p_lines) * 22
        
    top_h = max(data_h, 280 + 50) # min height to match image box
    cur_y += top_h + 30
    
    # Stats Grid
    stat_h = 25 * 2 + 40 # card pad + title
    s_rows = 1
    if len(data["stats"]) > 0:
        # layout: 1st row has max 3 items. subsequent items might be full width
        row_items = 0
        for st in data["stats"]:
            if st["full"]:
                s_rows += 1
                row_items = 0
            else:
                row_items += 1
                if row_items > 3:
                    s_rows += 1
                    row_items = 1
    stat_h += s_rows * 90 + max(0, s_rows - 1) * 20
    cur_y += stat_h + 30
    
    # Footer
    cur_y += 70 + 50 # footer + extra pad
    total_h = max(cur_y, 800)
    
    # ---------------- 2. 实际绘制 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h, data["bg"])
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    
    # === Header ===
    for i in range(data["rarity"]):
        cx = PAD + i * 26
        d.ellipse([cx, y+4, cx + 18, y + 22], fill=C_ACCENT)
        d.ellipse([cx + 3, y + 7, cx + 15, y + 19], fill=(255, 204, 0, 255))
    y += 30
    
    draw_text_mixed(d, (PAD, y - 5), data["name"], cn_font=F64, en_font=F64, fill=C_TEXT)
    y += 70
    
    # Type Tag
    tt_w = int(M20.getlength(data["type_tag"])) + 30
    d.polygon([(PAD + 8, y), (PAD + tt_w + 8, y), (PAD + tt_w - 8, y + 32), (PAD - 8, y + 32)], fill=(51, 51, 51, 255))
    draw_text_mixed(d, (PAD + 15, y + 3), data["type_tag"], cn_font=M20, en_font=M20, fill=C_ACCENT)
    
    y += 32 + 20
    d.line([(PAD, y), (W - PAD, y)], fill=(255, 255, 255, 25), width=1)
    y += 20
    
    # === Top Row ===
    data_x = PAD
    data_w = INNER_W - 280 - 30
    
    d.rectangle([data_x, y, data_x + data_w, y + top_h], fill=C_CARD_BG, outline=(255,255,255,25), width=1)
    
    dy = y + 25
    dy = draw_section_title(d, data_x + 25, dy, "情报", "DATA", data_w - 50)
    
    for line in desc_lines:
        draw_text_mixed(d, (data_x + 25, dy), line, cn_font=F15, en_font=F15, fill=(204, 204, 204, 255))
        dy += 24
        
    if data["acquisition"]:
        dy += 10
        draw_text_mixed(d, (data_x + 25, dy), "[获取方式]", cn_font=F14, en_font=F14, fill=C_ACCENT)
        acq_w = int(F14.getlength("[获取方式]")) + 5
        draw_text_mixed(d, (data_x + 25 + acq_w, dy), data["acquisition"], cn_font=F14, en_font=F14, fill=C_SUBTEXT)
        dy += 20
        
    if data["passive"]:
        dy += 15
        d.rectangle([data_x + 25, dy, data_x + data_w - 25, dy + len(p_lines)*22 + 45], fill=(255, 230, 0, 12))
        d.line([(data_x + 25, dy), (data_x + 25, dy + len(p_lines)*22 + 45)], fill=C_ACCENT, width=3)
        draw_text_mixed(d, (data_x + 40, dy + 15), data["passive"]["name"], cn_font=F18, en_font=F18, fill=C_TEXT)
        dy += 45
        for line in p_lines:
            draw_text_mixed(d, (data_x + 40, dy), line, cn_font=F14, en_font=F14, fill=(204, 204, 204, 255))
            dy += 22
            
    # Right Image
    ix = PAD + data_w + 30
    iw = 280
    d.rectangle([ix, y, ix + iw, y + top_h], fill=(255, 255, 255, 7), outline=(255,255,255,25), width=1)
    if data["weapon_img"]:
        try:
            w_img = _b64_fit(data["weapon_img"], iw - 40, top_h - 40)
            canvas.alpha_composite(w_img, (ix + 20, y + 20))
        except Exception: pass
        
    y += top_h + 30
    
    # === Stats Row ===
    d.rectangle([PAD, y, W - PAD, y + stat_h], fill=C_CARD_BG, outline=(255,255,255,25), width=1)
    sy = y + 25
    sy = draw_section_title(d, PAD + 25, sy, "基础属性", "BASE STATISTICS", INNER_W - 50)
    
    cols = 3
    s_w = (INNER_W - 50 - 20*2) // cols
    curr_r, curr_c = 0, 0
    
    for st in data["stats"]:
        if st["full"]:
            if curr_c > 0:
                curr_r += 1
                curr_c = 0
            cx = PAD + 25
            cw = INNER_W - 50
            curr_r += 1
        else:
            cx = PAD + 25 + curr_c * (s_w + 20)
            cw = s_w
            curr_c += 1
            if curr_c >= cols:
                curr_c = 0
                curr_r += 1
                
        r_y = sy + (curr_r - 1 if st["full"] else curr_r) * (90 + 20)
        
        d.rectangle([cx, r_y, cx + cw, r_y + 90], fill=(0, 0, 0, 51))
        d.line([(cx, r_y), (cx, r_y + 90)], fill=(255, 255, 255, 25), width=2)
        
        draw_text_mixed(d, (cx + 20, r_y + 15), st["label"], cn_font=F14, en_font=F14, fill=C_SUBTEXT)
        draw_text_mixed(d, (cx + 20, r_y + 38), st["main"], cn_font=O32, en_font=O32, fill=C_TEXT)
        
        if st["max"]:
            draw_text_mixed(d, (cx + 20, r_y + 70), f"MAX: {st['max']}", cn_font=O14, en_font=O14, fill=C_ACCENT)
            
    # === Footer ===
    fy = total_h - 70
    d.rectangle([0, fy, W, total_h], fill=(0,0,0,255))
    d.line([(0, fy), (W, fy)], fill=C_ACCENT, width=1)
    
    if data["end_logo"]:
        try:
            logo = _b64_img(data["end_logo"])
            lh = 24
            lw = int(logo.width * (lh / logo.height))
            logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
            canvas.alpha_composite(logo, (40, fy + 23))
        except Exception: pass
        
    fw = int(O16.getlength(f"PROTOCOL SYSTEM // DATABASE_ID: {data['name']}"))
    draw_text_mixed(d, (W - 40 - fw, fy + 26), f"PROTOCOL SYSTEM // DATABASE_ID: {data['name']}", cn_font=O16, en_font=O16, fill=C_SUBTEXT)

    # 最终输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()