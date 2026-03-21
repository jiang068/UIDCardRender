# 战双体力与日程辅助 卡片渲染器 (PIL 重构精简版)

from __future__ import annotations
import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageOps, ImageChops

# 从统一包中导入所有所需函数
from . import (
    F14, F16, F18, F20, F22, F24, F26, F28, F30, F32, F42,
    M14, M16, M18, M20, M22, M24, M26, M28, M30, M32, M42,
    draw_text_mixed, _b64_img, _b64_fit,
    _draw_rounded_rect, _draw_clipped_rect,
    parse_common_header, draw_common_header, draw_title_bar
)

# --- 尺寸与颜色常量 ---
W = 800
PAD = 24
INNER_W = W - PAD * 2  # 752

C_BG_PAGE = (226, 235, 245, 255)
C_PRIMARY = (27, 115, 201, 255)
C_TEXT_MAIN = (43, 43, 43, 255)
C_TEXT_GRAY = (140, 147, 157, 255)
C_BORDER = (220, 227, 235, 255)
C_URGENT = (255, 77, 79, 255)
C_DONE = (39, 174, 96, 255)

def _parse_color(color_str: str, default: tuple) -> tuple:
    color_str = color_str.strip().lower()
    if color_str.startswith("#"):
        c = color_str.lstrip("#")
        if len(c) == 3: c = "".join([x*2 for x in c])
        if len(c) == 6: return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255)
    return default

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    # 1. 抽取基础公共 Header 数据
    data = parse_common_header(soup, html)

    # 2. 提取特有数据
    s_icon = soup.select_one('.serum-icon')
    data['serumIconB64'] = s_icon['src'] if s_icon else ""
    
    s_cur = soup.select_one('.serum-current')
    data['serumCur'] = s_cur.get_text(strip=True) if s_cur else "0"
    data['serumUrgent'] = s_cur and 'urgent' in s_cur.get('class', [])
    data['serumMax'] = soup.select_one('.serum-max').get_text(strip=True).replace("/", "").strip() if soup.select_one('.serum-max') else "0"
    data['serumTime'] = soup.select_one('.serum-time').get_text(strip=True) if soup.select_one('.serum-time') else ""
    
    s_fill = soup.select_one('.serum-progress-fill')
    data['serumPercent'] = 0.0
    data['serumColor'] = C_PRIMARY
    if s_fill and 'style' in s_fill.attrs:
        m_w = re.search(r"width:\s*([\d.]+)%", s_fill['style'])
        if m_w: data['serumPercent'] = float(m_w.group(1)) / 100.0
        m_c = re.search(r"background-color:\s*([^;]+)", s_fill['style'])
        if m_c: data['serumColor'] = _parse_color(m_c.group(1), C_PRIMARY)

    c_stats = soup.select('.comm-stats span strong')
    data['commDone'] = c_stats[0].get_text(strip=True) if len(c_stats)>0 else "0"
    data['commPending'] = c_stats[1].get_text(strip=True) if len(c_stats)>1 else "0"

    d_cur = soup.select_one('.daily-value .current')
    data['activeCur'] = d_cur.get_text(strip=True) if d_cur else "0"
    d_max = soup.select_one('.daily-value .max')
    data['activeMax'] = d_max.get_text(strip=True).replace("/", "").strip() if d_max else "0"
    a_fill = soup.select_one('.progress-bar-fill')
    data['activePercent'] = 0.0
    if a_fill and 'style' in a_fill.attrs:
        m_aw = re.search(r"width:\s*([\d.]+)%", a_fill['style'])
        if m_aw: data['activePercent'] = float(m_aw.group(1)) / 100.0

    data['tasks'] = []
    for t_card in soup.select('.task-card'):
        task = {}
        task['name'] = t_card.select_one('.task-title').get_text(strip=True) if t_card.select_one('.task-title') else ""
        t_time = t_card.select_one('.task-time')
        task['time'] = t_time.get_text(strip=True) if t_time else ""
        task['timeUrgent'] = t_time and 'urgent' in t_time.get('class', [])
        
        t_cur = t_card.select_one('.task-progress .current')
        task['cur'] = t_cur.get_text(strip=True) if t_cur else "0"
        task['done'] = t_cur and 'done' in t_cur.get('class', [])
        task['max'] = t_card.select_one('.task-progress .max').get_text(strip=True) if t_card.select_one('.task-progress .max') else ""
        data['tasks'].append(task)

    p_img = soup.select_one('.portrait-img')
    data['portraitB64'] = p_img['src'] if p_img else ""

    return data


# --- 主渲染逻辑 ---
def render(html: str) -> bytes:
    data = parse_html(html)
    
    MAX_H = 4000
    canvas = Image.new("RGBA", (W, MAX_H), C_BG_PAGE)
    if data.get('contentBgB64'):
        try:
            bg_img = _b64_img(data['contentBgB64'])
            bg_img = ImageOps.fit(bg_img, (W, MAX_H), Image.LANCZOS)
            canvas.alpha_composite(bg_img)
        except: pass

    d = ImageDraw.Draw(canvas)
    y = PAD

    # --- Header & Title Bar 组件化渲染 ---
    y = draw_common_header(canvas, d, data, PAD, INNER_W, y)
    y = draw_title_bar(canvas, d, "日程助手", data.get('titleBgB64', ''), PAD, INNER_W, y)

    # --- Main Layout 计算动态高度 ---
    left_w = INNER_W - 240
    content_w = left_w - 32  
    task_rows = (len(data['tasks']) + 1) // 2
    task_grid_h = task_rows * 92 + max(0, task_rows - 1) * 12
    main_h = 16 + 85 + 16 + 60 + 16 + task_grid_h + 24

    # --- Main Layout 底图绘制 ---
    _draw_clipped_rect(canvas, PAD, y, INNER_W, main_h, fill=(255,255,255,255), outline=C_BORDER, clip_size=24)

    if data['portraitB64']:
        try:
            p_raw = _b64_img(data['portraitB64'])
            pw, ph = p_raw.size
            ratio = max(240 / pw, main_h / ph)
            new_w, new_h = int(pw * ratio), int(ph * ratio)
            p_img = p_raw.resize((new_w, new_h), Image.LANCZOS)
            
            left = (new_w - 240) // 2
            p_crop = p_img.crop((left, 0, left + 240, main_h))
            
            mask_clip = Image.new("L", (240, main_h), 0)
            md = ImageDraw.Draw(mask_clip)
            md.polygon([(0, 0), (240, 0), (240, main_h - 24), (216, main_h), (0, main_h)], fill=255)
            
            p_alpha = p_crop.split()[3] if p_crop.mode == "RGBA" else Image.new("L", p_crop.size, 255)
            p_crop.putalpha(ImageChops.multiply(p_alpha, mask_clip))
            canvas.alpha_composite(p_crop, (PAD + left_w, y))
        except: pass

    # --- 左侧数据流 ---
    ly = y + 16
    lx = PAD + 16

    # 1. 血清 & 委托
    if data['serumIconB64']:
        try:
            s_img = _b64_fit(data['serumIconB64'], 72, 72)
            canvas.alpha_composite(s_img, (lx, ly + 6))
        except: pass

    sx = lx + 72 + 16
    s_bar_w = 180 
    
    draw_text_mixed(d, (sx, ly + 6), "血清", cn_font=F22, en_font=M22, fill=C_TEXT_MAIN)
    lbl_w = int(F22.getlength("血清")) + 10
    
    s_col = C_URGENT if data['serumUrgent'] else C_PRIMARY
    draw_text_mixed(d, (sx + lbl_w, ly), data['serumCur'], cn_font=F42, en_font=M42, fill=s_col)
    cur_w = int(F42.getlength(data['serumCur'])) + 4
    
    draw_text_mixed(d, (sx + lbl_w + cur_w, ly + 18), f"/ {data['serumMax']}", cn_font=F24, en_font=M24, fill=C_TEXT_GRAY)
    draw_text_mixed(d, (sx, ly + 46), data['serumTime'], cn_font=F18, en_font=M18, fill=C_URGENT if data['serumUrgent'] else C_TEXT_GRAY)

    s_bar_y = ly + 74
    _draw_rounded_rect(canvas, sx, s_bar_y, sx + s_bar_w, s_bar_y + 6, 3, (229, 233, 240, 255))
    if data['serumPercent'] > 0:
        f_w = int(s_bar_w * data['serumPercent'])
        _draw_rounded_rect(canvas, sx, s_bar_y, sx + f_w, s_bar_y + 6, 3, data['serumColor'])

    dx = sx + 200 
    d.rectangle([dx, ly + 14, dx + 1, ly + 70], fill=(209, 216, 223, 255))

    cx = dx + 20
    draw_text_mixed(d, (cx, ly + 6), "委托情况", cn_font=F22, en_font=M22, fill=C_TEXT_MAIN)
    
    draw_text_mixed(d, (cx, ly + 42), "已完成", cn_font=F18, en_font=M18, fill=C_TEXT_GRAY)
    draw_text_mixed(d, (cx + int(F18.getlength("已完成")) + 4, ly + 36), data['commDone'], cn_font=F24, en_font=M24, fill=C_PRIMARY)
    
    cx2 = cx + int(F18.getlength("已完成")) + 4 + int(F24.getlength(data['commDone'])) + 12
    draw_text_mixed(d, (cx2, ly + 42), "待领取", cn_font=F18, en_font=M18, fill=C_TEXT_GRAY)
    draw_text_mixed(d, (cx2 + int(F18.getlength("待领取")) + 4, ly + 36), data['commPending'], cn_font=F24, en_font=M24, fill=C_PRIMARY)

    ly += 85 + 16
    d.line([(lx, ly), (lx + content_w, ly)], fill=C_BORDER, width=1)
    ly += 16

    # 2. 每日活跃
    _draw_rounded_rect(canvas, lx, ly + 4, lx + 18, ly + 22, 4, C_PRIMARY)
    draw_text_mixed(d, (lx + 26, ly), "每日活跃", cn_font=F22, en_font=M22, fill=C_TEXT_MAIN)

    aw = int(F32.getlength(data['activeCur']))
    draw_text_mixed(d, (lx + content_w - aw - int(F20.getlength(f" / {data['activeMax']}")), ly - 4), data['activeCur'], cn_font=F32, en_font=M32, fill=C_PRIMARY)
    draw_text_mixed(d, (lx + content_w - int(F20.getlength(f" / {data['activeMax']}")), ly + 8), f" / {data['activeMax']}", cn_font=F20, en_font=M20, fill=C_TEXT_GRAY)

    a_bar_y = ly + 40
    _draw_rounded_rect(canvas, lx, a_bar_y, lx + content_w, a_bar_y + 6, 3, (229, 233, 240, 255))
    if data['activePercent'] > 0:
        f_aw = int(content_w * data['activePercent'])
        _draw_rounded_rect(canvas, lx, a_bar_y, lx + f_aw, a_bar_y + 6, 3, C_PRIMARY)

    ly += 60 + 16

    # 3. 任务网格
    t_card_w = (content_w - 12) // 2
    for i, task in enumerate(data['tasks']):
        col = i % 2
        row = i // 2
        tx = lx + col * (t_card_w + 12)
        ty = ly + row * (92 + 12)
        
        _draw_rounded_rect(canvas, tx, ty, tx + t_card_w, ty + 92, 4, (255,255,255,0))
        d.rounded_rectangle([tx, ty, tx + t_card_w, ty + 92], radius=4, outline=C_BORDER, width=1)
        
        draw_text_mixed(d, (tx + 16, ty + 16), task['name'], cn_font=F20, en_font=M20, fill=C_TEXT_MAIN)
        
        time_w = int(F16.getlength(task['time']))
        t_col = C_URGENT if task['timeUrgent'] else C_TEXT_GRAY
        draw_text_mixed(d, (tx + t_card_w - 16 - time_w, ty + 20), task['time'], cn_font=F16, en_font=M16, fill=t_col)

        cur_col = C_DONE if task['done'] else C_PRIMARY
        draw_text_mixed(d, (tx + 16, ty + 46), task['cur'], cn_font=F30, en_font=M30, fill=cur_col)
        cw = int(F30.getlength(task['cur'])) + 4
        
        draw_text_mixed(d, (tx + 16 + cw, ty + 56), f" / {task['max']}", cn_font=F18, en_font=M18, fill=C_TEXT_GRAY)

        line_col = C_DONE if task['done'] else C_PRIMARY
        _draw_rounded_rect(canvas, tx + 16, ty + 88, tx + t_card_w - 16, ty + 92, 2, line_col)

    y += main_h + 20

    out_rgb = canvas.crop((0, 0, W, y)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()