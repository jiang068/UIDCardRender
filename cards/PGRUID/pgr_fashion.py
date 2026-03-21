# 战双涂装列表 卡片渲染器 (PIL 重构精简版)

from __future__ import annotations
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageOps

# 从统一包中导入所有所需函数
from . import (
    F13, F14, F16, F20, F22, F24, F26, F28, F30, F44,
    M13, M14, M16, M20, M22, M24, M26, M28, M30, M44,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask,
    _ty, truncate_text,
    parse_common_header, draw_common_header, draw_title_bar
)

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2

C_BG_PAGE = (226, 235, 245, 255)
C_PRIMARY = (24, 107, 181, 255)
C_TEXT_DARK = (51, 51, 51, 255)
C_TEXT_GRAY = (102, 102, 102, 255)

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    # 1. 抽取基础公共 Header 数据
    data = parse_common_header(soup, html)
    data['sections'] = []

    # 2. 提取公共条幅背景和涂装底图
    r_bg = soup.select_one('.fashion-role-bg')
    data['roleBgB64'] = r_bg['src'] if r_bg else ""

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
                    icon_b64 = imgs[1]['src'] if len(imgs) > 1 else ""
                    data['sections'][-1]['items'].append({'name': name, 'iconB64': icon_b64})

    return data


# --- 主渲染逻辑 ---
def render(html: str) -> bytes:
    data = parse_html(html)
    
    MAX_H = 6000
    canvas = Image.new("RGBA", (W, MAX_H), C_BG_PAGE)
    if data.get('contentBgB64'):
        try:
            bg_img = _b64_img(data['contentBgB64'])
            bg_img = ImageOps.fit(bg_img, (W, MAX_H), Image.LANCZOS)
            canvas.alpha_composite(bg_img)
        except: pass

    d = ImageDraw.Draw(canvas)
    y = PAD

    # --- Header 组件式调用 ---
    y = draw_common_header(canvas, d, data, PAD, INNER_W, y)

    shared_role_bg = None
    if data['roleBgB64']:
        try:
            shared_role_bg = _b64_fit(data['roleBgB64'], 176, 176)
        except: pass

    # --- Sections (角色涂装 / 武器涂装) ---
    for sec in data['sections']:
        # 1. 动态生成模块标题条
        y = draw_title_bar(canvas, d, sec['title'], data.get('titleBgB64', ''), PAD, INNER_W, y)
        
        # 2. 绘制网格
        if not sec['items']:
            continue
            
        card_w, img_h, name_h, border_h = 176, 176, 32, 4
        card_h = img_h + name_h + border_h
        gap = 10
        
        for i, item in enumerate(sec['items']):
            col = i % 5
            row = i // 5
            cx = PAD + col * (card_w + gap)
            cy = y + row * (card_h + gap)
            
            c_img = Image.new("RGBA", (card_w, card_h), (255,255,255,0))
            cd = ImageDraw.Draw(c_img)
            
            if shared_role_bg:
                c_img.paste(shared_role_bg, (0, 0))
            else:
                cd.rectangle([0, 0, card_w, img_h], fill=(40,45,55,255))
                
            if item['iconB64']:
                try:
                    icon_img = _b64_fit(item['iconB64'], card_w, img_h)
                    c_img.alpha_composite(icon_img, (0, 0))
                except: pass
                
            cd.rectangle([0, img_h, card_w, img_h + name_h], fill=(27, 32, 40, 255))
            cd.rectangle([0, img_h + name_h, card_w, card_h], fill=(231, 92, 36, 255))
            
            short_name = truncate_text(item['name'], F13, card_w - 8)
            tw = int(F13.getlength(short_name))
            draw_text_mixed(cd, ((card_w - tw)//2, img_h + _ty(F13, short_name, name_h)), short_name, cn_font=F13, en_font=M13, fill=(255,255,255,255))
            
            canvas.paste(c_img, (cx, cy), _round_mask(card_w, card_h, 4))
            
        rows = (len(sec['items']) + 4) // 5
        grid_total_h = rows * card_h + (rows - 1) * gap
        y += grid_total_h + 30

    out_rgb = canvas.crop((0, 0, W, y)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()