# 明日方舟：终末地 个人名片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# 避免循环导入，直接引入工具函数并局部生成字体
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit, _round_mask,
    F14, F16, F22, F28, F48, F64,
    M14, M16, M20, M24,
    O14, O18, O24, O36, O48, O64
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

# 稀有度颜色
R_COLORS = {
    6: (255, 78, 32, 255),
    5: (255, 201, 0, 255),
    4: (163, 102, 255, 255),
    3: (0, 145, 255, 255)
}


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg_url": "",
        "avatar": "",
        "name": "未知用户",
        "uid": "",
        "awake_date": "UNKNOWN",
        "dash_cards": [],
        "chars": []
    }

    # 背景
    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg_url"] = bg_el.get("src", "")

    # 头像区
    av_el = soup.select_one(".avatar-box img")
    if av_el: data["avatar"] = av_el.get("src", "")
    
    name_el = soup.select_one(".user-name")
    if name_el:
        clone = BeautifulSoup(str(name_el), "lxml").select_one(".user-name")
        for tag in clone.select("span"): tag.decompose()
        data["name"] = clone.get_text(strip=True)
        
    uid_el = soup.select_one(".uid-tag")
    if uid_el: data["uid"] = uid_el.get_text(strip=True).replace("UID", "").strip()
    
    awake_el = soup.select_one(".awake-date")
    if awake_el: data["awake_date"] = awake_el.get_text(strip=True).replace("苏醒日：", "").strip()

    # 仪表盘数据
    for dc in soup.select(".dash-card"):
        is_mission = "card-mission" in dc.get("class", [])
        is_logo = "card-logo" in dc.get("class", [])
        
        if is_logo:
            img = dc.select_one("img")
            data["dash_cards"].append({"type": "logo", "src": img.get("src", "") if img else ""})
        elif is_mission:
            num = dc.select_one(".stat-num").get_text(strip=True) if dc.select_one(".stat-num") else ""
            lbl = dc.select_one(".stat-label").get_text(strip=True) if dc.select_one(".stat-label") else ""
            data["dash_cards"].append({"type": "mission", "num": num, "label": lbl})
        else:
            num_el = dc.select_one(".stat-num")
            lbl_el = dc.select_one(".stat-label")
            if num_el and lbl_el:
                data["dash_cards"].append({
                    "type": "stat", 
                    "num": num_el.get_text(strip=True), 
                    "label": lbl_el.get_text(strip=True)
                })

    # 干员列表
    for cc in soup.select(".char-card"):
        if cc.get("style") and "opacity:0.3" in cc.get("style").replace(" ", ""):
            data["chars"].append({"empty": True})
            continue
            
        img_el = cc.select_one(".char-img")
        avatar = img_el.get("src", "") if img_el and img_el.name == "img" else ""
            
        icons = [img.get("src", "") for img in cc.select(".char-icon")]
        
        pot_el = cc.select_one(".potential-num")
        pot = pot_el.get_text(strip=True) if pot_el else ""
        
        lvl_el = cc.select_one(".char-lvl")
        lvl = lvl_el.get_text(strip=True) if lvl_el else ""
        
        name_el = cc.select_one(".ch-name")
        name = name_el.get_text(strip=True) if name_el else ""
        
        rarity = 3
        r_line = cc.select_one(".rarity-line")
        if r_line:
            classes = r_line.get("class", [])
            for c in classes:
                if c.startswith("r-"):
                    try:
                        rarity = int(c.replace("r-", ""))
                    except Exception: pass
                    
        data["chars"].append({
            "empty": False,
            "avatar": avatar,
            "icons": icons,
            "potential": pot,
            "level": lvl,
            "name": name,
            "rarity": rarity
        })

    return data


def draw_bg(canvas: Image.Image, w: int, h: int, bg_src: str):
    """绘制背景：偏灰的底色 + 微弱网格"""
    if bg_src:
        try:
            bg_img = _b64_fit(bg_src, w, h).convert("RGBA")
            bg_img.putalpha(Image.new("L", (w, h), 25)) 
            canvas.alpha_composite(bg_img)
        except Exception: pass

    # Radial Gradient (调整为更亮的偏灰色 #222328 -> #0f1014)
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

    # Grid Deco (几乎不可见的超微弱网格)
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


def render(html: str) -> bytes:
    data = parse_html(html)
    
    # ---------------- 1. 高度预计算阶段 ----------------
    cur_y = PAD
    
    cur_y += 130 + 40
    
    dash_col_w = (INNER_W - 15 * 3) // 4
    dash_row_h = 140
    dash_gap = 15
    grid_matrix = [[False]*4 for _ in range(10)]
    curr_r, curr_c = 0, 0
    dash_positions = []
    
    for dc in data["dash_cards"]:
        span = 2 if dc["type"] == "mission" else 1
        while curr_c + span > 4 or any(grid_matrix[curr_r][curr_c+i] for i in range(span)):
            curr_c += 1
            if curr_c + span > 4:
                curr_c = 0
                curr_r += 1
                
        dash_positions.append({
            "card": dc, "r": curr_r, "c": curr_c, "span": span
        })
        for i in range(span):
            grid_matrix[curr_r][curr_c + i] = True
            
    dash_rows = max((pos["r"] for pos in dash_positions), default=0) + 1
    cur_y += dash_rows * dash_row_h + max(0, dash_rows - 1) * dash_gap + 40
    
    cur_y += 28 + 20
    
    char_cols = 5
    char_gap = 15
    char_w = (INNER_W - char_gap * (char_cols - 1)) // char_cols
    char_h = int(char_w * 280 / 180)
    
    char_rows = math.ceil(len(data["chars"]) / char_cols)
    cur_y += char_rows * char_h + max(0, char_rows - 1) * char_gap + PAD
    
    total_h = max(cur_y, 800)
    
    # ---------------- 2. 实际绘制阶段 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h, data["bg_url"])
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    
    # === Header ===
    aw = 130
    d.rectangle([PAD, y, PAD + aw, y + aw], fill=(17, 17, 17, 255), outline=(255, 255, 255, 51), width=2)
    if data["avatar"]:
        try:
            av_img = _b64_fit(data["avatar"], aw, aw)
            canvas.paste(av_img, (PAD, y))
        except Exception: pass
        
    ux = PAD + aw + 30
    draw_text_mixed(d, (ux, y + 10), data["name"], cn_font=F64, en_font=F64, fill=C_TEXT)
    name_w = int(F64.getlength(data["name"]))
    
    # UID 标签 (放大字号，颜色调亮)
    if data["uid"]:
        uid_x = ux + name_w + 15
        uid_text = f"UID {data['uid']}"
        uid_w = int(M20.getlength(uid_text))
        d.rounded_rectangle([uid_x, y + 32, uid_x + uid_w + 20, y + 32 + 30], radius=4, fill=(255, 255, 255, 20))
        draw_text_mixed(d, (uid_x + 10, y + 35), uid_text, cn_font=M20, en_font=M20, fill=(180, 180, 180, 255))
        
    # 苏醒日
    if data["awake_date"]:
        aw_y = y + 85
        aw_text = f"苏醒日：{data['awake_date']}"
        aw_w = int(M14.getlength(aw_text.replace("苏醒日：", ""))) + int(F14.getlength("苏醒日："))
        d.rectangle([ux, aw_y, ux + aw_w + 24, aw_y + 26], fill=(40, 40, 40, 204))
        d.rectangle([ux, aw_y, ux + 3, aw_y + 26], fill=C_SUBTEXT)
        draw_text_mixed(d, (ux + 12, aw_y + 5), aw_text, cn_font=F14, en_font=M14, fill=(170, 170, 170, 255))
        
    y += aw + 40
    
    # === Dashboard Grid ===
    for item in dash_positions:
        dc = item["card"]
        cx = PAD + item["c"] * (dash_col_w + dash_gap)
        cy = y + item["r"] * (dash_row_h + dash_gap)
        cw = dash_col_w * item["span"] + dash_gap * (item["span"] - 1)
        ch = dash_row_h
        
        # 将底层改为亮一点的浅灰色调，保证黑色 Logo 清晰可见
        d.rectangle([cx, cy, cx + cw, cy + ch], fill=(38, 40, 46, 255), outline=(255, 255, 255, 20), width=1)
        
        # 叠加微弱的反光渐变让卡片更立体
        shine = Image.new("RGBA", (cw, ch), (0,0,0,0))
        sd = ImageDraw.Draw(shine)
        for gy in range(ch):
            for gx in range(cw):
                alpha = int(15 * (1 - (gx + gy) / (cw + ch)))
                shine.putpixel((gx, gy), (255, 255, 255, max(0, alpha)))
        canvas.alpha_composite(shine, (cx, cy))
        
        if dc["type"] == "mission":
            draw_text_mixed(d, (cx + 25, cy + 25), dc["num"], cn_font=F48, en_font=O48, fill=C_TEXT)
            draw_text_mixed(d, (cx + 25, cy + 85), dc["label"], cn_font=F22, en_font=F22, fill=C_SUBTEXT)
            
        elif dc["type"] == "logo":
            if dc["src"]:
                try:
                    lg = _b64_fit(dc["src"], int(cw*0.8), int(ch*0.8))
                    canvas.alpha_composite(lg, (cx + (cw - lg.width)//2, cy + (ch - lg.height)//2))
                except Exception: pass
                
        elif dc["type"] == "stat":
            num_w = int(O64.getlength(dc["num"]))
            lbl_w = int(F22.getlength(dc["label"]))
            
            draw_text_mixed(d, (cx + (cw - num_w)//2, cy + 20), dc["num"], cn_font=O64, en_font=O64, fill=C_TEXT)
            draw_text_mixed(d, (cx + (cw - lbl_w)//2, cy + 90), dc["label"], cn_font=F22, en_font=F22, fill=C_SUBTEXT)
            
    y += dash_rows * dash_row_h + max(0, dash_rows - 1) * dash_gap + 40
    
    # === Characters Header ===
    d.polygon([(PAD, y), (PAD + 8, y), (PAD + 4, y + 28), (PAD - 4, y + 28)], fill=C_ACCENT)
    draw_text_mixed(d, (PAD + 20, y - 2), "[", cn_font=M24, en_font=M24, fill=(170, 170, 170, 255), dy_en=5)
    draw_text_mixed(d, (PAD + 40, y - 2), "干员", cn_font=F28, en_font=F28, fill=C_TEXT)
    draw_text_mixed(d, (PAD + 110, y - 2), "]", cn_font=M24, en_font=M24, fill=(170, 170, 170, 255), dy_en=5)
    
    y += 28 + 20
    
    # === Characters Grid ===
    for i, char in enumerate(data["chars"]):
        r, c = divmod(i, char_cols)
        cx = PAD + c * (char_w + char_gap)
        cy = y + r * (char_h + char_gap)
        
        if char.get("empty"):
            d.rectangle([cx, cy, cx + char_w, cy + char_h], outline=(68, 68, 68, 255), width=1)
            continue
            
        d.rectangle([cx, cy, cx + char_w, cy + char_h], fill=(34, 34, 34, 255))
        
        img_h = int(char_h * 0.86)
        if char["avatar"]:
            try:
                av = _b64_fit(char["avatar"], char_w, img_h)
                canvas.paste(av, (cx, cy))
            except Exception: pass
            
        icon_y = cy + 6
        for icon_src in char["icons"]:
            if icon_src:
                try:
                    ic = _b64_fit(icon_src, 36, 36)
                    shadow = Image.new("RGBA", (36, 36), (0,0,0,0))
                    shadow.paste((0,0,0,178), ic.split()[3])
                    shadow = shadow.filter(ImageFilter.GaussianBlur(2))
                    canvas.alpha_composite(shadow, (cx + 6, icon_y + 2))
                    canvas.alpha_composite(ic, (cx + 6, icon_y))
                    icon_y += 36 + 4
                except Exception: pass
                
        if char["potential"]:
            pot = char["potential"]
            p_val = int(pot.replace("P", "")) if "P" in pot else 1
            pot_colors = {1: (140,140,140), 2: (77,156,255), 3: (163,102,255), 4: (255,201,0), 5: (255,78,32)}
            pc = pot_colors.get(p_val, (255, 230, 0))
            
            badge_h = 20
            badge_w = int(O14.getlength(pot)) + 16
            bx = cx + char_w - 6 - badge_w
            by = cy + 6
            skew = 4
            
            d.polygon([
                (bx + skew, by), (bx + badge_w + skew, by),
                (bx + badge_w - skew, by + badge_h), (bx - skew, by + badge_h)
            ], fill=(0, 0, 0, 190))
            d.polygon([
                (bx + skew - 3, by), (bx + skew, by),
                (bx - skew, by + badge_h), (bx - skew - 3, by + badge_h)
            ], fill=pc + (255,))
            
            draw_text_mixed(d, (bx + 8, by + 1), pot, cn_font=O14, en_font=O14, fill=pc + (255,))
            
        # 等级文本 (超大号并带有极强的描边阴影)
        lvl_str = char["level"].replace("Lv.", "")
        lvl_w = int(O36.getlength(lvl_str)) + int(O18.getlength("Lv."))
        lx = cx + char_w - 6 - lvl_w
        ly = cy + img_h - 40
        
        # 全方位多层黑色阴影
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if dx == 0 and dy == 0: continue
                draw_text_mixed(d, (lx + dx, ly + 16 + dy), "Lv.", cn_font=O18, en_font=O18, fill=(0,0,0,230))
                draw_text_mixed(d, (lx + int(O18.getlength("Lv.")) + 2 + dx, ly + dy), lvl_str, cn_font=O36, en_font=O36, fill=(0,0,0,230))
                
        # 实际文本
        draw_text_mixed(d, (lx, ly + 16), "Lv.", cn_font=O18, en_font=O18, fill=C_TEXT)
        draw_text_mixed(d, (lx + int(O18.getlength("Lv.")) + 2, ly), lvl_str, cn_font=O36, en_font=O36, fill=C_TEXT)
        
        # 底部名字块
        d.rectangle([cx, cy + img_h, cx + char_w, cy + char_h], fill=(230, 230, 230, 255))
        n_w = int(F22.getlength(char["name"]))
        short_name = char["name"]
        if n_w > char_w - 16:
            while short_name and int(F22.getlength(short_name + "...")) > char_w - 16:
                short_name = short_name[:-1]
            short_name += "..."
        # 放大名字字号，居中偏下微调以填满灰条
        draw_text_mixed(d, (cx + 8, cy + img_h + 6), short_name, cn_font=F22, en_font=F22, fill=(26, 26, 26, 255))
        
        # 稀有度线
        rc = R_COLORS.get(char["rarity"], (139, 139, 139, 255))
        d.rectangle([cx, cy + char_h - 4, cx + char_w, cy + char_h], fill=rc)
        
    # 最终输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()