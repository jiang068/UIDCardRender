# 明日方舟：终末地 武器图鉴卡片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 避免循环导入，直接引入工具函数并局部生成字体
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit,
    F12, F14, F15, F16, F18, F20, F36, F64,
    M12, M14, M16, M20,
    O14, O16, O32
)

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
            r = int(34 + (15 - 34) * ratio)
            g = int(35 + (16 - 35) * ratio)
            b = int(40 + (20 - 40) * ratio)
            grad.putpixel((x, y), (r, g, b, 255))
            
    canvas.alpha_composite(grad.resize((w, h), Image.Resampling.LANCZOS))
    
    if bg_src:
        try:
            bg_img = _b64_fit(bg_src, w, h).convert("RGBA")
            bg_img.putalpha(Image.new("L", (w, h), 25)) # opacity ~0.1
            canvas.alpha_composite(bg_img)
        except Exception: pass

    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    grid_c = (38, 39, 44, 180)
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
    # F18 偏下 30% 约补偿 5px
    draw_text_mixed(d, (x, y - 5), title_cn, cn_font=F18, en_font=F18, fill=C_ACCENT)
    d.line([(x, y + 25), (x + width, y + 25)], fill=(255, 255, 255, 25), width=1)
    # Right align EN text
    en_w = int(M12.getlength(title_en))
    # F12/M12 偏下 30% 约补偿 4px
    draw_text_mixed(d, (x + width - en_w, y + 4 - 4), title_en, cn_font=F12, en_font=M12, fill=C_SUBTEXT)
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
    
    # === Stats Grid 动态预计算 (修复文字超长溢出) ===
    stat_rows = []
    cur_row = []
    
    for st in data["stats"]:
        is_full = st["full"]
        # 计算可用宽度（左右各留 20px padding）
        cw = INNER_W - 50 if is_full else (INNER_W - 50 - 20*2) // 3
        max_w = cw - 40
        
        # 标签自动换行
        lbl_lines = wrap_text(st["label"], F14, max_w)
        
        # === 修改后的 Stats Grid 动态预计算逻辑 ===
        if is_full or len(st["main"]) > 15 or F36.getlength(st["main"]) > max_w:
            # [修改] 字体不再使用 F15，而是统一使用大字号 F36
            main_cn_font = F36
            main_en_font = O32
            # [修改] 使用 F36 进行换行切分，这样长描述也会是大字且自动换行
            main_lines = wrap_text(st["main"], main_cn_font, max_w)
            m_line_h = 38  # 配合 F36 的行高
            y_offset = 8   # [修改] 下挪 20% 后的补偿值（11 - 3 = 8）
        else:
            main_cn_font = F36
            main_en_font = O32
            main_lines = [st["main"]]
            m_line_h = 38
            y_offset = 8   # [修改] 这里同步改为下挪 20% 后的值
            
        max_lines = wrap_text(f"MAX: {st['max']}", F14, max_w) if st["max"] else []
        
        # 精确计算这个属性框需要多高
        req_h = 15 + len(lbl_lines)*20 + (4 if main_cn_font == F15 else 8) + len(main_lines)*m_line_h
        if max_lines: req_h += 5 + len(max_lines)*20
        req_h += 15 # bottom padding
        
        box_h = max(90, req_h) # 最小保证 90px 高度
        
        # 存入内部属性供绘制时调用
        st.update({
            "_lbl_lines": lbl_lines, "_main_lines": main_lines, 
            "_main_cn": main_cn_font, "_main_en": main_en_font,
            "_max_lines": max_lines, "_m_line_h": m_line_h, 
            "_m_offset": y_offset, "_box_h": box_h, "_cw": cw
        })
        
        if is_full:
            if cur_row:
                stat_rows.append(cur_row)
                cur_row = []
            stat_rows.append([st])
        else:
            cur_row.append(st)
            if len(cur_row) == 3:
                stat_rows.append(cur_row)
                cur_row = []
                
    if cur_row:
        stat_rows.append(cur_row)
        
    stat_h = 25 * 2 + 40 # 整体区域 padding + 标题
    if stat_rows:
        for r in stat_rows:
            # 同一行的所有框高度对齐为这一行的最大值
            max_h = max(st["_box_h"] for st in r)
            for st in r: st["_row_h"] = max_h
            stat_h += max_h + 20
    
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
        # [修改] 外圈 Y轴坐标分别减去 9 (4->-5, 22->13)
        d.ellipse([cx, y - 5, cx + 18, y + 13], fill=C_ACCENT)
        # [修改] 内圈 Y轴坐标分别减去 9 (7->-2, 19->10)
        d.ellipse([cx + 3, y - 2, cx + 15, y + 10], fill=(255, 204, 0, 255))
    y += 30
    
    draw_text_mixed(d, (PAD, y - 5 - 19), data["name"], cn_font=F64, en_font=F64, fill=C_TEXT)
    y += 70
    
    tt_w = int(F20.getlength(data["type_tag"])) + 30
    d.polygon([(PAD + 8, y), (PAD + tt_w + 8, y), (PAD + tt_w - 8, y + 32), (PAD - 8, y + 32)], fill=(51, 51, 51, 255))
    draw_text_mixed(d, (PAD + 15, y + 3 - 6), data["type_tag"], cn_font=F20, en_font=M20, fill=C_ACCENT)
    
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
        # [修改] en_font 改为 O14，Y轴坐标由 dy - 4 改为 dy - 1
        draw_text_mixed(d, (data_x + 25, dy - 1), line, cn_font=F15, en_font=O14, fill=(204, 204, 204, 255))
        dy += 24
        
    if data["acquisition"]:
        dy += 10
        draw_text_mixed(d, (data_x + 25, dy - 4), "[获取方式]", cn_font=F14, en_font=F14, fill=C_ACCENT)
        acq_w = int(F14.getlength("[获取方式]")) + 5
        draw_text_mixed(d, (data_x + 25 + acq_w, dy - 4), data["acquisition"], cn_font=F14, en_font=F14, fill=C_SUBTEXT)
        dy += 20
        
    if data["passive"]:
        dy += 15
        d.rectangle([data_x + 25, dy, data_x + data_w - 25, dy + len(p_lines)*22 + 45], fill=(255, 230, 0, 12))
        d.line([(data_x + 25, dy), (data_x + 25, dy + len(p_lines)*22 + 45)], fill=C_ACCENT, width=3)
        draw_text_mixed(d, (data_x + 40, dy + 15 - 5), data["passive"]["name"], cn_font=F18, en_font=F18, fill=C_TEXT)
        dy += 45
        for line in p_lines:
            # [修改] en_font 改为 O14，Y轴坐标由 dy - 4 改为 dy - 1
            draw_text_mixed(d, (data_x + 40, dy - 1), line, cn_font=F14, en_font=O14, fill=(204, 204, 204, 255))
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
    
    curr_y = sy
    for r in stat_rows:
        curr_x = PAD + 25
        row_h = r[0]["_row_h"]
        
        for st in r:
            cw = st["_cw"]
            d.rectangle([curr_x, curr_y, curr_x + cw, curr_y + row_h], fill=(0, 0, 0, 51))
            d.line([(curr_x, curr_y), (curr_x, curr_y + row_h)], fill=(255, 255, 255, 25), width=2)
            
            ty = curr_y + 15
            # 画标题
            for line in st["_lbl_lines"]:
                draw_text_mixed(d, (curr_x + 20, ty - 4), line, cn_font=F14, en_font=F14, fill=C_SUBTEXT)
                ty += 20
                
            ty += 4 if st["_main_cn"] == F15 else 8
            # 画内容 (自适应换行或大数字)
            for line in st["_main_lines"]:
                draw_text_mixed(d, (curr_x + 20, ty - st["_m_offset"]), line, cn_font=st["_main_cn"], en_font=st["_main_en"], fill=C_TEXT)
                ty += st["_m_line_h"]
                
            # 画副内容
            if st["_max_lines"]:
                ty += 5
                for line in st["_max_lines"]:
                    draw_text_mixed(d, (curr_x + 20, ty - 4), line, cn_font=F14, en_font=O14, fill=C_ACCENT)
                    ty += 20
                    
            curr_x += cw + 20
            
        curr_y += row_h + 20
            
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
        
    fw = int(F16.getlength(f"PROTOCOL SYSTEM // DATABASE_ID: {data['name']}"))
    draw_text_mixed(d, (W - 40 - fw, fy + 26 - 5), f"PROTOCOL SYSTEM // DATABASE_ID: {data['name']}", cn_font=F16, en_font=O16, fill=C_SUBTEXT)

    # 最终输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()