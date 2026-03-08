# 鸣潮深境矩阵图鉴 (Matrix Wiki) 卡片渲染器 (PIL 版)

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
RE_BG_URL = re.compile(r"url\('([^']+)'\)")


# 使用包级统一字体对象（从包里导入以复用同一实例）
from . import F14B, F15, F17, F20B, F22B, F26, F28B, F34B, F72B
from . import M14, M15, M17, M20, M22, M26, M34, M72
from . import draw_text_mixed, _b64_img, _b64_fit, _round_mask

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

def parse_color(c_str: str, default=(255, 107, 107, 255)) -> tuple:
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


# 图像加载/缓存由包级统一实现（避免 data: URI 被本地缓存）

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
    main_color = parse_color(col_m.group(1), (255, 107, 107, 255)) if col_m else (255, 107, 107, 255)
    
    title = soup.select_one(".title").get_text(strip=True) if soup.select_one(".title") else ""
    subtitle = soup.select_one(".subtitle").get_text(strip=True) if soup.select_one(".subtitle") else ""
    footer_src = soup.select_one(".footer img").get("src") if soup.select_one(".footer img") else ""

    # Parse Buffs
    buffs = []
    buff_grid = soup.select_one(".buff-grid")
    if buff_grid:
        for b_el in buff_grid.select(".buff-item"):
            b_name = b_el.select_one(".buff-name").get_text(strip=True) if b_el.select_one(".buff-name") else ""
            b_desc = b_el.select_one(".buff-desc").get_text(strip=True) if b_el.select_one(".buff-desc") else ""
            buffs.append({"name": b_name, "desc": b_desc})

    # Parse Bosses
    bosses = []
    boss_grid = soup.select_one(".boss-grid")
    if boss_grid:
        for bs_el in boss_grid.select(".boss-card"):
            bs_icon = bs_el.select_one(".boss-icon").get("src") if bs_el.select_one(".boss-icon") and bs_el.select_one(".boss-icon").name == 'img' else ""
            bs_name = bs_el.select_one(".boss-name").get_text(strip=True) if bs_el.select_one(".boss-name") else ""
            
            tags = []
            for t_el in bs_el.select(".tag-badge"):
                t_name = t_el.get_text(strip=True)
                c_str = RE_COLOR.search(t_el.get("style", ""))
                t_col = parse_color(c_str.group(1)) if c_str else C_WHITE
                tags.append({"name": t_name, "color": t_col})
                
            desc_lines = []
            for d_el in bs_el.select(".boss-desc-line"):
                d_text = d_el.get_text(strip=True)
                is_round2 = "round2-line" in d_el.get("class", [])
                desc_lines.append({"text": d_text, "round2": is_round2})
                
            bosses.append({"icon": bs_icon, "name": bs_name, "tags": tags, "desc": desc_lines})

    # Parse Roles
    roles = []
    role_grid = soup.select_one(".role-grid")
    if role_grid:
        for r_el in role_grid.select(".role-item"):
            r_icon = r_el.select_one(".role-avatar").get("src") if r_el.select_one(".role-avatar") and r_el.select_one(".role-avatar").name == 'img' else ""
            r_name = r_el.select_one(".role-name").get_text(strip=True) if r_el.select_one(".role-name") else ""
            r_desc = r_el.select_one(".role-desc").get_text(strip=True) if r_el.select_one(".role-desc") else ""
            roles.append({"icon": r_icon, "name": r_name, "desc": r_desc})

    return {
        "bg_url": bg_url, "main_color": main_color, 
        "title": title, "subtitle": subtitle, "footer_src": footer_src,
        "buffs": buffs, "bosses": bosses, "roles": roles
    }


# 局部卡片绘制

def draw_buff_card(buff: dict, width: int) -> Image.Image:
    pad_x, pad_y = 18, 14
    desc_w = width - pad_x * 2 - 12 # 12 is gap (no icon, just padding from left border)
    
    n_h = 22 + 6 # 22px font + 6mb
    lines = _wrap_text(buff["desc"], F17, desc_w)
    d_h = len(lines) * 27 # 1.6 line height ~ 27px
    
    H = pad_y * 2 + n_h + d_h
    img = Image.new("RGBA", (width, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    
    _draw_rounded_rect(img, 0, 0, width, H, 10, (255,255,255,8))
    # left red bar
    d.rectangle([0, 0, 4, H], fill=(255, 107, 107, 128))
    
    cy = pad_y
    draw_text_mixed(d, (pad_x + 12, cy), buff["name"], cn_font=F22B, en_font=M22, fill=(255, 154, 154, 255))
    cy += n_h
    
    for l in lines:
        draw_text_mixed(d, (pad_x + 12, cy), l, cn_font=F17, en_font=M17, fill=C_DESC)
        cy += 27
        
    return img

def draw_boss_card(boss: dict, width: int) -> Image.Image:
    pad = 16
    H_hdr = 64
    gap_hdr_desc = 10
    
    desc_w = width - pad * 2 - 20 # 10px pad inside desc box
    
    # Calc Tags Wrap Height
    tag_h = 22 # font 14 + 2*pad
    curr_tx, curr_ty = 0, 0
    max_tw = width - pad * 2 - 64 - 14 # minus icon and gap
    for t in boss["tags"]:
        tw = int(F14B.getlength(t["name"])) + 20
        if curr_tx + tw > max_tw and curr_tx > 0:
            curr_tx = 0
            curr_ty += tag_h + 6
        curr_tx += tw + 6
        
    tags_total_h = curr_ty + tag_h
    info_h = 22 + 6 + tags_total_h # name(22) + mb(6)
    
    hdr_final_h = max(H_hdr, info_h)
    
    # Calc Desc Lines
    d_lines_rendered = []
    for d_line in boss["desc"]:
        lines = _wrap_text(d_line["text"], F15, desc_w)
        for l in lines:
            d_lines_rendered.append((l, d_line["round2"]))
            
    desc_h = 0
    if d_lines_rendered:
        # padding 8px top/bot
        desc_h = 16 + len(d_lines_rendered) * 23 # lh 1.5 ~ 23px
        
    H = pad * 2 + hdr_final_h + (gap_hdr_desc + desc_h if desc_h else 0)
    
    img = Image.new("RGBA", (width, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    
    _draw_rounded_rect(img, 0, 0, width, H, 16, (25, 25, 32, 180), outline=(255,255,255,25))
    
    # Header Icon
    ic_sz = 64
    if boss["icon"]:
        try:
            ic = _b64_fit(boss["icon"], ic_sz, ic_sz)
            img.paste(ic, (pad, pad), _round_mask(ic_sz, ic_sz, ic_sz//2))
        except: pass
    d.ellipse([pad, pad, pad+ic_sz, pad+ic_sz], outline=(255,255,255,51), width=2)
    
    # Header Info
    ix = pad + ic_sz + 14
    iy = pad + (hdr_final_h - info_h) // 2
    draw_text_mixed(d, (ix, iy), boss["name"], cn_font=F22B, en_font=M22, fill=C_WHITE)
    
    tx, ty = ix, iy + 22 + 6
    for t in boss["tags"]:
        tw = int(F14B.getlength(t["name"])) + 20
        if tx + tw > pad + ic_sz + 14 + max_tw and tx > ix:
            tx = ix
            ty += tag_h + 6
            
        c_rgb = t["color"]
        c_border = (c_rgb[0], c_rgb[1], c_rgb[2], int(255*0.5))
        _draw_rounded_rect(img, tx, ty, tx + tw, ty + tag_h, 11, (0,0,0,102), outline=c_border)
        draw_text_mixed(d, (tx + 10, ty + _ty(F14B, t["name"], tag_h)), t["name"], cn_font=F14B, en_font=M14, fill=c_rgb)
        tx += tw + 6

    # Desc Box
    if desc_h:
        dy = pad + hdr_final_h + gap_hdr_desc
        _draw_rounded_rect(img, pad, dy, width - pad, dy + desc_h, 8, (0,0,0,51))
        cy = dy + 8
        for l_txt, is_r2 in d_lines_rendered:
            col = (255, 209, 47, 255) if is_r2 else (187,187,187,255)
            draw_text_mixed(d, (pad + 10, cy), l_txt, cn_font=F15, en_font=M15, fill=col)
            cy += 23
            
    return img

def draw_role_card(role: dict, width: int) -> Image.Image:
    pad_x, pad_y = 16, 14
    av_sz = 56
    gap = 12
    
    desc_w = width - pad_x * 2 - av_sz - gap
    n_h = 20 + 4
    
    lines = _wrap_text(role["desc"], F15, desc_w)
    d_h = len(lines) * 23
    
    info_h = n_h + d_h
    H = pad_y * 2 + max(av_sz, info_h)
    
    img = Image.new("RGBA", (width, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    
    _draw_rounded_rect(img, 0, 0, width, H, 12, (255,255,255,8), outline=(255,255,255,20))
    
    if role["icon"]:
        try:
            ic = _b64_fit(role["icon"], av_sz, av_sz)
            img.paste(ic, (pad_x, pad_y), _round_mask(av_sz, av_sz, av_sz//2))
        except: pass
    d.ellipse([pad_x, pad_y, pad_x+av_sz, pad_y+av_sz], outline=(255, 107, 107, 128), width=2)
    
    ix = pad_x + av_sz + gap
    iy = pad_y + (max(av_sz, info_h) - info_h) // 2
    
    draw_text_mixed(d, (ix, iy), role["name"], cn_font=F20B, en_font=M20, fill=C_WHITE)
    iy += n_h
    for l in lines:
        draw_text_mixed(d, (ix, iy), l, cn_font=F15, en_font=M15, fill=C_DESC)
        iy += 23
        
    return img

def draw_section_block(title: str, items: list, render_func, cols: int, title_col=None) -> Image.Image:
    if not items: return Image.new("RGBA", (INNER_W, 0))
    
    gap = 14
    item_w = (INNER_W - 48 - gap * (cols - 1)) // cols # pad 24*2
    
    c_imgs = [render_func(it, item_w) for it in items]
    
    rows = math.ceil(len(c_imgs) / cols)
    row_heights = []
    for r in range(rows):
        mh = max(im.height for im in c_imgs[r*cols : (r+1)*cols])
        row_heights.append(mh)
        
    grid_h = sum(row_heights) + max(0, rows - 1) * gap
    
    pad = 24
    hdr_h = 34 + 12 + 8 # font + pb + mb
    
    H = pad * 2 + hdr_h + grid_h
    img = Image.new("RGBA", (INNER_W, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 16, C_CARD_BG, outline=C_BORDER)
    
    d.line([(pad, pad + 34 + 12), (INNER_W - pad, pad + 34 + 12)], fill=(255,255,255,20), width=2)
    
    tc = title_col if title_col else (255, 255, 255, 255)
    draw_text_mixed(d, (pad, pad), title, cn_font=F34B, en_font=M34, fill=tc)
    
    cy = pad + hdr_h
    for i, (cim) in enumerate(c_imgs):
        r, c = divmod(i, cols)
        r_max = row_heights[r]
        
        # Base container for equal height stretch
        fb = Image.new("RGBA", (item_w, r_max), (0,0,0,0))
        # Note: Boss and Roles naturally don't need stretch, but Buffs might look better. 
        # But per standard grid items are top-aligned or stretched. Here we just top-align inside their column.
        # So we just paste cim directly
        img.alpha_composite(cim, (pad + c * (item_w + gap), cy))
        
        if (i + 1) % cols == 0 or (i + 1) == len(c_imgs):
            cy += r_max + gap
            
    return img


# 主流程

def render(html: str) -> bytes:
    data = parse_html(html)
    
    # 1. Header
    tw = int(F72B.getlength(data["title"]))
    hdr_h = 100 if not data["subtitle"] else 140
    h_img = Image.new("RGBA", (INNER_W, hdr_h), (0,0,0,0))
    hd = ImageDraw.Draw(h_img)
    
    draw_text_mixed(hd, ((INNER_W - tw)//2, 0), data["title"], cn_font=F72B, en_font=M72, fill=C_WHITE)
    if data["subtitle"]:
        sw = int(F26.getlength(data["subtitle"]))
        _draw_rounded_rect(h_img, (INNER_W - sw - 56)//2, 85, (INNER_W + sw + 56)//2, 85 + 46, 23, (0,0,0,128), outline=(255,255,255,38))
    draw_text_mixed(hd, ((INNER_W - sw)//2, 85 + _ty(F26, data["subtitle"], 46)), data["subtitle"], cn_font=F26, en_font=M26, fill=(204,204,204,255))
        
    # 2. Sections
    s_imgs = []
    if data["buffs"]:
        s_imgs.append(draw_section_block("选择Buff", data["buffs"], draw_buff_card, 2, data["main_color"]))
    if data["bosses"]:
        s_imgs.append(draw_section_block("Boss列表", data["bosses"], draw_boss_card, 2, (255, 118, 118, 255))) # red title
    if data["roles"]:
        s_imgs.append(draw_section_block("角色增益", data["roles"], draw_role_card, 3, data["main_color"]))

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
    total_h += sum(im.height for im in s_imgs) + max(0, len(s_imgs) - 1) * gap
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
            lr_overlay = _get_h_gradient(W, total_h, (255, 107, 107, 38), (255, 107, 107, 0))
            canvas.alpha_composite(td_overlay)
            canvas.alpha_composite(lr_overlay)
        except: pass

    cy = PAD
    canvas.alpha_composite(h_img, (PAD, cy))
    cy += hdr_h + gap
    
    for sim in s_imgs:
        canvas.alpha_composite(sim, (PAD, cy))
        cy += sim.height + gap
        
    if f_img:
        f_alpha = f_img.copy()
        f_alpha.putalpha(f_alpha.getchannel("A").point(lambda a: int(a * 0.6)))
        canvas.alpha_composite(f_alpha, ((W - f_img.width)//2, cy - gap + 12))

    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
