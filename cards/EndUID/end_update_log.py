# 明日方舟：终末地 更新日志卡片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

# 【新增】导入 get_emoji_font 函数
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit, get_emoji_font,
    F28, F36, M22
)

# ---------------- 直接调用初始化里的 emoji 获取方法 ----------------
FEmoji = get_emoji_font(28)

# 画布基础属性
W = 800
PAD = 40
INNER_W = W - PAD * 2

# 颜色定义
C_BG = (15, 16, 20, 255)
C_ACCENT = (255, 230, 0, 255)
C_TEXT = (255, 255, 255, 255)
C_SUBTEXT = (139, 139, 139, 255)
C_CARD_BG = (255, 255, 255, 15)       # rgba(255,255,255,0.06)
C_CARD_BORDER = (255, 255, 255, 25)   # rgba(255,255,255,0.1)


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "icon_b64": "",
        "logs": []
    }

    logo_el = soup.select_one(".header-logo")
    if logo_el: data["icon_b64"] = logo_el.get("src", "")

    for item in soup.select(".log-item"):
        emoji = item.select_one(".log-emoji").get_text(strip=True) if item.select_one(".log-emoji") else ""
        text = item.select_one(".log-text").get_text(strip=True) if item.select_one(".log-text") else ""
        index = item.select_one(".log-index").get_text(strip=True).replace("#", "") if item.select_one(".log-index") else ""
        data["logs"].append({"emoji": emoji, "text": text, "index": index})

    return data


def draw_bg(canvas: Image.Image, w: int, h: int):
    # Radial Gradient
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

    # Grid Deco
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


def render(html: str) -> bytes:
    data = parse_html(html)
    
    # ---------------- 1. 高度预计算 ----------------
    cur_y = PAD
    
    logo_img = None
    lw, lh = 260, 0
    if data["icon_b64"]:
        try:
            raw_logo = _b64_img(data["icon_b64"])
            lh = int(raw_logo.height * (lw / raw_logo.width))
            logo_img = raw_logo.resize((lw, lh), Image.Resampling.LANCZOS)
        except Exception:
            pass

    header_h = 0
    if logo_img:
        header_h += lh + 16 
    header_h += 40 + 16 
    header_h += 26 + 24 
    
    cur_y += header_h + 24
    
    log_heights = []
    for item in data["logs"]:
        text_w = INNER_W - 172
        lines = wrap_text(item["text"], F28, text_w)
        
        item_h = 28 + len(lines) * 38
        item_h = max(60, item_h) 
        log_heights.append((lines, item_h))
        cur_y += item_h + 10 
        
    cur_y += 30 
    total_h = max(cur_y, 400)
    
    # ---------------- 2. 实际绘制 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h)
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    
    # === Header ===
    cx = W // 2
    if logo_img:
        shadow = Image.new("RGBA", (lw, lh), (0,0,0,0))
        shadow.paste(C_ACCENT, logo_img.split()[3])
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        shadow.putalpha(ImageChops.multiply(shadow.split()[3], Image.new("L", (lw, lh), 38)))
        
        canvas.alpha_composite(shadow, (cx - lw//2, y + 4))
        canvas.alpha_composite(logo_img, (cx - lw//2, y))
        y += lh + 16
        
    name_w = int(F36.getlength("EndUID"))
    draw_text_mixed(d, (cx - name_w//2, y), "EndUID", cn_font=F36, en_font=F36, fill=C_TEXT, dy_en=10)
    y += 40 + 16
    
    title_w = int(M22.getlength("UPDATE LOG"))
    draw_text_mixed(d, (cx - title_w//2, y), "UPDATE LOG", cn_font=M22, en_font=M22, fill=C_SUBTEXT, dy_en=6)
    y += 26 + 24
    
    d.line([(PAD, y), (W - PAD, y)], fill=(255, 255, 255, 25), width=2)
    y += 24
    
    # === Log List ===
    for i, item in enumerate(data["logs"]):
        lines, item_h = log_heights[i]
        
        d.rounded_rectangle([PAD, y, PAD + INNER_W, y + item_h], radius=10, fill=C_CARD_BG, outline=C_CARD_BORDER, width=1)
        
        # Emoji (包含 embedded_color=True 支持彩色渲染)
        if item["emoji"]:
            d.text((PAD + 20, y + (item_h - 28)//2 + 2), item["emoji"], font=FEmoji, fill=(255,255,255,255), embedded_color=True)
            
        # Text Lines
        ty = y + 14
        for line in lines:
            draw_text_mixed(d, (PAD + 86, ty), line, cn_font=F28, en_font=F28, fill=(224, 224, 224, 255), dy_en=8)
            ty += 38
            
        # Index
        idx_str = f"#{item['index']}"
        idx_w = int(M22.getlength(idx_str))
        draw_text_mixed(d, (PAD + INNER_W - 20 - idx_w, y + (item_h - 22)//2), idx_str, cn_font=M22, en_font=M22, fill=(255, 230, 0, 128), dy_en=6)

        y += item_h + 10

    # 最终输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()