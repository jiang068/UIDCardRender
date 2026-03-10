# 明日方舟：终末地 建设卡片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 从 __init__.py 导入字体与工具函数
from . import F14, F16, F20, F48
from . import M14, M16
from . import O14, O16, O18, O20
from . import get_font, draw_text_mixed, _b64_img, _b64_fit

# 特殊字号补充
F12 = get_font(12, family='cn')

# 画布基础属性
W = 1000
PAD = 40
INNER_W = W - PAD * 2

# 颜色定义
C_BG = (15, 16, 20, 255)
C_ACCENT = (255, 230, 0, 255)
C_TEXT = (255, 255, 255, 255)
C_SUBTEXT = (139, 139, 139, 255)
C_BORDER = (255, 255, 255, 25)  # rgba(255,255,255,0.1)
C_PANEL = (255, 255, 255, 8)    # rgba(255,255,255,0.03)


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg": "",
        "logo": "",
        "avatar": "",
        "name": "未知用户",
        "uid": "",
        "level": "0",
        "world_level": "0",
        "create_time": "N/A",
        "rooms": [],
        "domains": []
    }

    # 解析背景与 Logo
    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg"] = bg_el.get("src", "")
    logo_el = soup.select_one(".footer-logo")
    if logo_el: data["logo"] = logo_el.get("src", "")
    av_el = soup.select_one(".avatar img")
    if av_el: data["avatar"] = av_el.get("src", "")

    # 解析头部信息
    name_el = soup.select_one(".user-name")
    if name_el: data["name"] = name_el.get_text(strip=True)
    uid_el = soup.select_one(".user-uid")
    if uid_el: data["uid"] = uid_el.get_text(strip=True).replace("UID", "").strip()

    tags = soup.select(".info-tags .tag")
    if len(tags) >= 3:
        data["level"] = tags[0].select_one("strong").get_text(strip=True) if tags[0].select_one("strong") else "0"
        data["world_level"] = tags[1].select_one("strong").get_text(strip=True) if tags[1].select_one("strong") else "0"
        data["create_time"] = tags[2].select_one("strong").get_text(strip=True) if tags[2].select_one("strong") else "N/A"

    # 解析帝江号舱室
    for rc in soup.select(".room-card"):
        type_el = rc.select_one(".room-type")
        lvl_el = rc.select_one(".room-lvl")
        chars = [img.get("src", "") for img in rc.select(".mini-avatar img")]
        
        data["rooms"].append({
            "type": type_el.get_text(strip=True).replace("TYPE-", "") if type_el else "?",
            "level": lvl_el.get_text(strip=True).replace("Lv.", "") if lvl_el else "0",
            "chars": chars
        })

    # 解析区域建设
    for dc in soup.select(".domain-card"):
        d_name = dc.select_one(".domain-name")
        d_lvl = dc.select_one(".domain-header .tag strong")
        
        settlements = []
        for sc in dc.select(".settlement-item"):
            s_name = sc.select_one(".st-name")
            s_lvl = sc.select_one(".st-lvl")
            officers = [img.get("src", "") for img in sc.select(".mini-avatar img")]
            
            settlements.append({
                "name": s_name.get_text(strip=True) if s_name else "?",
                "level": s_lvl.get_text(strip=True).replace("Lv.", "") if s_lvl else "0",
                "officers": officers
            })
            
        data["domains"].append({
            "name": d_name.get_text(strip=True) if d_name else "?",
            "level": d_lvl.get_text(strip=True) if d_lvl else "0",
            "settlements": settlements
        })

    return data


def draw_bg(canvas: Image.Image, w: int, h: int, bg_src: str):
    """绘制背景：背景图叠底 + 径向渐变 + 网格装饰"""
    if bg_src:
        try:
            bg_img = _b64_fit(bg_src, w, h).convert("RGBA")
            # 模拟 opacity 0.1 和 mix-blend-mode: overlay (使用强透明度近似叠加)
            bg_img.putalpha(Image.new("L", (w, h), 38)) # 15% 透明度
            canvas.alpha_composite(bg_img)
        except Exception: pass

    # Radial Gradient
    sw, sh = w // 10, h // 10
    cx, cy = int(sw * 0.5), int(sh * 0.2)
    grad = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    max_dist = math.hypot(max(cx, sw - cx), max(cy, sh - cy))
    
    for y in range(sh):
        for x in range(sw):
            dist = math.hypot(x - cx, y - cy)
            ratio = min(dist / max_dist, 1.0)
            r = int(26 + (15 - 26) * ratio)
            g = int(27 + (16 - 27) * ratio)
            b = int(32 + (20 - 32) * ratio)
            grad.putpixel((x, y), (r, g, b, 230)) # 不要完全遮挡底部 bg
            
    grad = grad.resize((w, h), Image.Resampling.LANCZOS)
    canvas.alpha_composite(grad)

    # Grid Deco
    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    grid_c = (255, 255, 255, 8) 
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


def draw_section_title(d: ImageDraw.ImageDraw, x: int, y: int, title_cn: str, title_en: str):
    """绘制统一的板块标题"""
    d.rectangle([x, y + 2, x + 4, y + 22], fill=C_ACCENT)
    draw_text_mixed(d, (x + 12, y), title_cn, cn_font=F20, en_font=F20, fill=C_TEXT)
    cn_w = int(F20.getlength(title_cn))
    draw_text_mixed(d, (x + 12 + cn_w + 10, y + 6), title_en, cn_font=M14, en_font=M14, fill=C_SUBTEXT)
    return 24 # 返回标题占据的高度


def draw_avatar_list(canvas: Image.Image, d: ImageDraw.ImageDraw, x: int, y: int, max_w: int, avatars: list[str]) -> int:
    """流式绘制 36x36 迷你头像列表，返回所占用的总高度"""
    if not avatars:
        # 空槽位占位符
        d.rectangle([x, y, x + 36, y + 36], outline=(68, 68, 68, 255), width=1)
        d.line([(x, y + 18), (x + 36, y + 18)], fill=(68, 68, 68, 255), width=1)
        return 36
        
    curr_x, cur_y = x, y
    gap = 5
    sz = 36
    
    for av in avatars:
        if curr_x + sz > x + max_w:
            curr_x = x
            cur_y += sz + gap
            
        d.rectangle([curr_x, cur_y, curr_x + sz, cur_y + sz], fill=(34, 34, 34, 255), outline=(68, 68, 68, 255), width=1)
        if av:
            try:
                img = _b64_fit(av, sz, sz)
                canvas.paste(img, (curr_x, cur_y))
            except Exception: pass
            
        curr_x += sz + gap
        
    return (cur_y + sz) - y


def render(html: str) -> bytes:
    data = parse_html(html)
    
    # ---------------- 1. 高度预计算阶段 ----------------
    cur_y = PAD
    
    # Header 区域预留
    header_h = 100
    cur_y += header_h + 25 + 30 # padding-bottom 25 + gap 30
    
    # 帝江号区域预留
    cur_y += 24 + 15 # title height + margin
    spaceship_padding = 20
    spaceship_w = INNER_W - spaceship_padding * 2
    room_gap = 12
    room_cols = 4
    room_w = (spaceship_w - room_gap * (room_cols - 1)) // room_cols
    
    room_rows = math.ceil(len(data["rooms"]) / room_cols) if data["rooms"] else 1
    # 模拟计算每行高度
    spaceship_h = spaceship_padding * 2
    if not data["rooms"]:
        spaceship_h += 60 # 暂无数据高度
    else:
        temp_img = Image.new("RGBA", (1, 1))
        temp_d = ImageDraw.Draw(temp_img)
        for r_idx in range(room_rows):
            row_items = data["rooms"][r_idx*room_cols : (r_idx+1)*room_cols]
            max_rh = 0
            for item in row_items:
                # Room Card 内部: pad 10*2 + header(14+5+2) + avatar_list
                # 头像最大可用宽度: room_w - 20
                al_h = draw_avatar_list(temp_img, temp_d, 0, 0, room_w - 20, item["chars"])
                ch = 20 + 21 + al_h
                if ch > max_rh: max_rh = ch
            spaceship_h += max_rh
            if r_idx < room_rows - 1: spaceship_h += room_gap
            
    cur_y += spaceship_h + 30 # gap 30
    
    # 区域建设预留
    cur_y += 24 + 15
    domain_gap = 20
    domain_cols = 3
    domain_w = (INNER_W - domain_gap * (domain_cols - 1)) // domain_cols
    domain_rows = math.ceil(len(data["domains"]) / domain_cols) if data["domains"] else 0
    
    domain_grid_h = 0
    if data["domains"]:
        for r_idx in range(domain_rows):
            row_items = data["domains"][r_idx*domain_cols : (r_idx+1)*domain_cols]
            max_dh = 0
            for dom in row_items:
                # header: 42px (12*2 pad + 18 text)
                dh = 42 + 15 * 2 # body pad 15*2
                if not dom["settlements"]:
                    dh += 20
                else:
                    for st in dom["settlements"]:
                        # item pad 8*2 = 16. header 14+6 = 20. avatar list
                        al_h = draw_avatar_list(temp_img, temp_d, 0, 0, domain_w - 30 - 16, st["officers"])
                        dh += 16 + 20 + al_h + 10 # gap 10
                    dh -= 10 # last gap
                if dh > max_dh: max_dh = dh
            domain_grid_h += max_dh
            if r_idx < domain_rows - 1: domain_grid_h += domain_gap
            
    cur_y += domain_grid_h + PAD + 50 # padding bottom
    total_h = max(cur_y, 800)
    
    # ---------------- 2. 实际绘制阶段 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h, data["bg"])
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    
    # === Header ===
    d.rectangle([PAD, y, PAD + 100, y + 100], fill=(17, 17, 17, 255), outline=C_ACCENT, width=1)
    if data["avatar"]:
        try:
            av_img = _b64_fit(data["avatar"], 100, 100)
            canvas.paste(av_img, (PAD, y))
        except Exception: pass
        
    ux = PAD + 100 + 25
    draw_text_mixed(d, (ux, y + 5), data["name"], cn_font=F48, en_font=F48, fill=C_TEXT)
    name_w = int(F48.getlength(data["name"]))
    
    if data["uid"]:
        uid_x = ux + name_w + 15
        uid_text = f"UID {data['uid']}"
        uid_w = int(M16.getlength(uid_text))
        d.rounded_rectangle([uid_x, y + 32, uid_x + uid_w + 16, y + 32 + 24], radius=4, fill=(255, 255, 255, 12))
        draw_text_mixed(d, (uid_x + 8, y + 35), uid_text, cn_font=M16, en_font=M16, fill=C_SUBTEXT)
        
    # Tags
    tag_y = y + 65
    tx = ux
    
    def draw_tag(x, y, label, val, is_cn=False):
        lbl_f = F16 if is_cn else O16
        lbl_w = int(lbl_f.getlength(label))
        val_w = int(O18.getlength(val))
        tw = lbl_w + val_w + 5 + 24
        d.rectangle([x, y, x + tw, y + 28], fill=C_PANEL, outline=C_BORDER, width=1)
        draw_text_mixed(d, (x + 12, y + 4), label, cn_font=lbl_f, en_font=lbl_f, fill=(204, 204, 204, 255))
        draw_text_mixed(d, (x + 12 + lbl_w + 5, y + 3), val, cn_font=O18, en_font=O18, fill=C_ACCENT)
        return tw + 15
        
    tx += draw_tag(tx, tag_y, "LEVEL", data["level"])
    tx += draw_tag(tx, tag_y, "WORLD", data["world_level"])
    tx += draw_tag(tx, tag_y, "苏醒日", data["create_time"], is_cn=True)
    
    y += 100 + 25
    d.line([(PAD, y), (W - PAD, y)], fill=C_BORDER, width=1)
    y += 30
    
    # === Spaceship ===
    draw_section_title(d, PAD, y, "帝江号", "SPACESHIP")
    y += 24 + 15
    
    # 模拟线性渐变背景 (90deg)
    grad_1d = Image.new("RGBA", (INNER_W, 1))
    for xi in range(INNER_W):
        ratio = 1 - (xi / max(INNER_W - 1, 1))
        grad_1d.putpixel((xi, 0), (255, 255, 255, int(8 * ratio)))
    sp_bg = grad_1d.resize((INNER_W, spaceship_h), Image.NEAREST)
    canvas.alpha_composite(sp_bg, (PAD, y))
    d.rectangle([PAD, y, PAD + INNER_W, y + spaceship_h], outline=C_BORDER, width=1)
    
    sy = y + spaceship_padding
    if not data["rooms"]:
        draw_text_mixed(d, (W//2 - 60, sy + 20), "暂无舱室数据", cn_font=F16, en_font=F16, fill=(102, 102, 102, 255))
    else:
        for r_idx in range(room_rows):
            row_items = data["rooms"][r_idx*room_cols : (r_idx+1)*room_cols]
            max_rh = 0
            for c_idx, item in enumerate(row_items):
                rx = PAD + spaceship_padding + c_idx * (room_w + room_gap)
                
                al_h = draw_avatar_list(temp_img, temp_d, 0, 0, room_w - 20, item["chars"])
                ch = 20 + 21 + al_h
                if ch > max_rh: max_rh = ch
                
                # Draw Room Card
                d.rectangle([rx, sy, rx + room_w, sy + ch], fill=(0, 0, 0, 102), outline=C_BORDER, width=1)
                
                # Header
                draw_text_mixed(d, (rx + 10, sy + 10), f"TYPE-{item['type']}", cn_font=M14, en_font=M14, fill=(221, 221, 221, 255))
                lvl_w = int(O16.getlength(f"Lv.{item['level']}"))
                draw_text_mixed(d, (rx + room_w - 10 - lvl_w, sy + 8), f"Lv.{item['level']}", cn_font=O16, en_font=O16, fill=C_ACCENT)
                d.line([(rx + 10, sy + 30), (rx + room_w - 10, sy + 30)], fill=(255, 255, 255, 25), width=1)
                
                # Avatars
                draw_avatar_list(canvas, d, rx + 10, sy + 36, room_w - 20, item["chars"])
                
            sy += max_rh + room_gap
            
    y += spaceship_h + 30
    
    # === Domains ===
    draw_section_title(d, PAD, y, "区域建设", "DOMAINS")
    y += 24 + 15
    
    dy = y
    for r_idx in range(domain_rows):
        row_items = data["domains"][r_idx*domain_cols : (r_idx+1)*domain_cols]
        max_dh = 0
        for c_idx, dom in enumerate(row_items):
            dx = PAD + c_idx * (domain_w + domain_gap)
            
            # 计算当前卡片高度
            dh = 42 + 30
            if not dom["settlements"]:
                dh += 20
            else:
                for st in dom["settlements"]:
                    al_h = draw_avatar_list(temp_img, temp_d, 0, 0, domain_w - 30 - 16, st["officers"])
                    dh += 16 + 20 + al_h + 10
                dh -= 10
            if dh > max_dh: max_dh = dh
            
            # Draw Domain Card
            d.rectangle([dx, dy, dx + domain_w, dy + dh], fill=C_PANEL, outline=C_BORDER, width=1)
            d.rectangle([dx, dy, dx + domain_w, dy + 42], fill=(255, 255, 255, 12))
            d.line([(dx, dy + 42), (dx + domain_w, dy + 42)], fill=C_BORDER, width=1)
            
            draw_text_mixed(d, (dx + 15, dy + 12), dom["name"], cn_font=F16, en_font=M16, fill=C_TEXT)
            
            lvl_str = str(dom["level"])
            tl_w = int(F12.getlength("Lv.")) + int(O14.getlength(lvl_str)) + 16
            tx_st = dx + domain_w - 15 - tl_w
            d.rectangle([tx_st, dy + 10, tx_st + tl_w, dy + 30], fill=C_PANEL, outline=C_BORDER, width=1)
            draw_text_mixed(d, (tx_st + 8, dy + 12), "Lv.", cn_font=F12, en_font=F12, fill=(204, 204, 204, 255))
            draw_text_mixed(d, (tx_st + 8 + int(F12.getlength("Lv.")) + 2, dy + 10), lvl_str, cn_font=O14, en_font=O14, fill=C_ACCENT)
            
            sty = dy + 42 + 15
            if not dom["settlements"]:
                draw_text_mixed(d, (dx + domain_w//2 - 30, sty), "暂无据点", cn_font=F12, en_font=F12, fill=(102, 102, 102, 255))
            else:
                for st in dom["settlements"]:
                    al_h = draw_avatar_list(temp_img, temp_d, 0, 0, domain_w - 30 - 16, st["officers"])
                    st_tot_h = 16 + 20 + al_h
                    
                    d.rectangle([dx + 15, sty, dx + domain_w - 15, sty + st_tot_h], fill=(0, 0, 0, 51))
                    d.line([(dx + 15, sty), (dx + 15, sty + st_tot_h)], fill=(85, 85, 85, 255), width=2)
                    
                    draw_text_mixed(d, (dx + 25, sty + 8), st["name"], cn_font=F14, en_font=M14, fill=(204, 204, 204, 255))
                    slvl = f"Lv.{st['level']}"
                    draw_text_mixed(d, (dx + domain_w - 15 - 8 - int(O14.getlength(slvl)), sty + 8), slvl, cn_font=O14, en_font=O14, fill=C_SUBTEXT)
                    
                    draw_avatar_list(canvas, d, dx + 25, sty + 28, domain_w - 30 - 16, st["officers"])
                    sty += st_tot_h + 10
                    
        dy += max_dh + domain_gap
        
    # === Footer Logo ===
    if data["logo"]:
        try:
            logo = _b64_img(data["logo"])
            lw = 120
            lh = int(logo.height * (lw / logo.width))
            logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
            
            # 模拟 opacity 0.3
            logo.putalpha(ImageChops.multiply(logo.split()[3], Image.new("L", (lw, lh), 76)))
            canvas.alpha_composite(logo, (W - 40 - lw, total_h - 20 - lh))
        except Exception: pass

    # 最终输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()