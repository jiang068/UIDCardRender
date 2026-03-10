# 明日方舟：终末地 图鉴列表卡片渲染器 (PIL 版)

from __future__ import annotations

import math
import re
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# 避免循环导入，直接引入工具函数并局部生成字体
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit,
    F12, F16, F18, F24, F30, F56,
    M12, M22, M24
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
        "bg": "", 
        "end_logo": "",
        "title": "",
        "total": "",
        "list_type": "char",
        "groups": []
    }

    # 背景与 Logo
    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg"] = bg_el.get("src", "")
    logo_el = soup.select_one(".footer-logo")
    if logo_el: data["end_logo"] = logo_el.get("src", "")
        
    title_el = soup.select_one(".page-title")
    if title_el: data["title"] = title_el.get_text(strip=True)
    total_el = soup.select_one(".page-subtitle")
    if total_el: data["total"] = total_el.get_text(strip=True).replace("TOTAL", "").strip()

    if soup.select_one(".item-left-info"):
        data["list_type"] = "char"
    else:
        data["list_type"] = "weapon"

    for g_sec in soup.select(".group-section"):
        g_title_el = g_sec.select_one(".group-title")
        if not g_title_el: continue
            
        clone_title = BeautifulSoup(str(g_title_el), "lxml").select_one(".group-title")
        count_span = clone_title.select_one("span")
        if count_span: count_span.decompose()
        group_name = clone_title.get_text(strip=True)
        
        group_items = []
        for card in g_sec.select(".item-card"):
            item_data = {"name": "", "rarity": 3, "img": "", "icons": []}
            
            name_el = card.select_one(".item-name")
            if name_el: item_data["name"] = name_el.get_text(strip=True)
                
            r_line = card.select_one(".rarity-line")
            if r_line:
                classes = r_line.get("class", [])
                for c in classes:
                    if c.startswith("r-"):
                        try: item_data["rarity"] = int(c.replace("r-", ""))
                        except Exception: pass
                        
            img_el = card.select_one(".item-img")
            if img_el: item_data["img"] = img_el.get("src", "")
                
            if data["list_type"] == "char":
                for ic in card.select(".item-icon"):
                    item_data["icons"].append(ic.get("src", ""))
                    
            group_items.append(item_data)
            
        data["groups"].append({"name": group_name, "items": group_items})

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


def render(html: str) -> bytes:
    data = parse_html(html)
    
    cur_y = PAD
    cur_y += 60 + 30 + 30 
    
    cols = 5
    gap = 12
    item_w = (INNER_W - gap * (cols - 1)) // cols 
    item_h = int(item_w * 220 / 160)               
    img_h = int(item_h * 0.78)
    
    group_heights = []
    for g in data["groups"]:
        gh = 40 
        rows = math.ceil(len(g["items"]) / cols)
        if rows > 0:
            gh += rows * item_h + max(0, rows - 1) * gap
        group_heights.append(gh)
        cur_y += gh + 30
        
    cur_y += 10 + 40 + 20 
    total_h = max(cur_y, 600)
    
    # ---------------- 2. 实际绘制 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h, data["bg"])
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    
    # === Page Title ===
    # 中文名称（当前角色/当前武器）保持原位（y-5 视觉对齐）
    draw_text_mixed(d, (PAD, y - 5), data["title"], cn_font=F56, en_font=F56, fill=C_TEXT)
    # 英文标题 TOTAL 部分单独下移（y+60 是行高，再加 15px 左右的英文补偿）
    draw_text_mixed(d, (PAD, y + 60 + 15), f"TOTAL {data['total']}", cn_font=F24, en_font=M24, fill=C_SUBTEXT)
    y += 60 + 30 + 30
    
    # === Groups ===
    for idx, g in enumerate(data["groups"]):
        # Group Header
        d.polygon([(PAD, y), (PAD + 6, y), (PAD + 3, y + 24), (PAD - 3, y + 24)], fill=C_ACCENT)
        # 中文分类名保持原位（y-3 视觉对齐）
        draw_text_mixed(d, (PAD + 15, y - 3), g["name"], cn_font=F30, en_font=F30, fill=C_TEXT)
        
        name_w = int(F30.getlength(g["name"]))
        # 分类数量数字：在 y 基础上额外下移 12px
        draw_text_mixed(d, (PAD + 15 + name_w + 10, y + 12), str(len(g["items"])), cn_font=F18, en_font=M22, fill=C_SUBTEXT)
        
        y += 35
        d.line([(PAD, y), (W - PAD, y)], fill=(255, 255, 255, 25), width=2)
        y += 15
        
        # Grid Items
        for i, item in enumerate(g["items"]):
            r, c = divmod(i, cols)
            cx = PAD + c * (item_w + gap)
            cy = y + r * (item_h + gap)
            
            d.rectangle([cx, cy, cx + item_w, cy + item_h], fill=(26, 26, 31, 255))
            
            if item["img"]:
                try:
                    img = _b64_fit(item["img"], item_w, img_h)
                    canvas.paste(img, (cx, cy))
                except Exception: pass
            else:
                d.rectangle([cx, cy, cx + item_w, cy + img_h], fill=(30, 30, 35, 255))
                # 占位符文字下移 6px 居中
                n_text = item["name"][:2]
                draw_text_mixed(d, (cx + item_w//2 - 12, cy + img_h//2 + 6), n_text, cn_font=F16, en_font=F16, fill=(68, 68, 68, 255))
                
            if data["list_type"] == "char":
                icon_y = cy + 5
                for ic_src in item["icons"]:
                    if ic_src:
                        try:
                            ic = _b64_fit(ic_src, 36, 36)
                            shadow = Image.new("RGBA", (36, 36), (0,0,0,0))
                            shadow.paste((0,0,0,128), ic.split()[3])
                            shadow = shadow.filter(ImageFilter.GaussianBlur(2))
                            canvas.alpha_composite(shadow, (cx + 5, icon_y + 2))
                            canvas.alpha_composite(ic, (cx + 5, icon_y))
                            icon_y += 36 + 3
                        except Exception: pass
                        
            # 底部信息条
            d.rectangle([cx, cy + img_h, cx + item_w, cy + item_h], fill=(230, 230, 230, 255))
            
            # [核心修复] 卡片名称绘制：中文不偏移，英文/数字下移
            def draw_item_name(draw, text, pos, font_cn, font_en):
                curr_x, curr_y = pos
                # 正则匹配拆分中文与非中文
                parts = re.split(r'([a-zA-Z0-9\s\-\.\!\?]+)', text)
                for part in parts:
                    if not part: continue
                    is_en = bool(re.match(r'[a-zA-Z0-9\s\-\.\!\?]+', part))
                    # 英文/数字下移 20% 字号（约 5px）
                    offset_y = 5 if is_en else 0
                    draw_text_mixed(draw, (curr_x, curr_y + offset_y), part, cn_font=font_cn, en_font=font_en, fill=(26, 26, 26, 255))
                    curr_x += int(font_cn.getlength(part))

            # 执行绘制名称
            n_text = item["name"]
            if int(F24.getlength(n_text)) > item_w - 16:
                while n_text and int(F24.getlength(n_text + "...")) > item_w - 16:
                    n_text = n_text[:-1]
                n_text += "..."
            
            draw_item_name(d, n_text, (cx + 8, cy + img_h + 10), F24, F24)
                
            rc = R_COLORS.get(item["rarity"], (139, 139, 139, 255))
            d.rectangle([cx, cy + item_h - 4, cx + item_w, cy + item_h], fill=rc)
            
        if g["items"]:
            y += group_heights[idx] - 40
        y += 30
            
    # === Footer ===
    y += 10
    d.line([(PAD, y), (W - PAD, y)], fill=(255, 255, 255, 25), width=1)
    y += 20
    
    if data["end_logo"]:
        try:
            logo = _b64_img(data["end_logo"])
            lh = 40
            lw = int(logo.width * (lh / logo.height))
            logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
            logo.putalpha(ImageChops.multiply(logo.split()[3], Image.new("L", (lw, lh), 153)))
            canvas.alpha_composite(logo, (PAD, y))
        except Exception: pass
        
    fw = int(M12.getlength("ENDFIELD WIKI"))
    # 页脚英文下移 6px
    draw_text_mixed(d, (W - PAD - fw, y + 14 + 6), "ENDFIELD WIKI", cn_font=F12, en_font=M12, fill=C_SUBTEXT)

    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()