# 库洛币/用户信息卡片渲染器 (PIL 版)

from __future__ import annotations

import base64
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps


# 常量定义

W = 440  # 画布总宽
CARD_W = 420

C_BG_PAGE = (244, 247, 249, 255)  # #f4f7f9
C_BG_CARD = (255, 255, 255, 255)
C_TEXT_MAIN = (44, 62, 80, 255)   # #2c3e50
C_TEXT_SUB = (149, 165, 166, 255) # #95a5a6
C_SIG = (127, 140, 141, 255)      # #7f8c8d
C_ASSET_BG = (31, 31, 31, 255)    # #1f1f1f
C_GOLD_TEXT = (223, 174, 95, 255) # #dfae5f


from . import draw_text_mixed, M12, M13, M14, M15, M16, M17, M18, M20, M22, M24, M26, M28, M30, M32, M34, M36, M38, M42, M48, M72, _b64_img, _b64_fit, _round_mask

# 使用包级统一字体对象（从包里导入以复用同一实例）
from . import F13, F14, F16, F24B, F32B
def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1


# 图片加载/缓存委托给包级实现（避免 data: URI 被本地缓存）

def _circle_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    return mask

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int,
                       x1: int, y1: int, r: int, fill: tuple) -> None:
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill)
    canvas.alpha_composite(block, (x0, y0))

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


# HTML 解析

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    
    user_name = (soup.select_one(".user-name") or soup).get_text(strip=True) if soup.select_one(".user-name") else "Mbr"
    user_id_el = soup.select_one(".user-id")
    user_id = user_id_el.get_text(strip=True).replace("ID:", "").strip() if user_id_el else "0"
    
    sig_el = soup.select_one(".signature")
    signature = sig_el.get_text(strip=True) if sig_el else ""
    
    gold_el = soup.select_one(".asset-value")
    gold_num = gold_el.get_text(strip=True) if gold_el else "0"
    
    head_url = ""
    av = soup.select_one(".avatar-img")
    if av and av.get("src", "").startswith("data:"):
        head_url = av["src"]
        
    head_frame_url = ""
    frame = soup.select_one(".avatar-frame")
    if frame and frame.get("src", "").startswith("data:"):
        head_frame_url = frame["src"]
        
    coin_b64 = ""
    coin = soup.select_one(".coin-icon")
    if coin and coin.get("src", "").startswith("data:"):
        coin_b64 = coin["src"]
        
    footer_b64 = ""
    fi = soup.select_one(".footer img")
    if fi and fi.get("src", "").startswith("data:"):
        footer_b64 = fi["src"]

    return {
        "user_name": user_name,
        "user_id": user_id,
        "signature": signature,
        "gold_num": gold_num,
        "head_url": head_url,
        "head_frame_url": head_frame_url,
        "coin_b64": coin_b64,
        "footer_b64": footer_b64,
    }


# 主渲染逻辑

def render(html: str) -> bytes:
    data = parse_html(html)
    
    PAD_CARD = 35
    INFO_W = CARD_W - PAD_CARD * 2 - 90 - 20 # 240px
    
    # 1. 测算文字排版与高度
    sig_lines = _wrap_text(data["signature"], F13, INFO_W) if data["signature"] else []
    
    info_h = 24 + 8 + 14 # name + gap + id
    if sig_lines:
        info_h += 8 + len(sig_lines) * 18 # gap + line_height
        
    # User section minimum height is driven by avatar frame (106px) or text box
    user_sec_h = max(106, info_h, 90)
    
    # 总卡片高度 = 上边距 + 用户区 + 中间隙 + 资产区 + 下边距
    card_h = PAD_CARD + user_sec_h + 25 + 80 + PAD_CARD
    
    FOOTER_H = 0
    f_img = None
    if data["footer_b64"]:
        try:
            raw_f = _b64_img(data["footer_b64"])
            scale = 18 / raw_f.height
            fw = int(raw_f.width * scale)
            FOOTER_H = 18
            f_img = raw_f.resize((fw, FOOTER_H), Image.LANCZOS)
        except Exception: pass

    # 全局总高度 = 顶留白 + 容器留白 + 卡片高 + 底留白
    total_h = 10 + 10 + card_h + (15 + FOOTER_H if f_img else 10) + 10
    
    canvas = Image.new("RGBA", (W, total_h), C_BG_PAGE)
    d = ImageDraw.Draw(canvas)
    
    card_x = (W - CARD_W) // 2
    card_y = 10 + 10
    
    # 阴影模拟
    shadow = Image.new("RGBA", (CARD_W - 20, card_h - 10), (0, 0, 0, 10))
    canvas.paste(shadow, (card_x + 10, card_y + 15), _round_mask(CARD_W - 20, card_h - 10, 12))
    
    # 白底卡片
    _draw_rounded_rect(canvas, card_x, card_y, card_x + CARD_W, card_y + card_h, 12, C_BG_CARD)
    
    # --- 绘制用户区 ---
    sec_y = card_y + PAD_CARD
    
    # 头像组
    av_sz = 90
    av_x = card_x + PAD_CARD
    av_y = sec_y + (user_sec_h - av_sz) // 2
    
    # 头像底与描边
    d.ellipse([av_x, av_y, av_x + av_sz, av_y + av_sz], fill=(238, 238, 238, 255))
    if data["head_url"]:
        try:
            av_img = _b64_fit(data["head_url"], av_sz, av_sz)
            canvas.paste(av_img, (av_x, av_y), _circle_mask(av_sz))
        except Exception: pass
    d.ellipse([av_x, av_y, av_x + av_sz, av_y + av_sz], outline=C_BG_CARD, width=2)
    
    # 头像框 (z-index: 2, offset -8px)
    if data["head_frame_url"]:
        try:
            frame_img = _b64_fit(data["head_frame_url"], 106, 106)
            canvas.alpha_composite(frame_img, (av_x - 8, av_y - 8))
        except Exception: pass
        
    # 信息组
    info_x = av_x + av_sz + 20
    info_y = sec_y + (user_sec_h - info_h) // 2
    
    draw_text_mixed(d, (info_x, info_y - 4), data["user_name"], cn_font=F24B, en_font=M24, fill=C_TEXT_MAIN)
    curr_y = info_y + 24 + 8
    
    draw_text_mixed(d, (info_x, curr_y), f"ID: {data['user_id']}", cn_font=F14, en_font=M14, fill=C_TEXT_SUB)
    curr_y += 14 + 8
    
    if sig_lines:
        for line in sig_lines:
            draw_text_mixed(d, (info_x, curr_y), line, cn_font=F13, en_font=M13, fill=C_SIG)
            curr_y += 18
            
    # --- 绘制资产区 ---
    ass_y = sec_y + user_sec_h + 25
    ass_w = CARD_W - PAD_CARD * 2 # 350
    ass_x = card_x + PAD_CARD
    _draw_rounded_rect(canvas, ass_x, ass_y, ass_x + ass_w, ass_y + 80, 10, C_ASSET_BG)
    
    # 库洛币图标
    coin_sz = 50
    if data["coin_b64"]:
        try:
            coin_img = _b64_fit(data["coin_b64"], coin_sz, coin_sz)
            canvas.alpha_composite(coin_img, (ass_x + 25, ass_y + 15))
        except Exception: pass
        
    # 库洛币文本 (靠右)
    val_w = int(F32B.getlength(data["gold_num"]))
    lbl_w = int(F16.getlength("库洛币"))
    txt_total_w = lbl_w + 15 + val_w
    
    txt_start_x = ass_x + ass_w - 25 - txt_total_w
    draw_text_mixed(d, (txt_start_x, ass_y + _ty(F16, "库洛币", 80)), "库洛币", cn_font=F16, en_font=M16, fill=(170, 170, 170, 255))
    draw_text_mixed(d, (txt_start_x + lbl_w + 15, ass_y + _ty(F32B, data["gold_num"], 80) - 2), data["gold_num"], cn_font=F32B, en_font=M32, fill=C_GOLD_TEXT)

    # --- 绘制 Footer ---
    if f_img:
        fx = (W - f_img.width) // 2
        fy = card_y + card_h + 5
        # 用 alpha_composite 并调整不透明度(HTML opacity: 0.5)
        f_alpha = f_img.copy()
        f_alpha.putalpha(f_alpha.getchannel("A").point(lambda a: int(a * 0.5)))
        canvas.alpha_composite(f_alpha, (fx, fy))

    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
