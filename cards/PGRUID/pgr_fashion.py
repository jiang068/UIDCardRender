# 战双涂装列表 卡片渲染器 (PIL 极致性能版)

from __future__ import annotations

import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 从同一包内导入统一资源
from . import (
    F13, F14, F16, F20, F22, F24, F26, F28, F30, F44,
    M13, M14, M16, M20, M22, M24, M26, M28, M30, M44,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask
)

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2  # 920

# 背景色统一采用之前的浅蓝灰色
C_BG_PAGE = (226, 235, 245, 255)    # #e2ebf5
C_PRIMARY = (24, 107, 181, 255)     # #186bb5
C_TEXT_DARK = (51, 51, 51, 255)     # #333333
C_TEXT_GRAY = (102, 102, 102, 255)  # #666666

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1

def _draw_rounded_rect(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, r: int, fill: tuple):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill)
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

def truncate_text(text: str, font, max_w: int) -> str:
    """智能截断超长文本并添加省略号"""
    if font.getlength(text) <= max_w:
        return text
    while text and font.getlength(text + '...') > max_w:
        text = text[:-1]
    return text + '...'

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    data = {'sections': []}

    bg_match = re.search(r"background-image:\s*url\(['\"]?(data:[^'\"]+)['\"]?\)", html)
    data['contentBgB64'] = bg_match.group(1) if bg_match else ""

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

    # 提取公共条幅背景和涂装底图
    t_bg = soup.select_one('.section-title-bar img')
    data['titleBgB64'] = t_bg['src'] if t_bg else ""
    
    r_bg = soup.select_one('.fashion-role-bg')
    data['roleBgB64'] = r_bg['src'] if r_bg else ""

    # 解析涂装网格数据
    container = soup.select_one('.container')
    if container:
        current_title = ""
        for child in container.children:
            if child.name is None: continue
            cls = child.get('class', [])
            
            if 'section-title-bar' in cls:
                span = child.select_one('span')
                current_title = span.get_text(strip=True) if span else "涂装列表"
                data['sections'].append({'title': current_title, 'items': []})
                
            elif 'fashion-grid' in cls and data['sections']:
                for card in child.select('.fashion-card'):
                    name = card.select_one('.fashion-name').get_text(strip=True)
                    imgs = card.select('.fashion-img img')
                    # 第二张图才是 icon（第一张是 roleBg）
                    icon_b64 = imgs[1]['src'] if len(imgs) > 1 else ""
                    data['sections'][-1]['items'].append({
                        'name': name,
                        'iconB64': icon_b64
                    })

    return data


# --- 主渲染逻辑 ---
def render(html: str) -> bytes:
    data = parse_html(html)
    
    MAX_H = 6000
    canvas = Image.new("RGBA", (W, MAX_H), C_BG_PAGE)
    if data['contentBgB64']:
        try:
            bg_img = _b64_img(data['contentBgB64'])
            bg_img = ImageOps.fit(bg_img, (W, MAX_H), Image.LANCZOS)
            canvas.alpha_composite(bg_img)
        except: pass

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
    
    # 底层：头像框
    if data['avatarBoxB64']:
        try:
            abox = _b64_fit(data['avatarBoxB64'], av_w, av_h)
            h_img.alpha_composite(abox, (av_x, av_y))
        except: pass

    # 顶层：头像
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

    # 预加载公共涂装背景，加速渲染
    shared_role_bg = None
    if data['roleBgB64']:
        try:
            shared_role_bg = _b64_fit(data['roleBgB64'], 176, 176)
        except: pass

    # --- Sections (角色涂装 / 武器涂装) ---
    for sec in data['sections']:
        # 1. 绘制标题条幅
        T_H = 60
        _draw_v_gradient(canvas, PAD, y, PAD + INNER_W, y + T_H, (24, 45, 75, 255), (15, 25, 45, 255), r=6)
        if data['titleBgB64']:
            try:
                tbg = _b64_fit(data['titleBgB64'], INNER_W, T_H)
                canvas.paste(tbg, (PAD, y), _round_mask(INNER_W, T_H, 6))
            except: pass
        draw_text_mixed(d, (PAD + 24, y + _ty(F26, sec['title'], T_H)), sec['title'], cn_font=F26, en_font=M26, fill=(255,255,255,255))
        y += T_H + 20
        
        # 2. 绘制网格
        if not sec['items']:
            continue
            
        card_w = 176  # (920 - 4*10) / 5
        img_h = 176
        name_h = 32
        border_h = 4
        card_h = img_h + name_h + border_h # 212
        gap = 10
        
        for i, item in enumerate(sec['items']):
            col = i % 5
            row = i // 5
            cx = PAD + col * (card_w + gap)
            cy = y + row * (card_h + gap)
            
            # 建立单张涂装卡片画布 (RGBA)
            c_img = Image.new("RGBA", (card_w, card_h), (255,255,255,0))
            cd = ImageDraw.Draw(c_img)
            
            # 拼合图像部分
            if shared_role_bg:
                c_img.paste(shared_role_bg, (0, 0))
            else:
                cd.rectangle([0, 0, card_w, img_h], fill=(40,45,55,255))
                
            if item['iconB64']:
                try:
                    icon_img = _b64_fit(item['iconB64'], card_w, img_h)
                    c_img.alpha_composite(icon_img, (0, 0))
                except: pass
                
            # 名字背景块 (#1b2028)
            cd.rectangle([0, img_h, card_w, img_h + name_h], fill=(27, 32, 40, 255))
            
            # 底部高亮边框 (#e75c24)
            cd.rectangle([0, img_h + name_h, card_w, card_h], fill=(231, 92, 36, 255))
            
            # 智能截断并居中文字
            short_name = truncate_text(item['name'], F13, card_w - 8)
            tw = int(F13.getlength(short_name))
            draw_text_mixed(cd, ((card_w - tw)//2, img_h + _ty(F13, short_name, name_h)), short_name, cn_font=F13, en_font=M13, fill=(255,255,255,255))
            
            # 贴上主画布并切圆角
            canvas.paste(c_img, (cx, cy), _round_mask(card_w, card_h, 4))
            
        rows = (len(sec['items']) + 4) // 5
        grid_total_h = rows * card_h + (rows - 1) * gap
        y += grid_total_h + 30

    out_rgb = canvas.crop((0, 0, W, y)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()