# 明日方舟：终末地 公告卡片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter

# 引入工具函数并生成字体
from . import (F14, F15, F16, F18, F20, F28, F36, F42,
            M14, M15, M16, M18, 
            get_font, draw_text_mixed, _b64_img, _b64_fit, _round_mask
)

# 画布基础属性
W = 1100
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
    
    # 区分是列表模式还是详情模式
    is_list = soup.select_one(".ann-grid") is not None
    data = {"is_list": is_list}
    
    if is_list:
        header_title = soup.select_one(".header-title")
        header_sub = soup.select_one(".header-subtitle")
        data["title"] = header_title.get_text(strip=True) if header_title else "公告"
        data["subtitle"] = header_sub.get_text(strip=True) if header_sub else ""
        
        items = []
        for card in soup.select(".ann-card"):
            cid = card.select_one(".ann-card-id")
            cover = card.select_one(".ann-card-cover")
            title = card.select_one(".ann-card-title")
            avatar = card.select_one(".ann-card-avatar")
            user = card.select_one(".ann-card-username")
            date = card.select_one(".ann-card-date")
            
            items.append({
                "short_id": cid.get_text(strip=True).replace("#", "") if cid else "",
                "cover": cover.get("src", "") if cover and cover.name == "img" else "",
                "title": title.get_text(strip=True) if title else "",
                "avatar": avatar.get("src", "") if avatar and avatar.name == "img" else "",
                "user": user.get_text(strip=True) if user else "终末地",
                "date": date.get_text(strip=True) if date else ""
            })
        data["items"] = items
    else:
        title = soup.select_one(".detail-title")
        avatar = soup.select_one(".detail-avatar")
        user_el = soup.select_one(".detail-user span")
        time = soup.select_one(".detail-time")
        
        data["title"] = title.get_text(strip=True) if title else ""
        data["avatar"] = avatar.get("src", "") if avatar and avatar.name == "img" else ""
        data["user"] = user_el.get_text(strip=True) if user_el else "终末地"
        data["time"] = time.get_text(strip=True) if time else ""
        
        contents = []
        detail_content = soup.select_one(".detail-content")
        if detail_content:
            for child in detail_content.children:
                if child.name == "div" and "content-text" in child.get("class", []):
                    texts = [p.get_text(strip=True) for p in child.select("p") if p.get_text(strip=True)]
                    if texts:
                        contents.append({"type": "text", "lines": texts})
                elif child.name == "img" and "content-image" in child.get("class", []):
                    contents.append({"type": "image", "src": child.get("src", "")})
                elif child.name == "div" and "video-cover-container" in child.get("class", []):
                    cover = child.select_one(".video-cover")
                    if cover:
                        contents.append({"type": "video", "src": cover.get("src", "")})
        data["contents"] = contents

    return data


def draw_bg(canvas: Image.Image, w: int, h: int):
    """绘制径向渐变背景与网格掩码装饰"""
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

    # 绘制网格
    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    grid_c = (38, 39, 44, 180)
    for x in range(0, w, 40): gd.line([(x, 0), (x, h)], fill=grid_c, width=1)
    for y in range(0, h, 40): gd.line([(0, y), (w, y)], fill=grid_c, width=1)
    
    # 顶部往下 20% 实心，之后渐渐变透明的掩码
    mask = Image.new("L", (w, h), 255)
    md = ImageDraw.Draw(mask)
    fade_h = int(h * 0.2)
    for y in range(fade_h, h):
        alpha = int(255 * (1 - min((y - fade_h) / (h * 0.8), 1.0)))
        md.line([(0, y), (w, y)], fill=alpha)
        
    grid.putalpha(mask)
    canvas.alpha_composite(grid)


def wrap_text(text: str, font, max_width: int) -> list[str]:
    """简单的文本折行函数"""
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


def render_list_mode(data: dict) -> bytes:
    """渲染公告列表网格模式"""
    items = data["items"]
    
    cols = 3
    gap = 15
    card_w = (INNER_W - gap * (cols - 1)) // cols  # 约 330px
    cover_h = int(card_w * 10 / 16)                # 约 206px
    card_h = cover_h + 115                         # 卡片高度 321px
    
    rows = math.ceil(len(items) / cols)
    total_h = PAD + 42 + 20 + 20 + (rows * card_h) + max(0, rows - 1) * gap + PAD
    total_h = max(total_h, 600)
    
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h)
    d = ImageDraw.Draw(canvas)

    # 标题头
    hy = PAD
    d.polygon([(PAD, hy), (PAD + 8, hy), (PAD + 4, hy + 42), (PAD - 4, hy + 42)], fill=C_ACCENT)
    # [修改] 英文下沉 8px (42 * 20%)
    draw_text_mixed(d, (PAD + 20, hy - 4), data["title"], cn_font=F42, en_font=F42, fill=C_TEXT, dy_en=8)
    
    if data["subtitle"]:
        sub_w = int(M16.getlength(data["subtitle"]))
        # [修改] 英文下沉 3px
        draw_text_mixed(d, (W - PAD - sub_w, hy + 18), data["subtitle"], cn_font=F16, en_font=M16, fill=C_SUBTEXT, dy_en=3)
    
    line_y = hy + 42 + 20
    d.line([(PAD, line_y), (W - PAD, line_y)], fill=(255, 255, 255, 25), width=2)
    
    # 绘制网格卡片
    gy = line_y + 20
    for i, item in enumerate(items):
        row, col = i // cols, i % cols
        cx = PAD + col * (card_w + gap)
        cy = gy + row * (card_h + gap)
        
        # 卡片背景
        d.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=8, fill=C_CARD_BG, outline=C_CARD_BORDER, width=1)
        
        # 卡片封面图
        cover_rect = Image.new("RGBA", (card_w, cover_h), (34, 34, 34, 255))
        if item["cover"]:
            try:
                img = _b64_fit(item["cover"], card_w, cover_h)
                cover_rect.paste(img, (0, 0))
            except Exception: pass
        
        c_mask = Image.new("L", (card_w, cover_h), 0)
        ImageDraw.Draw(c_mask).rounded_rectangle([0, 0, card_w, cover_h + 16], radius=8, fill=255)
        canvas.paste(cover_rect, (cx, cy), c_mask)
        
        # ID 标签
        id_text = f"#{item['short_id']}"
        id_w = int(M15.getlength(id_text)) + 20
        d.rounded_rectangle([cx + 8, cy + 8, cx + 8 + id_w, cy + 8 + 24], radius=4, fill=(0, 0, 0, 178))
        # [修改] 从 -2 修正为 +3
        draw_text_mixed(d, (cx + 18, cy + 9), id_text, cn_font=M15, en_font=M15, fill=C_ACCENT, dy_en=3)
        
        # 内部标题
        by = cy + cover_h + 14
        bx = cx + 14
        
        title_lines = wrap_text(item["title"], F20, card_w - 28)
        if len(title_lines) > 2:
            title_lines = title_lines[:2]
            title_lines[1] = title_lines[1][:-1] + "..."
            
        for ti, tline in enumerate(title_lines):
            # [修改] 英文下沉 4px
            draw_text_mixed(d, (bx, by + ti * 28 - 2), tline, cn_font=F20, en_font=F20, fill=C_TEXT, dy_en=4)
            
        # 底部信息 Meta
        my = cy + card_h - 46
        d.line([(bx, my - 10), (cx + card_w - 14, my - 10)], fill=(255, 255, 255, 12), width=1)
        
        if item["avatar"]:
            try:
                av = _b64_fit(item["avatar"], 32, 32)
                rmask = _round_mask(32, 32, 16)
                canvas.paste(av, (bx, my), rmask)
            except Exception:
                d.ellipse([bx, my, bx + 32, my + 32], fill=(51, 51, 51, 255))
        else:
            d.ellipse([bx, my, bx + 32, my + 32], fill=(51, 51, 51, 255))
            
        # [修改] 英文下沉 3px
        draw_text_mixed(d, (bx + 40, my + 5), item["user"], cn_font=F16, en_font=M16, fill=C_SUBTEXT, dy_en=3)
        
        date_w = int(M16.getlength(item["date"]))
        # [修改] 中文垫底替换为 F16，英文下沉 3px
        draw_text_mixed(d, (cx + card_w - 14 - date_w, my + 5), item["date"], cn_font=F16, en_font=M16, fill=C_SUBTEXT, dy_en=3)

    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


def render_detail_mode(data: dict) -> bytes:
    """渲染公告详情长图模式"""
    
    # 第一次遍历，测量各组件需要的高度
    cur_y = PAD
    header_h = 110
    cur_y += header_h + 30
    
    elements = []
    text_lh = int(28 * 1.7) # 行高
    
    for content in data["contents"]:
        if content["type"] == "text":
            block_h = 40 # 上下 padding
            for para in content["lines"]:
                lines = wrap_text(para, F28, INNER_W - 48)
                block_h += len(lines) * text_lh + 10
            block_h -= 10
            elements.append({"type": "text", "h": block_h, "lines": content["lines"]})
            cur_y += block_h + 15
            
        elif content["type"] in ["image", "video"]:
            try:
                img = _b64_img(content["src"])
                scaled_h = int(img.height * (INNER_W / img.width))
                elements.append({"type": content["type"], "img": img, "h": scaled_h})
                cur_y += scaled_h + 15
            except Exception:
                pass
                
    total_h = max(cur_y + PAD, 600)
    
    # 第二次遍历，开始实际绘制图层
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h)
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    d.rounded_rectangle([PAD, y, PAD + INNER_W, y + header_h], radius=8, fill=C_CARD_BG, outline=C_CARD_BORDER, width=1)
    
    ax, ay = PAD + 20, y + 20
    if data["avatar"]:
        try:
            av = _b64_fit(data["avatar"], 70, 70)
            canvas.paste(av, (ax, ay), _round_mask(70, 70, 35))
        except Exception:
            d.ellipse([ax, ay, ax + 70, ay + 70], fill=(51, 51, 51, 255))
    else:
        d.ellipse([ax, ay, ax + 70, ay + 70], fill=(51, 51, 51, 255))
        
    # [修改] 英文下沉 7px
    draw_text_mixed(d, (ax + 90, ay - 2), data["title"], cn_font=F36, en_font=F36, fill=C_TEXT, dy_en=7)
    # [修改] 英文下沉 4px
    draw_text_mixed(d, (ax + 90, ay + 44), data["user"], cn_font=F18, en_font=M18, fill=C_SUBTEXT, dy_en=4)
    
    user_w = int(F18.getlength(data["user"])) if not data["user"].isascii() else int(M18.getlength(data["user"]))
    # [修改] 中文垫底替换为 F18，英文下沉 4px
    draw_text_mixed(d, (ax + 90 + user_w + 15, ay + 44), data["time"], cn_font=F18, en_font=M18, fill=C_SUBTEXT, dy_en=4)
    
    y += header_h + 30
    
    # 绘制内容块
    for el in elements:
        if el["type"] == "text":
            bh = el["h"]
            d.rounded_rectangle([PAD, y, PAD + INNER_W, y + bh], radius=8, fill=C_CARD_BG)
            ty = y + 20
            for para in el["lines"]:
                lines = wrap_text(para, F28, INNER_W - 48)
                for line in lines:
                    # [修改] 英文下沉 6px
                    draw_text_mixed(d, (PAD + 24, ty), line, cn_font=F28, en_font=F28, fill=(221, 221, 221, 255), dy_en=6)
                    ty += text_lh
                ty += 10 # 段落间距
            y += bh + 15
            
        elif el["type"] in ["image", "video"]:
            img = el["img"]
            ih = el["h"]
            resized = img.resize((INNER_W, ih), Image.Resampling.LANCZOS)
            canvas.paste(resized, (PAD, y), _round_mask(INNER_W, ih, 8))
            
            d.rounded_rectangle([PAD, y, PAD + INNER_W, y + ih], radius=8, outline=(0, 0, 0, 76), width=1)
            
            if el["type"] == "video":
                px, py = PAD + INNER_W // 2, y + ih // 2
                d.ellipse([px - 30, py - 30, px + 30, py + 30], fill=(0, 0, 0, 153))
                d.polygon([(px - 8, py - 12), (px + 12, py), (px - 8, py + 12)], fill=C_TEXT)
                
            y += ih + 15

    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue()


def render(html: str) -> bytes:
    data = parse_html(html)
    if data["is_list"]:
        return render_list_mode(data)
    else:
        return render_detail_mode(data)