# cards/XutheringWavesUID/ww_sign_calendar.py
from __future__ import annotations
import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageOps

from . import (
    F14, F16, F18, F20, F24, F28, F34,
    M14, M16, M18, M20, M24, M28, M34,
    draw_text_mixed, _b64_img, _b64_fit, _is_pure_en_num
)

# --- 绘图与计算辅助函数 ---

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, r: int, fill: tuple, outline: tuple = None, width: int = 1):
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(block, (x0, y0))

def _calc_mixed_w(text: str, cn_font, en_font) -> int:
    """计算混合排版文字的总长度"""
    if not text: return 0
    w = 0
    for ch in text:
        if _is_pure_en_num(ch): w += en_font.getlength(ch)
        else: w += cn_font.getlength(ch)
    return int(w)

def parse_color(c_str: str) -> tuple:
    """解析 CSS 颜色字符串为 RGBA 元组"""
    c_str = c_str.strip()
    if c_str.startswith('#'):
        c_str = c_str.lstrip('#')
        if len(c_str) == 3: c_str = ''.join(c*2 for c in c_str)
        return tuple(int(c_str[i:i+2], 16) for i in (0, 2, 4)) + (255,)
    m = re.search(r'rgba?\(([^)]+)\)', c_str)
    if m:
        parts = [p.strip() for p in m.group(1).split(',')]
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        a = int(float(parts[3]) * 255) if len(parts) >= 4 else 255
        return (r, g, b, a)
    return (255, 255, 255, 255)

# --- DOM 数据提取 ---

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    data = {}
    
    style_block = soup.select_one('style').get_text() if soup.select_one('style') else html
    
    # 解析动态注入的颜色变量
    bg_m = re.search(r'body\s*\{[^}]*background-color:\s*([^;]+);', style_block)
    data['main_bg_color'] = parse_color(bg_m.group(1)) if bg_m else (244, 245, 247, 255)
    
    mtc_m = re.search(r'\.box-top-line1\s*\{[^}]*color:\s*([^;]+);', style_block)
    data['month_text_color'] = parse_color(mtc_m.group(1)) if mtc_m else (51, 51, 51, 255)
    
    hltc_m = re.search(r'\.box-top-line1\s*\.highlight\s*\{[^}]*color:\s*([^;]+);', style_block)
    data['highlight_color'] = parse_color(hltc_m.group(1)) if hltc_m else (231, 76, 60, 255)
    
    # 提取公共图片与玩家信息
    data['cover_bg'] = soup.select_one('.cover-img')['src'] if soup.select_one('.cover-img') else ""
    data['role_name'] = soup.select_one('.user-name').get_text(strip=True) if soup.select_one('.user-name') else ""
    uid_node = soup.select_one('.user-uid')
    data['uid'] = uid_node.get_text(strip=True).replace('UID:', '').strip() if uid_node else ""
    
    data['box_top_bg'] = soup.select_one('.box-top-bg')['src'] if soup.select_one('.box-top-bg') else ""
    data['box_center_bg'] = soup.select_one('.calendar-center-bg img')['src'] if soup.select_one('.calendar-center-bg img') else ""
    data['box_bottom_bg'] = soup.select_one('.box-bottom-bg')['src'] if soup.select_one('.box-bottom-bg') else ""
    
    # 拆分具有不同样式的顶部第一行文字
    line1_parts = []
    l1_node = soup.select_one('.box-top-line1')
    if l1_node:
        for child in l1_node.contents:
            if isinstance(child, str) and child.strip():
                line1_parts.append({'text': child.strip(), 'highlight': False})
            elif getattr(child, 'name', None) == 'span' and 'highlight' in child.get('class', []):
                line1_parts.append({'text': child.get_text(strip=True), 'highlight': True})
    data['line1_parts'] = line1_parts
    
    l2_node = soup.select_one('.box-top-line2')
    data['line2'] = l2_node.get_text(strip=True) if l2_node else ""
    
    # 解析网格签到项
    grid = []
    for row in soup.select('.calendar-row'):
        row_items = []
        for item in row.select('.sign-item'):
            today_bg = item.select_one('.today-bg')
            price_bg = item.select_one('.price-bg')
            bg_node = today_bg if today_bg else price_bg
            
            icon_node = item.select_one('.goods-icon')
            num_node = item.select_one('.goods-num')
            day_bg_node = item.select_one('.day-label-bg')
            day_text_node = item.select_one('.day-label-text')
            overlay_node = item.select_one('.signed-overlay')

            row_items.append({
                'bg_src': bg_node['src'] if bg_node else "",
                'icon_src': icon_node['src'] if icon_node else "",
                'num': num_node.get_text(strip=True) if num_node else "",
                'day_bg_src': day_bg_node['src'] if day_bg_node else "",
                'day_text': day_text_node.get_text(strip=True) if day_text_node else "",
                'overlay_src': overlay_node['src'] if overlay_node else ""
            })
        grid.append(row_items)
    data['grid'] = grid
    
    return data

# --- 主渲染逻辑 ---

def render(html: str) -> bytes:
    data = parse_html(html)
    
    cover_img = _b64_img(data['cover_bg']) if data['cover_bg'] else Image.new("RGBA", (1000, 300))
    CW, CH = cover_img.size
    
    box_top_img = _b64_img(data['box_top_bg']) if data['box_top_bg'] else Image.new("RGBA", (1000, 150))
    BW, BTH = box_top_img.size
    
    box_bot_img = _b64_img(data['box_bottom_bg']) if data['box_bottom_bg'] else Image.new("RGBA", (1000, 50))
    _, BBH = box_bot_img.size
    
    # 根据第一件物品推断网格项的标准大小，避免循环加载
    IW, IH, DW, DH = 80, 80, 80, 30
    if data['grid'] and data['grid'][0]:
        first = data['grid'][0][0]
        if first['bg_src']:
            IW, IH = _b64_img(first['bg_src']).size
        if first['day_bg_src']:
            DW, DH = _b64_img(first['day_bg_src']).size
            
    item_w, item_h = max(IW, DW), IH + DH
    pad_t, pad_b = 15, 15
    gap_x, gap_y = 30, 30
    
    # 动态计算网格的左边距，使其在背景宽(BW)中完美居中
    cols_count = len(data['grid'][0]) if data['grid'] else 4
    grid_w = cols_count * item_w + (cols_count - 1) * gap_x
    pad_l = (BW - grid_w) // 2
    rows_count = len(data['grid'])
    calendar_h = pad_t + rows_count * item_h + max(0, rows_count - 1) * gap_y + pad_b
    
    W = max(CW, BW)
    # 增加一个底部留白常量，建议 40 像素（对应 HTML 的 padding-bottom）
    FINAL_PAD = 40 
    H = CH + BTH + calendar_h + BBH - 30 + FINAL_PAD
    
    canvas = Image.new("RGBA", (W, H), data['main_bg_color'])
    d = ImageDraw.Draw(canvas)
    
    # 1. 顶部全景封图与名片盒
    cover_x = (W - CW) // 2
    canvas.alpha_composite(cover_img, (cover_x, 0))
    
    ui_x, ui_y = cover_x + 14, 14
    name_w = _calc_mixed_w(data['role_name'], F20, M20)
    uid_str = f"UID: {data['uid']}"
    uid_w = _calc_mixed_w(uid_str, F14, M14)
    ui_w = 18 + name_w + 12 + 1 + 12 + uid_w + 18
    ui_h = 44
    
    _draw_rounded_rect(canvas, ui_x, ui_y, ui_x + ui_w, ui_y + ui_h, 12, (0, 0, 0, 153), outline=(255, 255, 255, 38))
    # 姓名与发光阴影模拟
    draw_text_mixed(d, (ui_x + 18, ui_y + 11), data['role_name'], F20, M20, fill=(0, 0, 0, 128))
    draw_text_mixed(d, (ui_x + 18, ui_y + 10), data['role_name'], F20, M20, fill=(255, 255, 255, 255))
    
    div_x = ui_x + 18 + name_w + 12
    d.rectangle([div_x, ui_y + 13, div_x + 1, ui_y + 31], fill=(255, 255, 255, 76))
    
    draw_text_mixed(d, (div_x + 13, ui_y + 15), uid_str, F14, M14, fill=(0, 0, 0, 128))
    draw_text_mixed(d, (div_x + 13, ui_y + 14), uid_str, F14, M14, fill=(255, 255, 255, 230))
    
    # 2. 表格头
    box_x = (W - BW) // 2
    box_y = CH
    canvas.alpha_composite(box_top_img, (box_x, box_y))
    
    cx = W // 2
    cy = box_y + BTH // 2
    l1_w = sum(_calc_mixed_w(p['text'], F34 if p['highlight'] else F28, M34 if p['highlight'] else M28) for p in data['line1_parts'])
    
    start_y = cy - 29 # 计算两行字整体居中偏移
    curr_x = cx - l1_w // 2
    for p in data['line1_parts']:
        f_cn, f_en = (F34, M34) if p['highlight'] else (F28, M28)
        color = data['highlight_color'] if p['highlight'] else data['month_text_color']
        y_off = 0 if p['highlight'] else 6  # 基线向下对齐处理
        draw_text_mixed(d, (curr_x, start_y + y_off), p['text'], f_cn, f_en, fill=color)
        curr_x += _calc_mixed_w(p['text'], f_cn, f_en)
        
    l2_w = _calc_mixed_w(data['line2'], F18, M18)
    draw_text_mixed(d, (cx - l2_w // 2, start_y + 40), data['line2'], F18, M18, fill=data['highlight_color'])
    
    # 3. 日历中部拉伸区
    cal_y = box_y + BTH
    if data['box_center_bg']:
        # 【重要修改】使用 resize 强制拉伸，而不是 _b64_fit（fit 会按比例裁剪导致边缘丢失和错位）
        center_img = _b64_img(data['box_center_bg']).resize((BW, calendar_h), Image.Resampling.LANCZOS)
        canvas.alpha_composite(center_img, (box_x, cal_y))
        
    for r_idx, row in enumerate(data['grid']):
        for c_idx, item in enumerate(row):
            item_cx = box_x + pad_l + c_idx * (item_w + gap_x) + item_w // 2
            item_top = cal_y + pad_t + r_idx * (item_h + gap_y)
            
            # 物品底框
            if item['bg_src']:
                bg_img = _b64_img(item['bg_src'])
                bg_x = item_cx - IW // 2
                canvas.alpha_composite(bg_img, (bg_x, item_top))
                
            # 物品图标
            if item['icon_src']:
                icon_img = _b64_fit(item['icon_src'], IW, IH)
                canvas.alpha_composite(icon_img, (item_cx - IW // 2, item_top))
                
            # 物品数量 (白底黑字描边替代多重投影渲染)
            if item['num']:
                num_w = _calc_mixed_w(item['num'], F16, M16)
                nx = item_cx + IW // 2 - num_w - 4
                ny = item_top + IH - 24
                d.text((nx-1, ny), item['num'], font=F16, fill=(255,255,255,204))
                d.text((nx+1, ny), item['num'], font=F16, fill=(255,255,255,204))
                d.text((nx, ny-1), item['num'], font=F16, fill=(255,255,255,204))
                d.text((nx, ny+1), item['num'], font=F16, fill=(255,255,255,204))
                draw_text_mixed(d, (nx, ny), item['num'], F16, M16, fill=(51,51,51,255))
                
            # 天数标签区
            dy = item_top + IH
            if item['day_bg_src']:
                day_img = _b64_img(item['day_bg_src'])
                canvas.alpha_composite(day_img, (item_cx - DW // 2, dy))
                
            if item['day_text']:
                day_w = _calc_mixed_w(item['day_text'], F20, M20)
                dtx = item_cx - day_w // 2
                dty = dy + (DH - 20) // 2 - 2
                draw_text_mixed(d, (dtx, dty), item['day_text'], F20, M20, fill=(255,255,255,255))
                
            # “已领”灰色半透遮罩
            if item['overlay_src']:
                ov_img = _b64_img(item['overlay_src']).resize((item_w, item_h), Image.Resampling.LANCZOS)
                canvas.alpha_composite(ov_img, (item_cx - item_w // 2, item_top))

    # 4. 表格尾部拼合
    bot_y = cal_y + calendar_h - 30
    canvas.alpha_composite(box_bot_img, (box_x, bot_y))
    
    # 格式化导出
    buf = BytesIO()
    canvas.convert('RGB').save(buf, format='JPEG', quality=92, optimize=True)
    return buf.getvalue()