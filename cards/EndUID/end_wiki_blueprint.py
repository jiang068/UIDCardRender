# cards/EndUID/end_wiki_blueprint.py
from __future__ import annotations
import urllib.request
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageOps

# 从包中获取常用字体和工具函数
from . import (
    F12, F13, F14, F15, F32,
    M12, M13, M14, M15, M32,
    draw_text_mixed, _b64_img, _round_mask
)

# --------------------------------------------------
# 常量与颜色
# --------------------------------------------------
W = 700
PAD = 30
INNER_W = W - PAD * 2  # 640

C_BG_TOP = (10, 22, 40, 255)
C_BG_MID = (15, 16, 20, 255)
C_BG_BOT = (10, 20, 32, 255)
C_ACCENT = (79, 195, 247, 255)
C_SUBTEXT = (139, 139, 139, 255)
C_TEXT = (221, 221, 221, 255)
C_MATERIAL = (240, 192, 96, 255)

# --------------------------------------------------
# 辅助绘图函数
# --------------------------------------------------
def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, r: int, fill: tuple, outline: tuple = None, width: int = 1):
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(block, (x0, y0))

def _draw_bg_gradient(canvas: Image.Image, w: int, h: int):
    """绘制整体的倾斜(伪)三段渐变背景"""
    base = Image.new("RGBA", (1, 3))
    base.putpixel((0, 0), C_BG_TOP)
    base.putpixel((0, 1), C_BG_MID)
    base.putpixel((0, 2), C_BG_BOT)
    grad = base.resize((w, h), Image.Resampling.BILINEAR)
    canvas.alpha_composite(grad, (0, 0))

def _calc_mixed_w(text: str, cn_font, en_font) -> int:
    """计算混合文本宽度"""
    if not text: return 0
    w = 0
    for ch in str(text):
        if 'a' <= ch <= 'z' or 'A' <= ch <= 'Z' or '0' <= ch <= '9' or ch in ' _-//:.':
            w += en_font.getlength(ch)
        else:
            w += cn_font.getlength(ch)
    return int(w)

def load_image(src: str) -> Image.Image:
    """强化版图片加载器：自动识别并下载 http 网络图片，否则回退到基础加载"""
    if not src:
        raise ValueError("Empty image source")
    if src.startswith("http://") or src.startswith("https://"):
        req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return Image.open(BytesIO(resp.read())).convert("RGBA")
    return _b64_img(src)

# --------------------------------------------------
# DOM 解析
# --------------------------------------------------
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    data = {}
    
    # 头部解析
    cover_img = soup.select_one('.bp-cover')
    data['cover_url'] = cover_img['src'] if cover_img else ""
    data['title'] = soup.select_one('.bp-title').get_text(strip=True) if soup.select_one('.bp-title') else "未知蓝图"
    badge_node = soup.select_one('.bp-badge')
    data['badge'] = badge_node.get_text(strip=True) if badge_node else ""
    
    # 解析信息行
    data['rows'] = []
    for row in soup.select('.bp-row'):
        label = row.select_one('.bp-label').get_text(strip=True) if row.select_one('.bp-label') else ""
        val_node = row.select_one('.bp-value')
        val_text = val_node.get_text(strip=True) if val_node else ""
        
        color_type = "normal"
        if val_node:
            classes = val_node.get('class', [])
            if 'product' in classes: color_type = "product"
            elif 'material' in classes: color_type = "material"
            
        data['rows'].append({
            "label": label,
            "value": val_text,
            "type": color_type
        })
        
    # 预览大图
    preview_img = soup.select_one('.bp-preview img')
    data['preview_url'] = preview_img['src'] if preview_img else ""
    
    # Footer
    logo_img = soup.select_one('.footer-logo')
    data['footer_logo'] = logo_img['src'] if logo_img else ""
    ft_text = soup.select_one('.footer-text')
    data['footer_text'] = ft_text.get_text(strip=True) if ft_text else f"BLUEPRINT // {data['title']}"

    return data


# --------------------------------------------------
# 主渲染引擎
# --------------------------------------------------
def render(html: str) -> bytes:
    data = parse_html(html)
    
    # 0. 提前预加载图片，避免后续计算高度和绘制时重复下载网络图片
    cover_img_obj = None
    if data['cover_url']:
        try: cover_img_obj = load_image(data['cover_url'])
        except: pass

    preview_img_obj = None
    if data['preview_url']:
        try: preview_img_obj = load_image(data['preview_url'])
        except: pass

    # 1. 动态预计算高度
    H = PAD + 80 + 20 # Header 高度 + margin-bottom
    
    if data['rows']:
        H += 16 * 2 # info 框的上下 padding
        H += len(data['rows']) * 31 - 16 # 每行字高加 padding 约 31，减最后一行多余
        H += 16 # margin-bottom
        
    if preview_img_obj:
        H += 16 + 18 + 8 # margin-top + label字高 + label margin-bottom
        pw, ph = preview_img_obj.size
        if pw > INNER_W:
            H += int(ph * INNER_W / pw)
        else:
            H += ph
            
    H += 70 # container padding-bottom
    H += 50 # Footer 高度
    
    # 2. 准备底板
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    _draw_bg_gradient(canvas, W, H)
    d = ImageDraw.Draw(canvas)
    y = PAD
    
    # --- 3. 绘制 Header ---
    if cover_img_obj:
        cv = ImageOps.fit(cover_img_obj, (80, 80), Image.Resampling.LANCZOS)
        _draw_rounded_rect(canvas, PAD, y, PAD + 80, y + 80, 10, (255, 255, 255, 13), outline=(79, 195, 247, 76), width=2)
        canvas.paste(cv, (PAD, y), _round_mask(80, 80, 10))
        
    tx = PAD + 96 if cover_img_obj else PAD
    draw_text_mixed(d, (tx, y + 10), data['title'], F32, M32, fill=(255, 255, 255, 255))
    if data['badge']:
        bw = _calc_mixed_w(data['badge'], F12, M12)
        _draw_rounded_rect(canvas, tx, y + 54, tx + bw + 20, y + 74, 3, (79, 195, 247, 38))
        draw_text_mixed(d, (tx + 10, y + 56), data['badge'], F12, M12, fill=C_ACCENT)
        
    y += 100
    
    # --- 4. 绘制 Info Rows ---
    if data['rows']:
        box_y = y
        box_h = 32 + len(data['rows']) * 31 - 16
        _draw_rounded_rect(canvas, PAD, box_y, PAD + INNER_W, box_y + box_h, 8, (20, 21, 24, 230), outline=(255, 255, 255, 20))
        
        row_y = box_y + 16
        for i, row in enumerate(data['rows']):
            draw_text_mixed(d, (PAD + 20, row_y + 8), row['label'], F14, M14, fill=C_SUBTEXT)
            
            # 判断颜色和字号
            if row['type'] == 'product':
                f_c, f_e = F15, M15
                fill_col = C_ACCENT
            elif row['type'] == 'material':
                f_c, f_e = F15, M15
                fill_col = C_MATERIAL
            elif '解锁条件' in row['label']:
                f_c, f_e = F13, M13
                fill_col = (170, 170, 170, 255)
            else:
                f_c, f_e = F15, M15
                fill_col = C_TEXT
                
            draw_text_mixed(d, (PAD + 120, row_y + 8), row['value'], f_c, f_e, fill=fill_col)
            
            row_y += 31
            if i < len(data['rows']) - 1:
                d.line([(PAD + 20, row_y), (PAD + INNER_W - 20, row_y)], fill=(255, 255, 255, 10), width=1)
                
        y += box_h + 16
        
    # --- 5. 绘制 Preview ---
    if preview_img_obj:
        y += 16
        draw_text_mixed(d, (PAD, y), "BLUEPRINT PREVIEW", F12, M12, fill=C_SUBTEXT)
        y += 20
        
        pw, ph = preview_img_obj.size
        if pw > INNER_W:
            new_h = int(ph * INNER_W / pw)
            prev = preview_img_obj.resize((INNER_W, new_h), Image.Resampling.LANCZOS)
            canvas.paste(prev, (PAD, y), _round_mask(INNER_W, new_h, 8))
            d.rounded_rectangle([PAD, y, PAD + INNER_W, y + new_h], radius=8, outline=(255, 255, 255, 25), width=1)
            y += new_h
        else:
            center_x = PAD + (INNER_W - pw) // 2
            canvas.paste(preview_img_obj, (center_x, y), _round_mask(pw, ph, 8))
            d.rounded_rectangle([center_x, y, center_x + pw, y + ph], radius=8, outline=(255, 255, 255, 25), width=1)
            y += ph

    # --- 6. Footer ---
    fy = H - 50
    _draw_rounded_rect(canvas, 0, fy, W, H, 0, (10, 10, 12, 250))
    d.line([(0, fy), (W, fy)], fill=(255, 255, 255, 25), width=1)
    
    if data['footer_logo']:
        try:
            f_logo = load_image(data['footer_logo'])
            lh = 24
            lw = int(f_logo.width * (lh / f_logo.height))
            f_logo = f_logo.resize((lw, lh), Image.Resampling.LANCZOS)
            
            # 应用 60% opacity (alpha=153)
            alpha = f_logo.getchannel('A')
            opacity_layer = Image.new('L', f_logo.size, 153)
            f_logo.putalpha(ImageDraw.ImageChops.multiply(alpha, opacity_layer))
            canvas.alpha_composite(f_logo, (30, fy + 13))
        except: pass
        
    fw = _calc_mixed_w(data['footer_text'], F13, M13)
    draw_text_mixed(d, (W - 30 - fw, fy + 18), data['footer_text'], F13, M13, fill=C_SUBTEXT)
    
    # 导出
    out_rgb = canvas.convert('RGB')
    buf = BytesIO()
    out_rgb.save(buf, format='JPEG', quality=92, optimize=True)
    return buf.getvalue()