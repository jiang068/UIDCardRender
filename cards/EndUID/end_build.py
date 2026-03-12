# 明日方舟：终末地 建设卡片渲染器 (PIL 版)

from __future__ import annotations

import math
import re
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 从 __init__.py 导入字体与工具函数
from . import (
    F12, F14, F16, F20, F24, F30, F48, F56,
    M12, M14, M16, M20, M22, M24,
    O14, O16, O18, O20,
    get_font, draw_text_mixed, _b64_img, _b64_fit
)

# 画布基础属性
W = 1000
PAD = 40
INNER_W = W - PAD * 2

# 颜色定义
C_BG = (15, 16, 20, 255)
C_ACCENT = (255, 230, 0, 255)
C_TEXT = (255, 255, 255, 255)
C_SUBTEXT = (139, 139, 139, 255)
C_BORDER = (255, 255, 255, 25)  # rgba(255,255,255,0.1)
C_PANEL = (255, 255, 255, 8)    # rgba(255,255,255,0.03)

def parse_color(c_str: str, default=(85, 85, 85, 255)) -> tuple:
    c_str = c_str.strip().lower()
    if c_str.startswith("#"):
        c_str = c_str.lstrip("#")
        if len(c_str) == 3: c_str = "".join(c+c for c in c_str)
        if len(c_str) == 6:
            return (int(c_str[0:2], 16), int(c_str[2:4], 16), int(c_str[4:6], 16), 255)
    return default

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg": "",
        "logo": "",
        "avatar": "",
        "name": "未知用户",
        "uid": "",
        "level": "0",
        "world_level": "0",
        "create_time": "N/A",
        "rooms": [],
        "domains": []
    }

    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg"] = bg_el.get("src", "")
    logo_el = soup.select_one(".footer-logo")
    if logo_el: data["logo"] = logo_el.get("src", "")
    av_el = soup.select_one(".avatar img")
    if av_el: data["avatar"] = av_el.get("src", "")

    name_el = soup.select_one(".user-name")
    if name_el: data["name"] = name_el.get_text(strip=True)
    uid_el = soup.select_one(".user-uid")
    if uid_el: data["uid"] = uid_el.get_text(strip=True).replace("UID", "").strip()

    tags = soup.select(".info-tags .tag")
    if len(tags) >= 3:
        data["level"] = tags[0].select_one("strong").get_text(strip=True) if tags[0].select_one("strong") else "0"
        data["world_level"] = tags[1].select_one("strong").get_text(strip=True) if tags[1].select_one("strong") else "0"
        data["create_time"] = tags[2].select_one("strong").get_text(strip=True) if tags[2].select_one("strong") else "N/A"

    # 解析帝江号舱室
    for rc in soup.select(".room-card"):
        color_match = re.search(r"border-top:\s*2px\s*solid\s*(#[a-fA-F0-9]+)", rc.get("style", ""))
        color = parse_color(color_match.group(1)) if color_match else (85, 85, 85, 255)
        
        type_name = rc.select_one(".room-type-name").get_text(strip=True) if rc.select_one(".room-type-name") else ""
        lvl_str = rc.select_one(".room-lvl-text").get_text(strip=True).replace("Lv.", "") if rc.select_one(".room-lvl-text") else "0"
        
        pips = rc.select(".level-pip")
        max_lvl = len(pips)
        cur_lvl = len([p for p in pips if 'filled' in p.get('class', [])])
        
        chars = []
        for ch in rc.select(".room-chars > div"):
            img = ch.select_one("img")
            if img:
                chars.append({"type": "img", "src": img.get("src", "")})
            else:
                chars.append({"type": "text", "text": ch.get_text(strip=True)})
                
        data["rooms"].append({
            "name": type_name,
            "level": lvl_str,
            "max_lvl": max_lvl,
            "cur_lvl": cur_lvl,
            "color": color,
            "chars": chars
        })

    # 解析区域建设
    for dc in soup.select(".domain-card"):
        d_name = dc.select_one(".domain-name").get_text(strip=True) if dc.select_one(".domain-name") else ""
        d_lvl = dc.select_one(".domain-header-left .tag strong").get_text(strip=True) if dc.select_one(".domain-header-left .tag strong") else "0"
        
        money_badge = dc.select_one(".domain-money-badge")
        money_str = ""
        if money_badge:
            # 提取 100 / 100 这类文字
            clone = BeautifulSoup(str(money_badge), "lxml").select_one(".domain-money-badge")
            lbl = clone.select_one(".domain-money-badge-label")
            if lbl: lbl.decompose()
            money_str = clone.get_text(strip=True)
            
        settlements = []
        for sc in dc.select(".settlement-item"):
            bat_pct = sc.select_one(".money-battery-text").get_text(strip=True) if sc.select_one(".money-battery-text") else "0%"
            bat_fill = 0
            fill_el = sc.select_one(".money-battery-fill")
            if fill_el:
                m = re.search(r"height:\s*([\d\.]+)%", fill_el.get("style", ""))
                if m: bat_fill = float(m.group(1))
                
            st_name = sc.select_one(".st-name").get_text(strip=True) if sc.select_one(".st-name") else ""
            st_lvl = sc.select_one(".st-lvl").get_text(strip=True).replace("Lv.", "") if sc.select_one(".st-lvl") else "0"
            
            st_money = sc.select_one(".st-money-text")
            st_money_str = st_money.get_text(strip=True) if st_money else ""
            
            exp_text = sc.select_one(".exp-text").get_text(strip=True) if sc.select_one(".exp-text") else ""
            exp_fill = 0
            is_max = False
            exp_el = sc.select_one(".exp-bar-fill")
            if exp_el:
                if "maxed" in exp_el.get("class", []): is_max = True
                m = re.search(r"width:\s*([\d\.]+)%", exp_el.get("style", ""))
                if m: exp_fill = float(m.group(1))
                if is_max: exp_fill = 100
                
            officers = []
            for oc in sc.select(".char-list > div"):
                img = oc.select_one("img")
                if img:
                    officers.append({"type": "img", "src": img.get("src", "")})
                else:
                    officers.append({"type": "text", "text": oc.get_text(strip=True)})
                    
            settlements.append({
                "bat_pct": bat_pct,
                "bat_fill": bat_fill,
                "name": st_name,
                "level": st_lvl,
                "money_str": st_money_str,
                "exp_text": exp_text,
                "exp_fill": exp_fill,
                "is_max": is_max,
                "officers": officers
            })
            
        data["domains"].append({
            "name": d_name,
            "level": d_lvl,
            "money_str": money_str,
            "settlements": settlements
        })

    return data


def draw_bg(canvas: Image.Image, w: int, h: int, bg_src: str):
    if bg_src:
        try:
            bg_img = _b64_fit(bg_src, w, h).convert("RGBA")
            bg_img.putalpha(Image.new("L", (w, h), 25))
            canvas.alpha_composite(bg_img)
        except Exception: pass

    sw, sh = w // 10, h // 10
    cx, cy = int(sw * 0.5), int(sh * 0.2)
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
            
    grad = grad.resize((w, h), Image.Resampling.LANCZOS)
    canvas.alpha_composite(grad)

    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    grid_c = (38, 39, 44, 180)
    for x in range(0, w, 40): gd.line([(x, 0), (x, h)], fill=grid_c, width=1)
    for y in range(0, h, 40): gd.line([(0, y), (w, y)], fill=grid_c, width=1)
    
    mask = Image.new("L", (w, h), 255)
    md = ImageDraw.Draw(mask)
    fade_h = int(h * 0.2)
    for y in range(fade_h, h):
        alpha = int(255 * (1 - min((y - fade_h) / (h * 0.8), 1.0)))
        md.line([(0, y), (w, y)], fill=alpha)
        
    grid.putalpha(mask)
    canvas.alpha_composite(grid)


def draw_section_title(d: ImageDraw.ImageDraw, x: int, y: int, title_cn: str, title_en: str):
    d.rectangle([x, y + 2, x + 4, y + 22], fill=C_ACCENT)
    draw_text_mixed(d, (x + 12, y - 2), title_cn, cn_font=F20, en_font=F20, fill=C_TEXT, dy_en=4)
    cn_w = int(F20.getlength(title_cn))
    draw_text_mixed(d, (x + 12 + cn_w + 10, y + 3), title_en, cn_font=M14, en_font=M14, fill=C_SUBTEXT, dy_en=3)
    return 24


def render(html: str) -> bytes:
    data = parse_html(html)
    
    # ---------------- 1. 高度预计算 ----------------
    cur_y = PAD
    cur_y += 100 + 25 + 30 # Header
    
    # 帝江号区域
    cur_y += 24 + 15
    space_pad = 20
    room_gap = 12
    room_cols = 5
    room_w = (INNER_W - space_pad * 2 - room_gap * (room_cols - 1)) // room_cols # 约 166px
    room_h = 104 # 固定高度
    
    room_rows = math.ceil(len(data["rooms"]) / room_cols) if data["rooms"] else 0
    spaceship_h = space_pad * 2
    if not data["rooms"]:
        spaceship_h += 60
    else:
        spaceship_h += room_rows * room_h + max(0, room_rows - 1) * room_gap
        
    cur_y += spaceship_h + 30
    
    # 区域建设区域
    cur_y += 24 + 15
    domain_gap = 20
    domain_cols = 2
    domain_w = (INNER_W - domain_gap * (domain_cols - 1)) // domain_cols # 450px
    domain_rows = math.ceil(len(data["domains"]) / domain_cols) if data["domains"] else 0
    
    domain_grid_h = 0
    if data["domains"]:
        for r_idx in range(domain_rows):
            row_items = data["domains"][r_idx*domain_cols : (r_idx+1)*domain_cols]
            max_dh = 0
            for dom in row_items:
                dh = 52 + 15 * 2 # header + body padding
                if not dom["settlements"]:
                    dh += 30
                else:
                    # 每个据点的高度
                    dh += len(dom["settlements"]) * 106 + max(0, len(dom["settlements"]) - 1) * 12
                if dh > max_dh: max_dh = dh
            domain_grid_h += max_dh
            if r_idx < domain_rows - 1: domain_grid_h += domain_gap
            
    cur_y += domain_grid_h + PAD + 50
    total_h = max(cur_y, 800)
    
    # ---------------- 2. 实际绘制 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h, data["bg"])
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    
    # === Header ===
    d.rectangle([PAD, y, PAD + 100, y + 100], fill=(17, 17, 17, 255), outline=C_ACCENT, width=1)
    if data["avatar"]:
        try:
            av_img = _b64_fit(data["avatar"], 100, 100)
            canvas.paste(av_img, (PAD, y))
        except Exception: pass
        
    ux = PAD + 100 + 25
    draw_text_mixed(d, (ux, y + 5), data["name"], cn_font=F48, en_font=F48, fill=C_TEXT, dy_en=10)
    name_w = int(F48.getlength(data["name"]))
    
    if data["uid"]:
        uid_x = ux + name_w + 15
        uid_text = f"UID {data['uid']}"
        uid_w = int(M16.getlength(uid_text))
        d.rounded_rectangle([uid_x, y + 25, uid_x + uid_w + 16, y + 25 + 24], radius=4, fill=(255, 255, 255, 12))
        draw_text_mixed(d, (uid_x + 8, y + 28), uid_text, cn_font=M16, en_font=M16, fill=C_SUBTEXT, dy_en=3)
        
    # Tags
    tag_y = y + 65
    tx = ux
    
    def draw_tag(x, y, label, val, is_cn=False):
        lbl_f = F16 if is_cn else O16
        lbl_w = int(lbl_f.getlength(label))
        val_w = int(O18.getlength(val))
        tw = lbl_w + val_w + 5 + 24
        d.rectangle([x, y, x + tw, y + 28], fill=C_PANEL, outline=C_BORDER, width=1)
        draw_text_mixed(d, (x + 12, y + 4), label, cn_font=lbl_f, en_font=lbl_f, fill=(204, 204, 204, 255), dy_en=3)
        draw_text_mixed(d, (x + 12 + lbl_w + 5, y + 3), val, cn_font=O18, en_font=O18, fill=C_ACCENT, dy_en=4)
        return tw + 15
        
    tx += draw_tag(tx, tag_y, "LEVEL", data["level"])
    tx += draw_tag(tx, tag_y, "WORLD", data["world_level"])
    tx += draw_tag(tx, tag_y, "苏醒日", data["create_time"], is_cn=True)
    
    y += 100 + 25
    d.line([(PAD, y), (W - PAD, y)], fill=C_BORDER, width=1)
    y += 30
    
    # === Spaceship ===
    draw_section_title(d, PAD, y, "帝江号", "SPACESHIP")
    y += 24 + 15
    
    grad_1d = Image.new("RGBA", (INNER_W, 1))
    for xi in range(INNER_W):
        ratio = 1 - (xi / max(INNER_W - 1, 1))
        grad_1d.putpixel((xi, 0), (255, 255, 255, int(8 * ratio)))
    sp_bg = grad_1d.resize((INNER_W, spaceship_h), Image.NEAREST)
    canvas.alpha_composite(sp_bg, (PAD, y))
    d.rectangle([PAD, y, PAD + INNER_W, y + spaceship_h], outline=C_BORDER, width=1)
    
    sy = y + space_pad
    if not data["rooms"]:
        draw_text_mixed(d, (W//2 - 60, sy + 20), "暂无舱室数据", cn_font=F16, en_font=F16, fill=(102, 102, 102, 255), dy_en=3)
    else:
        for r_idx in range(room_rows):
            row_items = data["rooms"][r_idx*room_cols : (r_idx+1)*room_cols]
            for c_idx, item in enumerate(row_items):
                rx = PAD + space_pad + c_idx * (room_w + room_gap)
                ry = sy + r_idx * (room_h + room_gap)
                
                # Card Background
                d.rectangle([rx, ry, rx + room_w, ry + room_h], fill=(0, 0, 0, 102), outline=C_BORDER, width=1)
                d.line([(rx, ry), (rx + room_w, ry)], fill=item["color"], width=2)
                
                # Header
                draw_text_mixed(d, (rx + 14, ry + 12), item["name"], cn_font=F14, en_font=M14, fill=(221, 221, 221, 255), dy_en=3)
                
                lvl_w = int(O14.getlength(f"Lv.{item['level']}"))
                draw_text_mixed(d, (rx + room_w - 14 - lvl_w, ry + 13), f"Lv.{item['level']}", cn_font=O14, en_font=O14, fill=C_SUBTEXT, dy_en=3)
                
                # Pips
                pip_w = 14
                pip_h = 10
                pip_gap = 3
                total_pip_w = item["max_lvl"] * pip_w + max(0, item["max_lvl"] - 1) * pip_gap
                px_start = rx + room_w - 14 - lvl_w - 6 - total_pip_w
                
                for p_i in range(item["max_lvl"]):
                    cx = px_start + p_i * (pip_w + pip_gap)
                    cy = ry + 15
                    skew = 2
                    pts = [(cx + skew, cy), (cx + pip_w + skew, cy), (cx + pip_w - skew, cy + pip_h), (cx - skew, cy + pip_h)]
                    
                    if p_i < item["cur_lvl"]:
                        d.polygon(pts, fill=item["color"])
                    else:
                        d.polygon(pts, outline=(255, 255, 255, 38), width=1)
                        
                d.line([(rx + 14, ry + 36), (rx + room_w - 14, ry + 36)], fill=(255, 255, 255, 12), width=1)
                
                # Avatars (44x44)
                ay = ry + 46
                if not item["chars"]:
                    # 空闲
                    d.rectangle([rx + 14, ay, rx + room_w - 14, ay + 44], outline=(51, 51, 51, 255), width=1)
                    draw_text_mixed(d, (rx + room_w//2 - 12, ay + 14), "空闲", cn_font=F12, en_font=F12, fill=(68, 68, 68, 255), dy_en=2)
                else:
                    curr_x = rx + 14
                    for char in item["chars"]:
                        if char["type"] == "img":
                            try:
                                av = _b64_fit(char["src"], 44, 44)
                                canvas.paste(av, (curr_x, ay))
                                d.rectangle([curr_x, ay, curr_x + 44, ay + 44], outline=(68, 68, 68, 255), width=1)
                            except Exception: pass
                        else:
                            d.rectangle([curr_x, ay, curr_x + 44, ay + 44], outline=(68, 68, 68, 255), width=1)
                            # 虚线效果简化为深灰色实线，居中文字
                            draw_text_mixed(d, (curr_x + 10, ay + 14), char["text"][:2], cn_font=F12, en_font=F12, fill=(68, 68, 68, 255), dy_en=2)
                        curr_x += 44 + 6
                        
    y += spaceship_h + 30
    
    # === Domains ===
    draw_section_title(d, PAD, y, "区域建设", "DOMAINS")
    y += 24 + 15
    
    dy = y
    for r_idx in range(domain_rows):
        row_items = data["domains"][r_idx*domain_cols : (r_idx+1)*domain_cols]
        max_dh = 0
        for c_idx, dom in enumerate(row_items):
            dx = PAD + c_idx * (domain_w + domain_gap)
            
            dh = 52 + 15 * 2
            if not dom["settlements"]: dh += 30
            else: dh += len(dom["settlements"]) * 106 + max(0, len(dom["settlements"]) - 1) * 12
            if dh > max_dh: max_dh = dh
            
            # Domain BG
            d.rectangle([dx, dy, dx + domain_w, dy + dh], fill=C_PANEL, outline=C_BORDER, width=1)
            d.rectangle([dx, dy, dx + domain_w, dy + 52], fill=(255, 255, 255, 12))
            d.line([(dx, dy + 52), (dx + domain_w, dy + 52)], fill=C_BORDER, width=1)
            
            # Header Name & Level
            draw_text_mixed(d, (dx + 18, dy + 14), dom["name"], cn_font=F20, en_font=F20, fill=C_TEXT, dy_en=4)
            name_w = int(F20.getlength(dom["name"]))
            
            lvl_x = dx + 18 + name_w + 12
            d.rectangle([lvl_x, dy + 16, lvl_x + 40, dy + 36], fill=C_PANEL, outline=C_BORDER, width=1)
            draw_text_mixed(d, (lvl_x + 5, dy + 18), f"Lv.{dom['level']}", cn_font=F14, en_font=O14, fill=C_ACCENT, dy_en=3)
            
            # Money Badge
            if dom["money_str"]:
                badge_w = int(M14.getlength(dom["money_str"])) + 50
                bx = dx + domain_w - 18 - badge_w
                d.rounded_rectangle([bx, dy + 14, bx + badge_w, dy + 38], radius=4, fill=(0, 0, 0, 64), outline=(255, 255, 255, 15), width=1)
                draw_text_mixed(d, (bx + 10, dy + 18), "调度券", cn_font=F12, en_font=F12, fill=(102, 102, 102, 255), dy_en=2)
                # 区分高亮部分 (通过空格简单分割)
                parts = dom["money_str"].split("/")
                if len(parts) == 2:
                    draw_text_mixed(d, (bx + 48, dy + 18), parts[0].strip(), cn_font=M14, en_font=M14, fill=C_ACCENT, dy_en=3)
                    p0_w = int(M14.getlength(parts[0].strip()))
                    draw_text_mixed(d, (bx + 48 + p0_w, dy + 18), f" / {parts[1].strip()}", cn_font=M14, en_font=M14, fill=C_SUBTEXT, dy_en=3)
                else:
                    draw_text_mixed(d, (bx + 48, dy + 18), dom["money_str"], cn_font=M14, en_font=M14, fill=C_SUBTEXT, dy_en=3)
                    
            # Settlements
            sty = dy + 52 + 15
            if not dom["settlements"]:
                draw_text_mixed(d, (dx + domain_w//2 - 30, sty + 5), "暂无据点", cn_font=F12, en_font=F12, fill=(102, 102, 102, 255), dy_en=2)
            else:
                for st in dom["settlements"]:
                    sh = 106
                    d.rectangle([dx + 15, sty, dx + domain_w - 15, sty + sh], fill=(0, 0, 0, 51))
                    d.line([(dx + 15, sty), (dx + 15, sty + sh)], fill=(85, 85, 85, 255), width=2)
                    
                    # Battery Col
                    bat_x, bat_y = dx + 27, sty + 12
                    
                    # Cap
                    d.rounded_rectangle([bat_x + 10, bat_y - 4, bat_x + 26, bat_y + 1], radius=2, fill=(255, 255, 255, 30))
                    # Body
                    d.rounded_rectangle([bat_x, bat_y, bat_x + 36, bat_y + 60], radius=3, fill=(0, 0, 0, 76), outline=(255, 255, 255, 30), width=1)
                    
                    # Fill
                    fill_h = max(0, min(60, int(60 * st["bat_fill"] / 100)))
                    if fill_h > 0:
                        fill_img = Image.new("RGBA", (34, fill_h))
                        fd = ImageDraw.Draw(fill_img)
                        for fi in range(fill_h):
                            ratio = fi / fill_h
                            fd.line([(0, fi), (34, fi)], fill=(int(255), int(230 + 25*ratio), int(0 + 102*ratio), 255))
                        canvas.alpha_composite(fill_img, (bat_x + 1, bat_y + 60 - fill_h))
                        
                    # Battery Text (Draw shadow then text)
                    tw = int(M12.getlength(st["bat_pct"]))
                    t_pos = (bat_x + 18 - tw//2, bat_y + 24)
                    for ox, oy in [(-1,-1), (1,-1), (-1,1), (1,1), (0,1)]:
                        draw_text_mixed(d, (t_pos[0]+ox, t_pos[1]+oy), st["bat_pct"], cn_font=M12, en_font=M12, fill=(0, 0, 0, 255), dy_en=2)
                    draw_text_mixed(d, t_pos, st["bat_pct"], cn_font=M12, en_font=M12, fill=(255, 255, 255, 255), dy_en=2)
                    
                    draw_text_mixed(d, (bat_x + 3, bat_y + 64), "调度券", cn_font=F12, en_font=F12, fill=(153, 153, 153, 255), dy_en=2)
                    
                    # Info Col
                    info_x = bat_x + 36 + 12
                    info_y = sty + 12
                    
                    draw_text_mixed(d, (info_x, info_y + 2), st["name"], cn_font=F16, en_font=F16, fill=(204, 204, 204, 255), dy_en=3)
                    nw = int(F16.getlength(st["name"]))
                    draw_text_mixed(d, (info_x + nw + 8, info_y + 3), f"Lv.{st['level']}", cn_font=O16, en_font=O16, fill=C_SUBTEXT, dy_en=3)
                    
                    money_w = int(M14.getlength(st["money_str"]))
                    mx = dx + domain_w - 15 - 12 - money_w
                    # 区分高亮部分
                    m_parts = st["money_str"].split("/")
                    if len(m_parts) == 2:
                        draw_text_mixed(d, (mx, info_y + 4), m_parts[0].strip(), cn_font=M14, en_font=M14, fill=C_ACCENT, dy_en=3)
                        mp0_w = int(M14.getlength(m_parts[0].strip()))
                        draw_text_mixed(d, (mx + mp0_w, info_y + 4), f" / {m_parts[1].strip()}", cn_font=M14, en_font=M14, fill=C_SUBTEXT, dy_en=3)
                    else:
                        draw_text_mixed(d, (mx, info_y + 4), st["money_str"], cn_font=M14, en_font=M14, fill=C_SUBTEXT, dy_en=3)
                        
                    # Exp Row
                    exp_y = info_y + 26
                    draw_text_mixed(d, (info_x, exp_y), "EXP", cn_font=M12, en_font=M12, fill=(153, 153, 153, 255), dy_en=2)
                    
                    exp_text_w = int(M12.getlength(st["exp_text"]))
                    exp_text_x = dx + domain_w - 15 - 12 - exp_text_w
                    tc = C_ACCENT if st["is_max"] else (153, 153, 153, 255)
                    draw_text_mixed(d, (exp_text_x, exp_y), st["exp_text"], cn_font=M12, en_font=M12, fill=tc, dy_en=2)
                    
                    bar_x = info_x + 28 + 8
                    bar_w = exp_text_x - bar_x - 8
                    d.rounded_rectangle([bar_x, exp_y + 3, bar_x + bar_w, exp_y + 13], radius=2, fill=(26, 26, 26, 255), outline=(255, 255, 255, 15), width=1)
                    if st["exp_fill"] > 0:
                        f_w = max(4, int(bar_w * st["exp_fill"] / 100))
                        fc = C_ACCENT if st["is_max"] else (119, 119, 119, 255)
                        d.rounded_rectangle([bar_x, exp_y + 3, bar_x + f_w, exp_y + 13], radius=2, fill=fc)
                        
                    # Officer Row
                    off_y = exp_y + 18
                    draw_text_mixed(d, (info_x, off_y + 12), "驻守", cn_font=F12, en_font=F12, fill=(153, 153, 153, 255), dy_en=2)
                    
                    ox = info_x + 28 + 8
                    if not st["officers"]:
                        d.rectangle([ox, off_y, ox + 40, off_y + 40], outline=(51, 51, 51, 255), width=1)
                        draw_text_mixed(d, (ox + 16, off_y + 12), "-", cn_font=F16, en_font=F16, fill=(68, 68, 68, 255), dy_en=3)
                    else:
                        for off in st["officers"]:
                            if off["type"] == "img":
                                try:
                                    av = _b64_fit(off["src"], 40, 40)
                                    canvas.paste(av, (ox, off_y))
                                    d.rectangle([ox, off_y, ox + 40, off_y + 40], outline=(68, 68, 68, 255), width=1)
                                except Exception: pass
                            else:
                                d.rectangle([ox, off_y, ox + 40, off_y + 40], outline=(51, 51, 51, 255), width=1)
                                draw_text_mixed(d, (ox + 10, off_y + 12), off["text"][:2], cn_font=F12, en_font=F12, fill=(68, 68, 68, 255), dy_en=2)
                            ox += 40 + 5

                    sty += sh + 12
                    
        dy += max_dh + domain_gap
        
    # === Footer ===
    if data["logo"]:
        try:
            logo = _b64_img(data["logo"])
            lw = 120
            lh = int(logo.height * (lw / logo.width))
            logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
            logo.putalpha(ImageChops.multiply(logo.split()[3], Image.new("L", (lw, lh), 76)))
            canvas.alpha_composite(logo, (W - 40 - lw, total_h - 20 - lh))
        except Exception: pass

    # 最终输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()