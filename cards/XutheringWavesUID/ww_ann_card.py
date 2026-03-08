# 鸣潮公告卡片渲染器 (PIL 版)

from __future__ import annotations

import base64
import math
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps


# 常量定义

W = 750
C_BG_PAGE   = (244, 247, 249, 255)  # #f4f7f9
C_BG_CARD   = (255, 255, 255, 255)  # #ffffff
C_HEADER_BG = (18,  18,  18,  255)  # #121212
C_TEXT_MAIN = (44,  62,  80,  255)  # #2c3e50
C_TEXT_SUB  = (149, 165, 166, 255)  # #95a5a6

RE_COLOR = re.compile(r"(?:color|background):\s*([^;]+)")


from . import draw_text_mixed, M12, M14, M15, M16, M17, M18, M20, M22, M24, M26, M28, M30, M32, M34, M36, M38, M42, M48, M72, _b64_img, _b64_fit, _round_mask

# 使用包级统一字体对象（从包里导入以复用同一实例）
from . import F11, F12, F12B, F13, F14, F14B, F20, F20B, F22B, F26B, F28B
def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1


# 颜色转换工具

def parse_color(c_str: str, default=(52, 152, 219, 255)) -> tuple:
    c_str = c_str.strip()
    if c_str.startswith("#"):
        c_str = c_str.lstrip("#")
        if len(c_str) == 3: c_str = "".join(c+c for c in c_str)
        if len(c_str) == 6:
            return (int(c_str[0:2], 16), int(c_str[2:4], 16), int(c_str[4:6], 16), 255)
    return default


# 图片加载/缓存委托给包级实现（避免 data: URI 被本地缓存）

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int,
                       x1: int, y1: int, r: int, fill: tuple, outline=None, width=1) -> None:
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(block)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(block, (x0, y0))

def _paste_rounded(canvas: Image.Image, img: Image.Image, x: int, y: int, r: int):
    w, h = img.size
    canvas.paste(img, (x, y), _round_mask(w, h, r))


# HTML 解析

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    
    is_list = soup.select_one(".list-section") is not None
    
    # Header Logo
    logo_src = ""
    logo = soup.select_one(".header-logo")
    if logo and logo.get("src", "").startswith("data:"):
        logo_src = logo["src"]

    # Header Titles
    title = (soup.select_one(".header-title") or soup).get_text(strip=True) if soup.select_one(".header-title") else ""
    subtitle = (soup.select_one(".header-subtitle") or soup).get_text(strip=True) if soup.select_one(".header-subtitle") else ""

    # User Info
    user_avatar = ""
    u_av = soup.select_one(".user-avatar-large")
    if u_av and u_av.get("src", "").startswith("data:"):
        user_avatar = u_av["src"]
        
    user_name = (soup.select_one(".user-name-large") or soup).get_text(strip=True) if soup.select_one(".user-name-large") else ""
    user_meta = (soup.select_one(".user-time-large") or soup).get_text(strip=True) if soup.select_one(".user-time-large") else ""

    # Footer
    footer_src = ""
    fi = soup.select_one(".footer img")
    if fi and fi.get("src", "").startswith("data:"):
        footer_src = fi["src"]

    data = {
        "is_list": is_list,
        "logo_src": logo_src,
        "title": title,
        "subtitle": subtitle,
        "user_avatar": user_avatar,
        "user_name": user_name,
        "user_meta": user_meta,
        "footer_src": footer_src,
        "list_sections": [],
        "detail_blocks": []
    }

    if is_list:
        for sec in soup.select(".list-section"):
            stitle_el = sec.select_one(".section-title")
            s_name = stitle_el.get_text(strip=True) if stitle_el else ""
            s_en = stitle_el.get("data-en", "") if stitle_el else ""
            
            s_color = (52, 152, 219, 255) # default blue
            if stitle_el and stitle_el.get("style"):
                m = RE_COLOR.search(stitle_el.get("style"))
                if m: s_color = parse_color(m.group(1))

            items = []
            for item in sec.select(".ann-item"):
                c_img = item.select_one(".ann-cover img")
                c_src = c_img["src"] if c_img and c_img.get("src", "").startswith("data:") else ""
                
                badge = item.select_one(".ann-id-badge")
                id_text = badge.get_text(strip=True) if badge else ""
                
                t_el = item.select_one(".ann-title")
                item_title = t_el.get_text(strip=True) if t_el else ""
                
                d_el = item.select_one(".ann-date")
                item_date = d_el.get_text(strip=True) if d_el else ""
                
                items.append({
                    "cover": c_src,
                    "id_text": id_text,
                    "title": item_title,
                    "date": item_date
                })
            data["list_sections"].append({
                "name": s_name,
                "en": s_en,
                "color": s_color,
                "items": items
            })
    else:
        for block in soup.select(".content > div"):
            classes = block.get("class", [])
            if "text-block" in classes:
                # 提取纯文本并保留换行
                text = block.get_text(separator="\n", strip=True)
                if text:
                    data["detail_blocks"].append({"type": "text", "content": text})
            elif "image-block" in classes or "video-block" in classes:
                img = block.select_one("img")
                if img and img.get("src", "").startswith("data:"):
                    b_type = "video" if "video-block" in classes else "image"
                    data["detail_blocks"].append({"type": b_type, "src": img["src"]})

    return data


# 辅助：文本折行器 (专门处理富文本段落)

def _wrap_paragraphs(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("") # 保留空行
            continue
            
        curr_line = ""
        for char in paragraph:
            if font.getlength(curr_line + char) <= max_w:
                curr_line += char
            else:
                lines.append(curr_line)
                curr_line = char
        if curr_line:
            lines.append(curr_line)
    return lines


# 各组件绘制函数

def draw_header(data: dict) -> Image.Image:
    # 高度自适应
    header_h = 130 if data["is_list"] else 150
    img = Image.new("RGBA", (W, header_h), C_HEADER_BG)
    d = ImageDraw.Draw(img)
    
    # 底部蓝边
    d.rectangle([0, header_h - 3, W, header_h], fill=(52, 152, 219, 255))
    
    y_offset = 30
    # Row 1: Logo & Title
    if data["logo_src"]:
        try:
            logo = _b64_fit(data["logo_src"], 180, 60)
            img.paste(logo, (30, y_offset), logo)
            x_offset = 30 + 180 + 20
        except Exception:
            x_offset = 30
    else:
        x_offset = 30

    if not data["is_list"] and data["title"]:
        draw_text_mixed(d, (x_offset, y_offset + _ty(F28B, data["title"], 60)), data["title"], cn_font=F28B, en_font=M28, fill=(255, 255, 255, 255))

    y_offset += 60 + 12

    # Row 2: Subtitle
    if data["is_list"] and data["subtitle"]:
        stw = int(F14.getlength(data["subtitle"]))
        _draw_rounded_rect(img, 30, y_offset, 30 + stw + 24, y_offset + 26, 4, (255, 255, 255, 25))
    draw_text_mixed(d, (30 + 12, y_offset + _ty(F14, data["subtitle"], 26)), data["subtitle"], cn_font=F14, en_font=M14, fill=(255, 255, 255, 178))

    return img

def draw_user_info(data: dict) -> Image.Image:
    if not data["user_name"]:
        return Image.new("RGBA", (W, 0))
        
    H = 110
    img = Image.new("RGBA", (W, H), C_BG_CARD)
    d = ImageDraw.Draw(img)
    
    # 底部边界线
    d.line([(0, H-1), (W, H-1)], fill=(237, 242, 247, 255), width=1)
    
    av_sz = 70
    av_x, av_y = 30, 20
    _draw_rounded_rect(img, av_x, av_y, av_x + av_sz, av_y + av_sz, av_sz//2, (200, 200, 200, 255))
    if data["user_avatar"]:
        try:
            av_img = _b64_fit(data["user_avatar"], av_sz, av_sz)
            _paste_rounded(img, av_img, av_x, av_y, av_sz//2)
        except Exception: pass
    d.ellipse([av_x, av_y, av_x + av_sz, av_y + av_sz], outline=(52, 152, 219, 255), width=2)
    
    tx = av_x + av_sz + 18
    draw_text_mixed(d, (tx, av_y + 8), data["user_name"], cn_font=F22B, en_font=M22, fill=C_TEXT_MAIN)
    if data["user_meta"]:
        draw_text_mixed(d, (tx, av_y + 40), data["user_meta"], cn_font=F14, en_font=M14, fill=C_TEXT_SUB)
        
    return img

# --- 列表模式绘制 ---
def draw_list_view(sections: list) -> Image.Image:
    blocks = []
    for sec in sections:
        # 1. Section Title (H=60)
        h_title = 60
        t_img = Image.new("RGBA", (W, h_title), (0, 0, 0, 0))
        td = ImageDraw.Draw(t_img)
        if sec["name"]:
            td.rectangle([25, 20, 31, 20 + 26], fill=sec["color"])
            draw_text_mixed(td, (43, 20 + _ty(F26B, sec["name"], 26)), sec["name"], cn_font=F26B, en_font=M26, fill=(26, 26, 26, 255))
            ew = int(F26B.getlength(sec["name"]))
            if sec["en"]:
                draw_text_mixed(td, (43 + ew + 12, 20 + _ty(F12B, sec["en"], 26) + 4), sec["en"], cn_font=F12B, en_font=M12, fill=(149, 165, 166, 204))
        blocks.append(t_img)

        # 2. Grid items
        PAD_X = 25
        GAP = 15
        ITEM_W = (W - PAD_X * 2 - GAP * 2) // 3  # 223px
        ITEM_H = 110 + 80  # Cover + Info padding
        
        items = sec["items"]
        rows = math.ceil(len(items) / 3)
        grid_h = rows * ITEM_H + max(0, rows - 1) * GAP + 20
        
        g_img = Image.new("RGBA", (W, grid_h), (0, 0, 0, 0))
        
        for i, item in enumerate(items):
            row, col = divmod(i, 3)
            ix = PAD_X + col * (ITEM_W + GAP)
            iy = row * (ITEM_H + GAP)
            
            # Draw Item
            card = Image.new("RGBA", (ITEM_W, ITEM_H), (0, 0, 0, 0))
            cd = ImageDraw.Draw(card)
            _draw_rounded_rect(card, 0, 0, ITEM_W, ITEM_H, 10, C_BG_CARD)
            
            # Cover
            if item["cover"]:
                try:
                    cv = _b64_fit(item["cover"], ITEM_W, 110)
                    card.paste(cv, (0, 0))
                except Exception: pass
            
            # Badge
            if item["id_text"]:
                bw = int(F12B.getlength(item["id_text"])) + 20
                _draw_rounded_rect(card, 0, 0, bw, 20, 0, sec["color"])
                # Right bottom radius for badge
                card.paste(Image.new("RGBA", (10, 10), sec["color"]), (bw-10, 10), _round_mask(10, 10, 10))
                draw_text_mixed(cd, (10, _ty(F12B, item["id_text"], 20)), item["id_text"], cn_font=F12B, en_font=M12, fill=C_BG_CARD)

            # Info (Title + Date)
            lines = _wrap_paragraphs(item["title"], F14B, ITEM_W - 24)
            y_txt = 110 + 12
            for line in lines[:2]: # Max 2 lines
                draw_text_mixed(cd, (12, y_txt), line, cn_font=F14B, en_font=M14, fill=C_TEXT_MAIN)
                y_txt += 20
            
            draw_text_mixed(cd, (ITEM_W - 12 - int(F12.getlength(item["date"])), ITEM_H - 12 - 16), item["date"], cn_font=F12, en_font=M12, fill=C_TEXT_SUB)
            
            # Outline
            cd.rounded_rectangle([0, 0, ITEM_W-1, ITEM_H-1], radius=10, outline=(0, 0, 0, 15), width=1)
            
            g_img.alpha_composite(card, (ix, iy))
            
        blocks.append(g_img)

    total_h = sum(b.height for b in blocks)
    out = Image.new("RGBA", (W, total_h), (0, 0, 0, 0))
    cy = 0
    for b in blocks:
        out.alpha_composite(b, (0, cy))
        cy += b.height
    return out

# --- 详情模式绘制 ---
def draw_detail_view(blocks_data: list) -> Image.Image:
    PAD_X = 20
    MAX_W = W - PAD_X * 2 # 710
    
    drawn_blocks = []
    for b in blocks_data:
        if b["type"] == "text":
            lines = _wrap_paragraphs(b["content"], F20, MAX_W)
            LH = 30 # line-height 1.5 of 20px
            bh = len(lines) * LH + 10 # 10px paragraph gap buffer
            
            img = Image.new("RGBA", (W, bh), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            cy = 0
            for line in lines:
                if line: draw_text_mixed(d, (PAD_X, cy + _ty(F20, line, LH)), line, cn_font=F20, en_font=M20, fill=(51, 51, 51, 255))
                cy += LH
            drawn_blocks.append(img)
            
        elif b["type"] in ["image", "video"]:
            try:
                raw_img = _b64_img(b["src"])
                # 依据 MAX_W 等比缩放
                scale = MAX_W / raw_img.width
                new_h = int(raw_img.height * scale)
                r_img = raw_img.resize((MAX_W, new_h), Image.LANCZOS)
                
                bh = new_h + 8 # margin 4px top/bottom
                img = Image.new("RGBA", (W, bh), (0, 0, 0, 0))
                
                _draw_rounded_rect(img, PAD_X, 4, PAD_X + MAX_W, 4 + new_h, 8, C_BG_CARD)
                _paste_rounded(img, r_img, PAD_X, 4, 8)
                ImageDraw.Draw(img).rounded_rectangle([PAD_X, 4, PAD_X+MAX_W-1, 4+new_h-1], radius=8, outline=(0, 0, 0, 15), width=1)
                
                if b["type"] == "video":
                    d = ImageDraw.Draw(img)
                    ImageDraw.Draw(img).rounded_rectangle([PAD_X, 4, PAD_X+MAX_W-1, 4+new_h-1], radius=8, outline=(52, 152, 219, 255), width=2)
                    
                    vw, vh = 70, 24
                    vx, vy = PAD_X + MAX_W - vw - 10, 4 + new_h - vh - 10
                    _draw_rounded_rect(img, vx, vy, vx + vw, vy + vh, 12, (0, 0, 0, 190))
                    draw_text_mixed(d, (vx + 10, vy + _ty(F11, "▶ 视频", vh)), "▶ 视频", cn_font=F11, en_font=M11, fill=C_BG_CARD)
                    
                drawn_blocks.append(img)
            except Exception as e:
                print(f"解析详情媒体失败: {e}")

    if not drawn_blocks:
        return Image.new("RGBA", (W, 20), (0, 0, 0, 0))
        
    total_h = sum(b.height for b in drawn_blocks) + 20 # bottom padding
    out = Image.new("RGBA", (W, total_h), (0, 0, 0, 0))
    cy = 10
    for b in drawn_blocks:
        out.alpha_composite(b, (0, cy))
        cy += b.height
    return out


# 主渲染逻辑

def render(html: str) -> bytes:
    data = parse_html(html)
    
    h_img = draw_header(data)
    u_img = draw_user_info(data)
    
    if data["is_list"]:
        c_img = draw_list_view(data["list_sections"])
    else:
        c_img = draw_detail_view(data["detail_blocks"])

    # Footer
    FOOTER_H = 0
    f_img = None
    if data["footer_src"]:
        try:
            raw_f = _b64_img(data["footer_src"])
            scale = W / raw_f.width
            FOOTER_H = int(raw_f.height * scale)
            f_img = raw_f.resize((W, FOOTER_H), Image.LANCZOS)
        except Exception: pass

    # Assemble
    content_h = h_img.height + u_img.height + c_img.height + 6 # 6px container padding
    total_h = content_h + (FOOTER_H if f_img else 0)
    
    canvas = Image.new("RGBA", (W, total_h), C_BG_PAGE)
    
    # Draw Container (White background with shadow)
    _draw_rounded_rect(canvas, 0, 0, W, content_h, 0, C_BG_CARD)
    
    y = 0
    canvas.alpha_composite(h_img, (0, y)); y += h_img.height
    canvas.alpha_composite(u_img, (0, y)); y += u_img.height
    canvas.alpha_composite(c_img, (0, y)); y += c_img.height
    
    if f_img:
        canvas.alpha_composite(f_img, (0, content_h))

    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
