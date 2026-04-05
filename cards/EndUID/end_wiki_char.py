# cards/EndUID/end_wiki_char.py
from __future__ import annotations

import math
import re
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# 避免循环导入，直接引入工具函数并局部生成字体
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit, _round_mask,
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


def _is_pure_en_num(ch: str) -> bool:
    return 'a' <= ch <= 'z' or 'A' <= ch <= 'Z' or '0' <= ch <= '9' or ch in ' _-//:.'

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, r: int, fill: tuple, outline: tuple = None, width: int = 1):
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(block, (x0, y0))

def _draw_h_gradient(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, left_rgba: tuple, right_rgba: tuple, r: int = 0):
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    base = Image.new("RGBA", (2, 1))
    base.putpixel((0, 0), left_rgba)
    base.putpixel((1, 0), right_rgba)
    grad = base.resize((w, h), Image.Resampling.BILINEAR)
    if r > 0:
        mask = _round_mask(w, h, r)
        grad.putalpha(ImageChops.multiply(grad.getchannel('A'), mask))
    canvas.alpha_composite(grad, (x0, y0))


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
        elif "BIRTHDAY" in lbl: data["info"]["birthday"] = val

    # Stats Table
    stats_rows = soup.select(".stats-table tr")
    if len(stats_rows) > 1:
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

    # Content Sections
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
            for sc in section.select(".skill-card"):
                icon_el = sc.select_one(".skill-icon")
                s_name = sc.select_one(".skill-name").get_text(strip=True) if sc.select_one(".skill-name") else ""
                badge_el = sc.select_one(".skill-type-badge")
                desc_el = sc.select_one(".skill-desc-text")
                
                skill_data = {
                    "name": s_name,
                    "icon": icon_el.get("src", "") if icon_el else "",
                    "badge": badge_el.get_text(strip=True) if badge_el else "",
                    "badge_cls": badge_el.get("class", []) if badge_el else [],
                    "desc": desc_el.get_text(strip=True) if desc_el else "",
                    "headers": [],
                    "rows": []
                }
                
                stats_table = sc.select_one(".skill-stats")
                if stats_table:
                    trs = stats_table.select("tr")
                    if trs:
                        for th in trs[0].select("th"):
                            skill_data["headers"].append({"text": th.get_text(strip=True), "mastery": "mastery" in th.get("class", [])})
                        for tr in trs[1:]:
                            row_cols = []
                            for td in tr.select("td"):
                                row_cols.append({"text": td.get_text(strip=True), "mastery": "mastery" in td.get("class", [])})
                            skill_data["rows"].append(row_cols)
                data["skills"].append(skill_data)

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
    # 【修改】：使用简单的从深灰色到黑色的垂直渐变，不再绘制网格
    base = Image.new("RGBA", (1, 2))
    base.putpixel((0, 0), (45, 45, 50, 255))  # 深灰色
    base.putpixel((0, 1), (8, 8, 10, 255))    # 黑色
    grad = base.resize((w, h), Image.Resampling.BILINEAR)
    canvas.alpha_composite(grad, (0, 0))
    
    if bg_src:
        try:
            bg_img = _b64_fit(bg_src, w, h).convert("RGBA")
            bg_img.putalpha(Image.new("L", (w, h), 38)) # 0.15 opacity
            canvas.alpha_composite(bg_img)
        except Exception: pass


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
    tw = int(M14.getlength(text)) if _is_pure_en_num(text) else int(F14.getlength(text))
    w = tw + 32 + (24 if icon_src else 0)
    skew = 12
    
    bg_c = (184, 45, 34, 255) if is_element else (255, 255, 255, 20)
    text_c = (255, 255, 255, 255) if is_element else (238, 238, 238, 255)
    
    pts = [(x + skew, y), (x + w + skew, y), (x + w - skew, y + h), (x - skew, y + h)]
    
    shadow = Image.new("RGBA", (W, 100), (0,0,0,0))
    ImageDraw.Draw(shadow).polygon([(p[0]+2, p[1]-y+2) for p in pts], fill=(0,0,0,102))
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    canvas.alpha_composite(shadow, (0, y))
    
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
        
    draw_text_mixed(d, (ix, y + 6), text, cn_font=F14, en_font=M14, fill=text_c)
    return w + 12


def render(html: str) -> bytes:
    data = parse_html(html)
    
    # ---------------- 1. 高度预计算 ----------------
    cur_y = PAD
    
    # Header Area
    cur_y += 100 + 35 + 40 # name + stars + tags 
    cur_y += 85 * 2 # info grid 2x2
    cur_y += 20 # scroll content top margin
    
    # Text height factors
    desc_lh = int(15 * 1.5)
    
    # Stats Table
    if data["stats"]:
        cur_y += 45 + 15
        cur_y += 38 + len(data["stats"]) * 40
        cur_y += 30
        
    # Talents
    if data["talents"]:
        cur_y += 45 + 15
        for t in data["talents"]:
            cur_y += 30 + 5
            for eff in t["effects"]:
                if eff["desc"]:
                    cur_y += 24
                    lines = wrap_text(eff["desc"], F15, INNER_W - 30)
                    cur_y += len(lines) * desc_lh + 8
            cur_y += 30
        cur_y += 20
        
    # Skills
    if data["skills"]:
        cur_y += 45 + 15
        for s in data["skills"]:
            lines = wrap_text(s["desc"], F14, INNER_W - 56 - 14 - 40) if s["desc"] else []
            meta_h = 22 + (4 + len(lines) * desc_lh if lines else 0)
            header_h = 32 + max(56, meta_h)
            
            body_h = 0
            if s["headers"]:
                body_h += 32
                body_h += 24
                body_h += len(s["rows"]) * 24
                
            skill_card_h = header_h + body_h # 【修复】：变量名改为 skill_card_h 防止覆盖全局 total_h
            cur_y += skill_card_h + 20
        cur_y += 20
        
    # Base Skills
    if data["base_skills"]:
        cur_y += 45 + 15
        cur_y += 30 
        for bs in data["base_skills"]:
            lines = wrap_text(bs["desc"], F14, INNER_W - 30 - 140)
            cur_y += max(20, len(lines) * desc_lh) + 14
        cur_y += 30
        
    # Potentials
    if data["potentials"]:
        cur_y += 45 + 15
        cur_y += 30
        for p in data["potentials"]:
            lines = wrap_text(p["desc"], F15, INNER_W - 30 - 55)
            cur_y += 28 + len(lines) * desc_lh + 12
        cur_y += 30

    # Footer
    cur_y += 90 
    total_h = max(cur_y, 1000)
    
    # ---------------- 2. 实际绘制 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h, data["bg"])
    
    # 角色大立绘 & 褪色遮罩
    if data["char_img"]:
        try:
            char_img = _b64_img(data["char_img"])
            cw, ch = char_img.size
            max_h = int(total_h * 0.72)
            max_w = int(W * 0.75)
            scale = min(max_w / cw, max_h / ch)
            cw, ch = int(cw * scale), int(ch * scale)
            char_img = char_img.resize((cw, ch), Image.Resampling.LANCZOS)
            
            mask = Image.new("L", (cw, ch), 255)
            fade_x = int(cw * 0.25)
            for x in range(fade_x):
                alpha = int(255 * (x / fade_x))
                for y in range(ch): mask.putpixel((x, y), alpha)
                
            fade_y = int(ch * 0.7)
            for y in range(fade_y, ch):
                alpha_y = int(255 * (1 - (y - fade_y) / (ch - fade_y)))
                for x in range(cw): 
                    curr_a = mask.getpixel((x, y))
                    mask.putpixel((x, y), min(curr_a, alpha_y))
                    
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
    draw_text_mixed(d, (PAD - 4, y - 38), data["name"], cn_font=F96, en_font=F96, fill=C_TEXT)
    y += 90
    
    for i in range(data["rarity"]):
        cx = PAD + i * 26
        d.ellipse([cx, y-5, cx + 18, y + 13], fill=C_ACCENT)
        d.ellipse([cx + 3, y - 2, cx + 15, y + 10], fill=(255, 204, 0, 255))
    y += 35
    
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
        ("生日 / BIRTHDAY", data["info"].get("birthday", "-"))
    ]
    for i, (lbl, val) in enumerate(info_items):
        r, c = divmod(i, info_cols)
        ix = PAD + c * (info_w + info_gap)
        iy = y + r * (58 + info_gap)
        d.rectangle([ix, iy, ix + info_w, iy + 58], fill=C_CARD_BG, outline=(255,255,255,25), width=1)
        draw_text_mixed(d, (ix + 15, iy + 6), lbl, cn_font=F12, en_font=M12, fill=C_SUBTEXT)
        f_val = F18
        draw_text_mixed(d, (ix + 15, iy + 25), val, cn_font=f_val, en_font=f_val, fill=C_TEXT)
    y += 2 * (58 + info_gap) + 20

    def draw_section_title(title_cn, title_en):
        d.rectangle([PAD, y + 2, PAD + 6, y + 28], fill=C_ACCENT)
        draw_text_mixed(d, (PAD + 15, y - 10), title_cn, cn_font=F28, en_font=F28, fill=C_ACCENT)
        cn_w = int(F28.getlength(title_cn))
        draw_text_mixed(d, (PAD + 15 + cn_w + 12, y + 3), title_en, cn_font=F16, en_font=M16, fill=C_SUBTEXT)
        d.line([(PAD, y + 35), (W - PAD, y + 35)], fill=(255, 255, 255, 25), width=2)
        return y + 50

    def draw_feature_card_bg(start_y, ch):
        bg = Image.new("RGBA", (INNER_W, ch))
        bd = ImageDraw.Draw(bg)
        for xi in range(INNER_W):
            alpha = int(12 * (1 - (xi / INNER_W)))
            bd.line([(xi, 0), (xi, ch)], fill=(255, 255, 255, alpha))
        canvas.alpha_composite(bg, (PAD, start_y))
        d.line([(PAD, start_y), (PAD, start_y + ch)], fill=(68, 68, 68, 255), width=4)

    # === Stats Table ===
    if data["stats"]:
        y = draw_section_title("基础属性", "STATS")
        col_w = INNER_W // 8
        headers = ["LV", "STR", "AGI", "INT", "WIL", "ATK", "HP", "DEF"]
        d.rectangle([PAD, y, W - PAD, y + 38], fill=C_CARD_BG)
        d.line([(PAD, y + 38), (W - PAD, y + 38)], fill=(255, 255, 255, 25), width=1)
        for i, h_txt in enumerate(headers):
            hw = int(O14.getlength(h_txt))
            draw_text_mixed(d, (PAD + i * col_w + (col_w - hw)//2, y + 6), h_txt, cn_font=F14, en_font=O14, fill=C_ACCENT)
        y += 38
        
        for r_data in data["stats"]:
            d.rectangle([PAD, y, W - PAD, y + 40], fill=C_CARD_BG)
            d.line([(PAD, y + 40), (W - PAD, y + 40)], fill=(255, 255, 255, 12), width=1)
            vals = [r_data["lv"], r_data["str"], r_data["agi"], r_data["int"], r_data["wil"], r_data["atk"], r_data["hp"], r_data["def"]]
            for i, val in enumerate(vals):
                vw = int(O20.getlength(val))
                fc = (136, 136, 136, 255) if i == 0 else C_TEXT
                draw_text_mixed(d, (PAD + i * col_w + (col_w - vw)//2, y + 2), val, cn_font=F20, en_font=O20, fill=fc)
            y += 40
        y += 30

    # === Talents ===
    if data["talents"]:
        y = draw_section_title("天赋", "TALENTS")
        for t in data["talents"]:
            start_y = y
            ch = 15 + 30
            for eff in t["effects"]:
                if eff["desc"]:
                    ch += 24
                    lines = wrap_text(eff["desc"], F15, INNER_W - 30)
                    ch += len(lines) * desc_lh + 8
            ch += 5
            
            draw_feature_card_bg(start_y, ch)
            
            ty = start_y + 15
            draw_text_mixed(d, (PAD + 15, ty - 6), t["name"], cn_font=F20, en_font=F20, fill=C_TEXT)
            ty += 35
            
            for eff in t["effects"]:
                if eff["desc"]:
                    pw = int(M12.getlength(eff["phase"]))
                    d.rounded_rectangle([PAD + 15, ty, PAD + 15 + pw + 12, ty + 20], fill=(51, 51, 51, 255), radius=2)
                    draw_text_mixed(d, (PAD + 21, ty - 2), eff["phase"], cn_font=F12, en_font=M12, fill=C_ACCENT)
                    ty += 24
                    
                    lines = wrap_text(eff["desc"], F15, INNER_W - 30)
                    for line in lines:
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
            lines = wrap_text(s["desc"], F14, INNER_W - 56 - 14 - 40) if s["desc"] else []
            meta_h = 22 + (4 + len(lines) * desc_lh if lines else 0)
            header_h = 32 + max(56, meta_h)
            
            body_h = 0
            if s["headers"]:
                body_h += 32
                body_h += 24
                body_h += len(s["rows"]) * 24
                
            skill_card_h = header_h + body_h # 【修复】：变量名改为 skill_card_h 防止覆盖全局 total_h
            
            _draw_rounded_rect(canvas, PAD, start_y, PAD + INNER_W, start_y + skill_card_h, 4, C_CARD_BG, outline=(255,255,255,20))
            _draw_h_gradient(canvas, PAD, start_y, PAD + int(INNER_W * 0.6), start_y + header_h, (255,230,0,15), (255,230,0,0), r=0)
            d.line([(PAD, start_y + header_h), (PAD + INNER_W, start_y + header_h)], fill=(255,255,255,15))
            
            ix, iy = PAD + 20, start_y + 16
            if s["icon"]:
                try:
                    ic = _b64_fit(s["icon"], 56, 56)
                    _draw_rounded_rect(canvas, ix, iy, ix+56, iy+56, 8, (0,0,0,0), outline=(255,230,0,76), width=2)
                    canvas.paste(ic, (ix, iy), _round_mask(56, 56, 8))
                except: pass
                
            mx, my = ix + 56 + 14, iy
            draw_text_mixed(d, (mx, my-4), s["name"], cn_font=F20, en_font=F20, fill=C_TEXT)
            nw = int(F20.getlength(s["name"]))
            
            if s["badge"]:
                badge_c_bg, badge_c_fg = (58, 58, 58, 255), C_ACCENT
                if "normal" in s["badge_cls"]: badge_c_bg, badge_c_fg = (42, 58, 42, 255), (124, 204, 124, 255)
                elif "battle" in s["badge_cls"]: badge_c_bg, badge_c_fg = (58, 42, 42, 255), (224, 96, 96, 255)
                elif "combo" in s["badge_cls"]: badge_c_bg, badge_c_fg = (42, 42, 58, 255), (96, 128, 224, 255)
                elif "ult" in s["badge_cls"]: badge_c_bg, badge_c_fg = (58, 58, 26, 255), (224, 192, 64, 255)
                
                bw = int(M12.getlength(s["badge"]))
                d.rounded_rectangle([mx + nw + 10, my+2, mx + nw + 10 + bw + 16, my + 18], radius=3, fill=badge_c_bg)
                draw_text_mixed(d, (mx + nw + 18, my), s["badge"], cn_font=F12, en_font=M12, fill=badge_c_fg)
                
            my += 26
            for line in lines:
                draw_text_mixed(d, (mx, my-2), line, cn_font=F14, en_font=M14, fill=(170,170,170,255))
                my += desc_lh
                
            ty = start_y + header_h + 16
            if s["headers"]:
                cols_count = len(s["headers"])
                col_w = (INNER_W - 40) // cols_count if cols_count else 0
                
                d.rectangle([PAD + 20, ty, PAD + INNER_W - 20, ty + 24], fill=(255,230,0,20))
                for i, th in enumerate(s["headers"]):
                    tc = C_ACCENT if th["mastery"] else C_ACCENT
                    if i == 0:
                        draw_text_mixed(d, (PAD + 30, ty), th["text"], cn_font=F12, en_font=M12, fill=tc)
                    else:
                        tw = int(M12.getlength(th["text"]))
                        draw_text_mixed(d, (PAD + 20 + i*col_w + (col_w - tw)//2, ty), th["text"], cn_font=F12, en_font=M12, fill=tc)
                d.line([(PAD+20, ty+24), (PAD+INNER_W-20, ty+24)], fill=(255,255,255,25))
                ty += 24
                
                for row in s["rows"]:
                    for i, td in enumerate(row):
                        tc = C_ACCENT if td["mastery"] else (204,204,204,255)
                        f_en = M12
                        f_cn = F12
                        if i == 0:
                            tc = (153,153,153,255)
                            draw_text_mixed(d, (PAD + 30, ty+2), td["text"], cn_font=f_cn, en_font=f_en, fill=tc)
                        else:
                            tw = int(f_en.getlength(td["text"])) if _is_pure_en_num(td["text"]) else int(f_cn.getlength(td["text"]))
                            draw_text_mixed(d, (PAD + 20 + i*col_w + (col_w - tw)//2, ty+2), td["text"], cn_font=f_cn, en_font=f_en, fill=tc)
                    d.line([(PAD+20, ty+24), (PAD+INNER_W-20, ty+24)], fill=(255,255,255,8))
                    ty += 24

            y += skill_card_h + 20
        y += 20

    # === Base Skills ===
    if data["base_skills"]:
        y = draw_section_title("基建技能", "BASE SKILLS")
        card_h = 30
        bs_heights = []
        for bs in data["base_skills"]:
            lines = wrap_text(bs["desc"], F14, INNER_W - 30 - 140)
            rh = max(20, len(lines) * desc_lh) + 14
            bs_heights.append((lines, rh))
            card_h += rh
            
        draw_feature_card_bg(y, card_h)
        
        ty = y + 15
        for i, bs in enumerate(data["base_skills"]):
            lines, rh = bs_heights[i]
            draw_text_mixed(d, (PAD + 15, ty - 2), bs["name"], cn_font=F16, en_font=F16, fill=(221,221,221,255))
            
            dy = ty
            for line in lines:
                draw_text_mixed(d, (PAD + 155, dy - 2), line, cn_font=F14, en_font=M14, fill=(204,204,204,255))
                dy += desc_lh
                
            d.line([(PAD + 15, ty + rh - 6), (PAD + INNER_W - 15, ty + rh - 6)], fill=(255,255,255,12))
            ty += rh
            
        y += card_h + 20

    # === Potentials ===
    if data["potentials"]:
        y = draw_section_title("潜能", "POTENTIALS")
        card_h = 30
        pot_heights = []
        for p in data["potentials"]:
            lines = wrap_text(p["desc"], F15, INNER_W - 30 - 55)
            rh = 28 + len(lines) * desc_lh + 12
            pot_heights.append((lines, rh))
            card_h += rh
            
        draw_feature_card_bg(y, card_h)
        
        ty = y + 15
        for i, p in enumerate(data["potentials"]):
            lines, rh = pot_heights[i]
            draw_text_mixed(d, (PAD + 15, ty - 4), f"P{p['rank']}", cn_font=F24, en_font=O24, fill=C_ACCENT)
            draw_text_mixed(d, (PAD + 70, ty), p["name"], cn_font=F16, en_font=F16, fill=C_TEXT)
            
            dy = ty + 26
            for line in lines:
                draw_text_mixed(d, (PAD + 70, dy - 2), line, cn_font=F15, en_font=O14, fill=(204,204,204,255))
                dy += desc_lh
                
            d.line([(PAD + 15, ty + rh - 6), (PAD + INNER_W - 15, ty + rh - 6)], fill=(255,255,255,25))
            ty += rh
            
        y += card_h + 20

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
    draw_text_mixed(d, (W - 40 - fw, fy + 23), f"WIKI DATABASE // {data['name']}", cn_font=F18, en_font=O18, fill=C_SUBTEXT)

    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()