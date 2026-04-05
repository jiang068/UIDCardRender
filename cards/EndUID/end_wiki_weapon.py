# cards/EndUID/end_wiki_weapon.py
from __future__ import annotations

import math
import re
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 导入所有必要的字体与工具函数
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit, _round_mask, _is_pure_en_num,
    F12, F13, F14, F15, F16, F17, F18, F20, F24, F28, F42,
    M10, M11, M12, M13, M14, M16, M20,
    O12, O14, O16, O20, O24
)

# --------------------------------------------------
# 常量定义与辅助函数
# --------------------------------------------------
W = 800
PAD = 40
INNER_W = W - PAD * 2  # 720

C_BG = (15, 16, 20, 255)
C_ACCENT = (255, 230, 0, 255)
C_TEXT = (255, 255, 255, 255)
C_SUBTEXT = (139, 139, 139, 255)
C_CARD_BG = (20, 21, 24, 230)

def parse_color(c_str: str, default=(255, 255, 255, 255)) -> tuple:
    if not c_str: return default
    c_str = c_str.strip()
    if c_str.startswith('#'):
        c_str = c_str.lstrip('#')
        if len(c_str) == 3: c_str = ''.join(c*2 for c in c_str)
        return tuple(int(c_str[i:i+2], 16) for i in (0, 2, 4)) + (255,)
    m = re.search(r'rgba?\(([^)]+)\)', c_str)
    if m:
        parts = [p.strip() for p in m.group(1).split(',')]
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        a = int(float(parts[3]) * 255) if len(parts) >= 4 else 255
        return (r, g, b, a)
    return default

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, r: int, fill: tuple, outline: tuple = None, width: int = 1):
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(block, (x0, y0))

def _calc_mixed_w(text: str, cn_font, en_font) -> int:
    if not text: return 0
    w = 0
    for ch in str(text):
        if _is_pure_en_num(ch): w += en_font.getlength(ch)
        else: w += cn_font.getlength(ch)
    return int(w)

def wrap_text_mixed(text: str, cn_font, en_font, max_width: int) -> list[str]:
    """智能中英混合字体文本换行系统"""
    lines = []
    line = ""
    for char in text:
        if _calc_mixed_w(line + char, cn_font, en_font) <= max_width:
            line += char
        else:
            lines.append(line)
            line = char
    if line:
        lines.append(line)
    return lines

# --------------------------------------------------
# DOM 解析
# --------------------------------------------------
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg": "", "end_logo": "", "name": "未知武器",
        "rarity": 0, "rarity_color": (255, 230, 0, 255),
        "type_tag": "", "weapon_img": "",
        "stats": [], "passives": [], "gems": [],
        "skills": [], "breakthroughs": []
    }

    style_tag = soup.select_one("style")
    if style_tag:
        m = re.search(r'--c-rarity:\s*(#[0-9a-fA-F]+)', style_tag.get_text())
        if m: data["rarity_color"] = parse_color(m.group(1))

    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg"] = bg_el.get("src", "")
    logo_el = soup.select_one(".footer-logo")
    if logo_el: data["end_logo"] = logo_el.get("src", "")

    name_el = soup.select_one(".weapon-name")
    if name_el: data["name"] = name_el.get_text(strip=True)
    data["rarity"] = len(soup.select(".rarity-star"))
    type_el = soup.select_one(".type-badge")
    if type_el: data["type_tag"] = type_el.get_text(strip=True)
    img_el = soup.select_one(".weapon-icon-wrap img")
    if img_el: data["weapon_img"] = img_el.get("src", "")

    for sec in soup.select(".section"):
        title_node = sec.select_one(".section-title")
        if not title_node: continue
        title_text = title_node.get_text()

        if "ATTRIBUTES" in title_text:
            for box in sec.select(".stat-box"):
                lbl = box.select_one(".stat-label").get_text(strip=True)
                init = box.select_one(".stat-init").get_text(strip=True) if box.select_one(".stat-init") else ""
                max_val = box.select_one(".stat-max").get_text(strip=True) if box.select_one(".stat-max") else ""
                data["stats"].append({"label": lbl, "init": init, "max": max_val})

        elif "PASSIVE" in title_text:
            for block in sec.select(".passive-block"):
                is_max = "max" in block.get("class", [])
                name = block.select_one(".passive-name").get_text(strip=True) if block.select_one(".passive-name") else ""
                desc = block.select_one(".passive-desc").get_text(strip=True) if block.select_one(".passive-desc") else ""
                data["passives"].append({"name": name, "desc": desc, "is_max": is_max})

        elif "RECOMMENDED GEM" in title_text:
            for row in sec.select("div[style*='flex-wrap:wrap'] > div"):
                img = row.select_one("img")
                cover = img["src"] if img else ""
                name = row.select("div")[-1].get_text(strip=True) if row.select("div") else ""
                data["gems"].append({"cover": cover, "name": name})

        elif "SKILL DATA" in title_text:
            for skill_div in sec.select("div[style*='margin-bottom:16px']"):
                s_name = skill_div.select_one("div").get_text(strip=True)
                table = skill_div.select_one(".rank-table")
                if not table: continue
                headers = [th.get_text(strip=True) for th in table.select("th")]
                values = [td.get_text(strip=True) for td in table.select("td")]
                data["skills"].append({"name": s_name, "headers": headers, "values": values})

        elif "BREAKTHROUGH" in title_text:
            for bt_div in sec.select("div[style*='margin-bottom:14px']"):
                lvl = bt_div.select_one("div").get_text(strip=True)
                mats = []
                for m_box in bt_div.select("div[style*='background:rgba(0,0,0,0.25)']"):
                    img = m_box.select_one("img")
                    m_cover = img["src"] if img else ""
                    m_name = m_box.select_one("div > div:nth-of-type(1)").get_text(strip=True)
                    m_count = m_box.select_one("div > div:nth-of-type(2)").get_text(strip=True)
                    mats.append({"cover": m_cover, "name": m_name, "count": m_count})
                data["breakthroughs"].append({"level": lvl, "materials": mats})

    return data


# --------------------------------------------------
# 主渲染引擎
# --------------------------------------------------
def render(html: str) -> bytes:
    data = parse_html(html)
    RC = data["rarity_color"]
    RC_alpha_border = (RC[0], RC[1], RC[2], int(255 * 0.4))
    RC_alpha_bg = (RC[0], RC[1], RC[2], int(255 * 0.08))

    # 1. 动态高度预计算与排版生成
    H = PAD
    H += 110 + 16 # Header 高度 + border bottom
    H += 20 # Header margin bottom

    desc_lh = 22 # 常规行高
    def _sec_title_h(): return 18 + 8 + 14

    # ==== 计算 基础属性 的动态高度 ====
    if data["stats"]:
        # 智能探测需要几列排版 (防止文字超长溢出)
        max_req_w = 0
        for st in data["stats"]:
            lw = _calc_mixed_w(st["label"], F12, M12)
            vw = _calc_mixed_w(st["init"], F24, O24)
            if st["max"]: vw += 24 + _calc_mixed_w(st["max"], F24, O24)
            max_req_w = max(max_req_w, max(lw, vw) + 28)

        if max_req_w > (INNER_W - 24) // 3: stat_cols = 2
        else: stat_cols = 3
        if max_req_w > (INNER_W - 12) // 2: stat_cols = 1
        
        col_w = (INNER_W - (stat_cols - 1) * 12) // stat_cols

        H += 18 * 2 + _sec_title_h()
        stat_rows = [data["stats"][i:i+stat_cols] for i in range(0, len(data["stats"]), stat_cols)]
        for row in stat_rows:
            max_h = 58
            for st in row:
                st["_lbl_lines"] = wrap_text_mixed(st["label"], F12, M12, col_w - 28)
                
                # 数值是否需要换行绘制
                vw = _calc_mixed_w(st["init"], F24, O24)
                if st["max"]: vw += 24 + _calc_mixed_w(st["max"], F24, O24)
                
                if vw <= col_w - 28:
                    st["_val_wrap"] = False
                    val_h = 24
                else:
                    st["_val_wrap"] = True
                    st["_init_lines"] = wrap_text_mixed(st["init"], F20, O20, col_w - 28)
                    st["_max_lines"] = wrap_text_mixed(st["max"], F20, O20, col_w - 28 - 24) if st["max"] else []
                    val_h = len(st["_init_lines"]) * 24 + len(st["_max_lines"]) * 24

                h = 12 + len(st["_lbl_lines"]) * 16 + 4 + val_h + 12
                if h > max_h: max_h = h
            for st in row: st["_row_h"] = max_h
            H += max_h + 12
        H -= 12
        H += 20

    if data["passives"]:
        H += 18 * 2 + _sec_title_h()
        for p in data["passives"]:
            H += 14 * 2 + 24 # pad + name row
            lines = wrap_text_mixed(p["desc"], F13, M13, INNER_W - 44 - 32)
            p["_lines"] = lines
            H += len(lines) * desc_lh + 6 # desc
            H += 10 # mb
        H += 20

    if data["gems"]:
        H += 18 * 2 + _sec_title_h()
        cur_x, cur_y, line_h = 0, 0, 68
        for g in data["gems"]:
            item_w = 32 + (60 if g["cover"] else 0) + _calc_mixed_w(g["name"], F16, M16)
            if cur_x + item_w > INNER_W - 44:
                cur_x = 0
                cur_y += line_h + 16
            cur_x += item_w + 16
        H += cur_y + line_h + 20

    # ==== 计算 技能数值 的动态高度 (支持单元格内长文本换行) ====
    if data["skills"]:
        H += 18 * 2 + _sec_title_h()
        for s in data["skills"]:
            s["_name_lines"] = wrap_text_mixed(s["name"], F15, F15, INNER_W - 48)
            H += len(s["_name_lines"]) * 22 + 6
            
            # 计算表格高度
            cols = len(s["headers"])
            col_w = INNER_W // max(1, cols)
            s["_col_w"] = col_w
            
            # 预计算每列的折行
            s["_val_lines_list"] = []
            max_lines = 1
            for v in s["values"]:
                v_lines = wrap_text_mixed(v, F12, M11, col_w - 10)
                s["_val_lines_list"].append(v_lines)
                max_lines = max(max_lines, len(v_lines))
                
            s["_row_h"] = max(28, max_lines * 18 + 10)
            H += 26 + s["_row_h"] + 16
        H += 20

    if data["breakthroughs"]:
        H += 18 * 2 + _sec_title_h()
        for bt in data["breakthroughs"]:
            H += 22
            cur_x, cur_y, line_h = 0, 0, 52
            for m in bt["materials"]:
                item_w = 24 + (44 if m["cover"] else 0) + max(_calc_mixed_w(m["name"], F13, M13), _calc_mixed_w(m["count"], F12, M12))
                if cur_x + item_w > INNER_W - 44:
                    cur_x = 0
                    cur_y += line_h + 12
                cur_x += item_w + 12
            H += cur_y + line_h + 14
        H += 20

    H += 80 # Footer + Bottom pad
    
    # 2. 准备底板与渐变背景
    canvas = Image.new("RGBA", (W, H), C_BG)
    
    base_grad = Image.new("RGBA", (1, 2))
    base_grad.putpixel((0, 0), (45, 45, 50, 255))
    base_grad.putpixel((0, 1), (8, 8, 10, 255))
    grad = base_grad.resize((W, H), Image.Resampling.BILINEAR)
    canvas.alpha_composite(grad, (0, 0))

    if data["bg"]:
        try:
            bg_img = _b64_fit(data["bg"], W, H).convert("RGBA")
            bg_img.putalpha(Image.new("L", (W, H), 38))
            canvas.alpha_composite(bg_img)
        except Exception: pass

    grad_layer = Image.new("RGBA", (1, 100), (0, 0, 0, 0))
    for i in range(100):
        if i >= 85:
            alpha = int(24 * ((i - 85) / 15))
            grad_layer.putpixel((0, i), (RC[0], RC[1], RC[2], alpha))
    grad_layer = grad_layer.resize((W, H), Image.Resampling.LANCZOS)
    canvas.alpha_composite(grad_layer, (0, 0))

    d = ImageDraw.Draw(canvas)
    y = PAD

    # --- 3. 绘制 Header ---
    _draw_rounded_rect(canvas, PAD, y, PAD + 110, y + 110, 12, (255, 255, 255, 7), outline=RC_alpha_border, width=2)
    if data["weapon_img"]:
        try:
            w_img = _b64_fit(data["weapon_img"], 100, 100)
            canvas.alpha_composite(w_img, (PAD + 5, y + 5))
        except: pass
    _draw_rounded_rect(canvas, PAD, y + 110 - 3, PAD + 110, y + 110, 0, RC)

    info_x = PAD + 130
    for i in range(data["rarity"]):
        cx = info_x + i * 26
        d.ellipse([cx, y + 2, cx + 18, y + 20], fill=RC)
        d.ellipse([cx + 3, y + 5, cx + 15, y + 17], fill=(255, 204, 0, 255))
    
    draw_text_mixed(d, (info_x - 4, y + 26), data["name"], F42, F42, fill=C_TEXT)
    
    tb_y = y + 76
    _draw_rounded_rect(canvas, info_x, tb_y, info_x + _calc_mixed_w(data["type_tag"], F13, M13) + 24, tb_y + 24, 0, RC_alpha_bg)
    d.line([(info_x, tb_y), (info_x, tb_y + 24)], fill=RC, width=3)
    draw_text_mixed(d, (info_x + 12, tb_y + 2), data["type_tag"], F13, M13, fill=RC)

    y += 110 + 16
    d.line([(PAD, y), (W - PAD, y)], fill=(255, 255, 255, 20), width=1)
    y += 20

    def draw_sec_title(title_cn, title_en):
        draw_text_mixed(d, (PAD + 22, y + 18 - 4), title_cn, F18, F18, fill=C_ACCENT)
        tw = _calc_mixed_w(title_cn, F18, F18)
        draw_text_mixed(d, (PAD + 22 + tw + 8, y + 24 - 2), title_en, F12, M12, fill=C_SUBTEXT)
        d.line([(PAD + 22, y + 46), (W - PAD - 22, y + 46)], fill=(255, 255, 255, 15), width=1)
        return y + 60

    # --- 4. 绘制 Sections ---
    if data["stats"]:
        sec_h = 18 * 2 + _sec_title_h()
        for row in stat_rows: sec_h += row[0]["_row_h"] + 12
        sec_h -= 12
        
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + sec_h, 0, C_CARD_BG, outline=(255, 255, 255, 15))
        cy = draw_sec_title("基础属性", "ATTRIBUTES")
        
        for row in stat_rows:
            max_h = row[0]["_row_h"]
            for c, st in enumerate(row):
                bx, by = PAD + 22 + c * (col_w + 12), cy
                d.rectangle([bx, by, bx + col_w, by + max_h], fill=(0, 0, 0, 76))
                d.line([(bx, by), (bx, by + max_h)], fill=(255, 255, 255, 15), width=2)
                
                ly = by + 12
                for line in st["_lbl_lines"]:
                    draw_text_mixed(d, (bx + 14, ly - 2), line, F12, M12, fill=C_SUBTEXT)
                    ly += 16
                
                vy = ly + 4
                if not st["_val_wrap"]:
                    draw_text_mixed(d, (bx + 14, vy), st["init"], F24, O24, fill=C_TEXT)
                    if st["max"]:
                        sw = _calc_mixed_w(st["init"], F24, O24)
                        draw_text_mixed(d, (bx + 14 + sw + 12, vy + 8), "→", F14, M14, fill=(85, 85, 85, 255))
                        draw_text_mixed(d, (bx + 14 + sw + 35, vy), st["max"], F24, O24, fill=RC)
                else:
                    for line in st["_init_lines"]:
                        draw_text_mixed(d, (bx + 14, vy), line, F20, O20, fill=C_TEXT)
                        vy += 24
                    if st["_max_lines"]:
                        for i, line in enumerate(st["_max_lines"]):
                            if i == 0:
                                draw_text_mixed(d, (bx + 14, vy + 6), "→", F14, M14, fill=(85, 85, 85, 255))
                                draw_text_mixed(d, (bx + 35, vy), line, F20, O20, fill=RC)
                            else:
                                draw_text_mixed(d, (bx + 35, vy), line, F20, O20, fill=RC)
                            vy += 24

            cy += max_h + 12
        y += sec_h + 20

    if data["passives"]:
        sec_h = 18 * 2 + _sec_title_h()
        for p in data["passives"]:
            sec_h += 28 + 24 + len(p["_lines"]) * desc_lh + 6 + 10
        
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + sec_h, 0, C_CARD_BG, outline=(255, 255, 255, 15))
        cy = draw_sec_title("附术效果", "PASSIVE (MAX)")
        
        for p in data["passives"]:
            bh = 28 + 24 + len(p["_lines"]) * desc_lh + 6
            p_bg = (255, 152, 0, 10) if p["is_max"] else RC_alpha_bg
            p_line = (255, 152, 0, 255) if p["is_max"] else RC
            
            d.rectangle([PAD + 22, cy, PAD + INNER_W - 22, cy + bh], fill=p_bg)
            d.line([(PAD + 22, cy), (PAD + 22, cy + bh)], fill=p_line, width=3)
            
            draw_text_mixed(d, (PAD + 38, cy + 14 - 3), p["name"], F17, F17, fill=C_TEXT)
            
            dy = cy + 42
            for line in p["_lines"]:
                draw_text_mixed(d, (PAD + 38, dy - 2), line, F13, M13, fill=(187, 187, 187, 255))
                dy += desc_lh
            cy += bh + 10
        y += sec_h + 20

    if data["gems"]:
        cur_x, cur_y, line_h = 0, 0, 68
        for g in data["gems"]:
            item_w = 32 + (60 if g["cover"] else 0) + _calc_mixed_w(g["name"], F16, M16)
            if cur_x + item_w > INNER_W - 44:
                cur_x = 0; cur_y += line_h + 16
            cur_x += item_w + 16
        
        sec_h = 18 * 2 + _sec_title_h() + cur_y + line_h
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + sec_h, 0, C_CARD_BG, outline=(255, 255, 255, 15))
        cy = draw_sec_title("基质推荐", "RECOMMENDED GEM")
        
        cx, dy = PAD + 22, cy
        for g in data["gems"]:
            item_w = 32 + (60 if g["cover"] else 0) + _calc_mixed_w(g["name"], F16, M16)
            if cx - (PAD + 22) + item_w > INNER_W - 44:
                cx = PAD + 22; dy += line_h + 16
                
            d.rectangle([cx, dy, cx + item_w, dy + line_h], fill=(0, 0, 0, 64))
            d.line([(cx, dy), (cx, dy + line_h)], fill=RC, width=2)
            
            ix = cx + 16
            if g["cover"]:
                try:
                    c_img = _b64_fit(g["cover"], 48, 48)
                    _draw_rounded_rect(canvas, ix, dy + 10, ix + 48, dy + 58, 8, (255, 255, 255, 7))
                    canvas.alpha_composite(c_img, (ix, dy + 10))
                    ix += 60
                except: pass
            
            draw_text_mixed(d, (ix, dy + 24), g["name"], F16, M16, fill=(221, 221, 221, 255))
            cx += item_w + 16
        y += sec_h + 20

    if data["skills"]:
        sec_h = 18 * 2 + _sec_title_h()
        for s in data["skills"]: 
            sec_h += len(s["_name_lines"]) * 22 + 6 + 26 + s["_row_h"] + 16
            
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + sec_h, 0, C_CARD_BG, outline=(255, 255, 255, 15))
        cy = draw_sec_title("技能数值", "SKILL DATA")
        
        for s in data["skills"]:
            for line in s["_name_lines"]:
                draw_text_mixed(d, (PAD + 24, cy - 2), line, F15, F15, fill=(221, 221, 221, 255))
                cy += 22
            cy += 6
            
            col_w = s["_col_w"]
            
            d.rectangle([PAD + 22, cy, PAD + INNER_W - 22, cy + 26], fill=(255, 230, 0, 15))
            d.line([(PAD + 22, cy + 26), (PAD + INNER_W - 22, cy + 26)], fill=(255, 255, 255, 20), width=1)
            
            for i, th in enumerate(s["headers"]):
                tw = _calc_mixed_w(th, F12, M11)
                x = PAD + 22 + i * col_w + (col_w - tw) // 2
                draw_text_mixed(d, (x, cy + 6 - 2), th, F12, M11, fill=C_ACCENT)
            cy += 26
            
            d.line([(PAD + 22, cy + s["_row_h"]), (PAD + INNER_W - 22, cy + s["_row_h"])], fill=(255, 255, 255, 7), width=1)
            
            for i, v_lines in enumerate(s["_val_lines_list"]):
                x_center = PAD + 22 + i * col_w + col_w // 2
                ly = cy + 8
                for line in v_lines:
                    tw = _calc_mixed_w(line, F12, M11)
                    draw_text_mixed(d, (x_center - tw//2, ly), line, F12, M11, fill=C_TEXT)
                    ly += 18
            cy += s["_row_h"] + 16
        y += sec_h + 20

    if data["breakthroughs"]:
        cur_x, cur_y, line_h = 0, 0, 52
        sec_h = 18 * 2 + _sec_title_h()
        for bt in data["breakthroughs"]:
            sec_h += 22
            cx, cy = 0, 0
            for m in bt["materials"]:
                item_w = 24 + (44 if m["cover"] else 0) + max(_calc_mixed_w(m["name"], F13, M13), _calc_mixed_w(m["count"], F12, M12))
                if cx + item_w > INNER_W - 44:
                    cx = 0; cy += line_h + 12
                cx += item_w + 12
            sec_h += cy + line_h + 14
        
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + sec_h, 0, C_CARD_BG, outline=(255, 255, 255, 15))
        cy = draw_sec_title("突破材料", "BREAKTHROUGH")
        
        for bt in data["breakthroughs"]:
            draw_text_mixed(d, (PAD + 22, cy - 2), bt["level"], F14, M14, fill=(170, 170, 170, 255))
            cy += 22
            
            cx, base_y = PAD + 22, cy
            for m in bt["materials"]:
                item_w = 24 + (44 if m["cover"] else 0) + max(_calc_mixed_w(m["name"], F13, M13), _calc_mixed_w(m["count"], F12, M12))
                if cx - (PAD + 22) + item_w > INNER_W - 44:
                    cx = PAD + 22; base_y += line_h + 12
                    
                _draw_rounded_rect(canvas, cx, base_y, cx + item_w, base_y + line_h, 4, (0, 0, 0, 64))
                ix = cx + 12
                if m["cover"]:
                    try:
                        c_img = _b64_fit(m["cover"], 36, 36)
                        canvas.alpha_composite(c_img, (ix, base_y + 8))
                        ix += 44
                    except: pass
                
                draw_text_mixed(d, (ix, base_y + 8), m["name"], F13, F13, fill=(221, 221, 221, 255))
                draw_text_mixed(d, (ix, base_y + 26), f"x{m['count']}", F12, M12, fill=RC)
                cx += item_w + 12
            cy = base_y + line_h + 14
        y += sec_h + 20

    # --- 5. Footer ---
    fy = H - 60
    _draw_rounded_rect(canvas, 0, fy, W, H, 0, (10, 10, 12, 250))
    d.line([(0, fy), (W, fy)], fill=(RC[0], RC[1], RC[2], 64), width=2)
    
    if data["end_logo"]:
        try:
            logo = _b64_img(data["end_logo"])
            lh = 24
            lw = int(logo.width * (lh / logo.height))
            logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
            logo.putalpha(ImageChops.multiply(logo.split()[3], Image.new("L", (lw, lh), 178)))
            canvas.alpha_composite(logo, (40, fy + 18))
        except: pass
        
    fw = _calc_mixed_w(f"WEAPON // {data['name']}", F14, O14)
    draw_text_mixed(d, (W - 40 - fw, fy + 22), f"WEAPON // {data['name']}", F14, O14, fill=C_SUBTEXT)

    # 导出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()