# 明日方舟：终末地 每日卡片渲染器 (PIL 版)

from __future__ import annotations

import re
from io import BytesIO
import math

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# 从 __init__.py 导入字体与工具函数
from . import F14, F16, F18, F28, F40, F60
from . import M12, M14, M16, M28
from . import O20, O40, O52, O60
from . import draw_text_mixed, _b64_img, _b64_fit

# 画布尺寸与颜色
W, H = 1150, 850
C_BG = (15, 16, 20, 255)
C_ACCENT = (255, 230, 0, 255)
C_TEXT = (255, 255, 255, 255)
C_BORDER = (255, 255, 255, 51) # rgba(255,255,255,0.2)

# --- HTML 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg_src": "", "char_src": "", "logo_src": "",
        "header": {"title": "Endfield Daily", "subtitle": "每日监控协议 // MONITORING", "recovery": "", "is_urgent": False},
        "stats": [],
        "user": {"avatar": "", "name": "", "uid": ""},
        "footer_stats": []
    }

    bg = soup.select_one(".bg-image")
    if bg: data["bg_src"] = bg.get("src", "")
    char = soup.select_one(".char-layer")
    if char: data["char_src"] = char.get("src", "")
    logo = soup.select_one(".logo")
    if logo: data["logo_src"] = logo.get("src", "")

    tb = soup.select_one(".time-badge")
    if tb:
        data["header"]["recovery"] = tb.get_text(strip=True).replace("RECOVERY", "").strip()
        data["header"]["is_urgent"] = "urgent" in tb.get("class", [])

    for card in soup.select(".stat-card"):
        icon = card.select_one(".stat-icon")
        cn = card.select_one(".stat-name-cn")
        en = card.select_one(".stat-name-en")
        cur = card.select_one(".stat-cur")
        tot = card.select_one(".stat-total")
        fill = card.select_one(".progress-fill")
        
        ratio = 0.0
        color = (255, 255, 255, 255)
        if fill and "style" in fill.attrs:
            st = fill["style"]
            m_w = re.search(r"width:\s*([\d.]+)%", st)
            if m_w: ratio = float(m_w.group(1)) / 100.0
            
            m_c = re.search(r"background-color:\s*(#[0-9a-fA-F]+|rgba?\([^)]+\))", st)
            if m_c:
                c_str = m_c.group(1).strip()
                if c_str.startswith("#"):
                    c_str = c_str.lstrip('#')
                    color = tuple(int(c_str[i:i+2], 16) for i in (0, 2, 4)) + (255,)
                elif c_str.startswith("rgb"):
                    nums = [int(x) for x in re.findall(r'\d+', c_str)]
                    if len(nums) >= 3: color = (nums[0], nums[1], nums[2], 255)

        data["stats"].append({
            "icon": icon.get("src", "") if icon else "",
            "cn": cn.get_text(strip=True) if cn else "",
            "en": en.get_text(strip=True) if en else "",
            "cur": cur.get_text(strip=True) if cur else "",
            "total": tot.get_text(strip=True).replace("/", "").strip() if tot else "",
            "ratio": ratio,
            "color": color
        })

    u_name = soup.select_one(".user-name")
    u_uid = soup.select_one(".user-uid")
    u_av = soup.select_one(".avatar-img")
    if u_name: data["user"]["name"] = u_name.get_text(strip=True)
    if u_uid: data["user"]["uid"] = u_uid.get_text(strip=True)
    if u_av: data["user"]["avatar"] = u_av.get("src", "")

    for m in soup.select(".mini-stat-box"):
        lbl = m.select_one(".mini-label")
        val = m.select_one(".mini-val")
        if lbl and val:
            v_text = val.get_text(strip=True).replace("MAX", "").strip()
            data["footer_stats"].append({
                "lbl": lbl.get_text(strip=True),
                "val": v_text,
                "is_max": "MAX" in val.get_text()
            })

    return data


# --- 绘图组件 ---
def draw_bg_grid(canvas: Image.Image, w: int, h: int):
    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(grid)
    line_c = (38, 39, 44, 180)
    for x in range(0, w, 50): d.line([(x, 0), (x, h)], fill=line_c, width=1)
    for y in range(0, h, 50): d.line([(0, y), (w, y)], fill=line_c, width=1)
    canvas.alpha_composite(grid)

def get_radial_gradient(w: int, h: int) -> Image.Image:
    sw, sh = w // 10, h // 10
    cx, cy = int(sw * 0.7), int(sh * 0.4)
    grad = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    max_dist = math.hypot(max(cx, sw - cx), max(cy, sh - cy))
    
    for y in range(sh):
        for x in range(sw):
            d = math.hypot(x - cx, y - cy)
            ratio = d / max_dist
            if ratio < 0.4: a = int(153 * (ratio / 0.4))
            elif ratio < 0.9: a = int(153 + (250 - 153) * ((ratio - 0.4) / 0.5))
            else: a = 250
            grad.putpixel((x, y), (15, 16, 20, a))
            
    return grad.resize((w, h), Image.Resampling.LANCZOS)

def draw_hexagon(img: Image.Image, size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    p = [
        (size * 0.15, 0), (size, 0), (size, size * 0.85),
        (size * 0.85, size), (0, size), (0, size * 0.15)
    ]
    d.polygon(p, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    ImageDraw.Draw(out).polygon(p, outline=(255, 255, 255, 76), width=2)
    return out


# --- 主渲染逻辑 ---
def render(html: str) -> bytes:
    data = parse_html(html)
    canvas = Image.new("RGBA", (W, H), C_BG)
    d = ImageDraw.Draw(canvas)

    # 1. 底图与氛围层
    if data["bg_src"]:
        try:
            bg = _b64_fit(data["bg_src"], W, H)
            bg = bg.convert("L").convert("RGBA")
            enhancer = Image.new("RGBA", (W, H), (0, 0, 0, 100))
            canvas.alpha_composite(bg)
            canvas.alpha_composite(enhancer)
        except Exception: pass
        
    draw_bg_grid(canvas, W, H)
    canvas.alpha_composite(get_radial_gradient(W, H))

    # 2. 右侧人物立绘层
    if data["char_src"]:
        try:
            char_img = _b64_img(data["char_src"])
            cw, ch = int(char_img.width * (892 / char_img.height)), 892
            char_img = char_img.resize((cw, ch), Image.Resampling.LANCZOS)
            
            mask = Image.new("L", (cw, ch), 255)
            md = ImageDraw.Draw(mask)
            fade_w = int(cw * 0.22)
            for x in range(fade_w):
                alpha = int(255 * (x / fade_w))
                md.line([(x, 0), (x, ch)], fill=alpha)
            
            shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            shadow.paste((0, 0, 0, 128), char_img.split()[3])
            shadow = shadow.filter(ImageFilter.GaussianBlur(10))
            
            cx = W - cw + 80
            cy = -40
            
            char_final = Image.new("RGBA", (cw, ch), (0,0,0,0))
            char_final.paste(char_img, (0,0), mask=ImageChops.multiply(char_img.split()[3], mask))
            
            canvas.alpha_composite(shadow, (cx - 10, cy + 5))
            canvas.alpha_composite(char_final, (cx, cy))
        except Exception: pass

    # 3. UI 顶层元素
    if data["logo_src"]:
        try:
            logo = _b64_img(data["logo_src"])
            lw, lh = 190, int(logo.height * (190 / logo.width))
            logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
            canvas.alpha_composite(logo, (40, 15))
        except Exception: pass

    # 4. HUD 侧边栏 (Header)
    sb_x, sb_y = 45, 120
    sb_w = 480
    
    d.rectangle([sb_x, sb_y, sb_x + 8, sb_y + 85], fill=C_ACCENT)
    
    draw_text_mixed(d, (sb_x + 20, sb_y - 10), data["header"]["title"].upper(), cn_font=O60, en_font=O60, fill=C_TEXT)
    # 使用 dy_cn 将副标题的中文字体单独向上提 2 像素（视觉上调平）
    draw_text_mixed(d, (sb_x + 20, sb_y + 60), data["header"]["subtitle"], cn_font=F16, en_font=M16, fill=C_ACCENT, dy_cn=-2)
    
    tb_y = sb_y + 90
    tb_bg = (255, 77, 79, 38) if data["header"]["is_urgent"] else (255, 255, 255, 20)
    tb_border = (255, 77, 79, 255) if data["header"]["is_urgent"] else (255, 255, 255, 25)
    tb_color = (255, 77, 79, 255) if data["header"]["is_urgent"] else (221, 221, 221, 255)
    
    t_text = f"RECOVERY  {data['header']['recovery']}"
    tb_w = int(F14.getlength(t_text)) + 30
    
    d.rectangle([sb_x + 20, tb_y, sb_x + 20 + tb_w, tb_y + 28], fill=tb_bg, outline=tb_border, width=1)
    # 使用 dy_cn 将 recovery 的中文字体向上提 3 像素，以弥补之前的落差
    draw_text_mixed(d, (sb_x + 35, tb_y + 5), t_text, cn_font=F14, en_font=F14, fill=tb_color, dy_cn=-3)

    sb_y += 145

    # 5. 状态卡片 (自适应间距，而非拉伸卡片)
    ft_y = H - 100 - 20 # 底部 Footer 的 Y 坐标
    avail_h = ft_y - sb_y - 15 
    num_cards = len(data["stats"])
    
    # 设定一个看起来比例最舒服的固定卡片高度（比105略宽一点点）
    c_h = 115 
    c_gap = 25
    
    if num_cards > 1:
        # 让“间距”去自适应剩余高度，而不是把卡片撑胖
        c_gap = (avail_h - c_h * num_cards) // (num_cards - 1)
        # 限制一下最大间距，防止卡片散得太开
        c_gap = min(c_gap, 40)

    for stat in data["stats"]:
        poly = [
            (sb_x, sb_y), (sb_x + sb_w, sb_y), 
            (sb_x + sb_w, sb_y + c_h * 0.82), 
            (sb_x + sb_w * 0.96, sb_y + c_h), 
            (sb_x, sb_y + c_h)
        ]
        
        c_bg = Image.new("RGBA", (sb_w, c_h), (30, 32, 35, 120))
        c_mask = Image.new("L", (sb_w, c_h), 0)
        ImageDraw.Draw(c_mask).polygon([(p[0]-sb_x, p[1]-sb_y) for p in poly], fill=255)
        
        c_layer = Image.new("RGBA", (W, H), (0,0,0,0))
        c_layer.paste(c_bg, (sb_x, sb_y), c_mask)
        canvas.alpha_composite(c_layer)
        
        d.polygon(poly, outline=C_BORDER, width=1)
        
        d.polygon([
            (sb_x + sb_w - 20, sb_y + c_h), 
            (sb_x + sb_w, sb_y + c_h - 20), 
            (sb_x + sb_w, sb_y + c_h)
        ], fill=(255, 230, 0, 204))

        # 内部元素根据拉高后的 c_h 进行自动居中偏移计算
        iy = sb_y + (c_h - 30 - 54) // 2
        
        # Icon
        ix = sb_x + 25
        d.rectangle([ix, iy, ix + 54, iy + 54], fill=(0,0,0,102), outline=(255,255,255,38))
        if stat["icon"]:
            try:
                icon_img = _b64_fit(stat["icon"], 36, 36)
                canvas.alpha_composite(icon_img, (ix + 9, iy + 9))
            except Exception: pass
            
        # 标签
        tx = ix + 72
        draw_text_mixed(d, (tx, iy - 4), stat["cn"], cn_font=F28, en_font=F28, fill=C_TEXT)
        draw_text_mixed(d, (tx, iy + 34), stat["en"].upper(), cn_font=M12, en_font=M12, fill=(119, 119, 119, 255))
        
        # 数值右对齐
        vx = sb_x + sb_w - 25
        tot_w = O20.getlength(f"/{stat['total']}") if stat["total"] and stat['total'] != "LEVEL" else O20.getlength(stat['total'])
        cur_w = O52.getlength(stat["cur"])
        
        if stat["total"] == "LEVEL":
            draw_text_mixed(d, (vx - tot_w, iy + 25), "LEVEL", cn_font=O20, en_font=O20, fill=(102, 102, 102, 255))
            draw_text_mixed(d, (vx - tot_w - cur_w - 5, iy - 6), stat["cur"], cn_font=O52, en_font=O52, fill=C_TEXT)
        else:
            draw_text_mixed(d, (vx - tot_w, iy + 25), f"/{stat['total']}", cn_font=O20, en_font=O20, fill=(102, 102, 102, 255))
            draw_text_mixed(d, (vx - tot_w - cur_w - 5, iy - 6), stat["cur"], cn_font=O52, en_font=O52, fill=C_TEXT)

        # 进度条位置自适应下压
        px, py = sb_x + 25, sb_y + c_h - 22
        pw, ph = sb_w - 50, 6
        d.rectangle([px, py, px + pw, py + ph], fill=(255, 255, 255, 25))
        
        fill_w = int(pw * stat["ratio"])
        if fill_w > 0:
            fill_c = stat["color"]
            d.rectangle([px, py, px + fill_w, py + ph], fill=fill_c)
            d.rectangle([px + fill_w - 2, py, px + fill_w, py + ph], fill=(255,255,255,255))

        sb_y += c_h + c_gap

    # 6. Footer (底栏)
    ft_right = W - 45
    ft_left = 45
    
    ms_x = ft_right
    cards_info = []
    for ms in reversed(data["footer_stats"]):
        mw = 160 if ms["is_max"] else 120
        cards_info.append({
            "lbl": ms["lbl"], "val": ms["val"], "is_max": ms["is_max"],
            "x": ms_x - mw, "w": mw
        })
        ms_x -= (mw + 15)

    # 渲染右侧小卡片
    for info in cards_info:
        cx = info["x"]
        cw = info["w"]
        
        card_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card_layer)
        cd.rectangle([cx, ft_y, cx + cw, ft_y + 100], fill=(0, 0, 0, 160), outline=C_BORDER)
        canvas.alpha_composite(card_layer)
        
        d.line([(cx - 1, ft_y - 1), (cx + 10, ft_y - 1)], fill=C_ACCENT, width=3)
        d.line([(cx - 1, ft_y - 1), (cx - 1, ft_y + 10)], fill=C_ACCENT, width=3)
        
        # 将此处改为严格左对齐 (固定加上 20 的内边距)
        draw_text_mixed(d, (cx + 20, ft_y + 18), info["lbl"], cn_font=F14, en_font=M14, fill=(153, 153, 153, 255))
        
        if info["is_max"]:
            draw_text_mixed(d, (cx + 20, ft_y + 42), info["val"], cn_font=O40, en_font=O40, fill=C_TEXT)
            v_w = int(O40.getlength(info["val"]))
            draw_text_mixed(d, (cx + 20 + v_w + 5, ft_y + 60), "MAX", cn_font=O20, en_font=O20, fill=(102, 102, 102, 255))
        else:
            draw_text_mixed(d, (cx + 20, ft_y + 42), info["val"], cn_font=O40, en_font=O40, fill=C_TEXT)
            
    # === 渲染左侧大 User Card ===
    uc_right = ms_x
    uc_w = uc_right - ft_left
    
    uc_poly = [(ft_left, ft_y), (ft_left + uc_w, ft_y), (ft_left + uc_w - 20, ft_y + 100), (ft_left, ft_y + 100)]
    uc_bg = Image.new("RGBA", (W, H), (0,0,0,0))
    ImageDraw.Draw(uc_bg).polygon(uc_poly, fill=(255, 255, 255, 12))
    canvas.alpha_composite(uc_bg)
    d.rectangle([ft_left, ft_y, ft_left + 6, ft_y + 100], fill=C_ACCENT)
    
    ax, ay = ft_left + 30, ft_y + 15
    d.polygon([
        (ax + 10.5, ay), (ax + 70, ay), (ax + 70, ay + 59.5),
        (ax + 59.5, ay + 70), (ax, ay + 70), (ax, ay + 10.5)
    ], fill=(34, 34, 34, 255))
    
    if data["user"]["avatar"]:
        try:
            av_img = _b64_fit(data["user"]["avatar"], 70, 70)
            canvas.alpha_composite(draw_hexagon(av_img, 70), (ax, ay))
        except Exception: pass
        
    ux = ax + 90
    draw_text_mixed(d, (ux, ft_y + 20), data["user"]["name"], cn_font=F28, en_font=F28, fill=C_TEXT)
    draw_text_mixed(d, (ux, ft_y + 58), f"UID_{data['user']['uid']}", cn_font=M16, en_font=M16, fill=C_ACCENT)

    # 最终输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()