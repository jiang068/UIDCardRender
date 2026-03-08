# 鸣潮角色别名卡片渲染器 (PIL 版)

from __future__ import annotations

import base64
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps


# 常量定义

W = 600
PAD = 25
INNER_W = W - PAD * 2   # 550

C_BG = (15, 17, 21, 255)
C_WHITE = (255, 255, 255, 255)
C_GOLD = (212, 177, 99, 255)


from . import draw_text_mixed, M12, M14, M15, M16, M17, M18, M20, M22, M24, M26, M28, M30, M32, M34, M36, M38, M42, M48, M72

# 使用包级统一字体对象（从包里导入以复用同一实例）
from . import F12, F14, F16, F32
def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1


# 图片预处理与缓存

@lru_cache(maxsize=128)
def _b64_img(src: str) -> Image.Image:
    if "," in src:
        src = src.split(",", 1)[1]
    return Image.open(BytesIO(base64.b64decode(src))).convert("RGBA")

@lru_cache(maxsize=128)
def _b64_fit(src: str, w: int, h: int) -> Image.Image:
    return ImageOps.fit(_b64_img(src), (w, h), Image.Resampling.LANCZOS)

@lru_cache(maxsize=64)
def _round_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return mask

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int,
                       x1: int, y1: int, r: int, fill: tuple, outline=None, width=1) -> None:
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(block)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
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

@lru_cache(maxsize=64)
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
    
    char_name = (soup.select_one(".char-name") or soup).get_text(strip=True) if soup.select_one(".char-name") else "未知角色"
    
    avatar_src = ""
    av = soup.select_one(".avatar")
    if av and av.get("src", "").startswith("data:"):
        avatar_src = av["src"]
        
    aliases = [item.get_text(strip=True) for item in soup.select(".alias-item")]
    
    bg_src = ""
    bg_img = soup.select_one(".bg-image")
    if bg_img and bg_img.get("src", "").startswith("data:"):
        bg_src = bg_img["src"]

    footer_src = ""
    fi = soup.select_one(".footer img")
    if fi and fi.get("src", "").startswith("data:"):
        footer_src = fi["src"]

    return {
        "char_name": char_name,
        "avatar_src": avatar_src,
        "aliases": aliases,
        "bg_src": bg_src,
        "footer_src": footer_src,
    }


# 智能换行排版引擎 (Flexbox Simulator)

def calculate_layout(aliases: list[str], max_w: int) -> tuple[list[list[dict]], int]:
    """计算别名药丸的换行布局。返回：(按行组织的药丸列表, body总高度)"""
    lines = []
    current_line = []
    current_x = 0
    
    GAP_X, GAP_Y = 8, 8
    PILL_H = 30  # (文本16px + 上下内边距7px*2 = 30)
    
    for i, alias in enumerate(aliases):
        text_w = int(F16.getlength(alias))
        pill_w = text_w + 28  # 左右内边距 14px*2
        
        if current_x + pill_w > max_w and current_line:
            lines.append(current_line)
            current_line = []
            current_x = 0
            
        current_line.append({
            "text": alias,
            "w": pill_w,
            "h": PILL_H,
            "is_first": (i == 0)
        })
        current_x += pill_w + GAP_X
        
    if current_line:
        lines.append(current_line)
        
    body_pad_y = 20 * 2
    label_h = 14
    label_mb = 12
    
    grid_h = len(lines) * PILL_H + max(0, len(lines) - 1) * GAP_Y
    total_body_h = body_pad_y + label_h + label_mb + grid_h if lines else body_pad_y + label_h
    
    return lines, total_body_h


# 卡片绘制

def draw_main_card(data: dict) -> Image.Image:
    # 1. 布局计算
    BODY_PAD_X = 25
    grid_max_w = INNER_W - BODY_PAD_X * 2
    
    alias_lines, body_h = calculate_layout(data["aliases"], grid_max_w)
    
    HEADER_H = 120
    CARD_H = HEADER_H + body_h
    
    card = Image.new("RGBA", (INNER_W, CARD_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    
    # 2. 卡片主背景与边框
    _draw_rounded_rect(card, 0, 0, INNER_W, CARD_H, 16, (30, 34, 42, 153), outline=(255, 255, 255, 25))
    
    # 顶部金色高亮线 (向两边变透明)
    card.alpha_composite(_get_h_gradient(INNER_W // 2, 4, (212, 177, 99, 0), (212, 177, 99, 204)), (0, 0))
    card.alpha_composite(_get_h_gradient(INNER_W // 2, 4, (212, 177, 99, 204), (212, 177, 99, 0)), (INNER_W // 2, 0))
    
    # 3. 绘制 Header
    card.alpha_composite(_get_v_gradient(INNER_W, HEADER_H, (255, 255, 255, 13), (255, 255, 255, 0)), (0, 0))
    d.line([(0, HEADER_H), (INNER_W, HEADER_H)], fill=(255, 255, 255, 20), width=1)
    
    # 头像
    AV_SZ = 80
    av_x, av_y = 25, 20
    
    # 基础底色与缺省处理
    _draw_rounded_rect(card, av_x, av_y, av_x + AV_SZ, av_y + AV_SZ, AV_SZ//2, (34, 34, 34, 255))
    if data["avatar_src"]:
        try:
            av_img = _b64_fit(data["avatar_src"], AV_SZ, AV_SZ)
            rmask = _round_mask(AV_SZ, AV_SZ, AV_SZ // 2)
            card.paste(av_img, (av_x, av_y), rmask)
        except Exception:
            draw_text_mixed(d, (av_x + 32, av_y + 24), "?", cn_font=F32, en_font=M32, fill=(85, 85, 85, 255))
    else:
        draw_text_mixed(d, (av_x + 32, av_y + 24), "?", cn_font=F32, en_font=M32, fill=(85, 85, 85, 255))
        
    # 头像环 (右下45度高亮段：PIL 坐标系中为 270到360度)
    d.ellipse([av_x-4, av_y-4, av_x+AV_SZ+4, av_y+AV_SZ+4], outline=(255, 255, 255, 25), width=1)
    d.arc([av_x-4, av_y-4, av_x+AV_SZ+4, av_y+AV_SZ+4], start=270, end=360, fill=C_GOLD, width=2)
    d.ellipse([av_x, av_y, av_x+AV_SZ, av_y+AV_SZ], outline=(212, 177, 99, 76), width=2)
    
    # 角色信息
    text_x = av_x + AV_SZ + 20
    draw_text_mixed(d, (text_x, av_y + 12), "CHARACTER NAME", cn_font=F12, en_font=M12, fill=C_GOLD)
    draw_text_mixed(d, (text_x, av_y + 32), data["char_name"], cn_font=F32, en_font=M32, fill=C_WHITE)
    
    # 4. 绘制 Body
    body_bg = Image.new("RGBA", (INNER_W, body_h), (0, 0, 0, 51))
    
    # 裁切出身体底部的圆角 (与主卡片一致)
    bmask = Image.new("L", (INNER_W, body_h), 255)
    ImageDraw.Draw(bmask).rounded_rectangle([0, -100, INNER_W - 1, body_h - 1], radius=16, fill=255)
    card.paste(body_bg, (0, HEADER_H), bmask)
    
    # 别名 Label
    label_y = HEADER_H + 20
    d.rounded_rectangle([25, label_y, 28, label_y + 14], radius=2, fill=C_GOLD)
    draw_text_mixed(d, (36, label_y - 2), "ALIASES", cn_font=F14, en_font=M14, fill=(170, 170, 170, 255))
    
    # 绘制 Alias Grid
    grid_y = label_y + 14 + 12
    for line in alias_lines:
        curr_x = BODY_PAD_X
        for pill in line:
            # 颜色判定
            if pill["is_first"]:
                bg_col = (212, 177, 99, 38)
                br_col = (212, 177, 99, 102)
                txt_col = (255, 255, 255, 255)
            else:
                bg_col = (255, 255, 255, 20)
                br_col = (255, 255, 255, 25)
                txt_col = (238, 238, 238, 255)
                
            _draw_rounded_rect(card, curr_x, grid_y, curr_x + pill["w"], grid_y + pill["h"], 
                               6, bg_col, outline=br_col)

            draw_text_mixed(d, (curr_x + 14, grid_y + _ty(F16, pill["text"], pill["h"])), 
                            pill["text"], cn_font=F16, en_font=M16, fill=txt_col)
            
            curr_x += pill["w"] + 8 # GAP_X
            
        grid_y += 30 + 8 # PILL_H + GAP_Y

    return card


# 主渲染逻辑

def render(html: str) -> bytes:
    data = parse_html(html)
    main_card = draw_main_card(data)
    
    # 尺寸计算
    FOOTER_GAP = 10
    BOTTOM_PAD = 20
    FOOTER_H = 0
    footer_img = None
    
    if data.get("footer_src"):
        try:
            footer_img = _b64_img(data["footer_src"])
            fw_orig, fh_orig = footer_img.size
            FOOTER_H = int(fh_orig * INNER_W / fw_orig)
            footer_img = footer_img.resize((INNER_W, FOOTER_H), Image.LANCZOS)
        except Exception:
            pass

    total_h = PAD + main_card.height
    if footer_img:
        total_h += FOOTER_GAP + FOOTER_H
    total_h += BOTTOM_PAD
    
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    
    # 全局背景
    if data.get("bg_src"):
        try:
            bg = _b64_img(data["bg_src"])
            bg = ImageOps.fit(bg, (W, total_h), Image.Resampling.LANCZOS)
            canvas.alpha_composite(bg)
        except Exception: 
            pass

    # 绘制卡片底部的弥散阴影 (伪装Box-Shadow)
    shadow = Image.new("RGBA", (INNER_W - 20, main_card.height - 10), (0, 0, 0, 150))
    canvas.paste(shadow, (PAD + 10, PAD + 15), _round_mask(INNER_W - 20, main_card.height - 10, 16))
    
    # 贴上主卡片
    canvas.alpha_composite(main_card, (PAD, PAD))
    
    # 贴上 Footer
    if footer_img:
        y = PAD + main_card.height + FOOTER_GAP
        canvas.alpha_composite(footer_img.convert("RGBA"), (PAD, y))

    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
