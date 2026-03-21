# 战双资源看板 卡片渲染器 (PIL 极致性能版)

from __future__ import annotations

import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops
from functools import lru_cache

# 从同一包内导入统一资源
from . import (
    F18, F22, F24, F26, F28, F30, F44, get_font,
    M18, M22, M24, M26, M28, M30, M44,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask
)

# 动态加载特大号字体
F56 = get_font(56, family='cn')
M56 = get_font(56, family='mono')
F64 = get_font(64, family='cn')
M64 = get_font(64, family='mono')

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2  # 920

# 基础背景色 (#1a1e23)
C_BG_BASE = (26, 30, 35)

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

def _draw_v_gradient(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, top_rgba: tuple, bottom_rgba: tuple, r: int = 0):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    base = Image.new("RGBA", (1, 2))
    base.putpixel((0, 0), top_rgba)
    base.putpixel((0, 1), bottom_rgba)
    grad = base.resize((w, h), Image.BILINEAR)
    if r > 0:
        mask = _round_mask(w, h, r)
        grad.putalpha(ImageChops.multiply(grad.getchannel('A'), mask))
    canvas.alpha_composite(grad, (x0, y0))

@lru_cache(maxsize=1)
def _generate_top_stamp() -> Image.Image:
    """纯代码生成 TOP 半年最高 虚线圆环印章，无需外部图片资源"""
    stamp = Image.new("RGBA", (180, 180), (0,0,0,0))
    d = ImageDraw.Draw(stamp)
    
    # 绘制虚线外环 (分段圆弧)
    for i in range(0, 360, 12):
        d.arc([10, 10, 170, 170], i, i+8, fill=(255,255,255,140), width=2)
    # 绘制实线内环
    d.ellipse([24, 24, 156, 156], outline=(255,255,255,140), width=3)
    
    # 绘制文字
    tw = int(F18.getlength("- 半年最高 -"))
    draw_text_mixed(d, (90 - tw//2, 38), "- 半年最高 -", cn_font=F18, en_font=M18, fill=(255,255,255,178))
    
    tw2 = int(M30.getlength("TOP"))
    draw_text_mixed(d, (90 - tw2//2, 104), "TOP", cn_font=F30, en_font=M30, fill=(255,255,255,178))
    
    # 绘制中心五角星
    d.polygon([(90, 68), (93, 76), (102, 76), (95, 82), (98, 91), (90, 85), (82, 91), (85, 82), (78, 76), (87, 76)], fill=(255,255,255,153))
    
    # 高质量旋转
    return stamp.rotate(30, resample=Image.BICUBIC, expand=True)

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    data = {}

    # 正则提取多重背景：shadowB64 和 contentBgB64
    body_style = soup.select_one('body').get('style', '') if soup.select_one('body') else html
    bgs = re.findall(r"url\(['\"]?(data:[^'\"]+)['\"]?\)", body_style)
    data['shadowB64'] = bgs[0] if len(bgs) > 0 else ""
    data['contentBgB64'] = bgs[1] if len(bgs) > 1 else ""

    # Header
    h_bg = soup.select_one('.header-bg')
    data['headerBgB64'] = h_bg['src'] if h_bg and h_bg.has_attr('src') else ""
    av = soup.select_one('.avatar-img')
    data['avatarB64'] = av['src'] if av else ""
    av_box = soup.select_one('.avatar-box')
    data['avatarBoxB64'] = av_box['src'] if av_box else ""
    
    data['roleName'] = soup.select_one('.header-name').get_text(strip=True) if soup.select_one('.header-name') else ""
    data['rank'] = soup.select_one('.level-val').get_text(strip=True) if soup.select_one('.level-val') else "0"
    
    server_node = soup.select_one('.header-server') or soup.select_one('.header-row-bottom span')
    data['serverName'] = server_node.get_text(strip=True) if server_node else ""
    uid_node = soup.select_one('.header-uid')
    raw_id = uid_node.get_text(strip=True) if uid_node else ""
    data['roleId'] = raw_id.replace("ID:", "").replace("ID", "").strip()

    t_bg = soup.select_one('.section-title-bar img')
    data['titleBgB64'] = t_bg['src'] if t_bg else ""

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
    if data['contentBgB64']:
        try:
            content_bg = _b64_fit(data['contentBgB64'], W, MAX_H).convert("RGB")
            bg_layer = ImageChops.multiply(bg_layer, content_bg)
        except: pass
    if data['shadowB64']:
        try:
            shadow_bg = _b64_fit(data['shadowB64'], W, MAX_H).convert("RGB")
            bg_layer = ImageChops.multiply(bg_layer, shadow_bg)
        except: pass
    
    # 将叠底后的背景贴入主画布
    canvas.paste(bg_layer, (0, 0))

    d = ImageDraw.Draw(canvas)
    y = PAD

    # --- Header ---
    H_H = 200
    h_img = Image.new("RGBA", (INNER_W, H_H), (0,0,0,0))
    hd = ImageDraw.Draw(h_img)
    
    _draw_rounded_rect(h_img, 0, 0, INNER_W, H_H, 8, (20,25,35,255))
    if data['headerBgB64']:
        try:
            hbg = _b64_fit(data['headerBgB64'], INNER_W, H_H)
            h_img.paste(hbg, (0,0), _round_mask(INNER_W, H_H, 8))
        except: pass

    av_w, av_h = 170, 170
    av_x, av_y = 30, (H_H - av_h)//2
    
    if data['avatarBoxB64']:
        try:
            abox = _b64_fit(data['avatarBoxB64'], av_w, av_h)
            h_img.alpha_composite(abox, (av_x, av_y))
        except: pass

    if data['avatarB64']:
        try:
            aimg = _b64_fit(data['avatarB64'], 120, 120)
            cmask = Image.new("L", (120, 120), 0)
            ImageDraw.Draw(cmask).ellipse([0,0,119,119], fill=255)
            h_img.paste(aimg, (av_x + 25, av_y + 25), cmask)
        except: pass

    info_x = av_x + av_w + 20
    draw_text_mixed(hd, (info_x, av_y + 20), data['roleName'], cn_font=F44, en_font=M44, fill=(255,255,255,255))
    name_w = int(F44.getlength(data['roleName']))
    
    rank_x = info_x + name_w + 16
    rank_val = data['rank']
    val_w = int(F22.getlength(rank_val))
    box_w = 64 + val_w + 14 
    
    _draw_rounded_rect(h_img, rank_x, av_y + 30, rank_x + box_w, av_y + 65, 4, (25,30,40,204))
    hd.rounded_rectangle([rank_x, av_y + 30, rank_x + box_w, av_y + 65], radius=4, outline=(80,100,120,153), width=1)
    draw_text_mixed(hd, (rank_x + 14, av_y + 30 + _ty(F22, "勋阶", 35)), "勋阶", cn_font=F22, en_font=M22, fill=(155,174,194,255))
    draw_text_mixed(hd, (rank_x + 64, av_y + 30 + _ty(F22, rank_val, 35)), rank_val, cn_font=F22, en_font=M22, fill=(229,141,60,255))

    bottom_y = av_y + 100
    if data['serverName']:
        draw_text_mixed(hd, (info_x, bottom_y), data['serverName'], cn_font=F24, en_font=M24, fill=(140,158,181,255))
        sw = int(F24.getlength(data['serverName']))
        draw_text_mixed(hd, (info_x + sw + 4, bottom_y), "|", cn_font=F24, en_font=M24, fill=(74,90,117,255))
        draw_text_mixed(hd, (info_x + sw + 20, bottom_y), f"ID:{data['roleId']}", cn_font=F24, en_font=M24, fill=(140,158,181,255))
    else:
        draw_text_mixed(hd, (info_x, bottom_y), f"ID:{data['roleId']}", cn_font=F24, en_font=M24, fill=(140,158,181,255))

    canvas.alpha_composite(h_img, (PAD, y))
    y += H_H + 20

    # --- 渲染标题条通用函数 ---
    def draw_title_bar(title):
        nonlocal y
        T_H = 60
        _draw_v_gradient(canvas, PAD, y, PAD + INNER_W, y + T_H, (24, 45, 75, 255), (15, 25, 45, 255), r=6)
        if data['titleBgB64']:
            try:
                tbg = _b64_fit(data['titleBgB64'], INNER_W, T_H)
                canvas.paste(tbg, (PAD, y), _round_mask(INNER_W, T_H, 6))
            except: pass
        draw_text_mixed(d, (PAD + 24, y + _ty(F26, title, T_H)), title, cn_font=F26, en_font=M26, fill=(255,255,255,255))
        y += T_H + 20

    # ==========================================
    # 性能黑科技：预加载 & 缓存通用资源底图
    # ==========================================
    card_w = (INNER_W - 24) // 3
    max_h = int(card_w * 0.42)  # 兜底高度
    cached_bgs = []

    # 从第一个月的卡片里“偷”图，只解码、缩放一次，存入内存
    if data['months'] and len(data['months'][0]['cards']) >= 3:
        for i in range(3):
            b64_data = data['months'][0]['cards'][i].get('imgB64')
            if b64_data:
                try:
                    c_img = _b64_img(b64_data)
                    cw, ch = c_img.size
                    th = int(card_w * (ch / cw))
                    max_h = max(max_h, th)
                    # 缩放好后直接存起来
                    cached_bgs.append(c_img.resize((card_w, th), Image.LANCZOS))
                except:
                    cached_bgs.append(None)
            else:
                cached_bgs.append(None)
    else:
        cached_bgs = [None, None, None]


    # 通用渲染函数：直接读取缓存图，不再做任何解码和缩放计算
    def draw_resource_cards(values, val_color):
        nonlocal y
        cx = PAD
        for i, val in enumerate(values[:3]): # 安全截取前3个
            # 1. 铺一层深色蒙版
            _draw_rounded_rect(canvas, cx, y, cx + card_w, y + max_h, 6, (0, 0, 0, 153))
            
            # 2. 从内存秒贴缓存图
            if i < len(cached_bgs) and cached_bgs[i]:
                canvas.paste(cached_bgs[i], (cx, y), _round_mask(card_w, cached_bgs[i].height, 6))
                
            # 3. 绘制文字
            vw = int(F56.getlength(val))
            draw_text_mixed(d, (cx + (card_w - vw)//2, y + max_h - 76), val, cn_font=F56, en_font=M56, fill=val_color)
            
            cx += card_w + 12
        y += max_h + 30


    # --- 半年资源总览 ---
    draw_title_bar("半年资源总览")
    
    # 提取总计数值，直接丢给通用函数渲染
    top_vals = [data['totalBlackCard'], data['totalDevelopResource'], data['totalTradeCredit']]
    draw_resource_cards(top_vals, (241, 224, 141, 255))


    # --- 往月收入情况 ---
    draw_title_bar("往月收入情况")

    stamp_img = _generate_top_stamp()

    for m in data['months']:
        # 月份 Label
        draw_text_mixed(d, (PAD + 4, y), m['month'], cn_font=F28, en_font=M28, fill=(224, 224, 224, 255))
        y += 42
        
        sy = y - 52
        
        # 提取当月数值，丢给通用函数
        month_vals = [c['val'] for c in m['cards']]
        draw_resource_cards(month_vals, (77, 166, 255, 255))
        
        # 最高月份盖章
        if m['isHighest']:
            sx = PAD + INNER_W - 20 - stamp_img.width
            canvas.alpha_composite(stamp_img, (sx, sy))

    out_rgb = canvas.crop((0, 0, W, y)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()