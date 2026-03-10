# 鸣潮物品图鉴 (Item Wiki) 卡片渲染器 (PIL 版)

from __future__ import annotations

import base64
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps


# 常量定义

W = 1500
PAD_X = 60
PAD_Y = 50
COL_GAP = 40
LEFT_W = 380
RIGHT_W = W - PAD_X * 2 - COL_GAP - LEFT_W  # 1000

C_BG = (15, 15, 19, 255)
C_WHITE = (255, 255, 255, 255)
C_DESC = (217, 217, 217, 255)  # rgba(255,255,255,0.85)
C_CARD_BG = (20, 20, 25, 166)  # rgba(20,20,25,0.65)
C_BORDER = (255, 255, 255, 38) # rgba(255,255,255,0.15)
C_TEXT_SUB = (160, 160, 160, 255)


# 使用包级统一字体对象（从包里导入以复用同一实例）
from . import F16, F18, F18B, F20B, F22, F22B, F36B, F72B
from . import M16, M18, M20, M22, M36, M72
from . import draw_text_mixed, _b64_img, _b64_fit, _round_mask

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1

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

def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
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


# 图像加载/缓存由包级统一实现（避免 data: URI 被本地缓存）

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, 
                       r: int, fill: tuple, outline=None, width=1) -> None:
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(block, (x0, y0))

def _paste_rounded(canvas: Image.Image, img: Image.Image, x: int, y: int, r: int):
    w, h = img.size
    canvas.paste(img, (x, y), _round_mask(w, h, r))


def _get_h_gradient(w: int, h: int, left_rgba: tuple, right_rgba: tuple) -> Image.Image:
    # Return an RGBA Image with a horizontal gradient from left_rgba to right_rgba
    grad = Image.new("RGBA", (w, 1))
    if w <= 0:
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
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
    if h <= 0:
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
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
    bg_m = re.search(r"background-image:\s*url\('([^']+)'\)", style_text)
    bg_url = bg_m.group(1) if bg_m else ""
    
    col_m = re.search(r"--main-color:\s*([^;]+);", style_text)
    main_color = parse_color(col_m.group(1), (111, 181, 255, 255)) if col_m else (111, 181, 255, 255)

    # Detect Type (Weapon or Echo)
    item_type = "echo"
    if soup.select_one(".type-tag"):
        item_type = "weapon"

    # Left Col
    icon_src = soup.select_one(".item-icon").get("src") if soup.select_one(".item-icon") else ""
    
    stats = []
    for st in soup.select(".stat-item"):
        lb = st.select_one(".stat-label").get_text(strip=True) if st.select_one(".stat-label") else ""
        vl = st.select_one(".stat-value").get_text(strip=True) if st.select_one(".stat-value") else ""
        stats.append((lb, vl))
        
    stats_title = "满级属性" if item_type == "weapon" else "声骸属性"

    # Right Col Header
    name = soup.select_one(".item-name").get_text(strip=True) if soup.select_one(".item-name") else ""
    rarity_icon = soup.select_one(".rarity-icon").get("src") if soup.select_one(".rarity-icon") else ""
    
    type_icon = soup.select_one(".type-icon").get("src") if soup.select_one(".type-icon") else ""
    type_name = soup.select_one(".type-name").get_text(strip=True) if soup.select_one(".type-name") else ""
    
    group_icons = []
    for g in soup.select(".group-tag"):
        gi = g.select_one(".group-icon").get("src") if g.select_one(".group-icon") else ""
        gn = g.select_one(".group-name").get_text(strip=True) if g.select_one(".group-name") else ""
        group_icons.append({"icon": gi, "name": gn})
        
    mats = [img.get("src") for img in soup.select(".material-item img") if img.get("src", "").startswith("data:")]

    # Right Col Detail
    effect_name = soup.select_one(".effect-name").get_text(strip=True) if soup.select_one(".effect-name") else ""
    
    desc_el = soup.select_one(".effect-desc")
    # To handle <strong> we will just do a simple text extraction for now, 
    # but since this wiki might have long text, we'll just extract raw string 
    # and strip out HTML tags for simplicity, or keep bold logic if needed.
    # For item description, usually pure text or slight bolding. We'll extract pure text and preserve \n
    effect_desc = desc_el.get_text(separator="\n", strip=True) if desc_el else ""
    
    footer = soup.select_one(".footer img").get("src") if soup.select_one(".footer img") else ""

    return {
        "bg_url": bg_url, "main_color": main_color, "item_type": item_type,
        "icon": icon_src, "stats_title": stats_title, "stats": stats,
        "name": name, "rarity_icon": rarity_icon,
        "type_icon": type_icon, "type_name": type_name,
        "group_icons": group_icons, "mats": mats,
        "effect_name": effect_name, "effect_desc": effect_desc,
        "footer": footer
    }


# 组件生成

def draw_left_col(data: dict, force_height: int = 0) -> Image.Image:
    # Icon Card (Square 380x380)
    ic_w = LEFT_W
    ic_h = LEFT_W
    
    # Stats Card height calc
    pad = 20
    sh = pad * 2 + 20 + 16 # padding + title(20) + mb(16)
    if data["stats"]:
        sh += len(data["stats"]) * 36 + max(0, len(data["stats"])-1) * 8 # item_h(36) + gap(8)
    else:
        sh = 0

    col_h = ic_h + 24 + sh
    
    # If force height is provided, we need to push stats card to bottom
    final_h = max(col_h, force_height) if force_height else col_h
    
    img = Image.new("RGBA", (LEFT_W, final_h), (0,0,0,0))
    d = ImageDraw.Draw(img)
    
    # 1. Icon Card
    ic_card = Image.new("RGBA", (ic_w, ic_h), (0,0,0,0))
    ic_d = ImageDraw.Draw(ic_card)
    _draw_rounded_rect(ic_card, 0, 0, ic_w, ic_h, 12, (255,255,255,8), outline=C_BORDER)
    
    if data["icon"]:
        try:
            # 90% size = 342
            ic = _b64_fit(data["icon"], int(ic_w * 0.9), int(ic_h * 0.9))
            ic_card.paste(ic, (int(ic_w * 0.05), int(ic_h * 0.05)), ic)
        except: pass
        
    # Corners
    mc = data["main_color"]
    mc_alpha = (mc[0], mc[1], mc[2], int(255 * 0.7))
    ic_d.line([(10, 10), (20, 10)], fill=mc_alpha, width=2)
    ic_d.line([(10, 10), (10, 20)], fill=mc_alpha, width=2)
    
    ic_d.line([(ic_w-10, ic_h-10), (ic_w-20, ic_h-10)], fill=mc_alpha, width=2)
    ic_d.line([(ic_w-10, ic_h-10), (ic_w-10, ic_h-20)], fill=mc_alpha, width=2)
    
    img.alpha_composite(ic_card, (0, 0))
    
    # 2. Stats Card (bottom aligned)
    if data["stats"]:
        st_y = final_h - sh
        _draw_rounded_rect(img, 0, st_y, LEFT_W, final_h, 12, C_CARD_BG, outline=C_BORDER)
        d.rectangle([0, st_y, 4, final_h], fill=data["main_color"])
        
        # Title
        draw_text_mixed(d, (24, st_y + pad), data["stats_title"], cn_font=F20B, en_font=M20, fill=(230,230,230,255))
        
        # Title line
        tw = int(F20B.getlength(data["stats_title"]))
        lx = 24 + tw + 10
        img.alpha_composite(_get_h_gradient(LEFT_W - 24 - lx, 1, (255,255,255,51), (255,255,255,0)), (lx, st_y + pad + 10))
        
        cy = st_y + pad + 20 + 16
        for lb, vl in data["stats"]:
            draw_text_mixed(d, (24 + 4, cy + _ty(F18, lb, 36)), lb, cn_font=F18, en_font=M18, fill=C_TEXT_SUB)
            vw = int(F20B.getlength(vl))
            draw_text_mixed(d, (LEFT_W - 24 - 4 - vw, cy + _ty(F20B, vl, 36)), vl, cn_font=F20B, en_font=M20, fill=C_WHITE)
            
            d.line([(24, cy + 36), (LEFT_W - 24, cy + 36)], fill=(255,255,255,13), width=1)
            cy += 36 + 8

    return img

def draw_right_col(data: dict) -> tuple[Image.Image, int]:
    # We will build it block by block to measure total height
    blocks = []
    
    # 1. Header Top (Title & Tags & Mats)
    # Estimate Header Left Height
    hl_h = 72 + 16 + 44 # name(72) + gap(16) + rarity(44)
    
    # Estimate Mats Height
    mats_h = 0
    mats_w = 0
    if data["mats"]:
        m_rows = math.ceil(len(data["mats"]) / 4) # assume max 4 cols
        mats_h = 18 * 2 + 18 + 12 + m_rows * 72 + max(0, m_rows-1)*12 # pad + title + mb + icons
        mats_w = 20 * 2 + min(len(data["mats"]), 4) * 72 + max(0, min(len(data["mats"]), 4)-1)*12
        
    top_h = max(hl_h, mats_h)
    
    top_img = Image.new("RGBA", (RIGHT_W, top_h), (0,0,0,0))
    d_top = ImageDraw.Draw(top_img)
    
    # Draw Title
    draw_text_mixed(d_top, (0, 0), data["name"], cn_font=F72B, en_font=M72, fill=C_WHITE)
    
    # Draw Tags
    rx = 0
    ry = 72 + 16
    if data["rarity_icon"]:
        try:
            ri = _b64_fit(data["rarity_icon"], 180, 44)
            top_img.paste(ri, (rx, ry), ri)
            rx += 180 + 20
        except: pass
        
    if data["item_type"] == "weapon" and data["type_icon"]:
        tw = int(F22B.getlength(data["type_name"]))
        w_tag = 18*2 + 36 + 8 + tw
        _draw_rounded_rect(top_img, rx, ry, rx + w_tag, ry + 52, 6, (111,181,255,13), outline=(111,181,255,102))
        try:
            ti = _b64_fit(data["type_icon"], 36, 36)
            # pseudo invert
            ti_inv = ImageOps.invert(ti.convert("RGB")).convert("RGBA")
            ti_inv.putalpha(ti.split()[3])
            top_img.paste(ti_inv, (rx + 18, ry + 8), ti_inv)
        except: pass
        draw_text_mixed(d_top, (rx + 18 + 36 + 8, ry + _ty(F22B, data["type_name"], 52)), data["type_name"], cn_font=F22B, en_font=M22, fill=(230,230,230,255))
        
    if data["item_type"] == "echo" and data["group_icons"]:
        for gr in data["group_icons"]:
            gw = int(F20B.getlength(gr["name"]))
            w_tag = 18*2 + 32 + 8 + gw
            _draw_rounded_rect(top_img, rx, ry, rx + w_tag, ry + 48, 6, (255,255,255,20), outline=C_BORDER)
            if gr["icon"]:
                try:
                    gi = _b64_fit(gr["icon"], 32, 32)
                    top_img.paste(gi, (rx + 18, ry + 8), gi)
                except: pass
            draw_text_mixed(d_top, (rx + 18 + 32 + 8, ry + _ty(F20B, gr["name"], 48)), gr["name"], cn_font=F20B, en_font=M20, fill=(230,230,230,255))
            rx += w_tag + 10

    # Draw Mats (Right aligned)
    if data["mats"]:
        mx = RIGHT_W - mats_w
        _draw_rounded_rect(top_img, mx, 0, RIGHT_W, mats_h, 12, (0,0,0,76), outline=C_BORDER)
        
        tw = int(F18B.getlength("突破材料"))
        draw_text_mixed(d_top, (RIGHT_W - 20 - tw, 18), "突破材料", cn_font=F18B, en_font=M18, fill=C_TEXT_SUB)
        
        my = 18 + 18 + 12
        cx = RIGHT_W - 20 - (min(len(data["mats"]), 4) * 72 + max(0, min(len(data["mats"]), 4)-1)*12)
        
        for i, m_src in enumerate(data["mats"]):
            r, c = divmod(i, 4)
            px = cx + c * (72 + 12)
            py = my + r * (72 + 12)
            
            _draw_rounded_rect(top_img, px, py, px + 72, py + 72, 10, (255,255,255,13), outline=(255,255,255,25))
            try:
                mi = _b64_fit(m_src, 72, 72)
                _paste_rounded(top_img, mi, px, py, 10)
            except: pass

    # Divider below header
    d_top.line([(0, top_h - 1), (RIGHT_W, top_h - 1)], fill=(255,255,255,25), width=1)
    
    # 2. Detail Card
    det_h = 0
    det_img = None
    
    pad = 32
    lines = []
    if data["effect_desc"]:
        lines = _wrap_text(data["effect_desc"], F22, RIGHT_W - pad * 2)
        
    if lines:
        det_h = pad * 2
        title_txt = "武器效果" if data["item_type"] == "weapon" else "技能描述"
        det_h += 16 + 10 # small title + mb
        if data["effect_name"]:
            det_h += 36 + 20 # effect name + mb
            
        # Lines
        LH = 40 # line height 1.8 of 22px
        det_h += len(lines) * LH
        
        det_img = Image.new("RGBA", (RIGHT_W, det_h), (0,0,0,0))
        dd = ImageDraw.Draw(det_img)
        
        _draw_rounded_rect(det_img, 0, 0, RIGHT_W, det_h, 12, C_CARD_BG, outline=C_BORDER)
        
        dy = pad
        draw_text_mixed(dd, (pad, dy), title_txt, cn_font=F16, en_font=M16, fill=(170,170,170,255))
        dy += 16 + 10
        
        if data["effect_name"]:
            # Fake golden gradient text
            draw_text_mixed(dd, (pad, dy), data["effect_name"], cn_font=F36B, en_font=M36, fill=(255, 236, 179, 255))
            dy += 36 + 20
            
        for l in lines:
            draw_text_mixed(dd, (pad, dy + _ty(F22, l, LH)), l, cn_font=F22, en_font=M22, fill=C_DESC)
            dy += LH

    total_h = top_h + 24 + (det_h if det_img else 0)
    
    # Combine Right Col
    out = Image.new("RGBA", (RIGHT_W, total_h), (0,0,0,0))
    out.alpha_composite(top_img, (0, 0))
    if det_img:
        # Align bottom if needed, but flex column will stack them
        out.alpha_composite(det_img, (0, top_h + 24))
        
    return out, total_h


# 主流程

def render(html: str) -> bytes:
    data = parse_html(html)
    
    # Render Right Col first to know the max height
    r_col_img, r_col_h = draw_right_col(data)
    
    # Left Col must stretch to match Right Col's height
    l_col_img = draw_left_col(data, force_height=r_col_h)
    
    content_h = max(l_col_img.height, r_col_h)
    
    FOOTER_H = 0
    f_img = None
    if data["footer"]:
        try:
            raw_f = _b64_img(data["footer"])
            scale = 18 / raw_f.height
            fw = int(raw_f.width * scale)
            FOOTER_H = 18
            f_img = raw_f.resize((fw, FOOTER_H), Image.LANCZOS)
        except: pass

    # Assemble
    total_h = PAD_Y * 2 + content_h
    if f_img:
        total_h += 15 + FOOTER_H # approx padding
        
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    
    if data["bg_url"]:
        try:
            bg_base = _b64_img(data["bg_url"])
            bg_base = ImageOps.fit(bg_base, (W, total_h), Image.Resampling.LANCZOS)
            canvas.alpha_composite(bg_base)
            
            # Overlay (Radial + Linear)
            rad_overlay = Image.new("RGBA", (W, total_h), (15, 15, 19, 153)) # simplified radial
            lr_overlay = _get_h_gradient(W, total_h, (15, 15, 19, 204), (15, 15, 19, 51))
            canvas.alpha_composite(rad_overlay)
            canvas.alpha_composite(lr_overlay)
        except: pass

    # Paste Columns
    canvas.alpha_composite(l_col_img, (PAD_X, PAD_Y))
    canvas.alpha_composite(r_col_img, (PAD_X + LEFT_W + COL_GAP, PAD_Y))

    # Footer
    if f_img:
        f_alpha = f_img.copy()
        f_alpha.putalpha(f_alpha.getchannel("A").point(lambda a: int(a * 0.6)))
        # invert to white
        f_inv = ImageOps.invert(f_alpha.convert("RGB")).convert("RGBA")
        f_inv.putalpha(f_alpha.split()[3])
        canvas.alpha_composite(f_inv, ((W - f_inv.width)//2, total_h - FOOTER_H - 15))

    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
