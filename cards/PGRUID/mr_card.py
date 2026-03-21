# 战双体力与日程辅助 卡片渲染器 (PIL 极致性能版)

from __future__ import annotations

import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 从同一包内导入统一资源
from . import (
    F14, F16, F18, F20, F22, F24, F26, F28, F30, F32, F42,
    M14, M16, M18, M20, M22, M24, M26, M28, M30, M32, M42,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask
)

# --- 尺寸与颜色常量 ---
W = 800
PAD = 24
INNER_W = W - PAD * 2  # 752

C_BG_PAGE = (226, 235, 245, 255)    # #e2ebf5
C_PRIMARY = (27, 115, 201, 255)     # #1b73c9
C_TEXT_MAIN = (43, 43, 43, 255)     # #2b2b2b
C_TEXT_GRAY = (140, 147, 157, 255)  # #8c939d
C_BORDER = (220, 227, 235, 255)     # #dce3eb
C_URGENT = (255, 77, 79, 255)       # #ff4d4f
C_DONE = (39, 174, 96, 255)         # #27ae60

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

def _draw_clipped_rect(canvas: Image.Image, x: int, y: int, w: int, h: int, fill: tuple, outline: tuple=None):
    """绘制带右下角缺角的面板"""
    block = Image.new("RGBA", (w, h), (0,0,0,0))
    d = ImageDraw.Draw(block)
    points = [(0, 0), (w, 0), (w, h - 24), (w - 24, h), (0, h)]
    d.polygon(points, fill=fill)
    if outline:
        points.append((0, 0))
        d.line(points, fill=outline, width=1)
    canvas.alpha_composite(block, (x, y))

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
    data = {}

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

    t_bg = soup.select_one('.section-title-bar img')
    data['titleBgB64'] = t_bg['src'] if t_bg else ""

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
    if data['contentBgB64']:
        try:
            bg_img = _b64_img(data['contentBgB64'])
            bg_img = ImageOps.fit(bg_img, (W, MAX_H), Image.LANCZOS)
            canvas.alpha_composite(bg_img)
        except: pass

    d = ImageDraw.Draw(canvas)
    y = PAD

    # --- Header ---
    H_H = 168
    h_img = Image.new("RGBA", (INNER_W, H_H), (0,0,0,0))
    hd = ImageDraw.Draw(h_img)
    
    _draw_rounded_rect(h_img, 0, 0, INNER_W, H_H, 8, (20,25,35,255))
    if data['headerBgB64']:
        try:
            hbg = _b64_fit(data['headerBgB64'], INNER_W, H_H)
            h_img.paste(hbg, (0,0), _round_mask(INNER_W, H_H, 8))
        except: pass

    av_w, av_h = 120, 120
    av_x, av_y = 24, (H_H - av_h)//2
    
    if data['avatarBoxB64']:
        try:
            abox = _b64_fit(data['avatarBoxB64'], av_w, av_h)
            h_img.alpha_composite(abox, (av_x, av_y))
        except: pass

    if data['avatarB64']:
        try:
            aimg = _b64_fit(data['avatarB64'], 68, 68)
            cmask = Image.new("L", (68, 68), 0)
            ImageDraw.Draw(cmask).ellipse([0,0,67,67], fill=255)
            h_img.paste(aimg, (av_x + 26, av_y + 26), cmask)
        except: pass

    info_x = av_x + av_w + 16
    draw_text_mixed(hd, (info_x, av_y + 8), data['roleName'], cn_font=F28, en_font=M28, fill=(255,255,255,255))
    name_w = int(F28.getlength(data['roleName']))
    
    rank_x = info_x + name_w + 12
    rank_val = data['rank']
    val_w = int(F16.getlength(rank_val))
    box_w = 40 + val_w + 10 
    
    _draw_rounded_rect(h_img, rank_x, av_y + 14, rank_x + box_w, av_y + 38, 4, (25,30,40,204))
    hd.rounded_rectangle([rank_x, av_y + 14, rank_x + box_w, av_y + 38], radius=4, outline=(80,100,120,153), width=1)
    draw_text_mixed(hd, (rank_x + 10, av_y + 14 + _ty(F16, "勋阶", 24)), "勋阶", cn_font=F16, en_font=M16, fill=(155,174,194,255))
    draw_text_mixed(hd, (rank_x + 46, av_y + 14 + _ty(F16, rank_val, 24)), rank_val, cn_font=F16, en_font=M16, fill=(229,141,60,255))

    bottom_y = av_y + 76
    if data['serverName']:
        draw_text_mixed(hd, (info_x, bottom_y), data['serverName'], cn_font=F18, en_font=M18, fill=(140,158,181,255))
        sw = int(F18.getlength(data['serverName']))
        draw_text_mixed(hd, (info_x + sw + 4, bottom_y), "|", cn_font=F18, en_font=M18, fill=(74,90,117,255))
        draw_text_mixed(hd, (info_x + sw + 16, bottom_y), f"ID:{data['roleId']}", cn_font=F18, en_font=M18, fill=(140,158,181,255))
    else:
        draw_text_mixed(hd, (info_x, bottom_y), f"ID:{data['roleId']}", cn_font=F18, en_font=M18, fill=(140,158,181,255))

    canvas.alpha_composite(h_img, (PAD, y))
    y += H_H + 16

    # --- Title Bar ---
    T_H = 60
    _draw_v_gradient(canvas, PAD, y, PAD + INNER_W, y + T_H, (24, 45, 75, 255), (15, 25, 45, 255), r=6)
    if data['titleBgB64']:
        try:
            tbg = _b64_fit(data['titleBgB64'], INNER_W, T_H)
            canvas.paste(tbg, (PAD, y), _round_mask(INNER_W, T_H, 6))
        except: pass
    draw_text_mixed(d, (PAD + 20, y + _ty(F20, "日程助手", T_H)), "日程助手", cn_font=F20, en_font=M20, fill=(255,255,255,255))
    y += T_H + 16

    # --- Main Layout 计算动态高度 ---
    left_w = INNER_W - 240
    content_w = left_w - 32  
    task_rows = (len(data['tasks']) + 1) // 2
    task_grid_h = task_rows * 92 + max(0, task_rows - 1) * 12
    # 修复1：增加底部留白，使得任务卡片不紧贴底部裁切边缘 (16 改为 24)
    main_h = 16 + 85 + 16 + 60 + 16 + task_grid_h + 24

    # --- Main Layout 底图绘制 ---
    _draw_clipped_rect(canvas, PAD, y, INNER_W, main_h, fill=(255,255,255,255), outline=C_BORDER)

    # --- 修复2：右侧立绘透明混合 ---
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
            
            # 提取原图 Alpha 并应用 mask，然后进行 Alpha 混合，避免黑底
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
    s_bar_w = 180  # 稍微恢复一点进度条长度，跟上方的文字差不多宽即可
    
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

    # 【核心修复】：固定竖线和委托模块的位置，强制留出 200px 给血清数字
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
        
        _draw_rounded_rect(canvas, tx, ty, tx + t_card_w, ty + 92, 4, (255,255,255,0), outline=C_BORDER)
        
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