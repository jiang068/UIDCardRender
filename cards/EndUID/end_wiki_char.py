# 明日方舟：终末地 角色图鉴(Wiki)卡片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# 避免循环导入，直接引入工具函数并局部生成字体
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit,
    F12, F14, F15, F16, F18, F20, F24, F28, F96,
    M12, M14, M16,
    O14, O18, O20, O24
)

# 画布基础属性
W = 800
PAD = 50
INNER_W = W - PAD * 2

# 颜色定义
C_BG = (15, 16, 20, 255)
C_ACCENT = (255, 230, 0, 255)
C_TEXT = (255, 255, 255, 255)
C_SUBTEXT = (139, 139, 139, 255)
C_CARD_BG = (20, 21, 24, 204)  # rgba(20,21,24,0.8)


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg": "", "char_img": "", "end_logo": "",
        "name": "", "rarity": 0, "tags": [],
        "property": "", "property_icon": "",
        "profession": "", "profession_icon": "",
        "info": {}, "stats": [], "talents": [], 
        "skills": [], "base_skills": [], "potentials": []
    }

    # 背景与立绘
    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg"] = bg_el.get("src", "")
    char_el = soup.select_one(".char-layer")
    if char_el: data["char_img"] = char_el.get("src", "")
    logo_el = soup.select_one(".footer-logo")
    if logo_el: data["end_logo"] = logo_el.get("src", "")

    # Header
    name_el = soup.select_one(".char-name")
    if name_el: data["name"] = name_el.get_text(strip=True)
    data["rarity"] = len(soup.select(".rarity-star"))

    for tag_box in soup.select(".tags-row .tag-box"):
        text = tag_box.get_text(strip=True)
        is_element = "element" in tag_box.get("class", [])
        icon_img = tag_box.select_one("img")
        if is_element:
            data["property"] = text
            data["property_icon"] = icon_img.get("src", "") if icon_img else ""
        elif icon_img:
            data["profession"] = text
            data["profession_icon"] = icon_img.get("src", "")
        else:
            data["tags"].append(text)

    # Info Grid
    for ic in soup.select(".info-card"):
        lbl = ic.select_one(".info-label").get_text(strip=True) if ic.select_one(".info-label") else ""
        val = ic.select_one(".info-value").get_text(strip=True) if ic.select_one(".info-value") else ""
        if "FACTION" in lbl: data["info"]["faction"] = val
        elif "RACE" in lbl: data["info"]["race"] = val
        elif "DATE" in lbl: data["info"]["date"] = val
        elif "SPECIALTIES" in lbl: data["info"]["specialties"] = val

    # Stats Table
    stats_rows = soup.select(".stats-table tr")
    if len(stats_rows) > 1:
        # skip header
        for r in stats_rows[1:]:
            cols = r.select("td")
            if len(cols) == 8:
                data["stats"].append({
                    "lv": cols[0].get_text(strip=True),
                    "str": cols[1].get_text(strip=True),
                    "agi": cols[2].get_text(strip=True),
                    "int": cols[3].get_text(strip=True),
                    "wil": cols[4].get_text(strip=True),
                    "atk": cols[5].get_text(strip=True),
                    "hp": cols[6].get_text(strip=True),
                    "def": cols[7].get_text(strip=True)
                })

    # Content Sections (Talents, Skills, Base, Potentials)
    for section in soup.select(".scroll-content > div"):
        st = section.select_one(".section-title")
        if not st: continue
        sec_title = st.get_text(strip=True)

        if "TALENTS" in sec_title:
            for card in section.select(".feature-card"):
                t_name = card.select_one(".feature-name").get_text(strip=True) if card.select_one(".feature-name") else ""
                effs = []
                for eff_div in card.select("div[style*='margin-top:8px']"):
                    ph = eff_div.select_one(".phase-badge").get_text(strip=True) if eff_div.select_one(".phase-badge") else ""
                    desc = eff_div.select_one(".feature-desc").get_text(strip=True) if eff_div.select_one(".feature-desc") else ""
                    effs.append({"phase": ph, "desc": desc})
                data["talents"].append({"name": t_name, "effects": effs})

        elif "SKILLS" in sec_title and "BASE" not in sec_title:
            for card in section.select(".feature-card"):
                s_name = card.select_one(".feature-name").get_text(strip=True) if card.select_one(".feature-name") else ""
                desc = card.select_one(".feature-desc").get_text(strip=True) if card.select_one(".feature-desc") else ""
                data["skills"].append({"name": s_name, "desc": desc})

        elif "BASE SKILLS" in sec_title:
            for bs_row in section.select(".feature-card > div"):
                cols = bs_row.find_all("div", recursive=False)
                if len(cols) == 2:
                    data["base_skills"].append({"name": cols[0].get_text(strip=True), "desc": cols[1].get_text(strip=True)})

        elif "POTENTIALS" in sec_title:
            for item in section.select(".potential-item"):
                pr = item.select_one(".p-rank").get_text(strip=True) if item.select_one(".p-rank") else ""
                info_divs = item.select("div > div")
                if len(info_divs) >= 2:
                    data["potentials"].append({"rank": pr, "name": info_divs[0].get_text(strip=True), "desc": info_divs[1].get_text(strip=True)})

    return data


def draw_bg(canvas: Image.Image, w: int, h: int, bg_src: str):
    sw, sh = w // 10, h // 10
    cx, cy = int(sw * 0.7), int(sh * 0.3)
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
    for x in range(0, w, 60): gd.line([(x, 0), (x, h)], fill=grid_c, width=1)
    for y in range(0, h, 60): gd.line([(0, y), (w, y)], fill=grid_c, width=1)
    
    mask = Image.new("L", (w, h), 255)
    md = ImageDraw.Draw(mask)
    fade_h = int(h * 0.2)
    for y in range(fade_h, h):
        alpha = int(255 * (1 - min((y - fade_h) / (h * 0.8), 1.0)))
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


def draw_skew_tag(canvas: Image.Image, d: ImageDraw.ImageDraw, x: int, y: int, icon_src: str, text: str, is_element: bool) -> int:
    h = 32
    tw = int(M14.getlength(text))
    w = tw + 32 + (24 if icon_src else 0)
    skew = 10
    
    bg_c = (184, 45, 34, 255) if is_element else (255, 255, 255, 20)
    text_c = (255, 255, 255, 255) if is_element else (238, 238, 238, 255)
    
    pts = [(x + skew, y), (x + w + skew, y), (x + w - skew, y + h), (x - skew, y + h)]
    
    shadow = Image.new("RGBA", (W, 100), (0,0,0,0))
    ImageDraw.Draw(shadow).polygon([(p[0]+3, 30+3) for p in pts], fill=(0,0,0,102))
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    canvas.alpha_composite(shadow, (0, y - 30))
    
    d.polygon(pts, fill=bg_c)
    if not is_element:
        d.polygon([(x - skew - 3, y), (x + skew, y), (x - skew, y + h), (x - skew - 3, y + h)], fill=C_ACCENT)
        
    ix = x + 16
    if icon_src:
        try:
            ic = _b64_fit(icon_src, 18, 18)
            canvas.paste(ic, (ix, y + 7), ic)
            ix += 24
        except Exception: pass
        
    # [修正] 基线补偿 y+8 -> y+8-4
    draw_text_mixed(d, (ix, y + 4), text, cn_font=F14, en_font=M14, fill=text_c)
    return w + 12


def render(html: str) -> bytes:
    data = parse_html(html)
    
    # ---------------- 1. 高度预计算 ----------------
    cur_y = PAD
    
    # Header Area
    cur_y += 100 + 35 + 40 # name + stars + tags + info grid
    cur_y += 85 * 2 # info grid 2 rows approx
    cur_y += 20 # scroll content top margin
    
    # Text height factors
    desc_f = F15
    desc_lh = int(15 * 1.5)
    
    # Stats Table
    if data["stats"]:
        cur_y += 45 + 15 # title
        cur_y += 38 + len(data["stats"]) * 40 # table header + rows
        cur_y += 30
        
    # Talents
    if data["talents"]:
        cur_y += 45 + 15
        for t in data["talents"]:
            cur_y += 30 + 5 # name margin
            for eff in t["effects"]:
                if eff["desc"]:
                    cur_y += 24 # badge
                    lines = wrap_text(eff["desc"], desc_f, INNER_W - 30)
                    cur_y += len(lines) * desc_lh + 8
            cur_y += 30 # card padding/margin
        cur_y += 20
        
    # Skills
    if data["skills"]:
        cur_y += 45 + 15
        for s in data["skills"]:
            cur_y += 30 + 5
            lines = wrap_text(s["desc"], desc_f, INNER_W - 30)
            cur_y += len(lines) * desc_lh + 30
        cur_y += 20
        
    # Base Skills
    if data["base_skills"]:
        cur_y += 45 + 15
        cur_y += 30 # card pad
        for bs in data["base_skills"]:
            # layout: 120px for name, remaining for desc
            lines = wrap_text(bs["desc"], desc_f, INNER_W - 30 - 140)
            cur_y += max(24, len(lines) * desc_lh) + 14
        cur_y += 30
        
    # Potentials
    if data["potentials"]:
        cur_y += 45 + 15
        cur_y += 30
        for p in data["potentials"]:
            cur_y += 24 + 4 # name
            lines = wrap_text(p["desc"], desc_f, INNER_W - 30 - 55)
            cur_y += len(lines) * desc_lh + 25 # pb
        cur_y += 30

    # Footer
    cur_y += 90 
    total_h = max(cur_y, 1000)
    
    # ---------------- 2. 实际绘制 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h, data["bg"])
    
    # 角色大立绘
    if data["char_img"]:
        try:
            char_img = _b64_img(data["char_img"])
            cw, ch = char_img.size
            max_h = int(total_h * 0.72)
            max_w = int(W * 0.75)
            scale = min(max_w / cw, max_h / ch)
            cw, ch = int(cw * scale), int(ch * scale)
            char_img = char_img.resize((cw, ch), Image.Resampling.LANCZOS)
            
            # 立绘渐变遮罩
            mask = Image.new("L", (cw, ch), 255)
            md = ImageDraw.Draw(mask)
            for x in range(cw):
                if x < cw * 0.25:
                    alpha = int(255 * (x / (cw * 0.25)))
                    for y in range(ch): mask.putpixel((x, y), alpha)
            for y in range(ch):
                if y > ch * 0.7:
                    alpha = int(255 * (1 - (y - ch * 0.7) / (ch * 0.3)))
                    for x in range(cw): 
                        curr_a = mask.getpixel((x, y))
                        mask.putpixel((x, y), min(curr_a, alpha))
                        
            char_img.putalpha(ImageChops.multiply(char_img.split()[3], mask))
            
            shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            shadow.paste((0, 0, 0, 128), char_img.split()[3])
            shadow = shadow.filter(ImageFilter.GaussianBlur(10))
            
            cx = W - cw
            cy = 0
            canvas.alpha_composite(shadow, (cx - 10, cy + 5))
            canvas.alpha_composite(char_img, (cx, cy))
        except Exception: pass

    d = ImageDraw.Draw(canvas)
    y = PAD
    
    # === Header Group ===
    # [修正] 基线补偿 F96 -> y-10-28
    draw_text_mixed(d, (PAD - 4, y - 38), data["name"], cn_font=F96, en_font=F96, fill=C_TEXT)
    y += 90
    
    # Stars [修正] 往上挪 9px
    for i in range(data["rarity"]):
        cx = PAD + i * 26
        d.ellipse([cx, y-5, cx + 18, y + 13], fill=C_ACCENT)
        d.ellipse([cx + 3, y - 2, cx + 15, y + 10], fill=(255, 204, 0, 255))
    y += 35
    
    # Tags
    tx = PAD
    if data["property"]: tx += draw_skew_tag(canvas, d, tx, y, data["property_icon"], data["property"], True)
    if data["profession"]: tx += draw_skew_tag(canvas, d, tx, y, data["profession_icon"], data["profession"], False)
    for tag in data["tags"]: tx += draw_skew_tag(canvas, d, tx, y, "", tag, False)
    y += 32 + 10
    
    # Info Grid
    info_cols = 2
    info_w = 280
    info_gap = 12
    info_items = [
        ("阵营 / FACTION", data["info"].get("faction", "UNKNOWN")),
        ("种族 / RACE", data["info"].get("race", "UNKNOWN")),
        ("实装 / DATE", data["info"].get("date", "-")),
        ("专长 / SPECIALTIES", data["info"].get("specialties", "-"))
    ]
    for i, (lbl, val) in enumerate(info_items):
        r, c = divmod(i, info_cols)
        ix = PAD + c * (info_w + info_gap)
        iy = y + r * (58 + info_gap)
        d.rectangle([ix, iy, ix + info_w, iy + 58], fill=C_CARD_BG, outline=(255,255,255,25), width=1)
        # [修正] 基线补偿 M12 -> iy+10-4
        draw_text_mixed(d, (ix + 15, iy + 6), lbl, cn_font=F12, en_font=M12, fill=C_SUBTEXT)
        f_val = F16 if "专长" in lbl else F18
        # [修正] 基线补偿 iy+30-5
        draw_text_mixed(d, (ix + 15, iy + 25), val, cn_font=f_val, en_font=f_val, fill=C_TEXT)
    y += 2 * (58 + info_gap) + 20

    def draw_section_title(title_cn, title_en):
        d.rectangle([PAD, y + 2, PAD + 6, y + 28], fill=C_ACCENT)
        # [修正] 基线补偿 F28 -> y-2-8
        draw_text_mixed(d, (PAD + 15, y - 10), title_cn, cn_font=F28, en_font=F28, fill=C_ACCENT)
        cn_w = int(F28.getlength(title_cn))
        # [修正] 基线补偿 M16 -> y+8-5
        draw_text_mixed(d, (PAD + 15 + cn_w + 12, y + 3), title_en, cn_font=F16, en_font=M16, fill=C_SUBTEXT)
        d.line([(PAD, y + 35), (W - PAD, y + 35)], fill=(255, 255, 255, 25), width=2)
        return y + 50

    # === Stats Table ===
    if data["stats"]:
        y = draw_section_title("基础属性", "STATS")
        
        # Table Header
        col_w = INNER_W // 8
        headers = ["LV", "STR", "AGI", "INT", "WIL", "ATK", "HP", "DEF"]
        d.rectangle([PAD, y, W - PAD, y + 38], fill=C_CARD_BG)
        d.line([(PAD, y + 38), (W - PAD, y + 38)], fill=(255, 255, 255, 25), width=1)
        for i, h_txt in enumerate(headers):
            hw = int(O14.getlength(h_txt))
            # [修正] 基线补偿 O14 -> y+10-4
            draw_text_mixed(d, (PAD + i * col_w + (col_w - hw)//2, y + 6), h_txt, cn_font=F14, en_font=O14, fill=C_ACCENT)
        y += 38
        
        # Table Rows
        for r_data in data["stats"]:
            d.rectangle([PAD, y, W - PAD, y + 40], fill=C_CARD_BG)
            d.line([(PAD, y + 40), (W - PAD, y + 40)], fill=(255, 255, 255, 12), width=1)
            vals = [r_data["lv"], r_data["str"], r_data["agi"], r_data["int"], r_data["wil"], r_data["atk"], r_data["hp"], r_data["def"]]
            for i, val in enumerate(vals):
                vw = int(O20.getlength(val))
                fc = (136, 136, 136, 255) if i == 0 else C_TEXT
                # [修正] 基线补偿 O20 -> y+8-6
                draw_text_mixed(d, (PAD + i * col_w + (col_w - vw)//2, y + 2), val, cn_font=F20, en_font=O20, fill=fc)
            y += 40
        y += 30

    def draw_feature_card_bg(start_y, ch):
        bg = Image.new("RGBA", (INNER_W, ch))
        bd = ImageDraw.Draw(bg)
        for xi in range(INNER_W):
            alpha = int(12 * (1 - (xi / INNER_W)))
            bd.line([(xi, 0), (xi, ch)], fill=(255, 255, 255, alpha))
        canvas.alpha_composite(bg, (PAD, start_y))
        d.line([(PAD, start_y), (PAD, start_y + ch)], fill=(68, 68, 68, 255), width=4)

    # === Talents ===
    if data["talents"]:
        y = draw_section_title("天赋", "TALENTS")
        for t in data["talents"]:
            start_y = y
            ch = 15 + 30 # pad_top + name + mb
            for eff in t["effects"]:
                if eff["desc"]:
                    ch += 24
                    lines = wrap_text(eff["desc"], F15, INNER_W - 30)
                    ch += len(lines) * desc_lh + 8
            ch += 5 # pad_bot
            
            draw_feature_card_bg(start_y, ch)
            
            ty = start_y + 15
            # [修正] 基线补偿 ty-6
            draw_text_mixed(d, (PAD + 15, ty - 6), t["name"], cn_font=F20, en_font=F20, fill=C_TEXT)
            ty += 35
            
            for eff in t["effects"]:
                if eff["desc"]:
                    pw = int(M12.getlength(eff["phase"]))
                    d.rectangle([PAD + 15, ty, PAD + 15 + pw + 12, ty + 20], fill=(51, 51, 51, 255), radius=2)
                    # [修正] 基线补偿 ty+2-4
                    draw_text_mixed(d, (PAD + 21, ty - 2), eff["phase"], cn_font=F12, en_font=M12, fill=C_ACCENT)
                    ty += 24
                    
                    lines = wrap_text(eff["desc"], F15, INNER_W - 30)
                    for line in lines:
                        # [修正] 基线补偿 ty-4
                        draw_text_mixed(d, (PAD + 15, ty - 4), line, cn_font=F15, en_font=O14, fill=(204, 204, 204, 255))
                        ty += desc_lh
                    ty += 8
            y += ch + 10
        y += 20

    # === Skills ===
    if data["skills"]:
        y = draw_section_title("技能", "SKILLS")
        for s in data["skills"]:
            start_y = y
            lines = wrap_text(s["desc"], F15, INNER_W - 30)
            ch = 15 + 30 + len(lines) * desc_lh + 15
            
            draw_feature_card_bg(start_y, ch)
            
            ty = start_y + 15
            # [修正] 基线补偿 ty-6
            draw_text_mixed(d, (PAD + 15, ty - 6), s["name"], cn_font=F20, en_font=F20, fill=C_TEXT)
            ty += 35
            for line in lines:
                # [修正] 基线补偿 ty-4
                draw_text_mixed(d, (PAD + 15, ty - 4), line, cn_font=F15, en_font=O14, fill=(204, 204, 204, 255))
                ty += desc_lh
            y += ch + 10
        y += 20

    # === Base Skills ===
    if data["base_skills"]:
        y = draw_section_title("基建技能", "BASE SKILLS")
        start_y = y
        
        ch = 15
        bs_heights = []
        for bs in data["base_skills"]:
            lines = wrap_text(bs["desc"], F15, INNER_W - 30 - 140)
            rh = max(24, len(lines) * desc_lh) + 14
            bs_heights.append((lines, rh))
            ch += rh
        ch += 5
        
        draw_feature_card_bg(start_y, ch)
        
        ty = start_y + 15
        for i, bs in enumerate(data["base_skills"]):
            lines, rh = bs_heights[i]
            # [修正] 基线补偿 ty-5
            draw_text_mixed(d, (PAD + 15, ty - 5), bs["name"], cn_font=F16, en_font=F16, fill=(221, 221, 221, 255))
            
            dy = ty
            for line in lines:
                # [修正] 基线补偿 dy-4
                draw_text_mixed(d, (PAD + 155, dy - 4), line, cn_font=F15, en_font=O14, fill=(204, 204, 204, 255))
                dy += desc_lh
                
            d.line([(PAD + 15, ty + rh - 6), (W - PAD - 15, ty + rh - 6)], fill=(255, 255, 255, 12), width=1)
            ty += rh
        y += ch + 20

    # === Potentials ===
    if data["potentials"]:
        y = draw_section_title("潜能", "POTENTIALS")
        start_y = y
        
        ch = 15
        pot_heights = []
        for p in data["potentials"]:
            lines = wrap_text(p["desc"], F15, INNER_W - 30 - 55)
            rh = 28 + len(lines) * desc_lh + 12
            pot_heights.append((lines, rh))
            ch += rh
        ch += 5
        
        draw_feature_card_bg(start_y, ch)
        
        ty = start_y + 15
        for i, p in enumerate(data["potentials"]):
            lines, rh = pot_heights[i]
            # [修正] 基线补偿 O24 -> ty-7
            draw_text_mixed(d, (PAD + 15, ty - 7), f"P{p['rank']}", cn_font=F24, en_font=O24, fill=C_ACCENT)
            # [修正] 基线补偿 ty+2-5
            draw_text_mixed(d, (PAD + 70, ty - 3), p["name"], cn_font=F16, en_font=F16, fill=C_TEXT)
            
            dy = ty + 28
            for line in lines:
                # [修正] 基线补偿 dy-4
                draw_text_mixed(d, (PAD + 70, dy - 4), line, cn_font=F15, en_font=O14, fill=(204, 204, 204, 255))
                dy += desc_lh
                
            d.line([(PAD + 15, ty + rh - 6), (W - PAD - 15, ty + rh - 6)], fill=(255, 255, 255, 25), width=1)
            ty += rh
        y += ch + 20

    # === Footer ===
    fy = total_h - 80
    f_bg = Image.new("RGBA", (W, 80), (10, 10, 12, 250))
    canvas.alpha_composite(f_bg, (0, fy))
    d.line([(0, fy), (W, fy)], fill=(255, 255, 255, 38), width=1)
    
    if data["end_logo"]:
        try:
            logo = _b64_img(data["end_logo"])
            lh = 32
            lw = int(logo.width * (lh / logo.height))
            logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
            logo.putalpha(ImageChops.multiply(logo.split()[3], Image.new("L", (lw, lh), 204)))
            canvas.alpha_composite(logo, (40, fy + 24))
        except Exception: pass
        
    fw = int(O18.getlength(f"WIKI DATABASE // {data['name']}"))
    # [修正] 基线补偿 O18 -> fy+28-5
    draw_text_mixed(d, (W - 40 - fw, fy + 23), f"WIKI DATABASE // {data['name']}", cn_font=F18, en_font=O18, fill=C_SUBTEXT)

    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()