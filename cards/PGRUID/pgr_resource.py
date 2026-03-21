# 战双资源看板 卡片渲染器 (PIL 重构精简版)

from __future__ import annotations
import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops, ImageOps
from functools import lru_cache

# 从统一包中导入所有所需函数与字体 (F56, M56 已在 __init__ 预置)
from . import (
    F18, F22, F24, F26, F28, F30, F44, F56,
    M18, M22, M24, M26, M28, M30, M44, M56,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask,
    _ty, _draw_rounded_rect,
    parse_common_header, draw_common_header, draw_title_bar
)

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2

# 基础背景色 (#1a1e23)
C_BG_BASE = (26, 30, 35)

@lru_cache(maxsize=1)
def _generate_top_stamp() -> Image.Image:
    """纯代码生成 TOP 半年最高 虚线圆环印章，无需外部图片资源"""
    stamp = Image.new("RGBA", (180, 180), (0,0,0,0))
    d = ImageDraw.Draw(stamp)
    
    for i in range(0, 360, 12):
        d.arc([10, 10, 170, 170], i, i+8, fill=(255,255,255,140), width=2)
    d.ellipse([24, 24, 156, 156], outline=(255,255,255,140), width=3)
    
    tw = int(F18.getlength("- 半年最高 -"))
    draw_text_mixed(d, (90 - tw//2, 38), "- 半年最高 -", cn_font=F18, en_font=M18, fill=(255,255,255,178))
    
    tw2 = int(M30.getlength("TOP"))
    draw_text_mixed(d, (90 - tw2//2, 104), "TOP", cn_font=F30, en_font=M30, fill=(255,255,255,178))
    
    d.polygon([(90, 68), (93, 76), (102, 76), (95, 82), (98, 91), (90, 85), (82, 91), (85, 82), (78, 76), (87, 76)], fill=(255,255,255,153))
    return stamp.rotate(30, resample=Image.BICUBIC, expand=True)

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    # 1. 抽取基础公共 Header 数据
    data = parse_common_header(soup, html)

    # 正则提取多重背景：shadowB64 和 contentBgB64
    body_style = soup.select_one('body').get('style', '') if soup.select_one('body') else html
    bgs = re.findall(r"url\(['\"]?(data:[^'\"]+)['\"]?\)", body_style)
    data['shadowB64'] = bgs[0] if len(bgs) > 0 else ""
    if len(bgs) > 1: data['contentBgB64'] = bgs[1] # 覆盖通用提取

    # Top Banner (总计)
    top_b = soup.select_one('.top-banner')
    data['topBannerB64'] = top_b['src'] if top_b else ""
    
    t_vals = soup.select('.top-val')
    data['totalBlackCard'] = t_vals[0].get_text(strip=True) if len(t_vals)>0 else "0"
    data['totalDevelopResource'] = t_vals[1].get_text(strip=True) if len(t_vals)>1 else "0"
    data['totalTradeCredit'] = t_vals[2].get_text(strip=True) if len(t_vals)>2 else "0"

    # 月份行
    data['months'] = []
    for row in soup.select('.month-row'):
        m_data = {
            'isHighest': row.select_one('.stamp-container') is not None,
            'month': row.select_one('.month-label').get_text(strip=True) if row.select_one('.month-label') else "",
            'cards': []
        }
        for card in row.select('.asset-card'):
            c_img = card.select_one('img')
            c_val = card.select_one('.card-value')
            m_data['cards'].append({
                'imgB64': c_img['src'] if c_img else "",
                'val': c_val.get_text(strip=True) if c_val else "0"
            })
        data['months'].append(m_data)

    return data


# --- 主渲染逻辑 ---
def render(html: str) -> bytes:
    data = parse_html(html)
    
    MAX_H = 6000
    canvas = Image.new("RGBA", (W, MAX_H), (*C_BG_BASE, 255))
    
    # 核心黑科技：完美复刻 background-blend-mode: multiply 正片叠底
    bg_layer = Image.new("RGB", (W, MAX_H), C_BG_BASE)
    if data.get('contentBgB64'):
        try:
            content_bg = _b64_fit(data['contentBgB64'], W, MAX_H).convert("RGB")
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

    # --- Header 组件式调用 ---
    y = draw_common_header(canvas, d, data, PAD, INNER_W, y)

    # ==========================================
    # 性能黑科技：预加载 & 缓存通用资源底图
    # ==========================================
    card_w = (INNER_W - 24) // 3
    max_h = int(card_w * 0.42)  # 兜底高度
    cached_bgs = []

    if data['months'] and len(data['months'][0]['cards']) >= 3:
        for i in range(3):
            b64_data = data['months'][0]['cards'][i].get('imgB64')
            if b64_data:
                try:
                    c_img = _b64_img(b64_data)
                    cw, ch = c_img.size
                    th = int(card_w * (ch / cw))
                    max_h = max(max_h, th)
                    cached_bgs.append(c_img.resize((card_w, th), Image.LANCZOS))
                except:
                    cached_bgs.append(None)
            else:
                cached_bgs.append(None)
    else:
        cached_bgs = [None, None, None]

    # 通用渲染函数
    def draw_resource_cards(values, val_color):
        nonlocal y
        cx = PAD
        for i, val in enumerate(values[:3]):
            _draw_rounded_rect(canvas, cx, y, cx + card_w, y + max_h, 6, (0, 0, 0, 153))
            if i < len(cached_bgs) and cached_bgs[i]:
                canvas.paste(cached_bgs[i], (cx, y), _round_mask(card_w, cached_bgs[i].height, 6))
                
            vw = int(F56.getlength(val))
            draw_text_mixed(d, (cx + (card_w - vw)//2, y + max_h - 76), val, cn_font=F56, en_font=M56, fill=val_color)
            cx += card_w + 12
        y += max_h + 30

    # --- 半年资源总览 ---
    y = draw_title_bar(canvas, d, "半年资源总览", data.get('titleBgB64', ''), PAD, INNER_W, y)
    top_vals = [data['totalBlackCard'], data['totalDevelopResource'], data['totalTradeCredit']]
    draw_resource_cards(top_vals, (241, 224, 141, 255))

    # --- 往月收入情况 ---
    y = draw_title_bar(canvas, d, "往月收入情况", data.get('titleBgB64', ''), PAD, INNER_W, y)
    stamp_img = _generate_top_stamp()

    for m in data['months']:
        draw_text_mixed(d, (PAD + 4, y), m['month'], cn_font=F28, en_font=M28, fill=(224, 224, 224, 255))
        y += 42
        sy = y - 52
        
        month_vals = [c['val'] for c in m['cards']]
        draw_resource_cards(month_vals, (77, 166, 255, 255))
        
        if m['isHighest']:
            sx = PAD + INNER_W - 20 - stamp_img.width
            canvas.alpha_composite(stamp_img, (sx, sy))

    out_rgb = canvas.crop((0, 0, W, y)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()