# PGRUID 更新记录 卡片渲染器 (PIL 极致性能版)

from __future__ import annotations

import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops, ImageFilter

# 从同一包内导入统一资源（引入 E28 Emoji 字体）
from . import (
    F22, F28, E28, get_font, _is_pure_en_num, _is_kr, _is_jp_kana,
    M22, M28,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask
)

# 补充加载特殊字号
F36 = get_font(36, family='cn')
M36 = get_font(36, family='mono')

# --- 尺寸与颜色常量 ---
W = 800
PAD = 40
INNER_W = W - PAD * 2  # 720

C_BG_BASE = (26, 30, 35)              # #1a1e23
C_ACCENT = (77, 166, 255, 255)        # #4da6ff
C_TEXT = (255, 255, 255, 255)         # #ffffff
C_SUBTEXT = (139, 139, 139, 255)      # #8b8b8b
C_CARD_BG = (255, 255, 255, 15)       # rgba(255,255,255,0.06)
C_CARD_BORDER = (255, 255, 255, 25)   # rgba(255,255,255,0.1)

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1

def _draw_rounded_rect(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, r: int, fill: tuple, outline: tuple=None):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(block)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill)
    if outline:
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, outline=outline, width=1)
    canvas.alpha_composite(block, (x0, y0))

def _get_mixed_text_length(text: str, cn_font, en_font) -> int:
    """高精度计算混合中英文字体的渲染总长度"""
    length = 0
    f_size_cn = getattr(cn_font, 'size', 24)
    jp_font = globals().get(f"J{f_size_cn}", cn_font)
    kr_font = globals().get(f"K{f_size_cn}", cn_font)
    
    for ch in text:
        if _is_pure_en_num(ch): length += en_font.getlength(ch)
        elif _is_kr(ch): length += kr_font.getlength(ch)
        elif _is_jp_kana(ch): length += jp_font.getlength(ch)
        else: length += cn_font.getlength(ch)
    return int(length)

def _wrap_mixed_text(text: str, max_w: int, cn_font, en_font) -> list[str]:
    """支持中英文混排的自动换行算法"""
    lines = []
    current_line = ""
    for char in text:
        if _get_mixed_text_length(current_line + char, cn_font, en_font) <= max_w:
            current_line += char
        else:
            lines.append(current_line)
            current_line = char
    if current_line:
        lines.append(current_line)
    return lines

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    data = {}

    # 背景
    body_style = soup.select_one('body').get('style', '') if soup.select_one('body') else html
    bgs = re.findall(r"url\(['\"]?(data:[^'\"]+)['\"]?\)", body_style)
    data['shadowB64'] = bgs[0] if len(bgs) > 0 else ""
    data['bgB64'] = bgs[1] if len(bgs) > 1 else ""

    # Logo
    logo = soup.select_one('.header-logo')
    data['iconB64'] = logo['src'] if logo else ""

    # Logs
    data['logs'] = []
    for item in soup.select('.log-item'):
        data['logs'].append({
            'emoji': item.select_one('.log-emoji').get_text(strip=True) if item.select_one('.log-emoji') else "",
            'text': item.select_one('.log-text').get_text(strip=True) if item.select_one('.log-text') else "",
            'index': item.select_one('.log-index').get_text(strip=True).replace('#', '') if item.select_one('.log-index') else ""
        })

    return data


# --- 主渲染逻辑 ---
def render(html: str) -> bytes:
    data = parse_html(html)
    
    # 动态计算高度
    est_h = PAD + 250 # 头部预估
    text_max_w = INNER_W - 40 - 50 - 16 - 80 - 16 # 左右padding 40, emoji 50+16, index 80+16
    for log in data['logs']:
        lines = _wrap_mixed_text(log['text'], text_max_w, F28, M28)
        est_h += 28 + len(lines) * 40 + 10 # padding + text_height + gap
    est_h += PAD
    
    MAX_H = max(400, est_h + 200) # 留足余量
    
    canvas = Image.new("RGBA", (W, MAX_H), (*C_BG_BASE, 255))
    
    # 渲染背景 (Multiply 叠底)
    bg_layer = Image.new("RGB", (W, MAX_H), C_BG_BASE)
    if data['bgB64']:
        try:
            content_bg = _b64_fit(data['bgB64'], W, MAX_H).convert("RGB")
            bg_layer = ImageChops.multiply(bg_layer, content_bg)
        except: pass
    if data['shadowB64']:
        try:
            shadow_bg = _b64_fit(data['shadowB64'], W, MAX_H).convert("RGB")
            bg_layer = ImageChops.multiply(bg_layer, shadow_bg)
        except: pass
    
    canvas.paste(bg_layer, (0, 0))

    d = ImageDraw.Draw(canvas)
    y = PAD

    # --- Header ---
    if data['iconB64']:
        try:
            logo_img = _b64_img(data['iconB64'])
            lw, lh = logo_img.size
            new_lh = int(200 * (lh / lw))
            logo_img = logo_img.resize((200, new_lh), Image.LANCZOS)
            lx = (W - 200) // 2
            
            # 原生高斯模糊实现 filter: drop-shadow(0 4px 20px rgba(77, 166, 255, 0.2))
            shadow = Image.new("RGBA", logo_img.size, (0,0,0,0))
            shadow_alpha = logo_img.getchannel('A').point(lambda p: p * 0.2)
            shadow.paste((77, 166, 255), (0,0), shadow_alpha)
            shadow = shadow.filter(ImageFilter.GaussianBlur(10)) # 高斯模糊 10px
            
            canvas.alpha_composite(shadow, (lx, y + 4)) # 偏移 4px
            canvas.alpha_composite(logo_img, (lx, y))
            y += new_lh + 16
        except: pass

    # Header Name
    nw = int(F36.getlength("PGRUID"))
    draw_text_mixed(d, ((W - nw)//2, y), "PGRUID", cn_font=F36, en_font=M36, fill=C_TEXT)
    y += 36 + 16

    # Header Title
    tw = int(M22.getlength("UPDATE LOG"))
    # 手动处理 letter-spacing: 4px
    tx = (W - tw - 4 * 9) // 2
    for char in "UPDATE LOG":
        draw_text_mixed(d, (tx, y), char, cn_font=F22, en_font=M22, fill=C_SUBTEXT)
        tx += int(M22.getlength(char)) + 4
    y += 22 + 24

    # Divider
    d.line([(PAD, y), (W - PAD, y)], fill=(255, 255, 255, 25), width=2)
    y += 24

    # --- Log List ---
    for log in data['logs']:
        # 换行计算
        lines = _wrap_mixed_text(log['text'], text_max_w, F28, M28)
        text_h = len(lines) * 40 # 每行行高约 40
        card_h = 14 + 14 + text_h # 上下 padding 14
        
        # 绘制卡片背景
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + card_h, 10, C_CARD_BG, outline=C_CARD_BORDER)
        
        # 【修改点】Emoji: 直接使用 E28 字体绘制单色 Emoji，不再通过 draw_text_mixed
        if log['emoji']:
            ew = int(E28.getlength(log['emoji']))
            d.text((PAD + 20 + (50 - ew)//2, y + 14 + _ty(E28, log['emoji'], text_h)), log['emoji'], font=E28, fill=C_TEXT)
        
        # Text
        ty = y + 14 + 6
        for line in lines:
            draw_text_mixed(d, (PAD + 20 + 50 + 16, ty), line, cn_font=F28, en_font=M28, fill=(224, 224, 224, 255))
            ty += 40
            
        # Index
        idx_str = f"#{log['index']}"
        idx_w = int(M22.getlength(idx_str))
        draw_text_mixed(d, (PAD + INNER_W - 20 - idx_w, y + 14 + _ty(M22, idx_str, text_h)), idx_str, cn_font=F22, en_font=M22, fill=(77, 166, 255, 127))
        
        y += card_h + 10

    y += 20 # 底部留白

    out_rgb = canvas.crop((0, 0, W, y)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()