# 鸣潮深境深渊 (Slash Wiki) 卡片渲染器 (PIL 版)

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
C_DESC = (204, 204, 204, 255)  # #ccc
C_CARD_BG = (20, 20, 25, 224)  # rgba(20,20,25,0.88)
C_BORDER = (255, 255, 255, 25) # rgba(255,255,255,0.1)

RE_COLOR = re.compile(r"color:\s*([^;]+)")
RE_BORDER = re.compile(r"border-color:\s*([^;]+)")
RE_BG_URL = re.compile(r"url\('([^']+)'\)")


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

F13  = _load_font(13)
F13B = _load_font(13, bold=True)
F16B = _load_font(16, bold=True)
F18  = _load_font(18)
F22B = _load_font(22, bold=True)
F26  = _load_font(26)
F28B = _load_font(28, bold=True)
F34B = _load_font(34, bold=True)
F72B = _load_font(72, bold=True)

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1

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

def _truncate_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    if font.getlength(text) <= max_w:
        return text
    for i in range(len(text) - 1, 0, -1):
        if font.getlength(text[:i] + "...") <= max_w:
            return text[:i] + "..."
    return "..."

def parse_color(c_str: str, default=(111, 181, 255, 255)) -> tuple:
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


# HTML 解析

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    
    style_text = soup.select_one("style").string if soup.select_one("style") else ""
    bg_m = RE_BG_URL.search(style_text)
    bg_url = bg_m.group(1) if bg_m else ""
    
    col_m = re.search(r"--main-color:\s*([^;]+);", style_text)
    main_color = parse_color(col_m.group(1), (111, 181, 255, 255)) if col_m else (111, 181, 255, 255)
    
    title = soup.select_one(".title").get_text(strip=True) if soup.select_one(".title") else ""
    subtitle = soup.select_one(".subtitle").get_text(strip=True) if soup.select_one(".subtitle") else ""
    footer_src = soup.select_one(".footer img").get("src") if soup.select_one(".footer img") else ""

    # Parse Global Buffs
    global_desc = []
    global_buffs = []
    gb_card = soup.select_one(".global-buffs")
    if gb_card:
        for block in gb_card.select(".section-block"):
            bt = block.select_one(".block-title").get_text(strip=True)
            if "海域特性" in bt:
                global_desc = [t.get_text(strip=True) for t in block.select(".buff-text")]
            elif "本期信物" in bt:
                for bi in block.select(".buff-item"):
                    global_buffs.append({
                        "name": bi.select_one(".buff-name").get_text(strip=True),
                        "desc": bi.select_one(".buff-desc").get_text(strip=True)
                    })

    # Parse Floors
    floors = []
    for card in soup.select(".content > .card:not(.global-buffs)"):
        f_name = card.select_one(".card-title").get_text(strip=True) if card.select_one(".card-title") else ""
        meta_el = card.select_one(".card-meta")
        f_cost = meta_el.get_text(strip=True).replace("消耗疲劳:", "").strip() if meta_el else ""
        
        f_desc = []
        f_buffs = []
        f_monsters = []
        
        for block in card.select(".section-block"):
            bt_el = block.select_one(".block-title")
            if not bt_el: continue
            bt = bt_el.get_text(strip=True)
            
            if "区域详情" in bt:
                f_desc = [t.get_text(strip=True) for t in block.select(".buff-text")]
            elif "环境Buff" in bt:
                f_buffs = [t.get_text(strip=True) for t in block.select(".buff-text")]
            elif "敌人列表" in bt:
                for m_el in block.select(".monster-card"):
                    m_icon = m_el.select_one(".monster-icon").get("src") if m_el.select_one(".monster-icon") and m_el.select_one(".monster-icon").name == 'img' else ""
                    m_name = m_el.select_one(".monster-name").get_text(strip=True) if m_el.select_one(".monster-name") else ""
                    
                    e_el = m_el.select_one(".element-badge")
                    m_ele = e_el.get_text(strip=True).replace("抗性", "").strip() if e_el else ""
                    
                    c_str = RE_COLOR.search(e_el.get("style", "")) if e_el else None
                    m_col = parse_color(c_str.group(1), (255, 255, 255, 255)) if c_str else (255, 255, 255, 255)
                    
                    f_monsters.append({"icon": m_icon, "name": m_name, "element": m_ele, "color": m_col})
                    
        floors.append({"name": f_name, "cost": f_cost, "desc": f_desc, "buffs": f_buffs, "monsters": f_monsters})

    return {
        "bg_url": bg_url, "main_color": main_color, 
        "title": title, "subtitle": subtitle, "footer_src": footer_src,
        "global_desc": global_desc, "global_buffs": global_buffs,
        "floors": floors
    }


# 局部卡片绘制

def draw_buff_text(text: str, width: int) -> Image.Image:
    pad_x, pad_y = 14, 8
    avail_w = width - pad_x * 2 - 4 # 4px border
    lines = _wrap_text(text, F18, avail_w)
    lh = 28 # 18px * 1.6
    
    H = pad_y * 2 + len(lines) * lh
    img = Image.new("RGBA", (width, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    
    _draw_rounded_rect(img, 0, 0, width, H, 8, (255,255,255,8))
    d.rectangle([0, 0, 3, H], fill=(100, 180, 255, 102))
    
    cy = pad_y
    for l in lines:
        d.text((pad_x + 4, cy + _ty(F18, l, lh)), l, font=F18, fill=C_DESC)
        cy += lh
        
    return img

def draw_global_buff_item(buff: dict, width: int) -> Image.Image:
    pad_x, pad_y = 18, 14
    avail_w = width - pad_x * 2 - 4
    
    name_h = 22 + 6
    lines = _wrap_text(buff["desc"], F18, avail_w)
    lh = 28
    
    H = pad_y * 2 + name_h + len(lines) * lh
    img = Image.new("RGBA", (width, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    
    _draw_rounded_rect(img, 0, 0, width, H, 10, (255,255,255,8))
    d.rectangle([0, 0, 4, H], fill=(100, 180, 255, 128))
    
    cy = pad_y
    d.text((pad_x + 4, cy), buff["name"], font=F22B, fill=(168, 212, 255, 255))
    cy += name_h
    
    for l in lines:
        d.text((pad_x + 4, cy + _ty(F18, l, lh)), l, font=F18, fill=C_DESC)
        cy += lh
        
    return img

def draw_monster_slim(monster: dict, width: int) -> Image.Image:
    H = 62 # padding 8*2 + icon 46
    pad_x = 10
    
    img = Image.new("RGBA", (width, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    
    mc_rgb = monster["color"]
    border_col = (mc_rgb[0], mc_rgb[1], mc_rgb[2], 64)
    
    _draw_rounded_rect(img, 0, 0, width, H, 16, (20, 20, 30, 200), outline=border_col)
    
    ic_sz = 46
    d.ellipse([pad_x, 8, pad_x+ic_sz, 8+ic_sz], fill=(mc_rgb[0], mc_rgb[1], mc_rgb[2], 76))
    if monster["icon"]:
        try:
            ic = _b64_fit(monster["icon"], ic_sz, ic_sz)
            img.paste(ic, (pad_x, 8), _round_mask(ic_sz, ic_sz, ic_sz//2))
        except: pass
    d.ellipse([pad_x, 8, pad_x+ic_sz, 8+ic_sz], outline=mc_rgb, width=2)
    
    tx = pad_x + ic_sz + 10
    max_tw = width - tx - 10
    
    name_trunc = _truncate_text(monster["name"], F16B, max_tw)
    
    # Text vertical align
    # Name 16, Gap 2, Badge 15 -> Total 33
    # Start Y = (62 - 33) // 2 = 14
    d.text((tx, 12), name_trunc, font=F16B, fill=C_WHITE)
    
    if monster["element"]:
        d.text((tx, 32), f"{monster['element']}抗性", font=F13B, fill=mc_rgb)
        
    return img

def draw_global_card(data: dict) -> Image.Image:
    pad = 24
    cw = INNER_W
    inner_w = cw - pad * 2
    
    blocks = []
    
    if data["global_desc"]:
        blocks.append(("【海域特性】", data["main_color"], data["global_desc"], draw_buff_text))
        
    if data["global_buffs"]:
        blocks.append(("【本期信物】", data["main_color"], data["global_buffs"], draw_global_buff_item))
        
    if not blocks:
        return Image.new("RGBA", (cw, 0))

    b_imgs = []
    for title, tcol, items, draw_func in blocks:
        th = 28 + 12 # font + mb
        
        item_imgs = [draw_func(it, inner_w) for it in items]
        ih = sum(im.height for im in item_imgs) + max(0, len(item_imgs)-1) * 8
        
        bh = th + ih
        bim = Image.new("RGBA", (inner_w, bh), (0,0,0,0))
        bd = ImageDraw.Draw(bim)
        
        bd.text((0,0), title, font=F28B, fill=tcol)
        cy = th
        for im in item_imgs:
            bim.alpha_composite(im, (0, cy))
            cy += im.height + 8
            
        b_imgs.append(bim)

    H = pad * 2 + sum(im.height for im in b_imgs) + max(0, len(b_imgs)-1) * 24
    
    img = Image.new("RGBA", (cw, H), (0,0,0,0))
    _draw_rounded_rect(img, 0, 0, cw, H, 16, C_CARD_BG, outline=C_BORDER)
    
    cy = pad
    for bim in b_imgs:
        img.alpha_composite(bim, (pad, cy))
        cy += bim.height + 24
        
    return img

def draw_floor_card(floor: dict, main_color: tuple) -> Image.Image:
    pad = 24
    cw = INNER_W
    inner_w = cw - pad * 2
    
    # 1. Header
    hdr_h = 34 + 12 + 8 # font + pb + mb
    
    # 2. Blocks
    blocks = []
    if floor["desc"]:
        blocks.append(("【区域详情】", main_color, floor["desc"], draw_buff_text, 1))
    if floor["buffs"]:
        blocks.append(("【环境Buff】", main_color, floor["buffs"], draw_buff_text, 1))
    if floor["monsters"]:
        blocks.append(("【敌人列表】", (255, 118, 118, 255), floor["monsters"], draw_monster_slim, 4))
        
    b_imgs = []
    for title, tcol, items, draw_func, cols in blocks:
        th = 28 + 12
        
        if cols == 1:
            item_imgs = [draw_func(it, inner_w) for it in items]
            ih = sum(im.height for im in item_imgs) + max(0, len(item_imgs)-1) * 8
            
            bh = th + ih
            bim = Image.new("RGBA", (inner_w, bh), (0,0,0,0))
            bd = ImageDraw.Draw(bim)
            bd.text((0,0), title, font=F28B, fill=tcol)
            cy = th
            for im in item_imgs:
                bim.alpha_composite(im, (0, cy))
                cy += im.height + 8
            b_imgs.append(bim)
            
        elif cols == 4:
            gap = 12
            mw = (inner_w - gap * 3) // 4
            item_imgs = [draw_func(it, mw) for it in items]
            
            rows = math.ceil(len(item_imgs) / 4)
            ih = rows * 62 + max(0, rows - 1) * gap
            
            bh = th + ih
            bim = Image.new("RGBA", (inner_w, bh), (0,0,0,0))
            bd = ImageDraw.Draw(bim)
            bd.text((0,0), title, font=F28B, fill=tcol)
            
            for i, im in enumerate(item_imgs):
                r, c = divmod(i, 4)
                bim.alpha_composite(im, (c * (mw + gap), th + r * (62 + gap)))
            b_imgs.append(bim)

    H = pad * 2 + hdr_h + sum(im.height for im in b_imgs) + max(0, len(b_imgs)-1) * 24
    
    img = Image.new("RGBA", (cw, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    _draw_rounded_rect(img, 0, 0, cw, H, 16, C_CARD_BG, outline=C_BORDER)
    
    # Header Draw
    d.text((pad, pad), floor["name"], font=F34B, fill=main_color)
    d.line([(pad, pad + 34 + 12), (cw - pad, pad + 34 + 12)], fill=(255,255,255,20), width=2)
    
    if floor["cost"]:
        c_txt = f"消耗疲劳: {floor['cost']}"
        cw_meta = int(F22B.getlength(c_txt)) + 24
        _draw_rounded_rect(img, cw - pad - cw_meta, pad + 4, cw - pad, pad + 34, 6, (255,255,255,25))
        d.text((cw - pad - cw_meta + 12, pad + 4 + _ty(F22B, c_txt, 30)), c_txt, font=F22B, fill=(187,187,187,255))
        
    cy = pad + hdr_h
    for bim in b_imgs:
        img.alpha_composite(bim, (pad, cy))
        cy += bim.height + 24
        
    return img


# 主流程

def render(html: str) -> bytes:
    data = parse_html(html)
    
    # 1. Header
    tw = int(F72B.getlength(data["title"]))
    hdr_h = 100 if not data["subtitle"] else 140
    h_img = Image.new("RGBA", (INNER_W, hdr_h), (0,0,0,0))
    hd = ImageDraw.Draw(h_img)
    
    hd.text(((INNER_W - tw)//2, 0), data["title"], font=F72B, fill=C_WHITE)
    if data["subtitle"]:
        sw = int(F26.getlength(data["subtitle"]))
        _draw_rounded_rect(h_img, (INNER_W - sw - 56)//2, 85, (INNER_W + sw + 56)//2, 85 + 46, 23, (0,0,0,128), outline=(255,255,255,38))
        hd.text(((INNER_W - sw)//2, 85 + _ty(F26, data["subtitle"], 46)), data["subtitle"], font=F26, fill=(204,204,204,255))

    # 2. Content Cards
    c_imgs = []
    
    gb_card = draw_global_card(data)
    if gb_card.height > 0:
        c_imgs.append(gb_card)
        
    for f in data["floors"]:
        c_imgs.append(draw_floor_card(f, data["main_color"]))
        
    # 3. Footer
    FOOTER_H = 0
    f_img = None
    if data["footer_src"]:
        try:
            raw_f = _b64_img(data["footer_src"])
            scale = 24 / raw_f.height
            fw = int(raw_f.width * scale)
            FOOTER_H = 24
            f_img = raw_f.resize((fw, FOOTER_H), Image.LANCZOS)
        except: pass

    # Assemble
    gap = 25
    total_h = PAD + hdr_h + gap
    total_h += sum(im.height for im in c_imgs) + max(0, len(c_imgs) - 1) * gap
    if f_img:
        total_h += 12 + FOOTER_H
    total_h += PAD
    
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    
    if data["bg_url"]:
        try:
            bg_base = _b64_img(data["bg_url"])
            bg_base = ImageOps.fit(bg_base, (W, total_h), Image.Resampling.LANCZOS)
            canvas.alpha_composite(bg_base)
            
            # Complex Overlay
            td_overlay = _get_v_gradient(W, total_h, (15, 15, 19, 102), (15, 15, 19, 242))
            lr_overlay = _get_h_gradient(W, total_h, (78, 124, 255, 38), (78, 124, 255, 0))
            canvas.alpha_composite(td_overlay)
            canvas.alpha_composite(lr_overlay)
        except: pass

    cy = PAD
    canvas.alpha_composite(h_img, (PAD, cy))
    cy += hdr_h + gap
    
    for cim in c_imgs:
        canvas.alpha_composite(cim, (PAD, cy))
        cy += cim.height + gap
        
    if f_img:
        f_alpha = f_img.copy()
        f_alpha.putalpha(f_alpha.getchannel("A").point(lambda a: int(a * 0.6)))
        canvas.alpha_composite(f_alpha, ((W - f_img.width)//2, cy - gap + 12))

    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
