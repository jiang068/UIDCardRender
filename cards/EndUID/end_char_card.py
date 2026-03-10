# 明日方舟：终末地 单角色详情卡片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# 避免循环导入，直接引入工具函数并局部生成字体
from . import get_font, draw_text_mixed, _b64_img, _b64_fit, _round_mask

F14 = get_font(14, family='cn')
F16 = get_font(16, family='cn')
F18 = get_font(18, family='cn')
F24 = get_font(24, family='cn')
F28 = get_font(28, family='cn')
F100 = get_font(100, family='cn')

M14 = get_font(14, family='mono')
M16 = get_font(16, family='mono')
M18 = get_font(18, family='mono')

O12 = get_font(12, family='oswald')
O16 = get_font(16, family='oswald')
O20 = get_font(20, family='oswald')
O24 = get_font(24, family='oswald')
O26 = get_font(26, family='oswald')
O28 = get_font(28, family='oswald')
O60 = get_font(60, family='oswald')
O160 = get_font(160, family='oswald')

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

R_COLORS = {
    6: (255, 78, 32, 255),
    5: (255, 201, 0, 255),
    4: (163, 102, 255, 255),
    3: (0, 145, 255, 255)
}

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
        data["weapon"] = {
            "level": lvl,
            "rarity": w_stars,
            "name": w_name,
            "icon": w_img.get("src", "") if w_img else ""
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
    # 背景渐变与叠底
    sw, sh = W // 10, H // 10
    grad = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    for y in range(sh):
        for x in range(sw):
            dist = math.hypot(x - sw*0.5, y - sh*0.3)
            ratio = min(dist / (math.hypot(sw, sh)*0.7), 1.0)
            r = int(26 + (15 - 26) * ratio)
            g = int(27 + (16 - 27) * ratio)
            b = int(32 + (20 - 32) * ratio)
            grad.putpixel((x, y), (r, g, b, 255))
    canvas.alpha_composite(grad.resize((W, H), Image.Resampling.LANCZOS))
    
    if data["bg_url"]:
        try:
            bg_img = _b64_fit(data["bg_url"], W, H).convert("RGBA")
            bg_img.putalpha(Image.new("L", (W, H), 38)) # opacity 0.15 近似
            canvas.alpha_composite(bg_img)
        except Exception: pass

    # 装饰网格
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    grid_c = (255, 255, 255, 12) 
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

    # 角色大立绘
    if data["char_url"]:
        try:
            char_img = _b64_img(data["char_url"])
            cw, ch = int(char_img.width * (1150 / char_img.height)), 1150
            char_img = char_img.resize((cw, ch), Image.Resampling.LANCZOS)
            
            # 立绘阴影
            shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            shadow.paste((0, 0, 0, 153), char_img.split()[3])
            shadow = shadow.filter(ImageFilter.GaussianBlur(12))
            
            cx = W - cw + 120
            cy = -60
            canvas.alpha_composite(shadow, (cx - 15, cy + 5))
            canvas.alpha_composite(char_img, (cx, cy))
        except Exception: pass

    # 底部渐变遮罩 (overlay-gradient)
    grad_h = int(H * 0.65)
    grad_y = H - grad_h
    overlay = Image.new("RGBA", (W, grad_h), (0,0,0,0))
    for y in range(grad_h):
        ratio = y / grad_h
        if ratio < 0.45: # 对应 top 55% 到 100% 透明过渡
            alpha = int(242 * (ratio / 0.45))
        elif ratio < 0.85:
            alpha = int(242 + (255 - 242) * ((ratio - 0.45)/0.40))
        else:
            alpha = 255
        ImageDraw.Draw(overlay).line([(0, y), (W, y)], fill=(15, 16, 20, alpha))
    canvas.alpha_composite(overlay, (0, grad_y))


def draw_skew_tag(canvas: Image.Image, d: ImageDraw.ImageDraw, x: int, y: int, icon_src: str, text: str, is_element: bool) -> int:
    h = 36
    tw = int(M16.getlength(text))
    w = tw + 48 + (28 if icon_src else 0)
    skew = 12
    
    bg_c = (209, 60, 49, 255) if is_element else (255, 255, 255, 20)
    text_c = (255, 255, 255, 255) if is_element else (238, 238, 238, 255)
    
    # 倾斜平行四边形
    pts = [(x + skew, y), (x + w + skew, y), (x + w - skew, y + h), (x - skew, y + h)]
    
    # 阴影层
    shadow = Image.new("RGBA", (W, H), (0,0,0,0))
    ImageDraw.Draw(shadow).polygon([(p[0]+5, p[1]+5) for p in pts], fill=(0,0,0,102))
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    canvas.alpha_composite(shadow)
    
    d.polygon(pts, fill=bg_c)
    if not is_element:
        d.polygon([(x - skew - 3, y), (x + skew, y), (x - skew, y + h), (x - skew - 3, y + h)], fill=C_ACCENT)
        
    ix = x + 16
    if icon_src:
        try:
            ic = _b64_fit(icon_src, 20, 20)
            canvas.paste(ic, (ix, y + 8), ic)
            ix += 28
        except Exception: pass
        
    draw_text_mixed(d, (ix, y + 8), text, cn_font=M16, en_font=M16, fill=text_c)
    return w + 15


def draw_section_title(d: ImageDraw.ImageDraw, x: int, y: int, title_cn: str, title_en: str):
    d.rectangle([x, y + 2, x + 6, y + 26], fill=C_ACCENT)
    draw_text_mixed(d, (x + 15, y), title_cn, cn_font=F24, en_font=F24, fill=C_TEXT)
    cn_w = int(F24.getlength(title_cn))
    draw_text_mixed(d, (x + 15 + cn_w + 12, y + 8), title_en, cn_font=M14, en_font=M14, fill=C_SUBTEXT)


def render(html: str) -> bytes:
    data = parse_html(html)
    canvas = Image.new("RGBA", (W, H), C_BG)
    d = ImageDraw.Draw(canvas)
    
    draw_bg_and_char(canvas, d, data)
    
    # ---------------- UI 层绘制 ----------------
    
    # 1. 顶部 Header 区
    hy = PAD + 40
    
    # 左侧: 名字与星级
    draw_text_mixed(d, (PAD - 5, hy), data["name"], cn_font=F100, en_font=F100, fill=C_TEXT)
    sy = hy + 110
    for i in range(data["rarity"]):
        # 简单用黄色圆圈占位替代复杂的SVG星
        cx = PAD + 5 + i * 28
        d.ellipse([cx, sy, cx + 20, sy + 20], fill=C_ACCENT)
        d.ellipse([cx + 4, sy + 4, cx + 16, sy + 16], fill=(255, 204, 0, 255))
        
    # Tags Row 1
    ty = sy + 35
    tx = PAD
    if data["property"]:
        tx += draw_skew_tag(canvas, d, tx, ty, data["property_icon"], data["property"], True)
    if data["profession"]:
        tx += draw_skew_tag(canvas, d, tx, ty, data["profession_icon"], data["profession"], False)
        
    # Tags Row 2
    ty += 36 + 10
    tx = PAD
    if data["weapon_type"]:
        tx += draw_skew_tag(canvas, d, tx, ty, "", data["weapon_type"], False)
    for tag in data["char_tags"]:
        tx += draw_skew_tag(canvas, d, tx, ty, "", tag, False)

    # 右侧: 等级与潜能
    rx = W - PAD
    lvl_y = hy
    draw_text_mixed(d, (rx - int(O24.getlength("LEVEL")), lvl_y), "LEVEL", cn_font=O24, en_font=O24, fill=C_SUBTEXT)
    lvl_num_w = int(O160.getlength(data["level"]))
    draw_text_mixed(d, (rx - lvl_num_w, lvl_y + 10), data["level"], cn_font=O160, en_font=O160, fill=C_TEXT)
    
    pb_y = lvl_y + 175
    pb_text = f"PHASE {data['evolve_phase']} / POTENTIAL {data['potential']}"
    pb_w = int(M18.getlength(pb_text)) + 32
    pb_x = rx - pb_w
    d.polygon([(pb_x + 8, pb_y), (pb_x + pb_w + 8, pb_y), (pb_x + pb_w - 8, pb_y + 26), (pb_x - 8, pb_y + 26)], fill=C_ACCENT)
    draw_text_mixed(d, (pb_x + 16, pb_y + 2), pb_text, cn_font=M18, en_font=M18, fill=(15, 16, 20, 255))

    # 2. 底部 Content Panel (从下往上排，因为 HTML 里是 justify-content: flex-end)
    cy = H - 80 - 40 # 减去 footer 和 bottom-gap
    
    # 装备区
    cy -= 320
    eq_y = cy
    draw_section_title(d, PAD, eq_y - 45, "装备", "EQUIPMENT")
    
    eq_lw = 280
    eq_h = 320
    # 左侧大装备卡
    d.rectangle([PAD, eq_y, PAD + eq_lw, eq_y + eq_h], fill=(255, 255, 255, 12), outline=(255, 255, 255, 30), width=1)
    if data["body_equip"]:
        be = data["body_equip"]
        draw_text_mixed(d, (PAD + 15, eq_y + 12), be["level"], cn_font=O26, en_font=O26, fill=C_TEXT)
        draw_text_mixed(d, (PAD + 15 + int(O26.getlength(be["level"])) + 2, eq_y + 22), "LEVEL", cn_font=O14, en_font=O14, fill=(255,255,255,153))
        if be["icon"]:
            try:
                ic = _b64_fit(be["icon"], 200, 200)
                canvas.alpha_composite(ic, (PAD + 40, eq_y + 70))
            except Exception: pass
        draw_text_mixed(d, (PAD + 15, eq_y + eq_h - 35), be["name"], cn_font=F18, en_font=M18, fill=(221, 221, 221, 255))
    else:
        d.rectangle([PAD, eq_y, PAD + eq_lw, eq_y + eq_h], fill=(255, 255, 255, 5))
        d.rectangle([PAD+1, eq_y+1, PAD + eq_lw-1, eq_y + eq_h-1], outline=(255, 255, 255, 20)) # dashed mock
        draw_text_mixed(d, (PAD + eq_lw//2 - 20, eq_y + eq_h//2 - 10), "EMPTY", cn_font=M12, en_font=O12, fill=(255,255,255,25))
        
    # 右侧 4 格装备
    eq_rx = PAD + eq_lw + 15
    eq_rw = (INNER_W - eq_lw - 15 - 15) // 2
    eq_rh = (eq_h - 15) // 2
    for i in range(4):
        col = i % 2
        row = i // 2
        cx = eq_rx + col * (eq_rw + 15)
        r_y = eq_y + row * (eq_rh + 15)
        
        d.rectangle([cx, r_y, cx + eq_rw, r_y + eq_rh], fill=(255, 255, 255, 12), outline=(255, 255, 255, 30), width=1)
        if i < len(data["equip_slots"]) and not data["equip_slots"][i]["empty"]:
            eq = data["equip_slots"][i]
            draw_text_mixed(d, (cx + 15, r_y + 12), eq["level"], cn_font=O26, en_font=O26, fill=C_TEXT)
            draw_text_mixed(d, (cx + 15 + int(O26.getlength(eq["level"])) + 2, r_y + 22), "Lv", cn_font=O14, en_font=O14, fill=(255,255,255,153))
            if eq["icon"]:
                try:
                    ic = _b64_fit(eq["icon"], 100, 100)
                    canvas.alpha_composite(ic, (cx + eq_rw//2 - 50, r_y + 20))
                except Exception: pass
            draw_text_mixed(d, (cx + 15, r_y + eq_rh - 35), eq["name"], cn_font=F18, en_font=M18, fill=(221, 221, 221, 255))
        else:
            d.rectangle([cx, r_y, cx + eq_rw, r_y + eq_rh], fill=(255, 255, 255, 5))
            draw_text_mixed(d, (cx + eq_rw//2 - 20, r_y + eq_rh//2 - 10), "EMPTY", cn_font=M12, en_font=O12, fill=(255,255,255,25))

    # 武器区
    cy -= (140 + 30 + 45)
    wp_y = cy
    draw_section_title(d, PAD, wp_y, "武器", "WEAPON")
    wy = wp_y + 45
    d.polygon([(PAD, wy), (PAD + INNER_W, wy), (PAD + INNER_W, wy + 119), (PAD + INNER_W - 20, wy + 140), (PAD, wy + 140)], fill=(224, 224, 224, 255))
    d.polygon([(PAD, wy), (PAD + 8, wy), (PAD + 8, wy + 140), (PAD, wy + 140)], fill=C_ACCENT)
    
    if data["weapon"]:
        wp = data["weapon"]
        draw_text_mixed(d, (PAD + 40, wy + 20), wp["level"], cn_font=O60, en_font=O60, fill=(26, 26, 26, 255))
        draw_text_mixed(d, (PAD + 40 + int(O60.getlength(wp["level"])) + 5, wy + 55), "Lv", cn_font=O20, en_font=O20, fill=(85, 85, 85, 255))
        
        ws_y = wy + 85
        for i in range(wp["rarity"]):
            cx = PAD + 40 + i * 20
            d.ellipse([cx, ws_y, cx + 16, ws_y + 16], fill=(85, 85, 85, 255))
            
        draw_text_mixed(d, (PAD + 40, wy + 105), wp["name"], cn_font=F24, en_font=F24, fill=(26, 26, 26, 255))
        
        if wp["icon"]:
            try:
                ic = _b64_fit(wp["icon"], 300, 140)
                ic = ic.rotate(8, expand=True, resample=Image.BICUBIC)
                canvas.alpha_composite(ic, (W - PAD - 380, wy - 20))
            except Exception: pass
    else:
        d.polygon([(PAD, wy), (PAD + INNER_W, wy), (PAD + INNER_W, wy + 119), (PAD + INNER_W - 20, wy + 140), (PAD, wy + 140)], fill=(255, 255, 255, 12))
        d.polygon([(PAD, wy), (PAD + 8, wy), (PAD + 8, wy + 140), (PAD, wy + 140)], fill=(85, 85, 85, 255))
        draw_text_mixed(d, (PAD + 40, wy + 55), "未装备武器", cn_font=F24, en_font=F24, fill=(102, 102, 102, 255))

    # 技能区
    cy -= (120 + 30 + 45)
    sk_y = cy
    draw_section_title(d, PAD, sk_y, "技能", "SKILLS")
    sy = sk_y + 45
    sx = PAD + 10
    for sk in data["skills"]:
        # 技能圆圈背景
        d.ellipse([sx, sy, sx + 90, sy + 90], fill=(20, 20, 20, 153), outline=(255, 255, 255, 38), width=2)
        if sk["icon"]:
            try:
                ic = _b64_fit(sk["icon"], 70, 70)
                canvas.paste(ic, (sx + 10, sy + 10), ic)
            except Exception: pass
            
        # Rank 标签
        rw = int(O12.getlength(f"RANK {sk['level']}")) + 20
        rx = sx + 45 - rw//2
        d.rounded_rectangle([rx, sy + 80, rx + rw, sy + 100], radius=8, fill=(42, 42, 42, 255), outline=C_ACCENT, width=1)
        draw_text_mixed(d, (rx + 10, sy + 83), f"RANK {sk['level']}", cn_font=O12, en_font=O12, fill=C_ACCENT)
        
        # 名字
        nw = int(F16.getlength(sk["name"]))
        draw_text_mixed(d, (sx + 45 - nw//2, sy + 110), sk["name"], cn_font=F16, en_font=F16, fill=(221, 221, 221, 255))
        
        sx += 90 + 35

    # 3. 底部 Footer 区
    fy = H - 80
    
    # 毛玻璃背景
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
    
    draw_text_mixed(d, (PAD + 75, fy + 26), data["user"]["name"], cn_font=F28, en_font=F28, fill=C_TEXT)
    un_w = int(F28.getlength(data["user"]["name"]))
    
    ut_x = PAD + 75 + un_w + 12
    d.rectangle([ut_x, fy + 28, ut_x + int(M16.getlength(f"Lv.{data['user']['level']}")) + 24, fy + 52], fill=(255, 255, 255, 25))
    draw_text_mixed(d, (ut_x + 12, fy + 30), f"Lv.{data['user']['level']}", cn_font=M16, en_font=M16, fill=(170, 170, 170, 255))
    
    ut_x += int(M16.getlength(f"Lv.{data['user']['level']}")) + 32
    w_text = f"WORLD {data['user']['world_level']}"
    d.rectangle([ut_x, fy + 28, ut_x + int(M16.getlength(w_text)) + 24, fy + 52], fill=(255, 255, 255, 25))
    draw_text_mixed(d, (ut_x + 12, fy + 30), w_text, cn_font=M16, en_font=M16, fill=(170, 170, 170, 255))
    
    uid_text = f"UID {data['user']['uid']}"
    uid_w = int(O28.getlength(uid_text))
    draw_text_mixed(d, (W - PAD - uid_w, fy + 24), uid_text, cn_font=O28, en_font=O28, fill=C_ACCENT)

    # 输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()