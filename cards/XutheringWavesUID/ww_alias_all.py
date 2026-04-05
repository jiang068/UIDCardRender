# cards/XutheringWavesUID/ww_alias_all.py
from __future__ import annotations
import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageOps, ImageChops

# 从统一包中导入所有需要用到的字体和辅助函数
from . import (
    F12, F14, F16, F18, F32,
    M12, M14, M16, M18, M32,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask, _is_pure_en_num
)

# --------------------------------------------------
# 绘图与排版辅助函数
# --------------------------------------------------
def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, r: int, fill: tuple, outline: tuple = None, width: int = 1):
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(block, (x0, y0))

def _calc_mixed_w(text: str, cn_font, en_font) -> int:
    if not text: return 0
    w = 0
    for ch in str(text):
        if _is_pure_en_num(ch): w += en_font.getlength(ch)
        else: w += cn_font.getlength(ch)
    return int(w)

def calc_card_layout(aliases: list[str]) -> tuple[list[list[dict]], int]:
    """
    智能换行排版引擎：
    计算单张卡片内别名标签的折行布局，并返回总布局高度。
    卡片内部最大安全宽度 = 232(列宽) - 16(左Pad) - 16(右Pad) = 200px
    """
    MAX_W = 200
    lines = []
    curr_line = []
    curr_x = 0
    
    for a in aliases:
        tw = _calc_mixed_w(a, F12, M12)
        tag_w = tw + 16  # 左右各 8px 内边距
        
        # 换行判定
        if curr_x + tag_w > MAX_W and curr_line:
            lines.append(curr_line)
            curr_line = []
            curr_x = 0
            
        curr_line.append({"text": a, "w": tag_w})
        curr_x += tag_w + 6  # 标签之间的列间距 (gap-x = 6)
        
    if curr_line:
        lines.append(curr_line)
        
    # 计算本卡片的需要高度
    # 顶部空隙(70) = top_pad(14) + header_h(40) + mb(8) + pb(8) 
    # 每行标签高度 20px，行间距 4px
    tags_h = len(lines) * 20 + max(0, len(lines) - 1) * 4
    total_h = 70 + tags_h + 14 # 加上底部 14px 内边距
    
    return lines, total_h


# --------------------------------------------------
# DOM 深度解析
# --------------------------------------------------
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    
    bg_img = soup.select_one('.bg-layer img')
    bg_url = bg_img['src'] if bg_img else ""
    
    title = soup.select_one('.title').get_text(strip=True) if soup.select_one('.title') else "角色别名表"
    subtitle = soup.select_one('.subtitle').get_text(strip=True) if soup.select_one('.subtitle') else "ALIAS TABLE"
    
    chars = []
    for card in soup.select('.card'):
        av_img = card.select_one('.card-avatar')
        av_src = av_img['src'] if av_img and av_img.name == 'img' else ""
        
        name = card.select_one('.card-name').get_text(strip=True) if card.select_one('.card-name') else ""
        aliases = [tag.get_text(strip=True) for tag in card.select('.alias-tag')]
        
        chars.append({
            "avatar": av_src,
            "name": name,
            "aliases": aliases
        })
        
    footer_img = soup.select_one('.footer-img')
    footer_b64 = footer_img['src'] if footer_img else ""
    
    footer_text_node = soup.select_one('.footer-text')
    footer_text = footer_text_node.get_text(strip=True) if footer_text_node else "WUTHERING WAVES ALIAS TABLE"
    
    return {
        "bg_url": bg_url,
        "title": title,
        "subtitle": subtitle,
        "chars": chars,
        "footer_b64": footer_b64,
        "footer_text": footer_text
    }


# --------------------------------------------------
# 渲染核心逻辑
# --------------------------------------------------
def render(html: str) -> bytes:
    data = parse_html(html)
    
    # 尺寸设定
    W = 800
    PAD = 40
    COL_W = 232  # (800 - 40*2 - 12*2) // 3 = 232
    
    # 1. 预计算所有卡片的布局与排版高度
    for c in data['chars']:
        c['lines'], c['h'] = calc_card_layout(c['aliases'])
        
    # 分割为 3 列一行的二维数组
    rows = [data['chars'][i:i+3] for i in range(0, len(data['chars']), 3)]
    
    # 2. 动态预计算全局高度
    H = PAD
    H += 38 + 6  # Title 高度 + Margin
    H += 18 + 24 # Subtitle 高度 + Margin
    
    row_heights = []
    for row in rows:
        max_h = max(c['h'] for c in row)
        row_heights.append(max_h)
        H += max_h + 12 # 本行最大高度 + 网格行间距
        
    H -= 12 # 扣除最后多加的一个行间距
    H += 80 # .container padding-bottom
    H += 60 # Footer 高度
    
    # 3. 构建底板
    canvas = Image.new("RGBA", (W, H), (15, 17, 21, 255))
    
    if data['bg_url']:
        try:
            bg_img = _b64_img(data['bg_url']).resize((W, H), Image.Resampling.LANCZOS)
            if bg_img.mode != "RGBA":
                bg_img = bg_img.convert("RGBA")
            # 应用 15% 不透明度
            alpha = bg_img.getchannel('A')
            opacity_layer = Image.new('L', bg_img.size, int(255 * 0.15))
            new_alpha = ImageChops.multiply(alpha, opacity_layer)
            bg_img.putalpha(new_alpha)
            canvas.alpha_composite(bg_img, (0, 0))
        except: pass
        
    d = ImageDraw.Draw(canvas)
    y = PAD
    
    # --- 绘制 Title 与 Subtitle ---
    draw_text_mixed(d, (PAD, y), data['title'], F32, M32, fill=(232, 201, 99, 255))
    y += 38 + 6
    draw_text_mixed(d, (PAD, y), data['subtitle'], F14, M14, fill=(139, 139, 139, 255))
    y += 18 + 24
    
    # --- 绘制网格卡片 ---
    for r_idx, row in enumerate(rows):
        max_h = row_heights[r_idx]
        
        for c_idx, c in enumerate(row):
            x = PAD + c_idx * (COL_W + 12)
            
            # 卡片背景 (让它撑满当前行的最大高度)
            _draw_rounded_rect(canvas, x, y, x + COL_W, y + max_h, 8, (30, 34, 42, 178), outline=(255, 255, 255, 15))
            
            # Header
            av_x, av_y = x + 16, y + 14
            _draw_rounded_rect(canvas, av_x, av_y, av_x + 40, av_y + 40, 20, (34, 34, 34, 255), outline=(232, 201, 99, 76))
            
            if c['avatar']:
                try:
                    av_img = _b64_fit(c['avatar'], 40, 40)
                    canvas.paste(av_img, (av_x, av_y), _round_mask(40, 40, 20))
                except:
                    draw_text_mixed(d, (av_x + 14, av_y + 10), "?", F16, M16, fill=(85, 85, 85, 255))
            else:
                draw_text_mixed(d, (av_x + 14, av_y + 10), "?", F16, M16, fill=(85, 85, 85, 255))
                
            draw_text_mixed(d, (av_x + 50, av_y + 10), c['name'], F18, M18, fill=(255, 255, 255, 255))
            
            # Divider
            div_y = y + 62
            d.line([(x + 16, div_y), (x + COL_W - 16, div_y)], fill=(255, 255, 255, 15), width=1)
            
            # 绘制折行标签
            tag_y = div_y + 8
            for line in c['lines']:
                tag_x = x + 16
                for tag in line:
                    _draw_rounded_rect(canvas, tag_x, tag_y, tag_x + tag['w'], tag_y + 20, 3, (255, 255, 255, 15))
                    draw_text_mixed(d, (tag_x + 8, tag_y + 2), tag['text'], F12, M12, fill=(170, 170, 170, 255))
                    tag_x += tag['w'] + 6
                tag_y += 24 # 20px height + 4px gap-y
                
        y += max_h + 12
        
    # --- 绘制绝对定位在最底部的 Footer ---
    fy = H - 60
    _draw_rounded_rect(canvas, 0, fy, W, H, 0, (10, 10, 12, 250))
    d.line([(0, fy), (W, fy)], fill=(232, 201, 99, 51), width=1)
    
    if data['footer_b64']:
        try:
            f_raw = _b64_img(data['footer_b64'])
            fw, fh = f_raw.size
            new_fw = int(fw * 30 / fh)
            f_img = f_raw.resize((new_fw, 30), Image.Resampling.LANCZOS)
            canvas.alpha_composite(f_img, ((W - new_fw) // 2, fy + 15))
        except: pass
    else:
        fw = _calc_mixed_w(data['footer_text'], F14, M14)
        draw_text_mixed(d, ((W - fw) // 2, fy + 22), data['footer_text'], F14, M14, fill=(139, 139, 139, 255))
        
    # 格式化导出
    out_rgb = canvas.convert('RGB')
    buf = BytesIO()
    out_rgb.save(buf, format='JPEG', quality=92, optimize=True)
    return buf.getvalue()