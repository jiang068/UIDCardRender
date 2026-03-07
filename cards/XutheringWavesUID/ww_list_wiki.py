# 鸣潮列表图鉴 (List Wiki) 卡片渲染器 (PIL 版)

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

W = 1320
PAD = 32
INNER_W = W - PAD * 2   # 1256

C_BG = (15, 15, 19, 255)
C_WHITE = (255, 255, 255, 255)
C_MAIN = (111, 181, 255, 255) # #6fb5ff
C_BORDER = (255, 255, 255, 25) # rgba(255, 255, 255, 0.1) 边框颜色

# 星级进度条颜色
STAR_COLORS = {
    5: ((255, 215, 0), (255, 170, 0)),
    4: ((200, 130, 255), (153, 68, 204)),
    3: ((111, 181, 255), (68, 136, 204)),
    2: ((136, 204, 136), (85, 170, 85)),
    1: ((170, 170, 170), (136, 136, 136)),
}


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

F12  = _load_font(12)
F14B = _load_font(14, bold=True)
F17  = _load_font(17)
F18B = _load_font(18, bold=True)
F24B = _load_font(24, bold=True)
F28B = _load_font(28, bold=True)
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


# 图像缓存与工具

@lru_cache(maxsize=128)
def _b64_img(src: str) -> Image.Image:
    if "," in src: src = src.split(",", 1)[1]
    return Image.open(BytesIO(base64.b64decode(src))).convert("RGBA")

@lru_cache(maxsize=128)
def _b64_fit(src: str, w: int, h: int) -> Image.Image:
    return ImageOps.fit(_b64_img(src), (w, h), Image.Resampling.LANCZOS)

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
    
    bg_url = soup.select_one(".container").get("style", "")
    bg_m = re.search(r"background-image:\s*url\('([^']+)'\)", bg_url)
    bg_src = bg_m.group(1) if bg_m else ""
    
    title = soup.select_one(".title").get_text(strip=True) if soup.select_one(".title") else ""
    footer_src = soup.select_one(".footer img").get("src") if soup.select_one(".footer img") else ""
    
    list_type = "weapon" if soup.select_one(".weapon-types-row") else "sonata"
    single_type = "single-type" in (soup.select_one(".weapon-types-row").get("class", []) if soup.select_one(".weapon-types-row") else [])

    groups = []
    if list_type == "weapon":
        for g_el in soup.select(".weapon-type-group"):
            g_title = g_el.select_one(".group-title").get_text(strip=True) if g_el.select_one(".group-title") else ""
            weapons = []
            for w_el in g_el.select(".weapon-card"):
                w_icon = w_el.select_one(".weapon-icon").get("src") if w_el.select_one(".weapon-icon") else ""
                w_name = w_el.select_one(".weapon-name").get_text(strip=True) if w_el.select_one(".weapon-name") else ""
                w_eff = w_el.select_one(".weapon-effect").get_text(strip=True) if w_el.select_one(".weapon-effect") else ""
                
                star_class = w_el.select_one(".star-overlay").get("class", []) if w_el.select_one(".star-overlay") else []
                star = 3
                for sc in star_class:
                    # 排除掉 star-overlay 本身，并确保后面跟着的是数字
                    if sc.startswith("star-") and sc != "star-overlay":
                        try:
                            star = int(sc.split("-")[1])
                            break
                        except ValueError:
                            pass
                weapons.append({"name": w_name, "effect": w_eff, "icon": w_icon, "star": star})
            groups.append({"title": g_title, "weapons": weapons})
            
    elif list_type == "sonata":
        for g_el in soup.select(".group"):
            g_ver = g_el.select_one(".group-title").get_text(strip=True).replace("版本", "").strip() if g_el.select_one(".group-title") else ""
            sonatas = []
            for s_el in g_el.select(".sonata-card"):
                s_icon = s_el.select_one(".sonata-icon").get("src") if s_el.select_one(".sonata-icon") else ""
                s_name = s_el.select_one(".sonata-name").get_text(strip=True) if s_el.select_one(".sonata-name") else ""
                effects = []
                for e_el in s_el.select(".sonata-effect"):
                    e_cnt = e_el.select_one(".effect-count").get_text(strip=True) if e_el.select_one(".effect-count") else ""
                    e_desc = e_el.select_one(".effect-desc").get_text(strip=True) if e_el.select_one(".effect-desc") else ""
                    effects.append({"count": e_cnt, "desc": e_desc})
                sonatas.append({"name": s_name, "icon": s_icon, "effects": effects})
            groups.append({"version": g_ver, "sonatas": sonatas})

    return {
        "bg_src": bg_src, "title": title, "footer_src": footer_src,
        "list_type": list_type, "single_type": single_type, "groups": groups
    }


# 组件渲染

def draw_weapon_card(w_data: dict, width: int) -> Image.Image:
    pad_x = 4
    pad_y = 8
    H = 135
    
    img = Image.new("RGBA", (width, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    
    _draw_rounded_rect(img, 0, 0, width, H, 12, (20,20,30,166), outline=(255,255,255,25))
    
    # Icon Wrapper (78x78)
    ic_w, ic_h = 78, 78
    ic_x = (width - ic_w) // 2
    ic_y = pad_y
    
    if w_data["icon"]:
        try:
            ic = _b64_fit(w_data["icon"], 72, 72)
            img.paste(ic, (ic_x + 3, ic_y + 3), ic)
        except: pass
        
    # Star overlay
    star = w_data["star"]
    c1, c2 = STAR_COLORS.get(star, STAR_COLORS[3])
    img.alpha_composite(_get_h_gradient(ic_w, 4, (*c1, 255), (*c2, 255)), (ic_x, ic_y + ic_h - 4))
    
    # Text
    ty = ic_y + ic_h + 6
    n_trunc = _truncate_text(w_data["name"], F14B, width - 8)
    tw = int(F14B.getlength(n_trunc))
    d.text(((width - tw)//2, ty), n_trunc, font=F14B, fill=C_WHITE)
    
    ty += 20
    e_trunc = _truncate_text(w_data["effect"], F12, width - 8)
    ew = int(F12.getlength(e_trunc))
    d.text(((width - ew)//2, ty), e_trunc, font=F12, fill=(170,170,170,255))
    
    return img

def render_weapon_view(data: dict) -> Image.Image:
    single_type = data["single_type"]
    groups = data["groups"]
    
    if single_type:
        group = groups[0]
        # Grid 5 cols
        cols = 5
        gap = 10
        w_w = (INNER_W - gap * (cols - 1)) // cols
        
        w_imgs = [draw_weapon_card(w, w_w) for w in group["weapons"]]
        rows = math.ceil(len(w_imgs) / cols)
        
        H = rows * 135 + max(0, rows - 1) * gap
        out = Image.new("RGBA", (INNER_W, H), (0,0,0,0))
        
        for i, wi in enumerate(w_imgs):
            r, c = divmod(i, cols)
            out.alpha_composite(wi, (c * (w_w + gap), r * (135 + gap)))
            
        return out
    
    else:
        # Grid 5 columns of GROUPS
        cols = 5
        grp_gap = 8
        grp_w = (INNER_W - grp_gap * (cols - 1)) // cols
        
        # Pre-calc each group height
        grp_imgs = []
        max_h = 0
        for g in groups:
            # inner weapons grid is 2 cols
            i_gap = 6
            i_cols = 2
            iw = (grp_w - 16 - i_gap) // i_cols # pad 8*2 = 16
            
            w_imgs = [draw_weapon_card(w, iw) for w in g["weapons"]]
            i_rows = math.ceil(len(w_imgs) / i_cols)
            
            g_h = 8*2 + 24 + 8 + i_rows * 135 + max(0, i_rows - 1) * i_gap # pad + title(24) + mb(8)
            max_h = max(max_h, g_h)
            
            grp_imgs.append((g, w_imgs, iw, i_gap))
            
        # Draw equal height groups
        out = Image.new("RGBA", (INNER_W, max_h), (0,0,0,0))
        d = ImageDraw.Draw(out)
        
        cx = 0
        for g, w_imgs, iw, i_gap in grp_imgs:
            # Draw bg
            _draw_rounded_rect(out, cx, 0, cx + grp_w, max_h, 16, (255,255,255,8), outline=(255,255,255,25))
            
            # Title
            d.rectangle([cx + 10, 8, cx + 14, 8 + 24], fill=C_MAIN)
            d.text((cx + 20, 8), g["title"], font=F24B, fill=C_MAIN)
            
            # Weapons (Align to top after title)
            cy = 8 + 24 + 8
            for i, wi in enumerate(w_imgs):
                r, c = divmod(i, 2)
                out.alpha_composite(wi, (cx + 8 + c * (iw + i_gap), cy + r * (135 + i_gap)))
                
            cx += grp_w + grp_gap
            
        return out

def draw_sonata_card(s_data: dict, width: int) -> tuple[Image.Image, int]:
    pad = 16
    avail_w = width - pad * 2
    
    # Calc dynamic height based on text wrap
    eff_h = 0
    eff_lines = []
    
    count_w = int(F18B.getlength("5件:")) + 8
    desc_w = avail_w - count_w
    
    for e in s_data["effects"]:
        lines = _wrap_text(e["desc"], F17, desc_w)
        eff_lines.append((e["count"], lines))
        eff_h += len(lines) * 24 + 6 # line-height ~24, mb 6
        
    hdr_h = 56 # icon
    
    H = pad * 2 + hdr_h + 12 + eff_h # 12 gap
    
    img = Image.new("RGBA", (width, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    _draw_rounded_rect(img, 0, 0, width, H, 16, (20,20,30,166), outline=(255,255,255,25))
    
    # Header centered
    nw = int(F28B.getlength(s_data["name"]))
    total_hdr_w = 56 + 12 + nw
    hx = (width - total_hdr_w) // 2
    
    if s_data["icon"]:
        try:
            ic = _b64_fit(s_data["icon"], 56, 56)
            img.paste(ic, (hx, pad), ic)
        except: pass
        
    d.text((hx + 56 + 12, pad + _ty(F28B, s_data["name"], 56)), s_data["name"], font=F28B, fill=C_MAIN)
    
    # Effects
    ey = pad + hdr_h + 12
    for count, lines in eff_lines:
        d.text((pad, ey), count, font=F18B, fill=(255,213,79,255))
        cy = ey
        for l in lines:
            d.text((pad + count_w, cy), l, font=F17, fill=(221,221,221,255))
            cy += 24
        ey += len(lines) * 24 + 6
        
    return img, H

def render_sonata_view(data: dict) -> Image.Image:
    groups = data["groups"]
    
    out_imgs = []
    
    for g in groups:
        # Group Header
        h_img = Image.new("RGBA", (INNER_W, 40), (0,0,0,0))
        hd = ImageDraw.Draw(h_img)
        title = f"{g['version']} 版本"
        hd.text((25, 0), title, font=F24B, fill=C_MAIN)
        hd.rectangle([10, 4, 14, 28], fill=C_MAIN)
        
        # Sonata Grid (3 cols)
        cols = 3
        gap = 18
        s_w = (INNER_W - 50 - gap * (cols - 1)) // cols # pad 25*2
        
        # Pre-calc to find row max heights
        s_cards = [draw_sonata_card(s, s_w) for s in g["sonatas"]]
        
        grid_rows = math.ceil(len(s_cards) / cols)
        row_heights = []
        for r in range(grid_rows):
            mh = max(c[1] for c in s_cards[r*cols : (r+1)*cols])
            row_heights.append(mh)
            
        g_grid_h = sum(row_heights) + max(0, grid_rows - 1) * gap
        
        g_h = 25*2 + 40 + 8 + g_grid_h # pad + title + mb + grid
        
        g_img = Image.new("RGBA", (INNER_W, g_h), (0,0,0,0))
        _draw_rounded_rect(g_img, 0, 0, INNER_W, g_h, 20, (20,20,25,224), outline=C_BORDER)
        
        g_img.alpha_composite(h_img, (0, 25))
        
        cy = 25 + 40 + 8
        for i, (card_img, raw_h) in enumerate(s_cards):
            r, c = divmod(i, cols)
            r_max = row_heights[r]
            
            # Re-draw card to stretch to max height
            final_card = Image.new("RGBA", (s_w, r_max), (0,0,0,0))
            _draw_rounded_rect(final_card, 0, 0, s_w, r_max, 16, (20,20,30,166), outline=(255,255,255,25))
            final_card.alpha_composite(card_img, (0,0))
            
            g_img.alpha_composite(final_card, (25 + c * (s_w + gap), cy))
            
            if (i + 1) % cols == 0 or (i + 1) == len(s_cards):
                cy += r_max + gap
                
        out_imgs.append(g_img)

    total_h = sum(im.height for im in out_imgs) + max(0, len(out_imgs) - 1) * 22
    out = Image.new("RGBA", (INNER_W, total_h), (0,0,0,0))
    y = 0
    for im in out_imgs:
        out.alpha_composite(im, (0, y))
        y += im.height + 22
        
    return out


# 主流程

def render(html: str) -> bytes:
    data = parse_html(html)
    
    # 1. Header
    tw = int(F72B.getlength(data["title"]))
    hdr_h = 90
    
    # 2. Content
    if data["list_type"] == "weapon":
        content_img = render_weapon_view(data)
    else:
        content_img = render_sonata_view(data)
        
    # 3. Footer
    FOOTER_H = 0
    f_img = None
    if data["footer_src"]:
        try:
            raw_f = _b64_img(data["footer_src"])
            scale = 20 / raw_f.height
            fw = int(raw_f.width * scale)
            FOOTER_H = 20
            f_img = raw_f.resize((fw, FOOTER_H), Image.LANCZOS)
        except: pass

    # Assemble
    total_h = PAD + hdr_h + content_img.height + (10 + FOOTER_H if f_img else 0) + PAD
    
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    
    if data["bg_src"]:
        try:
            bg_base = _b64_img(data["bg_src"])
            bg_base = ImageOps.fit(bg_base, (W, total_h), Image.Resampling.LANCZOS)
            canvas.alpha_composite(bg_base)
            
            td_overlay = _get_v_gradient(W, total_h, (15, 15, 19, 51), (15, 15, 19, 242))
            lr_overlay = _get_h_gradient(W, total_h, (78, 124, 255, 38), (78, 124, 255, 0))
            canvas.alpha_composite(td_overlay)
            canvas.alpha_composite(lr_overlay)
        except: pass

    y = PAD
    
    # Draw Title
    d = ImageDraw.Draw(canvas)
    d.text(((W - tw)//2, y), data["title"], font=F72B, fill=C_WHITE)
    y += hdr_h
    
    canvas.alpha_composite(content_img, (PAD, y))
    y += content_img.height + 10
    
    if f_img:
        f_alpha = f_img.copy()
        f_alpha.putalpha(f_alpha.getchannel("A").point(lambda a: int(a * 0.6)))
        canvas.alpha_composite(f_alpha, ((W - f_img.width)//2, y))

    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
