# 明日方舟：终末地 活动日历卡片渲染器 (PIL 版)

from __future__ import annotations

import math
import re
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# 引入工具函数并生成字体
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit, _round_mask,
    F12, F14, F16, F18, F20, F24, F36,
    M12, M14, M16, M24,
    O14, O16
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
C_BORDER = (255, 255, 255, 25)

def parse_color(c_str: str, default=(255, 230, 0, 255)) -> tuple:
    c_str = c_str.strip().lower()
    if c_str.startswith("#"):
        c_str = c_str.lstrip("#")
        if len(c_str) == 3: c_str = "".join(c+c for c in c_str)
        if len(c_str) == 6:
            return (int(c_str[0:2], 16), int(c_str[2:4], 16), int(c_str[4:6], 16), 255)
        elif len(c_str) == 8:
            return (int(c_str[0:2], 16), int(c_str[2:4], 16), int(c_str[4:6], 16), int(c_str[6:8], 16))
    return default

def _parse_progress_style(style_str: str) -> tuple[float, tuple]:
    prog = 0.0
    color = C_ACCENT
    if not style_str: return prog, color
    pm = re.search(r"width:\s*([\d\.]+)%", style_str)
    if pm: prog = float(pm.group(1))
    cm = re.search(r"background:\s*([^;]+)", style_str)
    if cm: color = parse_color(cm.group(1), default=color)
    return prog, color

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg": "", "end_logo": "", "now": "", "banner": "",
        "charPools": [], "weaponPools": [], "activities": []
    }

    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg"] = bg_el.get("src", "")
    logo_el = soup.select_one(".footer-logo")
    if logo_el: data["end_logo"] = logo_el.get("src", "")
        
    now_el = soup.select_one(".calendar-date")
    if now_el: data["now"] = now_el.get_text(strip=True)
        
    banner_el = soup.select_one(".banner-wrap img")
    if banner_el: data["banner"] = banner_el.get("src", "")

    for sec in soup.select(".container > div"):
        stitle_el = sec.select_one(".section-title")
        if not stitle_el: continue
        stitle = stitle_el.get_text(strip=True)

        if "干员寻访" in stitle:
            for card in sec.select(".pool-card"):
                pool = {"chars": [], "name": "", "time": "", "status": "", "remaining": "", "progress": 0.0, "color": C_ACCENT}
                for ch in card.select(".pool-char"):
                    classes = ch.get("class", [])
                    rarity = 5
                    if "rarity_6" in classes: rarity = 6
                    pic = ch.select_one("img").get("src", "") if ch.select_one("img") else ""
                    is_up = ch.select_one(".pool-char-badge") is not None
                    pool["chars"].append({"rarity": rarity, "pic": pic, "is_up": is_up})
                pool["name"] = card.select_one(".pool-name").get_text(strip=True) if card.select_one(".pool-name") else ""
                pool["time"] = card.select_one(".pool-time").get_text(strip=True) if card.select_one(".pool-time") else ""
                sb = card.select_one(".status-badge")
                if sb: pool["status"] = sb.get_text(strip=True)
                rem = card.select_one(".remaining-text")
                if rem: pool["remaining"] = rem.get_text(strip=True)
                pb = card.select_one(".progress-bar-fill")
                if pb:
                    p_val, p_col = _parse_progress_style(pb.get("style", ""))
                    pool["progress"], pool["color"] = p_val, p_col
                data["charPools"].append(pool)

        elif "武器寻访" in stitle:
            for card in sec.select(".pool-card"):
                pool = {"name": "", "time": "", "status": "", "remaining": "", "progress": 0.0, "color": C_ACCENT}
                pool["name"] = card.select_one(".pool-name").get_text(strip=True) if card.select_one(".pool-name") else ""
                pool["time"] = card.select_one(".pool-time").get_text(strip=True) if card.select_one(".pool-time") else ""
                sb = card.select_one(".status-badge")
                if sb: pool["status"] = sb.get_text(strip=True)
                rem = card.select_one(".remaining-text")
                if rem: pool["remaining"] = rem.get_text(strip=True)
                pb = card.select_one(".progress-bar-fill")
                if pb:
                    p_val, p_col = _parse_progress_style(pb.get("style", ""))
                    pool["progress"], pool["color"] = p_val, p_col
                data["weaponPools"].append(pool)

        elif "活动日历" in stitle:
            for card in sec.select(".activity-card"):
                act = {"pic": "", "name": "", "desc": "", "time": "", "status": "", "remaining": "", "progress": 0.0, "color": C_ACCENT}
                pic_el = card.select_one(".activity-pic img")
                if pic_el: act["pic"] = pic_el.get("src", "")
                act["name"] = card.select_one(".activity-name").get_text(strip=True) if card.select_one(".activity-name") else ""
                act["desc"] = card.select_one(".activity-desc").get_text(strip=True) if card.select_one(".activity-desc") else ""
                act["time"] = card.select_one(".activity-time").get_text(strip=True) if card.select_one(".activity-time") else ""
                sb = card.select_one(".status-badge")
                if sb: act["status"] = sb.get_text(strip=True)
                rem = card.select_one(".remaining-text")
                if rem: act["remaining"] = rem.get_text(strip=True)
                pb = card.select_one(".progress-bar-fill")
                if pb:
                    p_val, p_col = _parse_progress_style(pb.get("style", ""))
                    act["progress"], act["color"] = p_val, p_col
                data["activities"].append(act)

    return data


def draw_bg(canvas: Image.Image, w: int, h: int, bg_src: str):
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
            
    canvas.alpha_composite(grad.resize((w, h), Image.Resampling.LANCZOS))
    
    if bg_src:
        try:
            bg_img = _b64_fit(bg_src, w, h).convert("RGBA")
            bg_img.putalpha(Image.new("L", (w, h), 25)) 
            canvas.alpha_composite(bg_img)
        except Exception: pass

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
    d.line([(x, y), (x, y + 24)], fill=C_ACCENT, width=4)
    # [上提 10%] dy_en 从 4 改为 2
    draw_text_mixed(d, (x + 12, y - 2), title_cn, cn_font=F24, en_font=F24, fill=C_TEXT, dy_en=2)
    cn_w = int(F24.getlength(title_cn))
    # [上提 10%] dy_en 从 2 改为 0
    draw_text_mixed(d, (x + 12 + cn_w + 10, y + 6 - 2), title_en, cn_font=F16, en_font=M16, fill=(170, 170, 170, 255), dy_en=0)
    return 38


def draw_status_row(d: ImageDraw.ImageDraw, x: int, y: int, status: str, remaining: str, progress: float, p_color: tuple, max_w: int):
    if status == '进行中':
        bg_c, bd_c, txt_c = (255, 230, 0, 38), (255, 230, 0, 76), C_ACCENT
    elif status == '已结束':
        bg_c, bd_c, txt_c = (255, 255, 255, 12), (255, 255, 255, 20), (102, 102, 102, 255)
    else:
        bg_c, bd_c, txt_c = (74, 158, 255, 38), (74, 158, 255, 76), (74, 158, 255, 255)

    st_w = int(F14.getlength(status)) + 24
    d.rounded_rectangle([x, y, x + st_w, y + 22], radius=3, fill=bg_c, outline=bd_c, width=1)
    # [上提 10%] dy_en 从 2 改为 0
    draw_text_mixed(d, (x + 12, y + 2 - 1), status, cn_font=F14, en_font=M14, fill=txt_c, dy_en=0)

    curr_x = x + st_w + 10

    if remaining:
        rem_w = int(M14.getlength(remaining))
        # [上提 10%] 剩余时间倒计时对齐，dy_en 从 2 改为 0
        draw_text_mixed(d, (curr_x, y + 3 - 1), remaining, cn_font=F14, en_font=M14, fill=(221, 221, 221, 255), dy_en=0)
        curr_x += rem_w + 10

    bar_w = max_w - (curr_x - x)
    if bar_w > 20:
        bar_y = y + 6
        d.rounded_rectangle([curr_x, bar_y, curr_x + bar_w, bar_y + 10], radius=4, fill=(26, 26, 26, 255), outline=C_BORDER, width=1)
        fill_w = int(bar_w * progress / 100)
        if fill_w > 0:
            d.rounded_rectangle([curr_x, bar_y, curr_x + fill_w, bar_y + 10], radius=4, fill=p_color)


def render(html: str) -> bytes:
    data = parse_html(html)
    
    # ---------------- 1. 高度预计算 ----------------
    cur_y = PAD
    
    cur_y += 36 + 20 + 25 
    
    if data["banner"]:
        cur_y += 280 + 25
        
    if data["charPools"]:
        cur_y += 38
        for pool in data["charPools"]:
            cur_y += 132 + 14
        cur_y += 25 - 14
        
    if data["weaponPools"]:
        cur_y += 38
        for pool in data["weaponPools"]:
            cur_y += 114 + 14
        cur_y += 25 - 14
        
    if data["activities"]:
        cur_y += 38
        rows = math.ceil(len(data["activities"]) / 2)
        cur_y += rows * 140 + max(0, rows - 1) * 14
        cur_y += 25
        
    total_h = max(cur_y + 50, 600)
    
    # ---------------- 2. 实际绘制 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h, data["bg"])
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    
    # === Header ===
    # [上提 10%]
    draw_text_mixed(d, (PAD, y - 4), "活动日历", cn_font=F36, en_font=F36, fill=C_TEXT, dy_en=2)
    draw_text_mixed(d, (PAD + 160, y + 16 - 2), "CALENDAR", cn_font=F16, en_font=M16, fill=C_SUBTEXT, dy_en=0)
    
    date_w = int(M14.getlength(data["now"]))
    dx = W - PAD - date_w - 24
    d.rounded_rectangle([dx, y + 10, dx + date_w + 24, y + 32], radius=4, fill=(255, 255, 255, 12))
    # [上提 10%] 日期数字上提
    draw_text_mixed(d, (dx + 12, y + 13 - 1), data["now"], cn_font=F14, en_font=M14, fill=C_SUBTEXT, dy_en=0)
    
    y += 36 + 20
    d.line([(PAD, y), (W - PAD, y)], fill=C_BORDER, width=1)
    y += 25
    
    # === Banner ===
    if data["banner"]:
        try:
            ban_img = _b64_fit(data["banner"], INNER_W, 280)
            canvas.paste(ban_img, (PAD, y), _round_mask(INNER_W, 280, 4))
            d.rounded_rectangle([PAD, y, PAD + INNER_W, y + 280], radius=4, outline=C_BORDER, width=1)
        except Exception: pass
        y += 280 + 25
        
    # === Char Pools ===
    if data["charPools"]:
        y += draw_section_title(d, PAD, y, "干员寻访", "RECRUITMENT")
        
        for pool in data["charPools"]:
            d.rectangle([PAD, y, PAD + INNER_W, y + 132], fill=(0, 0, 0, 76), outline=C_BORDER, width=1)
            
            # Chars
            cx = PAD + 20
            cy = y + 16
            for ch in pool["chars"]:
                rc_color = (255, 157, 58, 255) if ch["rarity"] == 6 else (192, 132, 252, 255)
                
                d.rounded_rectangle([cx, cy, cx + 100, cy + 100], radius=6, fill=(255, 255, 255, 12), outline=rc_color, width=2)
                if ch["pic"]:
                    try:
                        pic = _b64_fit(ch["pic"], 96, 96)
                        canvas.paste(pic, (cx + 2, cy + 2), _round_mask(96, 96, 4))
                    except Exception: pass
                    
                if ch["is_up"]:
                    d.rectangle([cx + 2, cy + 100 - 20, cx + 98, cy + 98], fill=(0, 0, 0, 178))
                    # [上提 10%] UP标签
                    draw_text_mixed(d, (cx + 50 - int(M12.getlength("UP"))//2, cy + 100 - 18 - 1), "UP", cn_font=M12, en_font=M12, fill=C_ACCENT, dy_en=0)
                    
                cx += 110
                
            # Info
            ix = cx + 6
            iy = y + 16
            # [上提 10%]
            draw_text_mixed(d, (ix, iy - 2), pool["name"], cn_font=F24, en_font=F24, fill=C_TEXT, dy_en=1)
            draw_text_mixed(d, (ix, iy + 34 - 2), pool["time"], cn_font=F16, en_font=M16, fill=(204, 204, 204, 255), dy_en=0)
            
            max_w = PAD + INNER_W - 20 - ix
            draw_status_row(d, ix, iy + 64, pool["status"], pool["remaining"], pool["progress"], pool["color"], max_w)
            
            y += 132 + 14
        y += 25 - 14

    # === Weapon Pools ===
    if data["weaponPools"]:
        y += draw_section_title(d, PAD, y, "武器寻访", "WEAPON POOL")
        
        for pool in data["weaponPools"]:
            d.rectangle([PAD, y, PAD + INNER_W, y + 114], fill=(0, 0, 0, 76), outline=C_BORDER, width=1)
            
            ix = PAD + 20
            iy = y + 16
            # [上提 10%]
            draw_text_mixed(d, (ix, iy - 2), pool["name"], cn_font=F24, en_font=F24, fill=C_TEXT, dy_en=1)
            draw_text_mixed(d, (ix, iy + 34 - 2), pool["time"], cn_font=F16, en_font=M16, fill=(204, 204, 204, 255), dy_en=0)
            
            max_w = INNER_W - 40
            draw_status_row(d, ix, iy + 64, pool["status"], pool["remaining"], pool["progress"], pool["color"], max_w)
            
            y += 114 + 14
        y += 25 - 14
        
    # === Activities ===
    if data["activities"]:
        y += draw_section_title(d, PAD, y, "活动日历", "EVENTS")
        
        cols = 2
        gap = 14
        cw = (INNER_W - gap) // cols # 453px
        
        for i, act in enumerate(data["activities"]):
            row, col = i // cols, i % cols
            ax = PAD + col * (cw + gap)
            ay = y + row * (140 + gap)
            
            d.rectangle([ax, ay, ax + cw, ay + 140], fill=(0, 0, 0, 76), outline=C_BORDER, width=1)
            
            if act["pic"]:
                try:
                    pic = _b64_fit(act["pic"], 160, 140)
                    canvas.paste(pic, (ax, ay))
                except Exception: pass
                
            bx = ax + 160
            by = ay
            bw = cw - 160
            
            # Name Truncate
            name_str = act["name"]
            if int(F18.getlength(name_str)) > bw - 28:
                while name_str and int(F18.getlength(name_str + "...")) > bw - 28:
                    name_str = name_str[:-1]
                name_str += "..."
            # [上提 10%]
            draw_text_mixed(d, (bx + 14, by + 12 - 2), name_str, cn_font=F18, en_font=F18, fill=C_TEXT, dy_en=0)
            
            # Desc Truncate
            desc_str = act["desc"]
            if int(F14.getlength(desc_str)) > bw - 28:
                while desc_str and int(F14.getlength(desc_str + "...")) > bw - 28:
                    desc_str = desc_str[:-1]
                desc_str += "..."
            # [上提 10%]
            draw_text_mixed(d, (bx + 14, by + 40 - 1), desc_str, cn_font=F14, en_font=F14, fill=(187, 187, 187, 255), dy_en=0)
            
            # [上提 10%] 时间数字
            draw_text_mixed(d, (bx + 14, by + 82 - 1), act["time"], cn_font=F12, en_font=M12, fill=(153, 153, 153, 255), dy_en=0)
            
            draw_status_row(d, bx + 14, by + 104, act["status"], act["remaining"], act["progress"], act["color"], bw - 28)
            
        rows = math.ceil(len(data["activities"]) / 2)
        y += rows * 140 + max(0, rows - 1) * gap + 25

    # === Footer Logo ===
    if data["end_logo"]:
        try:
            logo = _b64_img(data["end_logo"])
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