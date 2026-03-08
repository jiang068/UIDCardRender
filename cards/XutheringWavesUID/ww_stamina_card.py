# 鸣潮体力卡片渲染器 (PIL 版 · 复刻 HTML 样式)

from __future__ import annotations

import base64
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

# 画布尺寸
W = 1150
H = 850

# 颜色
C_BG          = (15, 17, 21, 255)       # #0f1115
C_WHITE       = (255, 255, 255, 255)
C_GOLD        = (212, 177, 99, 255)     # #d4b163
C_URGENT_BG   = (186, 55, 42, 230)      # rgba(186, 55, 42, 0.9)
C_TIME_BG     = (0, 0, 0, 128)          # rgba(0, 0, 0, 0.5)
C_TRACK       = (0, 0, 0, 76)           # rgba(0, 0, 0, 0.3)
C_FILL_DEF    = (212, 177, 99, 255)     # 默认进度条填充颜色


# 【关键修改 1】：不仅导入 F 系列(中文)，还要导入 M 系列(英文) 和混排引擎
from . import F14, F18, F20, F22, F24, F28, F30, F40, F42, F46
from . import M14, M18, M20, M22, M24, M28, M30, M40, M42, M46
from . import draw_text_mixed

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    text_h = bb[3] - bb[1]
    return (box_h - text_h) // 2 - bb[1] + 1

# 【关键修改 2】：重写阴影文字绘制函数，让它内部使用智能混排
def _draw_text_shadow(d: ImageDraw.ImageDraw, xy: tuple, text: str, cn_font, en_font, fill, shadow=(0,0,0,200), offset=(0,2)):
    x, y = xy
    draw_text_mixed(d, (x + offset[0], y + offset[1]), text, cn_font=cn_font, en_font=en_font, fill=shadow)
    draw_text_mixed(d, (x, y), text, cn_font=cn_font, en_font=en_font, fill=fill)


# 图片与蒙版处理缓存
@lru_cache(maxsize=256)
def _b64_img(src: str) -> Image.Image:
    if "," in src:
        src = src.split(",", 1)[1]
    return Image.open(BytesIO(base64.b64decode(src))).convert("RGBA")

@lru_cache(maxsize=256)
def _b64_fit(src: str, w: int, h: int) -> Image.Image:
    img = _b64_img(src)
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    if scale < 0.5:
        img = img.resize((max(nw * 2, w), max(nh * 2, h)), Image.BOX)
        scale = max(w / img.width, h / img.height)
        nw, nh = int(img.width * scale), int(img.height * scale)
    img = img.resize((nw, nh), Image.BILINEAR)
    x, y = (nw - w) // 2, (nh - h) // 2
    return img.crop((x, y, x + w, y + h))

@lru_cache(maxsize=64)
def _round_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return mask


# 渐变背景绘制
def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, r: int, fill: tuple):
    w, h = x1 - x0, y1 - y0
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill)
    canvas.alpha_composite(block, (x0, y0))

def _draw_h_gradient(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, left_rgba: tuple, right_rgba: tuple, r: int = 0):
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    grad_1d = Image.new("RGBA", (w, 1))
    for xi in range(w):
        t = xi / max(w - 1, 1)
        if t <= 0.6:
            a = int(left_rgba[3] - (left_rgba[3] * 0.5) * (t / 0.6))
        else:
            a = int((left_rgba[3] * 0.5) * (1.0 - (t - 0.6) / 0.4))
        color = (left_rgba[0], left_rgba[1], left_rgba[2], a)
        grad_1d.putpixel((xi, 0), color)
    grad = grad_1d.resize((w, h), Image.NEAREST)
    if r > 0:
        mask = _round_mask(w, h, r)
        new_a = ImageChops.multiply(grad.split()[3], mask)
        grad.putalpha(new_a)
    canvas.alpha_composite(grad, (x0, y0))

def _draw_v_gradient(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, top_rgba: tuple, bottom_rgba: tuple):
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    grad_1d = Image.new("RGBA", (1, h))
    for yi in range(h):
        t = yi / max(h - 1, 1)
        color = tuple(int(top_rgba[i] + (bottom_rgba[i] - top_rgba[i]) * t) for i in range(4))
        grad_1d.putpixel((0, yi), color)
    grad = grad_1d.resize((w, h), Image.NEAREST)
    canvas.alpha_composite(grad, (x0, y0))


# HTML 解析
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg_src": "", "char_src": "", "top_status": [],
        "sidebar": {"title": "每日状态", "time_badge": "", "is_urgent": False, "rows": []},
        "user": {"avatar_src": "", "name": "", "uid": ""},
        "footer_stats": []
    }

    bg = soup.select_one(".bg-layer .bg-image")
    if bg: data["bg_src"] = bg.get("src", "")

    char = soup.select_one(".char-layer")
    if char: data["char_src"] = char.get("src", "")

    for badge in soup.select(".top-status .status-badge"):
        img = badge.select_one("img")
        span = badge.select_one("span")
        if span:
            data["top_status"].append({
                "icon": img.get("src", "") if img else "",
                "text": span.get_text(strip=True)
            })

    head_title = soup.select_one(".sidebar-header .header-title")
    if head_title: data["sidebar"]["title"] = head_title.get_text(strip=True)
    time_badge = soup.select_one(".sidebar-header .time-badge")
    if time_badge:
        data["sidebar"]["time_badge"] = time_badge.get_text(strip=True)
        data["sidebar"]["is_urgent"] = "urgent" in time_badge.get("class", [])

    for row in soup.select(".stat-row"):
        icon = row.select_one(".stat-icon")
        name = row.select_one(".stat-name")
        cur = row.select_one(".stat-cur")
        tot = row.select_one(".stat-total")
        fill = row.select_one(".progress-fill")

        ratio = 0.0
        fill_color = C_FILL_DEF
        
        if fill and "style" in fill.attrs:
            style_str = fill["style"]
            w_match = re.search(r"width:\s*([\d.]+)%", style_str)
            if w_match: ratio = float(w_match.group(1)) / 100.0

        if ratio == 0.0 and cur and tot:
            try:
                c_val = float(re.sub(r'[^\d.]', '', cur.get_text()))
                t_val = float(re.sub(r'[^\d.]', '', tot.get_text()))
                if t_val > 0: ratio = min(c_val / t_val, 1.0)
            except: pass

        data["sidebar"]["rows"].append({
            "icon": icon.get("src", "") if icon else "",
            "name": name.get_text(strip=True) if name else "",
            "cur": cur.get_text(strip=True) if cur else "",
            "total": tot.get_text(strip=True).replace("/", "").strip() if tot else "",
            "ratio": ratio, "color": fill_color
        })

    av = soup.select_one(".user-section .avatar-img")
    if av: data["user"]["avatar_src"] = av.get("src", "")
    uname = soup.select_one(".user-section .user-name")
    if uname: data["user"]["name"] = uname.get_text(strip=True)
    uuid = soup.select_one(".user-section .user-uid")
    if uuid: data["user"]["uid"] = uuid.get_text(strip=True).replace("UID", "").strip()

    for stat in soup.select(".footer-stats .mini-stat"):
        val = stat.select_one(".mini-val")
        lbl = stat.select_one(".mini-label")
        sub = stat.select_one(".mini-sub")
        if val and lbl:
            data["footer_stats"].append({
                "val": val.get_text(strip=True),
                "label": lbl.get_text(strip=True),
                "sub": sub.get_text(strip=True) if sub else ""
            })
    return data


# 主渲染逻辑
def render(html: str) -> bytes:
    data = parse_html(html)
    canvas = Image.new("RGBA", (W, H), C_BG)
    d = ImageDraw.Draw(canvas)

    # 1. 绘制底层背景图
    if data["bg_src"]:
        try:
            bg = _b64_fit(data["bg_src"], W, H)
            canvas.alpha_composite(bg)
        except: pass

    # 2. 绘制右侧立绘层 (char-layer)
    if data["char_src"]:
        try:
            char_img = _b64_img(data["char_src"])
            scale = H / char_img.height
            cw, ch = int(char_img.width * scale), int(char_img.height * scale)
            char_img = char_img.resize((cw, ch), Image.LANCZOS)
            
            shadow = Image.new("RGBA", char_img.size, (0, 0, 0, 0))
            shadow.paste((0, 0, 0, 100), char_img.split()[3])
            shadow = shadow.filter(ImageFilter.GaussianBlur(10))
            
            cx = W - cw + 30
            cy = -90
            canvas.alpha_composite(shadow, (cx - 10, cy))
            canvas.alpha_composite(char_img, (cx, cy))
        except: pass

    # 3. Footer 底部渐变背景
    FOOTER_H = 160
    _draw_v_gradient(canvas, 0, H - FOOTER_H, W, H, (0, 0, 0, 0), (0, 0, 0, 217))

    # 4. 绘制 Top Status Badges (左上角)
    tx, ty = 40, 50
    for badge in data["top_status"]:
        bw = int(F22.getlength(badge["text"])) + 24 + 10 + 40
        bh = 40
        _draw_rounded_rect(canvas, tx, ty, tx + bw, ty + bh, 20, (0, 0, 0, 140))
        d.rounded_rectangle([tx, ty, tx + bw, ty + bh], radius=20, outline=(255,255,255,40), width=1)
        
        icon_x = tx + 16
        if badge["icon"]:
            try:
                icon_img = _b64_fit(badge["icon"], 24, 24)
                canvas.alpha_composite(icon_img, (icon_x, ty + 8))
            except: pass
        
        # 【修改 3】：传入中/英两套字体
        _draw_text_shadow(d, (icon_x + 30, ty + _ty(F22, badge["text"], bh)), badge["text"], F22, M22, C_WHITE)
        tx += bw + 15

    # 5. 绘制 Sidebar (左侧主体数据)
    sb_x = 40
    sb_y = 150
    sb_w = 480 
    
    _draw_text_shadow(d, (sb_x + 10, sb_y), data["sidebar"]["title"], F28, M28, C_WHITE)
    
    if data["sidebar"]["time_badge"]:
        t_text = data["sidebar"]["time_badge"]
        tw = int(F20.getlength(t_text)) + 36
        th = 36
        tx_badge = sb_x + sb_w - tw
        bg_col = C_URGENT_BG if data["sidebar"]["is_urgent"] else C_TIME_BG
        _draw_rounded_rect(canvas, tx_badge, sb_y - 2, tx_badge + tw, sb_y - 2 + th, 18, bg_col)
        # 替换普通的 d.text
        draw_text_mixed(d, (tx_badge + 18, sb_y - 2 + _ty(F20, t_text, th)), t_text, F20, M20, C_WHITE)

    sb_y += 55

    for row in data["sidebar"]["rows"]:
        row_h = 140  
        _draw_h_gradient(canvas, sb_x, sb_y, sb_x + sb_w, sb_y + row_h, (0,0,0,102), (0,0,0,0), r=16)

        if row["icon"]:
            try:
                r_icon = _b64_fit(row["icon"], 84, 84)
                canvas.alpha_composite(r_icon, (sb_x + 25, sb_y + 14))
            except: pass
        
        text_x = sb_x + 25 + 84 + 20
        _draw_text_shadow(d, (text_x, sb_y + 20), row["name"], F22, M22, (255,255,255,240))
        
        cur_w = F46.getlength(row["cur"])
        _draw_text_shadow(d, (text_x, sb_y + 54), row["cur"], F46, M46, C_WHITE, offset=(0,2))
        
        if row["total"]:
            total_str = f" / {row['total']}"
            _draw_text_shadow(d, (text_x + cur_w + 5, sb_y + 68), total_str, F30, M30, (255,255,255,200))
        
        track_w = sb_w - 50
        track_y = sb_y + row_h - 26
        _draw_rounded_rect(canvas, sb_x + 25, track_y, sb_x + 25 + track_w, track_y + 8, 4, C_TRACK)
        
        fill_w = int(track_w * row["ratio"])
        if fill_w > 0:
            _draw_rounded_rect(canvas, sb_x + 25, track_y, sb_x + 25 + fill_w, track_y + 8, 4, row["color"])
        
        sb_y += row_h + 30

    # 6. 绘制 Footer User Section & Stats
    fy = H - FOOTER_H
    
    av_x = 40
    av_y = fy + (FOOTER_H - 110) // 2
    av_size = 110
    _draw_rounded_rect(canvas, av_x, av_y, av_x + av_size, av_y + av_size, av_size//2, (0,0,0,76))
    if data["user"]["avatar_src"]:
        try:
            av_img = _b64_fit(data["user"]["avatar_src"], av_size, av_size)
            rmask = _round_mask(av_size, av_size, av_size//2)
            canvas.paste(av_img, (av_x, av_y), rmask)
        except: pass
    d.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], outline=(212, 177, 99, 204), width=3)

    user_tx = av_x + av_size + 25
    _draw_text_shadow(d, (user_tx, av_y + 15), data["user"]["name"], F40, M40, C_WHITE)
    uid_str = f"UID {data['user']['uid']}"
    _draw_text_shadow(d, (user_tx, av_y + 65), uid_str, F24, M24, C_GOLD)

    stat_x = W - 40
    C_WARN_RED = (255, 80, 80, 255)  

    for i, stat in enumerate(reversed(data["footer_stats"])):
        val_text = stat["val"]
        lbl_text = stat["label"]
        
        s_val_w = F42.getlength(val_text)
        s_lbl_w = F18.getlength(lbl_text)
        block_w = max(s_val_w, s_lbl_w, 100)
        
        sx = stat_x - block_w
        val_x = sx + (block_w - s_val_w) // 2
        val_y = fy + 35
        
        if '/' in val_text:
            n_str, d_str = val_text.split('/', 1)
            if n_str.strip() != d_str.strip():
                _draw_text_shadow(d, (val_x, val_y), n_str, F42, M42, C_WARN_RED)
                n_w = F42.getlength(n_str)
                _draw_text_shadow(d, (val_x + n_w, val_y), "/" + d_str, F42, M42, C_WHITE)
            else:
                _draw_text_shadow(d, (val_x, val_y), val_text, F42, M42, C_WHITE)
        else:
            if lbl_text == "千道门扉" and val_text != "6000":
                _draw_text_shadow(d, (val_x, val_y), val_text, F42, M42, C_WARN_RED)
            else:
                _draw_text_shadow(d, (val_x, val_y), val_text, F42, M42, C_WHITE)

        _draw_text_shadow(d, (sx + (block_w - s_lbl_w)//2, fy + 85), lbl_text, F18, M18, (255,255,255,200))
        
        if stat["sub"]:
            s_sub_w = F14.getlength(stat["sub"])
            _draw_text_shadow(d, (sx + (block_w - s_sub_w)//2, fy + 110), stat["sub"], F14, M14, (255,255,255,150))
        
        if i < len(data["footer_stats"]) - 1:
            line_x = sx - 17
            d.line([(line_x, fy + 50), (line_x, fy + 110)], fill=(255,255,255,76), width=1)
            stat_x = sx - 35
        else:
            stat_x = sx - 35

    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()