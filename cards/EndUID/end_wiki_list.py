# 明日方舟：终末地 图鉴列表卡片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# 避免循环导入，直接引入工具函数并局部生成字体
from . import get_font, draw_text_mixed, _b64_img, _b64_fit

F16 = get_font(16, family='cn')
F24 = get_font(24, family='cn')
F30 = get_font(30, family='cn')
F56 = get_font(56, family='cn')

M12 = get_font(12, family='mono')
M22 = get_font(22, family='mono')
M24 = get_font(24, family='mono')

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

    # 判断是角色还是武器列表 (通过是否包含 item-left-info 里的职业角标判断)
    if soup.select_one(".item-left-info"):
        data["list_type"] = "char"
    else:
        data["list_type"] = "weapon"

    # Groups 解析
    for g_sec in soup.select(".group-section"):
        g_title_el = g_sec.select_one(".group-title")
        if not g_title_el: continue
            
        # 移除 span.group-count 获取纯文本
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
            r = int(26 + (15 - 26) * ratio)
            g = int(27 + (16 - 27) * ratio)
            b = int(32 + (20 - 32) * ratio)
            grad.putpixel((x, y), (r, g, b, 255))
            
    canvas.alpha_composite(grad.resize((w, h), Image.Resampling.LANCZOS))
    
    if bg_src:
        try:
            bg_img = _b64_fit(bg_src, w, h).convert("RGBA")
            bg_img.putalpha(Image.new("L", (w, h), 25)) # opacity 0.1
            canvas.alpha_composite(bg_img)
        except Exception: pass

    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    grid_c = (255, 255, 255, 8) 
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
    
    # ---------------- 1. 高度预计算 ----------------
    cur_y = PAD
    
    # Page Title
    cur_y += 60 + 30 + 30 
    
    # Grid settings
    cols = 5
    gap = 12
    item_w = (INNER_W - gap * (cols - 1)) // cols # 约 169px
    item_h = int(item_w * 220 / 160)              # 约 232px
    img_h = int(item_h * 0.78)
    
    # Groups
    group_heights = []
    for g in data["groups"]:
        gh = 40 # title row + margin
        rows = math.ceil(len(g["items"]) / cols)
        if rows > 0:
            gh += rows * item_h + max(0, rows - 1) * gap
        group_heights.append(gh)
        cur_y += gh + 30
        
    # Footer
    cur_y += 10 + 40 + 20 
    total_h = max(cur_y, 600)
    
    # ---------------- 2. 实际绘制 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h, data["bg"])
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    
    # === Page Title ===
    draw_text_mixed(d, (PAD, y - 5), data["title"], cn_font=F56, en_font=F56, fill=C_TEXT)
    draw_text_mixed(d, (PAD, y + 60), f"TOTAL {data['total']}", cn_font=M24, en_font=M24, fill=C_SUBTEXT)
    y += 60 + 30 + 30
    
    # === Groups ===
    for idx, g in enumerate(data["groups"]):
        # Group Header
        d.polygon([(PAD, y), (PAD + 6, y), (PAD + 3, y + 24), (PAD - 3, y + 24)], fill=C_ACCENT)
        draw_text_mixed(d, (PAD + 15, y - 3), g["name"], cn_font=F30, en_font=F30, fill=C_TEXT)
        
        name_w = int(F30.getlength(g["name"]))
        draw_text_mixed(d, (PAD + 15 + name_w + 10, y + 5), str(len(g["items"])), cn_font=M22, en_font=M22, fill=C_SUBTEXT)
        
        y += 35
        d.line([(PAD, y), (W - PAD, y)], fill=(255, 255, 255, 25), width=2)
        y += 15
        
        # Grid Items
        for i, item in enumerate(g["items"]):
            r, c = divmod(i, cols)
            cx = PAD + c * (item_w + gap)
            cy = y + r * (item_h + gap)
            
            # 卡片背景
            d.rectangle([cx, cy, cx + item_w, cy + item_h], fill=(26, 26, 31, 255))
            
            # 主图
            if item["img"]:
                try:
                    img = _b64_fit(item["img"], item_w, img_h)
                    canvas.paste(img, (cx, cy))
                except Exception: pass
            else:
                d.rectangle([cx, cy, cx + item_w, cy + img_h], fill=(30, 30, 35, 255))
                n_text = item["name"][:2]
                draw_text_mixed(d, (cx + item_w//2 - 12, cy + img_h//2 - 10), n_text, cn_font=F16, en_font=F16, fill=(68, 68, 68, 255))
                
            # 左上角图标 (只有角色有)
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
            # 文本限制长度处理
            n_w = int(F24.getlength(item["name"]))
            if n_w > item_w - 16:
                short_name = item["name"]
                while short_name and int(F24.getlength(short_name + "...")) > item_w - 16:
                    short_name = short_name[:-1]
                draw_text_mixed(d, (cx + 8, cy + img_h + 10), short_name + "...", cn_font=F24, en_font=F24, fill=(26, 26, 26, 255))
            else:
                draw_text_mixed(d, (cx + 8, cy + img_h + 10), item["name"], cn_font=F24, en_font=F24, fill=(26, 26, 26, 255))
                
            # 稀有度条
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
    draw_text_mixed(d, (W - PAD - fw, y + 14), "ENDFIELD WIKI", cn_font=M12, en_font=M12, fill=C_SUBTEXT)

    # 最终输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()