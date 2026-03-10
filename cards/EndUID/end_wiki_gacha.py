# 明日方舟：终末地 卡池信息卡片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 避免循环导入，直接引入工具函数并局部生成字体
# [修复] 补全了缺失的中文字体映射 F20, F24
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit,
    F12, F16, F18, F20, F24, F28, F56,
    M12, M16, M18, M20, M24
)

# 画布基础属性
W = 1000
PAD = 50
INNER_W = W - PAD * 2

# 颜色定义
C_BG = (15, 16, 20, 255)
C_ACCENT = (255, 230, 0, 255)
C_TEXT = (255, 255, 255, 255)
C_SUBTEXT = (139, 139, 139, 255)


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg": "", 
        "end_logo": "",
        "banners": []
    }

    # 背景与 Logo
    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg"] = bg_el.get("src", "")
    logo_el = soup.select_one(".footer-logo")
    if logo_el: data["end_logo"] = logo_el.get("src", "")

    # Banners 解析
    for bc in soup.select(".banner-card"):
        banner = {
            "icon": "", "type": "", "name": "", "target": "",
            "time_text": "", "time_status": "active", "events": [],
            "not_started": False
        }
        
        if "not-started" in bc.get("class", []):
            banner["not_started"] = True
            
        icon_img = bc.select_one(".banner-icon img")
        if icon_img: banner["icon"] = icon_img.get("src", "")
            
        type_el = bc.select_one(".banner-type")
        if type_el: banner["type"] = type_el.get_text(strip=True)
            
        name_el = bc.select_one(".banner-name")
        if name_el: banner["name"] = name_el.get_text(strip=True)
            
        target_el = bc.select_one(".banner-target")
        if target_el: banner["target"] = target_el.get_text(strip=True).replace("UP:", "").strip()
            
        time_el = bc.select_one(".banner-time")
        if time_el:
            banner["time_text"] = time_el.get_text(strip=True)
            cls = time_el.get("class", [])
            if "active" in cls: banner["time_status"] = "active"
            elif "upcoming" in cls: banner["time_status"] = "upcoming"
            elif "ended" in cls: banner["time_status"] = "ended"
                
        for ev in bc.select(".event-tag"):
            banner["events"].append(ev.get_text(strip=True))
            
        data["banners"].append(banner)

    return data


def draw_bg(canvas: Image.Image, w: int, h: int, bg_src: str):
    sw, sh = w // 10, h // 10
    cx, cy = int(sw * 0.5), int(sh * 0.2)
    grad = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    max_dist = math.hypot(max(cx, sw - cx), max(cy, sh - cy))
    
    for y in range(sh):
        for x in range(sw):
            dist = math.hypot(x - cx, y - cy)
            ratio = min(dist / max_dist, 1.0)
            r = int(34 + (15 - 34) * ratio)
            g = int(35 + (16 - 35) * ratio)
            b = int(40 + (20 - 40) * ratio)
            grad.putpixel((x, y), (r, g, b, 255))
            
    canvas.alpha_composite(grad.resize((w, h), Image.Resampling.LANCZOS))
    
    if bg_src:
        try:
            bg_img = _b64_fit(bg_src, w, h).convert("RGBA")
            bg_img.putalpha(Image.new("L", (w, h), 25)) # opacity 0.1
            canvas.alpha_composite(bg_img)
        except Exception: pass

    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    grid_c = (38, 39, 44, 180)
    for x in range(0, w, 40): gd.line([(x, 0), (x, h)], fill=grid_c, width=1)
    for y in range(0, h, 40): gd.line([(0, y), (w, y)], fill=grid_c, width=1)
    
    mask = Image.new("L", (w, h), 255)
    md = ImageDraw.Draw(mask)
    fade_h = int(h * 0.2)
    for y in range(fade_h, h):
        alpha = int(255 * (1 - min((y - fade_h) / (h * 0.8), 1.0)))
        md.line([(0, y), (w, y)], fill=alpha)
    grid.putalpha(mask)
    canvas.alpha_composite(grid)


def render(html: str) -> bytes:
    data = parse_html(html)
    
    # ---------------- 1. 高度预计算 ----------------
    cur_y = PAD
    
    # 页面标题
    cur_y += 60 + 35 + 30 
    
    # 动态 Banner 高度计算
    banner_heights = []
    if not data["banners"]:
        cur_y += 100 # no banners height
    else:
        for b in data["banners"]:
            bh = 25 * 2 # padding Y
            bh += 25 # type
            bh += 34 # name
            if b["target"]: bh += 24
            if b["time_text"]: bh += 26
            if b["events"]: bh += 30
            bh = max(170, bh)
            banner_heights.append(bh)
            cur_y += bh + 30
            
    # Footer
    cur_y += 10 + 40 + 20 # margin + pad + line
    total_h = max(cur_y, 600)
    
    # ---------------- 2. 实际绘制 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h, data["bg"])
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    
    # === Page Title ===
    # [修复] F56 补偿约 17px 使其视觉居中
    draw_text_mixed(d, (PAD, y + 12), "当前卡池", cn_font=F56, en_font=F56, fill=C_TEXT)
    # [修复] M24 补偿约 7px
    draw_text_mixed(d, (PAD, y + 60 + 7), "CURRENT BANNERS", cn_font=F24, en_font=M24, fill=C_SUBTEXT)
    y += 60 + 35 + 30
    
    # === Banners ===
    if not data["banners"]:
        draw_text_mixed(d, (W//2 - 60, y + 40), "暂无卡池信息", cn_font=F18, en_font=F18, fill=(102, 102, 102, 255))
        y += 100
    else:
        for i, b in enumerate(data["banners"]):
            bh = banner_heights[i]
            bx = PAD
            
            card_img = Image.new("RGBA", (INNER_W, bh), (0,0,0,0))
            cd = ImageDraw.Draw(card_img)
            
            for cx in range(INNER_W):
                alpha = int(20 + (5 - 20) * (cx / INNER_W))
                cd.line([(cx, 0), (cx, bh)], fill=(255, 255, 255, alpha))
            cd.rectangle([0, 0, INNER_W, bh], outline=(255, 255, 255, 25), width=1)
            cd.rectangle([0, 0, 6, bh], fill=C_ACCENT) 
            
            # 图标
            ic_x, ic_y = 30, (bh - 120)//2
            cd.rectangle([ic_x, ic_y, ic_x + 120, ic_y + 120], fill=(17, 17, 17, 255), outline=(255, 255, 255, 38), width=2)
            if b["icon"]:
                try:
                    ic = _b64_fit(b["icon"], 120, 120)
                    card_img.paste(ic, (ic_x, ic_y))
                except Exception: pass
            else:
                draw_text_mixed(cd, (ic_x + 50, ic_y + 40 + 7), "?", cn_font=F24, en_font=M24, fill=(51, 51, 51, 255))
                
            # 右侧信息
            tx = ic_x + 120 + 30
            ty = 25
            
            # [修复] 采用 F20 支持中文类型标签；补偿 6px
            draw_text_mixed(cd, (tx, ty + 6), b["type"], cn_font=F20, en_font=M20, fill=C_ACCENT)
            ty += 28
            
            # [修复] F28 补偿 8px
            draw_text_mixed(cd, (tx, ty + 8), b["name"], cn_font=F28, en_font=F28, fill=C_TEXT)
            ty += 34
            
            if b["target"]:
                # [修复] 补偿 5px
                draw_text_mixed(cd, (tx, ty + 5), f"UP: {b['target']}", cn_font=F18, en_font=M18, fill=(204, 204, 204, 255))
                ty += 24
                
            if b["time_text"]:
                t_w = int(F16.getlength(b["time_text"])) + 24
                tc = (136, 136, 136, 255)
                bg_c = (255, 255, 255, 12)
                if b["time_status"] == "active":
                    tc = (76, 255, 76, 255)
                    bg_c = (76, 255, 76, 25)
                elif b["time_status"] == "upcoming":
                    tc = C_ACCENT
                    bg_c = (255, 230, 0, 25)
                    
                cd.rounded_rectangle([tx, ty, tx + t_w, ty + 24], radius=2, fill=bg_c)
                # [修复] 采用 F16 支持中文时间文本；补偿 5px
                draw_text_mixed(cd, (tx + 12, ty + 3 + 5), b["time_text"], cn_font=F16, en_font=M16, fill=tc)
                ty += 30
                
            if b["events"]:
                ev_x = tx
                for ev in b["events"]:
                    ev_w = int(F16.getlength(ev)) + 24
                    cd.rounded_rectangle([ev_x, ty, ev_x + ev_w, ty + 24], radius=2, fill=(255, 255, 255, 15))
                    # [修复] 补偿 5px
                    draw_text_mixed(cd, (ev_x + 12, ty + 3 + 5), ev, cn_font=F16, en_font=F16, fill=(170, 170, 170, 255))
                    ev_x += ev_w + 8
            
            # 合并卡片到主画布
            if b["not_started"]:
                card_img.putalpha(ImageChops.multiply(card_img.split()[3], Image.new("L", (INNER_W, bh), 153))) 
                
            canvas.alpha_composite(card_img, (bx, y))
            y += bh + 30
            
    # === Footer ===
    y += 10
    d.line([(PAD, y), (W - PAD, y)], fill=(255, 255, 255, 25), width=1)
    y += 20
    
    if data["end_logo"]:
        try:
            logo = _b64_img(data["end_logo"])
            lh = 40
            lw = int(logo.width * (lh / logo.height))
            logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
            logo.putalpha(ImageChops.multiply(logo.split()[3], Image.new("L", (lw, lh), 153)))
            canvas.alpha_composite(logo, (PAD, y))
        except Exception: pass
        
    fw = int(M12.getlength("ENDFIELD WIKI"))
    # [修复] 基线补偿 4px
    draw_text_mixed(d, (W - PAD - fw, y + 14 + 4), "ENDFIELD WIKI", cn_font=F12, en_font=M12, fill=C_SUBTEXT)

    # 最终输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()