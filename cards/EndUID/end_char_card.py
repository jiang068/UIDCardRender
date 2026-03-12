# 明日方舟：终末地 单角色详情卡片渲染器 (PIL 版)

from __future__ import annotations

import math
import re
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# 避免循环导入，直接引入工具函数并局部生成字体
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit, _round_mask,
    F12, F14, F16, F18, F24, F28, F100,
    M12, M14, M16, M18,
    O12, O14, O16, O20, O24, O26, O28, O60, O160
)

# 画布基础属性
W = 1000
H = 1750
PAD = 50
INNER_W = W - PAD * 2

# 颜色定义
C_BG = (15, 16, 20, 255)
C_ACCENT = (255, 230, 0, 255)
C_TEXT = (255, 255, 255, 255)
C_SUBTEXT = (139, 139, 139, 255)

def parse_color(c_str: str, default=(255, 255, 255, 255)) -> tuple:
    c_str = c_str.strip().lower()
    if c_str.startswith("#"):
        c_str = c_str.lstrip("#")
        if len(c_str) == 3: c_str = "".join(c+c for c in c_str)
        if len(c_str) == 6:
            return (int(c_str[0:2], 16), int(c_str[2:4], 16), int(c_str[4:6], 16), 255)
    return default

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg_url": "", "char_url": "", "name": "", "rarity": 0,
        "property": "", "property_icon": "",
        "profession": "", "profession_icon": "",
        "weapon_type": "", "char_tags": [],
        "level": "0", "evolve_phase": "0", "potential": "1",
        "skills": [], "weapon": None, "body_equip": None, "equip_slots": [],
        "user": {"avatar": "", "name": "", "uid": "", "level": "0", "world_level": "0"}
    }

    # 背景和立绘
    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg_url"] = bg_el.get("src", "")
    char_el = soup.select_one(".char-layer")
    if char_el: data["char_url"] = char_el.get("src", "")

    # 头部左侧信息
    name_el = soup.select_one(".char-name")
    if name_el: data["name"] = name_el.get_text(strip=True)
    
    stars = soup.select(".rarity .rarity-star")
    data["rarity"] = len(stars)

    # 标签提取
    tag_boxes = soup.select(".tag-box")
    for tb in tag_boxes:
        is_element = "element" in tb.get("class", [])
        icon_el = tb.select_one("img")
        text = tb.get_text(strip=True)
        if is_element:
            data["property"] = text
            data["property_icon"] = icon_el.get("src", "") if icon_el else ""
        elif icon_el:
            data["profession"] = text
            data["profession_icon"] = icon_el.get("src", "")
        elif not data["weapon_type"]:
            data["weapon_type"] = text
        else:
            data["char_tags"].append(text)

    # 头部右侧信息
    lvl_el = soup.select_one(".level-num")
    if lvl_el: data["level"] = lvl_el.get_text(strip=True)
    
    phase_el = soup.select_one(".phase-badge span")
    if phase_el:
        p_text = phase_el.get_text(strip=True)
        if "/" in p_text:
            parts = p_text.split("/")
            data["evolve_phase"] = parts[0].replace("PHASE", "").strip()
            data["potential"] = parts[1].replace("POTENTIAL", "").strip()

    # 技能
    for sk in soup.select(".skill-item"):
        icon = sk.select_one(".skill-img")
        rank = sk.select_one(".skill-rank")
        name = sk.select_one(".skill-name")
        data["skills"].append({
            "icon": icon.get("src", "") if icon else "",
            "level": rank.get_text(strip=True).replace("RANK", "").strip() if rank else "1",
            "name": name.get_text(strip=True) if name else ""
        })

    # 武器
    wp_card = soup.select_one(".weapon-card")
    if wp_card and "未装备武器" not in wp_card.get_text():
        lvl = wp_card.select_one(".weapon-level").contents[0].strip() if wp_card.select_one(".weapon-level") else "1"
        w_stars = len(wp_card.select(".weapon-star"))
        w_name = wp_card.select_one(".weapon-name-text").get_text(strip=True) if wp_card.select_one(".weapon-name-text") else ""
        w_img = wp_card.select_one(".weapon-img")
        
        gem = None
        gem_wrap = wp_card.select_one(".weapon-gem-wrap")
        if gem_wrap:
            g_img = gem_wrap.select_one(".weapon-gem-img")
            g_name = gem_wrap.select_one(".weapon-gem-name")
            g_bar = gem_wrap.select_one(".weapon-gem-rarity-bar")
            g_color = "#ffffff"
            if g_bar and g_bar.get("style"):
                m = re.search(r"background:\s*(#[a-fA-F0-9]+)", g_bar.get("style"))
                if m: g_color = m.group(1)
            gem = {
                "icon": g_img.get("src", "") if g_img else "",
                "name": g_name.get_text(strip=True) if g_name else "",
                "rarity_color": g_color
            }
            
        data["weapon"] = {
            "level": lvl,
            "rarity": w_stars,
            "name": w_name,
            "icon": w_img.get("src", "") if w_img else "",
            "gem": gem
        }

    # 装备
    body_equip = soup.select_one(".equip-left .equip-card")
    if body_equip and not body_equip.select_one(".empty-slot"):
        lvl = body_equip.select_one(".equip-level").contents[0].strip() if body_equip.select_one(".equip-level") else ""
        icon = body_equip.select_one(".equip-icon")
        name = body_equip.select_one(".equip-name").get_text(strip=True) if body_equip.select_one(".equip-name") else ""
        data["body_equip"] = {"level": lvl, "name": name, "icon": icon.get("src", "") if icon else ""}
        
    for r_equip in soup.select(".equip-right .equip-card"):
        if r_equip.select_one(".empty-label"):
            data["equip_slots"].append({"empty": True})
        else:
            lvl = r_equip.select_one(".equip-level").contents[0].strip() if r_equip.select_one(".equip-level") else ""
            icon = r_equip.select_one(".equip-icon")
            name = r_equip.select_one(".equip-name").get_text(strip=True) if r_equip.select_one(".equip-name") else ""
            data["equip_slots"].append({"empty": False, "level": lvl, "name": name, "icon": icon.get("src", "") if icon else ""})

    # Footer 用户信息
    ft = soup.select_one(".footer")
    if ft:
        av = ft.select_one(".user-avatar img")
        data["user"]["avatar"] = av.get("src", "") if av else ""
        uname = ft.select_one(".user-name-text")
        data["user"]["name"] = uname.get_text(strip=True) if uname else ""
        uid = ft.select_one(".footer-right")
        data["user"]["uid"] = uid.get_text(strip=True).replace("UID", "").strip() if uid else ""
        tags = ft.select(".u-tag")
        if len(tags) >= 2:
            data["user"]["level"] = tags[0].get_text(strip=True).replace("Lv.", "")
            data["user"]["world_level"] = tags[1].get_text(strip=True).replace("WORLD", "").strip()

    return data


def draw_bg_and_char(canvas: Image.Image, d: ImageDraw.ImageDraw, data: dict):
    sw, sh = W // 10, H // 10
    grad = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    cx, cy = int(sw * 0.5), int(sh * 0.2)
    max_dist = math.hypot(max(cx, sw - cx), max(cy, sh - cy))
    
    for y in range(sh):
        for x in range(sw):
            dist = math.hypot(x - cx, y - cy)
            ratio = min(dist / max_dist, 1.0)
            r = int(34 + (15 - 34) * ratio)
            g = int(35 + (16 - 35) * ratio)
            b = int(40 + (20 - 40) * ratio)
            grad.putpixel((x, y), (r, g, b, 255))
            
    grad = grad.resize((W, H), Image.Resampling.LANCZOS)
    canvas.alpha_composite(grad)

    if data["bg_url"]:
        try:
            bg_img = _b64_fit(data["bg_url"], W, H).convert("RGBA")
            bg_img.putalpha(Image.new("L", (W, H), 25))
            canvas.alpha_composite(bg_img)
        except Exception: pass

    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    grid_c = (38, 39, 44, 180)
    for x in range(0, W, 40): gd.line([(x, 0), (x, H)], fill=grid_c, width=1)
    for y in range(0, H, 40): gd.line([(0, y), (W, y)], fill=grid_c, width=1)
    
    mask = Image.new("L", (W, H), 255)
    md = ImageDraw.Draw(mask)
    fade_h = int(H * 0.4)
    for y in range(fade_h, H):
        alpha = int(255 * (1 - min((y - fade_h) / (H * 0.6), 1.0)))
        md.line([(0, y), (W, y)], fill=alpha)
    grid.putalpha(mask)
    canvas.alpha_composite(grid)

    if data["char_url"]:
        try:
            char_img = _b64_img(data["char_url"])
            cw = int(char_img.width * (1150 / char_img.height))
            ch = 1150
            char_img = char_img.resize((cw, ch), Image.Resampling.LANCZOS)
            
            c_mask = char_img.split()[3] if char_img.mode == 'RGBA' else Image.new("L", (cw, ch), 255)
            fade_len = 200
            fade_mask = Image.new("L", (cw, ch), 255)
            fm_d = ImageDraw.Draw(fade_mask)
            for fy in range(ch - fade_len, ch):
                alpha = int(255 * max(0, 1 - (fy - (ch - fade_len)) / fade_len))
                fm_d.line([(0, fy), (cw, fy)], fill=alpha)
            c_mask = ImageChops.multiply(c_mask, fade_mask)
            char_img.putalpha(c_mask)
            
            shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            shadow.paste((0, 0, 0, 153), c_mask)
            shadow = shadow.filter(ImageFilter.GaussianBlur(12))
            
            cx_char = W - cw + 120
            cy_char = -60
            canvas.alpha_composite(shadow, (cx_char - 15, cy_char + 5))
            canvas.alpha_composite(char_img, (cx_char, cy_char))
        except Exception: pass

    grad_h = H - 650 
    grad_y = 650
    overlay = Image.new("RGBA", (W, grad_h), (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    for y in range(grad_h):
        if y < 200:
            alpha = int(242 * (y / 200))
        else:
            alpha = 242
        od.line([(0, y), (W, y)], fill=(15, 16, 20, alpha))
    canvas.alpha_composite(overlay, (0, grad_y))


def draw_skew_tag(canvas: Image.Image, d: ImageDraw.ImageDraw, x: int, y: int, icon_src: str, text: str, is_element: bool) -> int:
    h = 36
    tw = int(M16.getlength(text))
    w = tw + 48 + (28 if icon_src else 0)
    skew = 13
    
    bg_c = (209, 60, 49, 255) if is_element else (255, 255, 255, 20)
    text_c = (255, 255, 255, 255) if is_element else (238, 238, 238, 255)
    
    pts = [(x + skew, y), (x + w + skew, y), (x + w - skew, y + h), (x - skew, y + h)]
    
    shadow = Image.new("RGBA", (W, H), (0,0,0,0))
    ImageDraw.Draw(shadow).polygon([(p[0]+4, p[1]+4) for p in pts], fill=(0,0,0,102))
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    canvas.alpha_composite(shadow)
    
    d.polygon(pts, fill=bg_c)
    if not is_element:
        d.polygon([(x - skew - 3, y), (x + skew, y), (x - skew, y + h), (x - skew - 3, y + h)], fill=C_ACCENT)
        
    ix = x + 24 - skew
    if icon_src:
        try:
            ic = _b64_fit(icon_src, 20, 20)
            canvas.paste(ic, (ix, y + 8), ic)
            ix += 28
        except Exception: pass
        
    draw_text_mixed(d, (ix, y + 8), text, cn_font=F16, en_font=M16, fill=text_c, dy_en=3)
    return w + 15


def draw_section_title(d: ImageDraw.ImageDraw, x: int, y: int, title_cn: str, title_en: str):
    d.line([(x, y), (x, y + 24)], fill=C_ACCENT, width=6)
    draw_text_mixed(d, (x + 15 + 2, y + 2), title_cn, cn_font=F24, en_font=F24, fill=(0,0,0,128), dy_en=5)
    draw_text_mixed(d, (x + 15, y), title_cn, cn_font=F24, en_font=F24, fill=C_TEXT, dy_en=5)
    cn_w = int(F24.getlength(title_cn))
    draw_text_mixed(d, (x + 15 + cn_w + 12, y + 8), title_en, cn_font=F14, en_font=M14, fill=C_SUBTEXT, dy_en=3)


def render(html: str) -> bytes:
    data = parse_html(html)
    canvas = Image.new("RGBA", (W, H), C_BG)
    d = ImageDraw.Draw(canvas)
    
    draw_bg_and_char(canvas, d, data)
    
    # ---------------- 1. 顶部 Header 区 ----------------
    hy = PAD + 40
    
    draw_text_mixed(d, (PAD - 5, hy + 10), data["name"], cn_font=F100, en_font=F100, fill=(0,0,0,204), dy_en=20)
    draw_text_mixed(d, (PAD - 5, hy), data["name"], cn_font=F100, en_font=F100, fill=C_TEXT, dy_en=20)
    
    sy = hy + 110
    for i in range(data["rarity"]):
        cx = PAD + 5 + i * 28
        d.ellipse([cx, sy, cx + 20, sy + 20], fill=C_ACCENT)
        d.ellipse([cx + 4, sy + 4, cx + 16, sy + 16], fill=(255, 204, 0, 255))
        
    ty = sy + 35
    tx = PAD
    if data["property"]:
        tx += draw_skew_tag(canvas, d, tx, ty, data["property_icon"], data["property"], True)
    if data["profession"]:
        tx += draw_skew_tag(canvas, d, tx, ty, data["profession_icon"], data["profession"], False)
        
    ty += 36 + 10
    tx = PAD
    if data["weapon_type"]:
        tx += draw_skew_tag(canvas, d, tx, ty, "", data["weapon_type"], False)
    for tag in data["char_tags"]:
        tx += draw_skew_tag(canvas, d, tx, ty, "", tag, False)

    # === [优化] 角色等级数字排版上调 ===
    rx = W - PAD
    lvl_y = hy
    lvl_num_w = int(O160.getlength(data["level"]))
    # 向上移动约 20% 字高 (32px), 所以 y+10 变成 y-22
    draw_text_mixed(d, (rx - lvl_num_w, lvl_y - 22), data["level"], cn_font=O160, en_font=O160, fill=C_TEXT, dy_en=32)
    
    lbl_text = "L E V E L"
    lbl_w = int(O24.getlength(lbl_text))
    # 'LEVEL' 文字同样跟随上移
    draw_text_mixed(d, (rx - lbl_w, lvl_y - 20), lbl_text, cn_font=O24, en_font=O24, fill=C_SUBTEXT, dy_en=5)
    
    pb_y = lvl_y + 175
    pb_text = f"PHASE {data['evolve_phase']} / POTENTIAL {data['potential']}"
    pb_w = int(M18.getlength(pb_text)) + 32
    pb_x = rx - pb_w
    d.polygon([(pb_x + 10, pb_y), (pb_x + pb_w + 10, pb_y), (pb_x + pb_w - 10, pb_y + 30), (pb_x - 10, pb_y + 30)], fill=C_ACCENT)
    draw_text_mixed(d, (pb_x + 16, pb_y + 6), pb_text, cn_font=M18, en_font=M18, fill=(15, 16, 20, 255), dy_en=4)


    # ---------------- 2. 内容区 (正向排版) ----------------
    cy = 750 # 稍微上调技能位置给装备区留出拉伸空间
    
    # === 技能区 ===
    draw_section_title(d, PAD, cy, "技能", "SKILLS")
    sy = cy + 40
    sx = PAD + 10
    for sk in data["skills"]:
        d.ellipse([sx, sy, sx + 90, sy + 90], fill=(20, 20, 20, 153), outline=(255, 255, 255, 38), width=2)
        if sk["icon"]:
            try:
                ic = _b64_fit(sk["icon"], 70, 70)
                canvas.alpha_composite(ic, (sx + 10, sy + 10))
            except Exception: pass
            
        rw = int(O12.getlength(f"RANK {sk['level']}")) + 20
        rx = sx + 45 - rw//2
        d.rounded_rectangle([rx, sy + 80, rx + rw, sy + 100], radius=8, fill=(42, 42, 42, 255), outline=C_ACCENT, width=1)
        draw_text_mixed(d, (rx + 10, sy + 83), f"RANK {sk['level']}", cn_font=O12, en_font=O12, fill=C_ACCENT, dy_en=2)
        
        nw = int(F16.getlength(sk["name"]))
        draw_text_mixed(d, (sx + 45 - nw//2 + 1, sy + 110 + 1), sk["name"], cn_font=F16, en_font=F16, fill=(0,0,0,204), dy_en=3)
        draw_text_mixed(d, (sx + 45 - nw//2, sy + 110), sk["name"], cn_font=F16, en_font=F16, fill=(221, 221, 221, 255), dy_en=3)
        
        sx += 90 + 35
        
    cy = sy + 100 + 35 
    
    # === 武器区 ===
    draw_section_title(d, PAD, cy, "武器", "WEAPON")
    wy = cy + 40
    
    clip_pts = [(PAD, wy), (PAD + INNER_W, wy), (PAD + INNER_W, wy + 119), (PAD + INNER_W - 20, wy + 140), (PAD, wy + 140)]
    
    if data["weapon"]:
        wp = data["weapon"]
        d.polygon(clip_pts, fill=(224, 224, 224, 255))
        d.polygon([(PAD, wy), (PAD + 8, wy), (PAD + 8, wy + 140), (PAD, wy + 140)], fill=C_ACCENT)
        
        # === [优化] 武器等级数字排版上调 ===
        # 向上移动约 20% 字高 (12px), wy+20 变成 wy+8
        draw_text_mixed(d, (PAD + 40, wy + 8), wp["level"], cn_font=O60, en_font=O60, fill=(26, 26, 26, 255), dy_en=12)
        # 'Lv' 跟着上移
        draw_text_mixed(d, (PAD + 40 + int(O60.getlength(wp["level"])) + 5, wy + 43), "Lv", cn_font=O20, en_font=O20, fill=(85, 85, 85, 255), dy_en=4)
        
        ws_y = wy + 85
        for i in range(wp["rarity"]):
            cx = PAD + 40 + i * 20
            d.ellipse([cx, ws_y, cx + 16, ws_y + 16], fill=(85, 85, 85, 255))
            
        draw_text_mixed(d, (PAD + 40, wy + 105), wp["name"], cn_font=F24, en_font=F24, fill=(26, 26, 26, 255), dy_en=5)
        
        if wp["icon"]:
            try:
                ic = _b64_fit(wp["icon"], 400, 190).convert("RGBA")
                ic = ic.rotate(8, expand=True, resample=Image.BICUBIC)
                
                wp_layer = Image.new("RGBA", (W, H), (0,0,0,0))
                px = W - PAD - 160 - ic.width // 2
                py = wy - 25 + 95 - ic.height // 2
                wp_layer.paste(ic, (px, py))
                
                w_mask = Image.new("L", (W, H), 0)
                ImageDraw.Draw(w_mask).polygon(clip_pts, fill=255)
                
                wp_layer.putalpha(ImageChops.multiply(wp_layer.split()[3], w_mask))
                canvas.alpha_composite(wp_layer)
            except Exception: pass
            
        # === [修复] 基质(配件) 绘图逻辑 ===
        if wp["gem"]:
            g_wrap = Image.new("RGBA", (120, 140), (0,0,0,0))
            g_d = ImageDraw.Draw(g_wrap)
            g_c = parse_color(wp["gem"]["rarity_color"])
            
            # 修改渐变：使用白色作为主背景，确保文字清晰
            for g_y in range(140):
                ratio = g_y / 140
                if ratio < 0.7:
                    # 上半部分：白色背景，不透明度 0.9 (230)
                    bg_col = (255, 255, 255, 230)
                else:
                    # 下半部分：从白色向稀有度颜色过渡
                    prog = (ratio - 0.7) / 0.3
                    r = int(255 + (g_c[0] - 255) * prog)
                    g = int(255 + (g_c[1] - 255) * prog)
                    b = int(255 + (g_c[2] - 255) * prog)
                    bg_col = (r, g, b, 230)
                g_d.line([(0, g_y), (120, g_y)], fill=bg_col)
                
            if wp["gem"]["icon"]:
                try:
                    gic = _b64_fit(wp["gem"]["icon"], 90, 90)
                    # 居中贴图
                    g_wrap.paste(gic, (15, 8), gic)
                except Exception: pass
                
            # 绘制基质名称 (深色文字在白色背景上)
            name_text = wp["gem"]["name"]
            tw = int(F14.getlength(name_text))
            draw_text_mixed(g_d, (60 - tw // 2, 105), name_text, cn_font=F14, en_font=F14, fill=(26, 26, 26, 255), dy_en=3)
            
            # 底部稀有度色条
            g_d.rectangle([0, 136, 120, 140], fill=g_c)
            
            # 圆角裁剪并合并
            g_mask = _round_mask(120, 140, 8)
            canvas.paste(g_wrap, (W - PAD - 150, wy), g_mask)
            # 增加一个细微的黑色边框让卡片更立体
            d.rounded_rectangle([W - PAD - 150, wy, W - PAD - 30, wy + 140], radius=8, outline=(0, 0, 0, 40), width=1)
            
    else:
        d.polygon(clip_pts, fill=(255, 255, 255, 12))
        d.polygon([(PAD, wy), (PAD + 8, wy), (PAD + 8, wy + 140), (PAD, wy + 140)], fill=(85, 85, 85, 255))
        draw_text_mixed(d, (PAD + 40, wy + 55), "未装备武器", cn_font=F24, en_font=F24, fill=(102, 102, 102, 255), dy_en=5)

    cy = wy + 140 + 35
    
    # === [优化] 装备区自适应填满剩余下半部高度 ===
    draw_section_title(d, PAD, cy, "装备", "EQUIPMENT")
    eq_y = cy + 40
    eq_lw = 280
    
    # 动态计算剩余可用高度，确保底部留有安全边距对接Footer
    eq_h = (H - 80 - 100) - eq_y 
    eq_h = max(320, eq_h) # 确保最小不会比原来短
    
    # 左侧身体装备
    d.rectangle([PAD, eq_y, PAD + eq_lw, eq_y + eq_h], fill=(255, 255, 255, 15), outline=(255, 255, 255, 30), width=1)
    if data["body_equip"]:
        be = data["body_equip"]
        draw_text_mixed(d, (PAD + 15, eq_y + 12), be["level"], cn_font=O26, en_font=O26, fill=C_TEXT, dy_en=5)
        draw_text_mixed(d, (PAD + 15 + int(O26.getlength(be["level"])) + 4, eq_y + 22), "LEVEL", cn_font=O14, en_font=O14, fill=(255,255,255,153), dy_en=3)
        if be["icon"]:
            try:
                ic = _b64_fit(be["icon"], 200, 200)
                # 自适应居中绘制装备大图
                ic_y = eq_y + (eq_h - 200) // 2 - 15
                canvas.alpha_composite(ic, (PAD + 40, ic_y))
            except Exception: pass
        draw_text_mixed(d, (PAD + 15, eq_y + eq_h - 35), be["name"], cn_font=F18, en_font=F18, fill=(221, 221, 221, 255), dy_en=4)
    else:
        d.rectangle([PAD, eq_y, PAD + eq_lw, eq_y + eq_h], fill=(255, 255, 255, 5))
        draw_text_mixed(d, (PAD + eq_lw//2 - 20, eq_y + eq_h//2 - 10), "EMPTY", cn_font=M12, en_font=M12, fill=(255,255,255,25), dy_en=2)
        
    # 右侧 4 格装备
    eq_rx = PAD + eq_lw + 15
    eq_rw = (INNER_W - eq_lw - 15) // 2
    eq_rh = (eq_h - 15) // 2
    for i in range(4):
        col = i % 2
        row = i // 2
        cx = eq_rx + col * (eq_rw + 15)
        r_y = eq_y + row * (eq_rh + 15)
        
        d.rectangle([cx, r_y, cx + eq_rw, r_y + eq_rh], fill=(255, 255, 255, 12), outline=(255, 255, 255, 30), width=1)
        if i < len(data["equip_slots"]) and not data["equip_slots"][i]["empty"]:
            eq = data["equip_slots"][i]
            draw_text_mixed(d, (cx + 15, r_y + 12), eq["level"], cn_font=O26, en_font=O26, fill=C_TEXT, dy_en=5)
            draw_text_mixed(d, (cx + 15 + int(O26.getlength(eq["level"])) + 2, r_y + 22), "Lv", cn_font=O14, en_font=O14, fill=(255,255,255,153), dy_en=3)
            if eq["icon"]:
                try:
                    ic = _b64_fit(eq["icon"], int(eq_rw*0.75), int(eq_rh*0.65))
                    # 动态居中
                    ic_y = r_y + (eq_rh - ic.height) // 2 - 10
                    canvas.alpha_composite(ic, (cx + eq_rw//2 - ic.width//2, ic_y))
                except Exception: pass
            draw_text_mixed(d, (cx + 15, r_y + eq_rh - 35), eq["name"], cn_font=F18, en_font=F18, fill=(221, 221, 221, 255), dy_en=4)
        else:
            d.rectangle([cx, r_y, cx + eq_rw, r_y + eq_rh], fill=(255, 255, 255, 5))
            draw_text_mixed(d, (cx + eq_rw//2 - 20, r_y + eq_rh//2 - 10), "EMPTY", cn_font=M12, en_font=M12, fill=(255,255,255,25), dy_en=2)


    # ---------------- 3. 底部 Footer 区 ----------------
    fy = H - 80
    f_bg = Image.new("RGBA", (W, 80), (12, 13, 16, 240))
    canvas.alpha_composite(f_bg, (0, fy))
    d.line([(0, fy), (W, fy)], fill=(255, 255, 255, 38), width=1)
    
    if data["user"]["avatar"]:
        try:
            av = _b64_fit(data["user"]["avatar"], 50, 50)
            canvas.paste(av, (PAD, fy + 15), _round_mask(50, 50, 25))
        except Exception: pass
    else:
        d.ellipse([PAD, fy + 15, PAD + 50, fy + 65], fill=(34, 34, 34, 255))
    d.ellipse([PAD, fy + 15, PAD + 50, fy + 65], outline=C_ACCENT, width=2)
    
    draw_text_mixed(d, (PAD + 75, fy + 26), data["user"]["name"], cn_font=F28, en_font=F28, fill=C_TEXT, dy_en=6)
    un_w = int(F28.getlength(data["user"]["name"]))
    
    ut_x = PAD + 75 + un_w + 15
    d.rectangle([ut_x, fy + 28, ut_x + int(M16.getlength(f"Lv.{data['user']['level']}")) + 24, fy + 52], fill=(255, 255, 255, 25))
    draw_text_mixed(d, (ut_x + 12, fy + 30), f"Lv.{data['user']['level']}", cn_font=M16, en_font=M16, fill=(170, 170, 170, 255), dy_en=3)
    
    ut_x += int(M16.getlength(f"Lv.{data['user']['level']}")) + 32
    w_text = f"WORLD {data['user']['world_level']}"
    d.rectangle([ut_x, fy + 28, ut_x + int(M16.getlength(w_text)) + 24, fy + 52], fill=(255, 255, 255, 25))
    draw_text_mixed(d, (ut_x + 12, fy + 30), w_text, cn_font=M16, en_font=M16, fill=(170, 170, 170, 255), dy_en=3)
    
    uid_text = f"UID {data['user']['uid']}"
    uid_w = int(O28.getlength(uid_text))
    draw_text_mixed(d, (W - PAD - uid_w, fy + 24), uid_text, cn_font=O28, en_font=O28, fill=C_ACCENT, dy_en=6)

    # 输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()