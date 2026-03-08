# 鸣潮探索度卡片渲染器 (PIL 版)

from __future__ import annotations

import base64
import math
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps
from . import _b64_img, _b64_fit, _round_mask

# 常量定义

W = 1000
PAD = 30
INNER_W = W - PAD * 2  # 940

C_BG = (15, 17, 21, 255)
C_WHITE = (255, 255, 255, 255)
C_GOLD = (212, 177, 99, 255)

RE_COLOR = re.compile(r"color:\s*([^;]+)")
RE_BG_COLOR = re.compile(r"background-color:\s*([^;]+)")
RE_WIDTH = re.compile(r"width:\s*([0-9.]+)%")
RE_BG_URL = re.compile(r"url\('([^']+)'\)")


# 使用包级统一字体对象（从包里导入以复用同一实例，避免重复加载）
from . import F12, F14, F14B, F15, F16B, F17B, F18B, F19B, F22B, F24B, F34B, F36B, F48B
from . import M12, M14, M15, M16, M17, M18, M19, M22, M24, M34, M36, M48
from . import draw_text_mixed

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
    if c_str.startswith("rgb"):
        m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", c_str)
        if m: return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 255)
    return default


# 图像加载/缓存由包级统一实现（避免 data: URI 被本地缓存）

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, 
                       r: int, fill: tuple, outline=None, width=1) -> None:
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(block, (x0, y0))

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

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    
    # 基础信息
    user_name = (soup.select_one(".user-name") or soup).get_text(strip=True) if soup.select_one(".user-name") else ""
    uid = soup.select_one(".user-uid").get_text(strip=True).replace("UID", "").strip() if soup.select_one(".user-uid") else ""
    av_src = soup.select_one(".avatar").get("src", "") if soup.select_one(".avatar") else ""
    
    stats = []
    for st in soup.select(".stat-item"):
        v = st.select_one(".stat-value").get_text(strip=True) if st.select_one(".stat-value") else ""
        l = st.select_one(".stat-label").get_text(strip=True) if st.select_one(".stat-label") else ""
        stats.append((v, l))
        
    bg_src = soup.select_one(".bg-image").get("src", "") if soup.select_one(".bg-image") else ""
    footer_src = soup.select_one(".footer img").get("src", "") if soup.select_one(".footer img") else ""

    regions = []
    for r_el in soup.select(".region-card"):
        header = r_el.select_one(".region-header")
        style = header.get("style", "") if header else ""
        
        bg_url_m = RE_BG_URL.search(style)
        bg_url = bg_url_m.group(1) if bg_url_m else ""
        
        bg_color_m = RE_BG_COLOR.search(style)
        bg_color = parse_color(bg_color_m.group(1), (0,0,0,0)) if bg_color_m else (0,0,0,0)
        
        icon = header.select_one(".region-icon")
        icon_url = icon.get("src", "") if icon else ""
        
        name = header.select_one(".region-name").get_text(strip=True) if header.select_one(".region-name") else ""
        prog = header.select_one(".region-progress").get_text(strip=True).replace("探索度", "").strip() if header.select_one(".region-progress") else ""
        tag = header.select_one(".region-tag").get_text(strip=True) if header.select_one(".region-tag") else ""

        completed = []
        incomplete = []
        
        # 统一遍历并判定（弃用容易出兼容问题的 :not 伪类）
        for sub_el in r_el.select(".sub-area-card"):
            is_comp_class = "completed" in sub_el.get("class", [])
            
            s_name_el = sub_el.select_one(".sub-area-name")
            s_name = s_name_el.get_text(strip=True) if s_name_el else ""
            
            s_prog_el = sub_el.select_one(".sub-area-progress")
            s_prog = s_prog_el.get_text(strip=True) if s_prog_el else ""
            
            c_str = RE_COLOR.search(s_prog_el.get("style", "")) if s_prog_el else None
            p_col = parse_color(c_str.group(1)) if c_str else (212, 177, 99, 255)
            
            # 双重保险：只要含有 completed 样式类，或文本提示为 100%，全部归入满探索简略模式
            if is_comp_class or s_prog in ("100%", "100"):
                completed.append({"name": s_name, "progress": s_prog, "color": p_col})
            else:
                items = []
                for it_el in sub_el.select(".item-card"):
                    it_icon = it_el.select_one(".item-icon").get("src", "") if it_el.select_one(".item-icon") else ""
                    it_name = it_el.select_one(".item-name").get_text(strip=True) if it_el.select_one(".item-name") else ""
                    it_prog = it_el.select_one(".item-percent").get_text(strip=True) if it_el.select_one(".item-percent") else ""
                    
                    bar_fill = it_el.select_one(".progress-bar-fill")
                    bar_style = bar_fill.get("style", "") if bar_fill else ""
                    
                    b_wid_m = RE_WIDTH.search(bar_style)
                    b_wid = float(b_wid_m.group(1)) if b_wid_m else 0.0
                    
                    b_col_m = RE_BG_COLOR.search(bar_style)
                    b_col = parse_color(b_col_m.group(1), C_GOLD) if b_col_m else C_GOLD
                    
                    items.append({
                        "icon_url": it_icon,
                        "name": it_name,
                        "progress": it_prog,
                        "bar_width": b_wid,
                        "bar_color": b_col
                    })
                incomplete.append({"name": s_name, "progress": s_prog, "color": p_col, "items": items})

        regions.append({
            "bg_url": bg_url,
            "bg_color": bg_color,
            "icon_url": icon_url,
            "name": name,
            "progress": prog,
            "tag": tag,
            "completed": completed,
            "incomplete": incomplete
        })

    return {
        "user_name": user_name, "uid": uid, "avatar": av_src,
        "stats": stats, "bg_src": bg_src, "footer_src": footer_src,
        "regions": regions
    }


# 用户卡绘制

def draw_user_card(data: dict) -> Image.Image:
    H = 180
    card = Image.new("RGBA", (INNER_W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)

    _draw_rounded_rect(card, 0, 0, INNER_W, H, 16, (25, 28, 34, 230), outline=(255, 255, 255, 25))
    
    card.alpha_composite(_get_h_gradient(INNER_W - 280, H // 2, (212, 177, 99, 0), (212, 177, 99, 38)), (INNER_W - 280, 0))
    
    deco_txt = "SOLARIS EXPEDITION RECORD"
    draw_text_mixed(d, (INNER_W - 30 - F14B.getlength(deco_txt), 25), deco_txt, cn_font=F14B, en_font=M14, fill=(255, 255, 255, 25))

    AV_SZ = 120
    av_x, av_y = 30, (H - AV_SZ) // 2
    
    d.ellipse([av_x, av_y, av_x + AV_SZ, av_y + AV_SZ], fill=(34, 34, 34, 255))
    if data["avatar"]:
        try:
            av = _b64_fit(data["avatar"], AV_SZ, AV_SZ)
            card.paste(av, (av_x, av_y), _round_mask(AV_SZ, AV_SZ, AV_SZ//2))
        except Exception: pass
    
    d.ellipse([av_x-8, av_y-8, av_x+AV_SZ+8, av_y+AV_SZ+8], outline=(255, 255, 255, 13), width=1)
    d.arc([av_x-8, av_y-8, av_x+AV_SZ+8, av_y+AV_SZ+8], start=135, end=225, fill=C_GOLD, width=2)

    tx = av_x + AV_SZ + 30
    draw_text_mixed(d, (tx, 35), data["user_name"], cn_font=F48B, en_font=M48, fill=C_WHITE)
    
    uid_txt = f"UID {data['uid']}"
    name_w = int(F48B.getlength(data["user_name"]))
    uid_w = int(F24B.getlength(uid_txt)) + 32
    
    _draw_rounded_rect(card, tx + name_w + 20, 42, 
                       tx + name_w + 20 + uid_w, 42 + 40, 6, (0, 0, 0, 102), outline=(212, 177, 99, 51))
    draw_text_mixed(d, (tx + name_w + 36, 42 + _ty(F24B, uid_txt, 40)), uid_txt, cn_font=F24B, en_font=M24, fill=C_GOLD)
    
    sep_y = 100
    d.line([(tx, sep_y), (INNER_W - 30, sep_y)], fill=(255, 255, 255, 20), width=1)
    d.line([(tx, sep_y), (tx + 40, sep_y)], fill=C_GOLD, width=2)
    
    for i, (val, label) in enumerate(data["stats"]):
        sx = tx + i * 160
        draw_text_mixed(d, (sx, 115), val, cn_font=F36B, en_font=M36, fill=C_WHITE)
        draw_text_mixed(d, (sx, 155), label, cn_font=F14B, en_font=M14, fill=(109, 113, 122, 255))

    card.paste(Image.new("RGBA", (INNER_W, 16), (25, 28, 34, 230)), (0, 0))
    return card


# 网格区域绘制

GRID_GAP = 8
ITEM_W = (INNER_W - 20 - GRID_GAP * 2) // 3  # 920 // 3 = 301px

def draw_completed_card(area: dict) -> Image.Image:
    # 这是探索进度为 100% 时的简略卡片 (40px 高度，文字变灰)
    H = 40
    img = Image.new("RGBA", (ITEM_W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _draw_rounded_rect(img, 0, 0, ITEM_W, H, 8, (25, 28, 35, 153), outline=(255, 255, 255, 8))
    
    pw = int(F16B.getlength(area["progress"]))
    nx = 12
    max_nw = ITEM_W - 12 - 10 - pw - 10
    
    name_txt = _truncate_text(area["name"], F15, max_nw)
    draw_text_mixed(d, (nx, _ty(F15, name_txt, H)), name_txt, cn_font=F15, en_font=M15, fill=(170, 170, 170, 255))
    draw_text_mixed(d, (ITEM_W - 12 - pw, _ty(F16B, area["progress"], H)), area["progress"], cn_font=F16B, en_font=M16, fill=area["color"])
    return img

def draw_incomplete_card(area: dict) -> Image.Image:
    # 含有具体宝箱/声匣收集进度的完整卡片
    items = area["items"]
    H = 35 + (20 + len(items) * 44 + max(0, len(items) - 1) * 4 if items else 0)
    
    img = Image.new("RGBA", (ITEM_W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _draw_rounded_rect(img, 0, 0, ITEM_W, H, 8, (35, 38, 45, 102), outline=(255, 255, 255, 13))
    
    # 专属的左侧彩色粗边框
    d.rectangle([0, 0, 3, H], fill=area["color"])
    
    name_txt = _truncate_text(area["name"], F17B, ITEM_W - 100)
    draw_text_mixed(d, (12, 8), name_txt, cn_font=F17B, en_font=M17, fill=(224, 224, 224, 255))
    
    pw = int(F19B.getlength(area["progress"]))
    draw_text_mixed(d, (ITEM_W - 10 - pw, 6), area["progress"], cn_font=F19B, en_font=M19, fill=area["color"])
    
    if items:
        y = 35 + 8
        d.line([(10, y), (ITEM_W - 10, y)], fill=(255, 255, 255, 20), width=1)
        y += 8
        
        for it in items:
            _draw_rounded_rect(img, 8, y, ITEM_W - 8, y + 44, 6, (20, 22, 26, 102))
            
            if it["icon_url"]:
                try:
                    ic = _b64_fit(it["icon_url"], 32, 32)
                    _draw_rounded_rect(img, 14, y + 6, 14 + 32, y + 6 + 32, 4, (0, 0, 0, 76))
                    img.paste(ic, (14, y + 6), ic)
                except Exception: pass
                
            idx_x = 14 + 32 + 8
            
            it_name = _truncate_text(it["name"], F14B, ITEM_W - idx_x - 60)
            draw_text_mixed(d, (idx_x, y + 6), it_name, cn_font=F14B, en_font=M14, fill=(221, 221, 221, 255))
            
            it_pw = int(F14B.getlength(it["progress"]))
            draw_text_mixed(d, (ITEM_W - 14 - it_pw, y + 6), it["progress"], cn_font=F14B, en_font=M14, fill=(153, 153, 153, 255))
            
            bar_y = y + 28
            bar_w = ITEM_W - idx_x - 14
            _draw_rounded_rect(img, idx_x, bar_y, idx_x + bar_w, bar_y + 5, 3, (255, 255, 255, 25))
            fill_w = int(bar_w * (it["bar_width"] / 100.0))
            if fill_w > 0:
                _draw_rounded_rect(img, idx_x, bar_y, idx_x + fill_w, bar_y + 5, 3, it["bar_color"])
                
            y += 44 + 4

    return img

def draw_region_card(reg: dict) -> Image.Image:
    comp_imgs = [draw_completed_card(c) for c in reg["completed"]]
    incomp_imgs = [draw_incomplete_card(i) for i in reg["incomplete"]]
    
    comp_grid_h = 0
    if comp_imgs:
        rows = math.ceil(len(comp_imgs) / 3)
        comp_grid_h = rows * 40 + (rows - 1) * GRID_GAP
        
    incomp_rows = []
    incomp_grid_h = 0
    if incomp_imgs:
        for i in range(0, len(incomp_imgs), 3):
            chunk = incomp_imgs[i:i+3]
            max_h = max(im.height for im in chunk)
            incomp_rows.append((chunk, max_h))
            incomp_grid_h += max_h
        incomp_grid_h += max(0, len(incomp_rows) - 1) * GRID_GAP
        
    BODY_PAD = 10
    body_gap = 10 if (comp_imgs and incomp_imgs) else 0
    body_h = BODY_PAD * 2 + comp_grid_h + body_gap + incomp_grid_h
    
    HEADER_H = 120
    H = HEADER_H + body_h
    
    img = Image.new("RGBA", (INNER_W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, (20, 22, 26, 38), outline=(255, 255, 255, 25))
    
    hdr = Image.new("RGBA", (INNER_W, HEADER_H), reg["bg_color"])
    if reg["bg_url"]:
        try:
            bg_im = _b64_fit(reg["bg_url"], INNER_W, HEADER_H)
            hdr.paste(bg_im, (0, 0))
        except Exception: pass
        
    hdr.alpha_composite(_get_h_gradient(INNER_W, HEADER_H, (0, 0, 0, 128), (0, 0, 0, 51)), (0, 0))
    
    hd = ImageDraw.Draw(hdr)
    
    ix_off = 30
    if reg["icon_url"]:
        try:
            ic = _b64_fit(reg["icon_url"], 70, 70)
            hdr.paste(ic, (ix_off, 25), ic)
            ix_off += 70 + 25
        except Exception: pass
        
    draw_text_mixed(hd, (ix_off, 25), reg["name"], cn_font=F34B, en_font=M34, fill=C_WHITE)
    draw_text_mixed(hd, (ix_off, 68), f"探索度 {reg['progress']}" if "%" in reg['progress'] else f"探索度 {reg['progress']}%", cn_font=F22B, en_font=M22, fill=(238, 238, 238, 255))
    
    tw = int(F18B.getlength(reg["tag"])) + 32
    _draw_rounded_rect(hdr, INNER_W - 30 - tw, 42, INNER_W - 30, 42 + 36, 4, (255, 255, 255, 25), outline=(255, 255, 255, 51))
    draw_text_mixed(hd, (INNER_W - 30 - tw + 16, 42 + _ty(F18B, reg["tag"], 36)), reg["tag"], cn_font=F18B, en_font=M18, fill=C_WHITE)
    
    img.paste(hdr, (0, 0), _round_mask(INNER_W, HEADER_H, 12))
    img.paste(hdr.crop((0, HEADER_H - 12, INNER_W, HEADER_H)), (0, HEADER_H - 12))
    
    _draw_rounded_rect(img, 0, HEADER_H, INNER_W, H, 0, (0, 0, 0, 13)) 
    
    curr_y = HEADER_H + BODY_PAD
    
    if comp_imgs:
        for i, cim in enumerate(comp_imgs):
            row, col = divmod(i, 3)
            cx = 10 + col * (ITEM_W + GRID_GAP)
            cy = curr_y + row * (40 + GRID_GAP)
            img.alpha_composite(cim, (cx, cy))
        curr_y += comp_grid_h + body_gap
        
    if incomp_rows:
        for row_imgs, max_h in incomp_rows:
            for col, iim in enumerate(row_imgs):
                cx = 10 + col * (ITEM_W + GRID_GAP)
                img.alpha_composite(iim, (cx, curr_y))
            curr_y += max_h + GRID_GAP

    d.rounded_rectangle([0, 0, INNER_W - 1, H - 1], radius=12, outline=(255, 255, 255, 25), width=1)
    return img


# 主渲染逻辑

def render(html: str) -> bytes:
    data = parse_html(html)
    
    u_card = draw_user_card(data)
    reg_cards = [draw_region_card(r) for r in data["regions"]]
    
    GAP = 24
    regs_h = sum(c.height for c in reg_cards) + max(0, len(reg_cards) - 1) * GAP if reg_cards else 0
    
    FOOTER_H = 0
    f_img = None
    if data["footer_src"]:
        try:
            raw_f = _b64_img(data["footer_src"])
            scale = INNER_W / raw_f.width
            FOOTER_H = int(raw_f.height * scale)
            f_img = raw_f.resize((INNER_W, FOOTER_H), Image.LANCZOS)
        except Exception: pass

    total_h = PAD + u_card.height + GAP + regs_h + (15 + FOOTER_H if f_img else 0) + PAD
    
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    
    if data["bg_src"]:
        try:
            bg = _b64_img(data["bg_src"])
            bg = ImageOps.fit(bg, (W, total_h), Image.Resampling.LANCZOS)
            canvas.alpha_composite(bg)
            canvas.alpha_composite(Image.new("RGBA", (W, total_h), (0, 0, 0, 25)))
        except Exception: pass

    y = PAD
    canvas.alpha_composite(u_card, (PAD, y))
    y += u_card.height + GAP
    
    for rc in reg_cards:
        canvas.alpha_composite(rc, (PAD, y))
        y += rc.height + GAP
        
    if f_img:
        y = y - GAP + 15
        canvas.alpha_composite(f_img.convert("RGBA"), (PAD, y))

    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
