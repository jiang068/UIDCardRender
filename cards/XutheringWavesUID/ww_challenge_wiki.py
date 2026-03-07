# 鸣潮深塔图鉴 (Tower Wiki) 卡片渲染器 (PIL 版)

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

W = 1000
PAD = 40
INNER_W = W - PAD * 2   # 920

C_BG = (15, 15, 19, 255)
C_WHITE = (255, 255, 255, 255)

RE_BG_URL = re.compile(r"url\('([^']+)'\)")
RE_COLOR = re.compile(r"color:\s*([^;]+)")
RE_BORDER = re.compile(r"border-color:\s*([^;]+)")


# 字体加载

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    FONT_FILE = Path(__file__).parent.parent.parent / "assets" / "H7GBKHeavy.TTF"
    candidates = [
        str(FONT_FILE),
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(str(p), size)
        except Exception:
            continue
    return ImageFont.load_default()

F15  = _load_font(15, bold=True)
F16  = _load_font(16)
F18  = _load_font(18)
F18B = _load_font(18, bold=True)
F20B = _load_font(20, bold=True)
F26  = _load_font(26)
F28B = _load_font(28, bold=True)
F34B = _load_font(34, bold=True)
F72B = _load_font(72, bold=True)

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1

def _truncate_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    if font.getlength(text) <= max_w:
        return text
    for i in range(len(text) - 1, 0, -1):
        if font.getlength(text[:i] + "...") <= max_w:
            return text[:i] + "..."
    return "..."

def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines = []
    curr_line = ""
    for char in text:
        if font.getlength(curr_line + char) <= max_w:
            curr_line += char
        else:
            lines.append(curr_line)
            curr_line = char
    if curr_line:
        lines.append(curr_line)
    return lines


# 颜色工具

def parse_color(c_str: str, default=(255, 255, 255, 255)) -> tuple:
    c_str = c_str.strip().lower()
    if c_str.startswith("#"):
        c_str = c_str.lstrip("#")
        if len(c_str) == 3: c_str = "".join(c+c for c in c_str)
        if len(c_str) >= 6:
            r, g, b = int(c_str[0:2], 16), int(c_str[2:4], 16), int(c_str[4:6], 16)
            a = int(c_str[6:8], 16) if len(c_str) == 8 else 255
            return (r, g, b, a)
    if c_str.startswith("rgba"):
        m = re.match(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9.]+)\s*\)", c_str)
        if m: return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(float(m.group(4))*255))
    return default


# 图像缓存与辅助函数

@lru_cache(maxsize=128)
def _b64_img(src: str) -> Image.Image:
    if "," in src: src = src.split(",", 1)[1]
    return Image.open(BytesIO(base64.b64decode(src))).convert("RGBA")

@lru_cache(maxsize=128)
def _b64_fit(src: str, w: int, h: int) -> Image.Image:
    return ImageOps.fit(_b64_img(src), (w, h), Image.Resampling.LANCZOS)

@lru_cache(maxsize=64)
def _round_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return mask

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, 
                       r: int, fill: tuple, outline=None, width=1) -> None:
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(block, (x0, y0))

@lru_cache(maxsize=64)
def _get_h_gradient(w: int, h: int, left_rgba: tuple, right_rgba: tuple) -> Image.Image:
    grad = Image.new("RGBA", (w, 1))
    for xi in range(w):
        t = xi / max(w - 1, 1)
        grad.putpixel((xi, 0), (
            int(left_rgba[0] + (right_rgba[0] - left_rgba[0]) * t),
            int(left_rgba[1] + (right_rgba[1] - left_rgba[1]) * t),
            int(left_rgba[2] + (right_rgba[2] - left_rgba[2]) * t),
            int(left_rgba[3] + (right_rgba[3] - left_rgba[3]) * t)
        ))
    return grad.resize((w, h), Image.NEAREST)


# HTML 解析

def _parse_tower_column(tower_el, main_color) -> dict | None:
    if not tower_el: return None
    
    t_name = tower_el.select_one(".card-title").get_text(strip=True) if tower_el.select_one(".card-title") else ""
    
    floors = []
    for f_el in tower_el.select(".floor-block"):
        f_title_el = f_el.select_one(".sub-card-title")
        f_name = f_title_el.contents[0].strip() if f_title_el else ""
        f_cost = f_title_el.select_one(".cost-tag").get_text(strip=True).replace("消耗疲劳:", "").strip() if f_title_el and f_title_el.select_one(".cost-tag") else ""
        
        buffs = [b.get_text(strip=True) for b in f_el.select(".buff-text")]
        
        monsters = []
        for m_el in f_el.select(".monster-card"):
            m_icon = m_el.select_one(".monster-icon").get("src", "") if m_el.select_one(".monster-icon") else ""
            m_name = m_el.select_one(".monster-name").get_text(strip=True) if m_el.select_one(".monster-name") else ""
            
            e_el = m_el.select_one(".element-badge")
            m_ele = e_el.get_text(strip=True).replace("抗性", "").strip() if e_el else ""
            
            c_str = RE_COLOR.search(e_el.get("style", "")) if e_el else None
            m_col = parse_color(c_str.group(1)) if c_str else main_color
            
            monsters.append({"icon": m_icon, "name": m_name, "element": m_ele, "color": m_col})
            
        floors.append({"name": f_name, "cost": f_cost, "buffs": buffs, "monsters": monsters})
        
    return {"name": t_name, "floors": floors}

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    
    style_tag = soup.select_one("style")
    style_text = style_tag.string if style_tag else ""
    
    bg_url_m = re.search(r"background-image:\s*url\('([^']+)'\)", style_text)
    bg_url = bg_url_m.group(1) if bg_url_m else ""
    
    m_color_m = re.search(r"--main-color:\s*([^;]+);", style_text)
    main_color = parse_color(m_color_m.group(1), (212, 177, 99, 255)) if m_color_m else (212, 177, 99, 255)
    
    title = soup.select_one(".title").get_text(strip=True) if soup.select_one(".title") else ""
    subtitle = soup.select_one(".subtitle").get_text(strip=True) if soup.select_one(".subtitle") else ""
    
    footer_src = soup.select_one(".footer img").get("src", "") if soup.select_one(".footer img") else ""
    
    # 塔的分区寻找逻辑
    towers = soup.select(".tower-row > .tower-column > .card")
    left_tower = _parse_tower_column(towers[0] if len(towers) > 0 else None, main_color)
    right_tower = _parse_tower_column(towers[1] if len(towers) > 1 else None, main_color)
    
    deep_tower_el = soup.select_one(".content > .card:not(.tower-row .card)")
    deep_tower = _parse_tower_column(deep_tower_el, main_color)
    
    return {
        "bg_url": bg_url,
        "main_color": main_color,
        "title": title,
        "subtitle": subtitle,
        "footer_src": footer_src,
        "left_tower": left_tower,
        "right_tower": right_tower,
        "deep_tower": deep_tower,
    }


# 独立楼层绘制组件 (核心测算逻辑)

def draw_floor_block(floor: dict, width: int, main_color: tuple) -> Image.Image:
    pad = 18
    avail_w = width - pad * 2
    
    # 1. 估算标题区高度
    title_h = 28 + 14  # text size + margin-bottom
    
    # 2. 估算 Buff 区高度
    buff_imgs = []
    if floor["buffs"]:
        for b_text in floor["buffs"]:
            # buff padding: 8px 14px
            lines = _wrap_text(b_text, F18, avail_w - 28 - 3) 
            b_h = len(lines) * 28 + 16 # line-height 1.6 ~ 28px
            
            b_img = Image.new("RGBA", (avail_w, b_h), (0, 0, 0, 0))
            d_b = ImageDraw.Draw(b_img)
            _draw_rounded_rect(b_img, 0, 0, avail_w, b_h, 8, (255, 255, 255, 8))
            d_b.rectangle([0, 0, 3, b_h], fill=(100, 180, 255, 102))
            
            by = 8
            for line in lines:
                d_b.text((14, by), line, font=F18, fill=(204, 204, 204, 255))
                by += 28
            buff_imgs.append(b_img)
            
    buff_area_h = sum(im.height for im in buff_imgs) + max(0, len(buff_imgs) - 1) * 8 + 14 if buff_imgs else 0

    # 3. 估算 Monster 区高度
    m_grid_gap = 14
    m_w = (avail_w - m_grid_gap) // 2
    m_h = 20 + 56 # padding 10*2 + icon 56
    
    m_rows = math.ceil(len(floor["monsters"]) / 2) if floor["monsters"] else 0
    m_area_h = m_rows * m_h + max(0, m_rows - 1) * m_grid_gap
    
    # 4. 汇总组装
    H = pad * 2 + title_h + buff_area_h + m_area_h
    
    img = Image.new("RGBA", (width, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    _draw_rounded_rect(img, 0, 0, width, H, 12, (255, 255, 255, 5), outline=(255, 255, 255, 20))
    
    cy = pad
    
    # Draw Title
    d.rectangle([pad, cy + 4, pad + 5, cy + 28 - 4], fill=main_color)
    d.text((pad + 14, cy), floor["name"], font=F28B, fill=C_WHITE)
    
    nw = int(F28B.getlength(floor["name"])) + 26
    c_txt = f"消耗疲劳: {floor['cost']}"
    _draw_rounded_rect(img, pad + nw, cy + 2, pad + nw + int(F18.getlength(c_txt)) + 20, cy + 28 - 2, 12, (255, 255, 255, 20))
    d.text((pad + nw + 10, cy + 2 + _ty(F18, c_txt, 24)), c_txt, font=F18, fill=(153, 153, 153, 255))
    
    cy += title_h
    
    # Draw Buffs
    if buff_imgs:
        for bi in buff_imgs:
            img.alpha_composite(bi, (pad, cy))
            cy += bi.height + 8
        cy += 14 - 8
        
    # Draw Monsters
    if floor["monsters"]:
        for i, m in enumerate(floor["monsters"]):
            r, c = divmod(i, 2)
            mx = pad + c * (m_w + m_grid_gap)
            my = cy + r * (m_h + m_grid_gap)
            
            # Monster Card Base
            m_card = Image.new("RGBA", (m_w, m_h), (0, 0, 0, 0))
            md = ImageDraw.Draw(m_card)
            
            _draw_rounded_rect(m_card, 0, 0, m_w, m_h, 16, (20, 20, 25, 200), outline=(m["color"][0], m["color"][1], m["color"][2], 64))
            
            # Icon
            ic_sz = 56
            md.ellipse([14, 10, 14 + ic_sz, 10 + ic_sz], fill=(m["color"][0], m["color"][1], m["color"][2], 76))
            if m["icon"]:
                try:
                    ic = _b64_fit(m["icon"], ic_sz, ic_sz)
                    m_card.paste(ic, (14, 10), _round_mask(ic_sz, ic_sz, ic_sz//2))
                except Exception: pass
            md.ellipse([14, 10, 14 + ic_sz, 10 + ic_sz], outline=m["color"], width=2)
            
            # Text
            tx = 14 + ic_sz + 14
            m_name_trunc = _truncate_text(m["name"], F20B, m_w - tx - 10)
            md.text((tx, 14), m_name_trunc, font=F20B, fill=C_WHITE)
            
            if m["element"]:
                ele_txt = f"{m['element']}抗性"
                md.text((tx, 42), ele_txt, font=F15, fill=m["color"])
                
            img.alpha_composite(m_card, (mx, my))

    return img

def draw_tower_card(tower: dict, width: int, main_color: tuple) -> Image.Image:
    if not tower: return Image.new("RGBA", (width, 0))
    
    # 预渲染所有 floor 以获知高度
    f_imgs = [draw_floor_block(f, width - 48, main_color) for f in tower["floors"]]
    
    pad = 24
    title_h = 45 # 34 text + 12 pb + 8 mb
    floors_h = sum(im.height for im in f_imgs) + max(0, len(f_imgs) - 1) * 18 if f_imgs else 0
    
    H = pad * 2 + title_h + floors_h
    
    img = Image.new("RGBA", (width, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    # Card bg
    _draw_rounded_rect(img, 0, 0, width, H, 16, (20, 20, 25, 224), outline=(255, 255, 255, 25))
    
    d.text((pad, pad), tower["name"], font=F34B, fill=main_color)
    d.line([(pad, pad + 45), (width - pad, pad + 45)], fill=(255, 255, 255, 20), width=2)
    
    cy = pad + title_h + 8
    for f_im in f_imgs:
        img.alpha_composite(f_im, (pad, cy))
        cy += f_im.height + 18
        
    return img


# 主渲染逻辑

def render(html: str) -> bytes:
    data = parse_html(html)
    
    # Header Area
    hdr_h = 140 if data["subtitle"] else 100
    hdr_img = Image.new("RGBA", (INNER_W, hdr_h), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hdr_img)
    
    tw = int(F72B.getlength(data["title"]))
    hd.text(((INNER_W - tw) // 2, 0), data["title"], font=F72B, fill=C_WHITE)
    
    if data["subtitle"]:
        stw = int(F26.getlength(data["subtitle"]))
        _draw_rounded_rect(hdr_img, (INNER_W - stw - 56) // 2, 85, (INNER_W + stw + 56) // 2, 85 + 46, 23, (0, 0, 0, 128), outline=(255, 255, 255, 38))
        hd.text(((INNER_W - stw) // 2, 85 + _ty(F26, data["subtitle"], 46)), data["subtitle"], font=F26, fill=(204, 204, 204, 255))
        
    # Row 1: Left / Right Towers
    col_w = (INNER_W - 20) // 2
    l_card = draw_tower_card(data["left_tower"], col_w, data["main_color"])
    r_card = draw_tower_card(data["right_tower"], col_w, data["main_color"])
    
    row1_h = max(l_card.height, r_card.height)
    # 因为 CSS 是 align-items: stretch，我们需要把左右塔的底板拉伸到同样高
    if l_card.height > 0: l_card = draw_tower_card(data["left_tower"], col_w, data["main_color"]); _draw_rounded_rect(l_card, 0, 0, col_w, row1_h, 16, (20, 20, 25, 224), outline=(255, 255, 255, 25))
    if r_card.height > 0: r_card = draw_tower_card(data["right_tower"], col_w, data["main_color"]); _draw_rounded_rect(r_card, 0, 0, col_w, row1_h, 16, (20, 20, 25, 224), outline=(255, 255, 255, 25))
    
    # 重新画内容覆盖上去（暴力覆写底色实现等高）
    l_card = draw_tower_card(data["left_tower"], col_w, data["main_color"])
    r_card = draw_tower_card(data["right_tower"], col_w, data["main_color"])
    
    l_final = Image.new("RGBA", (col_w, row1_h), (0,0,0,0))
    if l_card.height > 0:
        _draw_rounded_rect(l_final, 0, 0, col_w, row1_h, 16, (20, 20, 25, 224), outline=(255, 255, 255, 25))
        l_final.alpha_composite(l_card, (0, 0))
        
    r_final = Image.new("RGBA", (col_w, row1_h), (0,0,0,0))
    if r_card.height > 0:
        _draw_rounded_rect(r_final, 0, 0, col_w, row1_h, 16, (20, 20, 25, 224), outline=(255, 255, 255, 25))
        r_final.alpha_composite(r_card, (0, 0))

    # Row 2: Deep Tower
    deep_img = Image.new("RGBA", (INNER_W, 0))
    if data["deep_tower"]:
        pad = 24
        title_h = 45
        f_imgs = [draw_floor_block(f, col_w, data["main_color"]) for f in data["deep_tower"]["floors"]]
        
        d_rows = math.ceil(len(f_imgs) / 2)
        
        # Calculate max height per row
        row_heights = []
        for i in range(d_rows):
            h1 = f_imgs[i*2].height if i*2 < len(f_imgs) else 0
            h2 = f_imgs[i*2+1].height if i*2+1 < len(f_imgs) else 0
            row_heights.append(max(h1, h2))
            
        deep_grid_h = sum(row_heights) + max(0, d_rows - 1) * 20
        deep_h = pad * 2 + title_h + 8 + deep_grid_h
        
        deep_img = Image.new("RGBA", (INNER_W, deep_h), (0, 0, 0, 0))
        dd = ImageDraw.Draw(deep_img)
        _draw_rounded_rect(deep_img, 0, 0, INNER_W, deep_h, 16, (20, 20, 25, 224), outline=(255, 255, 255, 25))
        
        dd.text((pad, pad), data["deep_tower"]["name"], font=F34B, fill=data["main_color"])
        dd.line([(pad, pad + 45), (INNER_W - pad, pad + 45)], fill=(255, 255, 255, 20), width=2)
        
        cy = pad + title_h + 8
        for i in range(d_rows):
            r_max_h = row_heights[i]
            
            # Left block in this row
            if i*2 < len(f_imgs):
                l_fb = f_imgs[i*2]
                l_base = Image.new("RGBA", (col_w, r_max_h), (0,0,0,0))
                _draw_rounded_rect(l_base, 0, 0, col_w, r_max_h, 12, (255, 255, 255, 5), outline=(255, 255, 255, 20))
                l_base.alpha_composite(l_fb, (0, 0))
                deep_img.alpha_composite(l_base, (pad, cy))
                
            # Right block in this row
            if i*2+1 < len(f_imgs):
                r_fb = f_imgs[i*2+1]
                r_base = Image.new("RGBA", (col_w, r_max_h), (0,0,0,0))
                _draw_rounded_rect(r_base, 0, 0, col_w, r_max_h, 12, (255, 255, 255, 5), outline=(255, 255, 255, 20))
                r_base.alpha_composite(r_fb, (0, 0))
                deep_img.alpha_composite(r_base, (pad + col_w + 20, cy))
                
            cy += r_max_h + 20

    # Footer
    FOOTER_H = 0
    f_img = None
    if data["footer_src"]:
        try:
            raw_f = _b64_img(data["footer_src"])
            scale = 24 / raw_f.height
            fw = int(raw_f.width * scale)
            FOOTER_H = 24
            f_img = raw_f.resize((fw, FOOTER_H), Image.LANCZOS)
        except Exception: pass

    # Total Canvas
    total_h = PAD + hdr_h + 25 + row1_h
    if deep_img.height > 0:
        total_h += 25 + deep_img.height
    if f_img:
        total_h += 12 + FOOTER_H
    total_h += PAD
    
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    
    if data["bg_url"]:
        try:
            bg_base = _b64_img(data["bg_url"])
            bg_base = ImageOps.fit(bg_base, (W, total_h), Image.Resampling.LANCZOS)
            canvas.alpha_composite(bg_base)
            
            # Overlay (Top-Down Black & Left-Right Blue)
            td_overlay = _get_v_gradient(W, total_h, (15, 15, 19, 102), (15, 15, 19, 242))
            lr_overlay = _get_h_gradient(W, total_h, (78, 124, 255, 38), (78, 124, 255, 0))
            canvas.alpha_composite(td_overlay)
            canvas.alpha_composite(lr_overlay)
        except Exception: pass

    # Paste components
    y = PAD
    canvas.alpha_composite(hdr_img, (PAD, y))
    y += hdr_h + 25
    
    if row1_h > 0:
        canvas.alpha_composite(l_final, (PAD, y))
        canvas.alpha_composite(r_final, (PAD + col_w + 20, y))
        y += row1_h + 25
        
    if deep_img.height > 0:
        canvas.alpha_composite(deep_img, (PAD, y))
        y += deep_img.height + 12
        
    if f_img:
        f_alpha = f_img.copy()
        f_alpha.putalpha(f_alpha.getchannel("A").point(lambda a: int(a * 0.6)))
        canvas.alpha_composite(f_alpha, ((W - f_img.width)//2, y))

    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()

def _get_v_gradient(w: int, h: int, top_rgba: tuple, bottom_rgba: tuple) -> Image.Image:
    grad = Image.new("RGBA", (1, h))
    for yi in range(h):
        t = yi / max(h - 1, 1)
        grad.putpixel((0, yi), (
            int(top_rgba[0] + (bottom_rgba[0] - top_rgba[0]) * t),
            int(top_rgba[1] + (bottom_rgba[1] - top_rgba[1]) * t),
            int(top_rgba[2] + (bottom_rgba[2] - top_rgba[2]) * t),
            int(top_rgba[3] + (bottom_rgba[3] - top_rgba[3]) * t)
        ))
    return grad.resize((w, h), Image.NEAREST)
