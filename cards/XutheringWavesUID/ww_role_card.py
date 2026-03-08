# 鸣潮角色卡片渲染器 (PIL 版 · 极限提速版)

from __future__ import annotations

import base64
import math
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageFilter


# 尺寸与颜色常量

W = 1000
PAD = 20
INNER_W = W - PAD * 2   # 960

C_BG          = (15, 17, 21, 255)
C_WHITE       = (255, 255, 255, 255)
C_GOLD        = (212, 177, 99, 255)
C_GREY        = (109, 113, 122, 255)
C_DARK_BG     = (20, 22, 26, 90)

CHAIN_COLORS = {
    0: (102, 102, 102),   # 零链: 灰
    1: (100, 220, 130),   # 一链: 绿
    2: (100, 180, 255),   # 二链: 蓝
    3: (100, 220, 130),   # 三链: 绿
    4: (220, 80, 220),    # 四链: 紫
    5: (255, 180, 60),    # 五链: 橙
    6: (255, 80, 80),     # 六链: 红
}


from . import draw_text_mixed, M12, M14, M15, M16, M17, M18, M20, M22, M24, M26, M28, M30, M32, M34, M36, M38, M42, M48, M72

# 使用包级统一字体对象（从包里导入以复用同一实例）
from . import F12, F14, F18, F20, F24, F26, F30, F42, _b64_img, _b64_fit, _round_mask

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    text_h = bb[3] - bb[1]
    return (box_h - text_h) // 2 - bb[1] + 1

def _draw_text_shadow(d: ImageDraw.ImageDraw, xy: tuple, text: str, font, fill, shadow=(0,0,0,150), offset=(0,2)):
    """Draw shadow + main text using mixed-font rendering.
    Try to infer mono font based on font.size.
    """
    x, y = int(round(xy[0])), int(round(xy[1]))
    en_font = globals().get(f"M{getattr(font, 'size', None)}", None)
    draw_text_mixed(d, (x + offset[0], y + offset[1]), text, cn_font=font, en_font=en_font, fill=shadow)
    draw_text_mixed(d, (x, y), text, cn_font=font, en_font=en_font, fill=fill)


# 图像加载/缓存由包级统一实现（只对本地路径启用缓存，避免 data: URI 导致内存增长）
def _preload_image(src: str, w: int, h: int):
    """用于线程池并发预热缓存的空函数（委托到包级 _b64_fit）"""
    if src:
        try:
            _b64_fit(src, w, h)
        except:
            pass


# 高性能绘制工具 (含静态预渲染组件)

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, r: int, fill: tuple):
    x0i, y0i, x1i, y1i = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1i - x0i, y1i - y0i
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=int(round(r)), fill=fill)
    canvas.alpha_composite(block, (x0i, y0i))

def _draw_h_gradient(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, left_rgba: tuple, right_rgba: tuple, r: int = 0):
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    grad_1d = Image.new("RGBA", (w, 1))
    for xi in range(w):
        t = xi / max(w - 1, 1)
        color = tuple(int(left_rgba[i] + (right_rgba[i] - left_rgba[i]) * t) for i in range(4))
        grad_1d.putpixel((xi, 0), color)
    grad = grad_1d.resize((w, h), Image.NEAREST)
    if r > 0:
        mask = _round_mask(w, h, r)
        new_a = ImageChops.multiply(grad.split()[3], mask)
        grad.putalpha(new_a)
    canvas.alpha_composite(grad, (x0, y0))

def _draw_v_gradient(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, top_rgba: tuple, bottom_rgba: tuple, r: int = 0):
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    grad_1d = Image.new("RGBA", (1, h))
    for yi in range(h):
        t = yi / max(h - 1, 1)
        color = tuple(int(top_rgba[i] + (bottom_rgba[i] - top_rgba[i]) * t) for i in range(4))
        grad_1d.putpixel((0, yi), color)
    grad = grad_1d.resize((w, h), Image.NEAREST)
    if r > 0:
        mask = _round_mask(w, h, r)
        new_a = ImageChops.multiply(grad.split()[3], mask)
        grad.putalpha(new_a)
    canvas.alpha_composite(grad, (x0, y0))

def _draw_gradient_text(canvas: Image.Image, xy: tuple, text: str, font, top_col, bot_col, shadow=(0,0,0,150)):
    x, y = int(round(xy[0])), int(round(xy[1]))
    d = ImageDraw.Draw(canvas)
    d.text((x, y+4), text, font=font, fill=shadow)
    bbox = font.getbbox(text)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if tw <= 0 or th <= 0: return
    t_mask = Image.new("L", (tw, th + 20), 0)
    ImageDraw.Draw(t_mask).text((-bbox[0], -bbox[1]), text, font=font, fill=255)
    grad = Image.new("RGBA", (tw, th + 20))
    _draw_v_gradient(grad, 0, 0, tw, th + 20, top_col, bot_col)
    canvas.paste(grad, (x + bbox[0], y + bbox[1]), t_mask)

# --- 预渲染可复用底板以提速 ---
@lru_cache(maxsize=4)
def _get_cached_role_base(card_w: int, card_h: int, is_5star: bool) -> Image.Image:
    bg = Image.new("RGBA", (card_w, card_h), (0,0,0,0))
    d = ImageDraw.Draw(bg)
    if is_5star:
        _draw_v_gradient(bg, 0, 0, card_w, card_h, (212,177,99,13), (30,34,42,204), r=10)
        d.rounded_rectangle([0, 0, card_w-1, card_h-1], radius=10, outline=(255,255,255,20), width=1)
        d.rectangle([2, 0, card_w-2, 2], fill=(212,177,99,102))
    else:
        _draw_rounded_rect(bg, 0, 0, card_w, card_h, 10, (30,34,42,153))
        d.rounded_rectangle([0, 0, card_w-1, card_h-1], radius=10, outline=(255,255,255,20), width=1)
        d.rectangle([2, 0, card_w-2, 2], fill=(132,63,161,102))
    # 半透明头层
    _draw_rounded_rect(bg, 0, 0, card_w, card_h, 10, (0,0,0,50))
    return bg

@lru_cache(maxsize=4)
def _get_cached_info_base(item_w: int, item_h: int, highlight: bool) -> Image.Image:
    cell = Image.new("RGBA", (item_w, item_h), (0,0,0,0))
    cd = ImageDraw.Draw(cell)
    if highlight:
        _draw_v_gradient(cell, 0, 0, item_w, item_h, (212, 177, 99, 15), (0,0,0,0))
        cd.rectangle([0,0, item_w, 1], fill=(212, 177, 99, 200))
        _draw_v_gradient(cell, 0, 0, 1, item_h, (212,177,99,200), (0,0,0,0))
        _draw_v_gradient(cell, item_w-1, 0, item_w, item_h, (212,177,99,200), (0,0,0,0))
        cd.rectangle([(item_w-20)//2, 0, (item_w+20)//2, 2], fill=C_GOLD)
    else:
        _draw_v_gradient(cell, 0, 0, item_w, item_h, (0,0,0,0), (212, 177, 99, 15))
        cd.rectangle([0,item_h-1, item_w, item_h], fill=(212, 177, 99, 200))
        _draw_v_gradient(cell, 0, 0, 1, item_h, (0,0,0,0), (212,177,99,200))
        _draw_v_gradient(cell, item_w-1, 0, item_w, item_h, (0,0,0,0), (212,177,99,200))
        cd.rectangle([(item_w-20)//2, item_h-2, (item_w+20)//2, item_h], fill=C_GOLD)
    return cell


# HTML 解析

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {"bg_src": "", "user": {}, "base_info": [], "roles": [], "footer_src": "", "date": ""}

    bg = soup.select_one(".bg-layer .bg-image")
    if bg: data["bg_src"] = bg.get("src", "")

    data["user"]["name"] = soup.select_one(".user-name").get_text(strip=True) if soup.select_one(".user-name") else ""
    uid_tag = soup.select_one(".user-uid")
    data["user"]["uid"] = uid_tag.get_text(strip=True).replace("UID", "").strip() if uid_tag else ""
    av = soup.select_one(".avatar")
    data["user"]["avatar_src"] = av.get("src", "") if av and "src" in av.attrs else ""
    
    stats = []
    for item in soup.select(".user-stats .stat-item"):
        val = item.select_one(".stat-value")
        lbl = item.select_one(".stat-label")
        if val and lbl:
            stats.append({"val": val.get_text(strip=True), "label": lbl.get_text(strip=True)})
    data["user"]["stats"] = stats

    date_el = soup.select_one(".section-header div[style*='font-family']")
    if date_el: data["date"] = date_el.get_text(strip=True)

    for item in soup.select(".base-info-grid .info-item"):
        key_el = item.select_one(".info-key")
        val_el = item.select_one(".info-value")
        hl = "highlight" in item.get("class", [])
        data["base_info"].append({
            "key": key_el.get_text(strip=True) if key_el else "",
            "value": val_el.get_text(strip=True) if val_el else "",
            "highlight": hl
        })

    for card in soup.select(".role-grid .role-card"):
        r = {"rarity": card.get("data-rarity", "4")}
        
        av_el = card.select_one(".role-avatar")
        r["avatar"] = av_el.get("src", "") if av_el else ""
        r["name"] = av_el.get("alt", "") if av_el else ""

        attr_el = card.select_one(".attribute-icon img")
        r["attr"] = attr_el.get("src", "") if attr_el else ""

        lvl_el = card.select_one(".role-level-badge")
        r["level"] = lvl_el.get_text(strip=True) if lvl_el else "Lv.1"

        wpn_el = card.select_one(".weapon-large img")
        r["weapon"] = wpn_el.get("src", "") if wpn_el else ""

        chain_el = card.select_one(".chain-large")
        r["chain_name"] = chain_el.get_text(strip=True) if chain_el else "零链"
        c_num = 0
        if chain_el:
            for cls in chain_el.get("class", []):
                m = re.match(r"chain-(\d+)", cls)
                if m: c_num = int(m.group(1))
        r["chain_num"] = c_num
        data["roles"].append(r)

    footer = soup.select_one(".footer img")
    if footer: data["footer_src"] = footer.get("src", "")

    return data


# 组件绘制

def draw_user_card(data: dict) -> Image.Image:
    H = 160
    card = Image.new("RGBA", (INNER_W, H), (0, 0, 0, 0))
    
    _draw_v_gradient(card, 0, 0, INNER_W, H, (30, 34, 42, 230), (15, 17, 21, 242), r=16)
    _draw_rounded_rect(card, 0, 0, INNER_W, H, 16, (255,255,255,5))
    
    d = ImageDraw.Draw(card)
    deco_txt = "R O V E R   R E S O N A N C E   C A R D"
    draw_text_mixed(d, (INNER_W - 300, 25), deco_txt, cn_font=F14, en_font=M14, fill=(255,255,255,30))

    av_x, av_y = 40, 30
    AV_SIZE = 100
    if data["user"]["avatar_src"]:
        try:
            av_img = _b64_fit(data["user"]["avatar_src"], AV_SIZE, AV_SIZE)
            rmask = _round_mask(AV_SIZE, AV_SIZE, AV_SIZE//2)
            card.paste(av_img, (av_x, av_y), rmask)
        except: pass
    d.arc([av_x - 6, av_y - 6, av_x + AV_SIZE + 6, av_y + AV_SIZE + 6], start=0, end=360, fill=(255,255,255,20), width=1)
    d.arc([av_x - 6, av_y - 6, av_x + AV_SIZE + 6, av_y + AV_SIZE + 6], start=135, end=225, fill=C_GOLD, width=3)

    tx = av_x + AV_SIZE + 30
    _draw_text_shadow(d, (tx, 30), data["user"]["name"], F42, C_WHITE)
    
    uid_str = f"UID {data['user']['uid']}"
    uid_w = F20.getlength(uid_str) + 24
    uid_x = tx + F42.getlength(data["user"]["name"]) + 20
    _draw_rounded_rect(card, uid_x, 38, uid_x + uid_w, 38 + 32, 6, (0,0,0,100))
    d.rounded_rectangle([uid_x, 38, uid_x + uid_w, 38 + 32], radius=6, outline=(212,177,99,50), width=1)
    draw_text_mixed(d, (uid_x + 12, 38 + _ty(F20, uid_str, 32)), uid_str, cn_font=F20, en_font=M20, fill=C_GOLD)

    d.line([(tx, 85), (tx + 40, 85)], fill=C_GOLD, width=2)
    d.line([(tx + 40, 85), (INNER_W - 40, 85)], fill=(255,255,255,20), width=1)

    stat_y = 95
    for i, st in enumerate(data["user"]["stats"]):
        sx = tx + i * 140
        _draw_gradient_text(card, (sx, stat_y), st["val"], M30, C_WHITE, C_GOLD)
        draw_text_mixed(d, (sx, stat_y + 36), st["label"], cn_font=F12, en_font=M12, fill=C_GREY)

    return card

def draw_base_info_section(data: dict) -> Image.Image:
    items = data["base_info"]
    if not items: return Image.new("RGBA", (1,1))

    cols = 6
    rows = math.ceil(len(items) / cols)
    gap = 15
    item_w = (910 - (cols - 1) * gap) // cols
    item_h = 110

    H = 20 + 40 + 25 + rows * item_h + (rows - 1) * gap + 20
    img = Image.new("RGBA", (INNER_W, H), (0,0,0,0))
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, C_DARK_BG)
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, (255,255,255,20))

    d = ImageDraw.Draw(img)
    _draw_text_shadow(d, (25, 20), "数据概览", F30, C_WHITE)
    tw = F30.getlength("数据概览")
    
    line_x = 25 + tw + 20
    _draw_h_gradient(img, int(line_x), 40, INNER_W - 150, 42, (212,177,99,204), (212,177,99,0))

    if data.get("date"):
        dw = F18.getlength(data["date"])
    draw_text_mixed(d, (INNER_W - 25 - dw, 30), data["date"], cn_font=F18, en_font=M18, fill=(136,136,136,255))

    y = 85
    for r in range(rows):
        x = 25
        for c in range(cols):
            idx = r * cols + c
            if idx >= len(items): break
            it = items[idx]

            # 直接复用预渲染的底板，不重复计算渐变
            cell = _get_cached_info_base(item_w, item_h, it["highlight"]).copy()
            cd = ImageDraw.Draw(cell)

            kw = F20.getlength(it["key"])
            draw_text_mixed(cd, ((item_w - kw)//2, 25), it["key"], cn_font=F20, en_font=M20, fill=(212,177,99,153))
            vw = F42.getlength(it["value"])
            _draw_text_shadow(cd, ((item_w - vw)//2, 55), it["value"], F42, C_WHITE, offset=(0,2))

            img.alpha_composite(cell, (x, y))
            x += item_w + gap
        y += item_h + gap

    return img

def draw_role_grid_section(data: dict) -> Image.Image:
    roles = data["roles"]
    if not roles: return Image.new("RGBA", (1,1))

    cols = 5
    rows = math.ceil(len(roles) / cols)
    gap = 15
    card_w = (910 - (cols - 1) * gap) // cols  # 170
    card_h = card_w
    
    overflow_y = 25 
    overflow_x = 15 

    H = 20 + 40 + 25 + rows * (card_h + overflow_y) + (rows - 1) * gap + 20
    img = Image.new("RGBA", (INNER_W, H), (0,0,0,0))
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, C_DARK_BG)
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, (255,255,255,20))

    d = ImageDraw.Draw(img)
    _draw_text_shadow(d, (25, 20), "共鸣者", F30, C_WHITE)
    tw = F30.getlength("共鸣者")
    _draw_h_gradient(img, int(25 + tw + 20), 40, INNER_W - 25, 42, (212,177,99,204), (212,177,99,0))

    y_offset = 85
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            if idx >= len(roles): break
            role = roles[idx]

            cell = Image.new("RGBA", (overflow_x + card_w, card_h + overflow_y), (0,0,0,0))
            cd = ImageDraw.Draw(cell)

            cx = overflow_x
            cy = 0

            # 1. 使用预渲染底板直接贴图
            base_bg = _get_cached_role_base(card_w, card_h, role["rarity"] == "5")
            cell.alpha_composite(base_bg, (cx, cy))

            # 2. 立绘
            if role["avatar"]:
                try:
                    av_sz = int(card_w * 0.85)
                    av = _b64_fit(role["avatar"], av_sz, av_sz)
                    av_mask = _round_mask(av_sz, av_sz, 8)
                    cell.paste(av, (cx + card_w - av_sz - 5, cy + 5), av_mask)
                except: pass

            # 3. 等级 Badge
            lw = F26.getlength(role["level"]) + 18
            _draw_h_gradient(cell, cx, cy+6, int(cx+lw), cy+6+34, (0,0,0,216), (0,0,0,0))
            cd.rectangle([cx, cy+6, cx+2, cy+6+34], fill=C_GOLD)
            _draw_text_shadow(cd, (cx+8, cy+6 + _ty(F26, role["level"], 34)), role["level"], F26, C_WHITE)

            # 4. 属性 Icon
            if role["attr"]:
                try:
                    attr = _b64_fit(role["attr"], 26, 26)
                    ax, ay = cx + card_w - 6 - 34, cy + 6
                    _draw_rounded_rect(cell, ax, ay, ax+34, ay+34, 17, (0,0,0,128))
                    cd.ellipse([ax, ay, ax+34, ay+34], outline=(255,255,255,40), width=1)
                    cell.alpha_composite(attr, (ax+4, ay+4))
                except: pass

            info_y_bottom = cy + card_h + overflow_y

            # 5. 武器
            if role["weapon"]:
                wpn_sz = 84
                w_base = Image.new("RGBA", (wpn_sz, wpn_sz), (50, 54, 60, 200))
                try:
                    w_img = _b64_fit(role["weapon"], wpn_sz, wpn_sz)
                    w_base.alpha_composite(w_img)
                except: pass
                
                w_final = Image.new("RGBA", (wpn_sz, wpn_sz), (0,0,0,0))
                w_mask = _round_mask(wpn_sz, wpn_sz, 8)
                w_final.paste(w_base, (0,0), w_mask)
                ImageDraw.Draw(w_final).rounded_rectangle([0,0, wpn_sz-1, wpn_sz-1], radius=8, outline=(255,255,255,60), width=1)
                
                w_rot = w_final.rotate(5, resample=Image.BILINEAR, expand=True)
                
                wx = cx - 15 + wpn_sz//2 - w_rot.width//2
                wy = info_y_bottom - 5 - wpn_sz + wpn_sz//2 - w_rot.height//2
                cell.alpha_composite(w_rot, (int(wx), int(wy)))

            # 6. 共鸣链
            ch_txt = role["chain_name"]
            ch_num = role["chain_num"]
            ch_col = CHAIN_COLORS.get(ch_num, (102,102,102))
            cw = F24.getlength(ch_txt) + 24
            
            ch_y = info_y_bottom - 8 - 28
            ch_x = cx + card_w - cw
            
            _draw_h_gradient(cell, int(ch_x-15), ch_y, int(cx+card_w), ch_y+28, (0,0,0,0), (0,0,0,230))
            cd.rectangle([cx+card_w-4, ch_y, cx+card_w, ch_y+28], fill=(*ch_col, 255))
            
            txt_col = (255,255,255,255) if ch_num > 0 else (170,170,170,255)
            if ch_num > 0:
                _draw_text_shadow(cd, (ch_x + 14, ch_y + _ty(F24, ch_txt, 28)), ch_txt, F24, txt_col, shadow=(*ch_col, 150), offset=(0,0))
            else:
                draw_text_mixed(cd, (ch_x + 14, ch_y + _ty(F24, ch_txt, 28)), ch_txt, cn_font=F24, en_font=M24, fill=txt_col)

            ix = 25 + c * (card_w + gap) - overflow_x
            iy = y_offset + r * (card_h + overflow_y + gap)
            img.alpha_composite(cell, (ix, iy))

    return img


# 主渲染逻辑

def render(html: str) -> bytes:
    data = parse_html(html)

    # ── 并发预热缓存，消除单线程解码造成的 I/O 等待 ──
    tasks = []
    card_w = (910 - (5 - 1) * 15) // 5 
    av_sz = int(card_w * 0.85)
    
    if data["user"]["avatar_src"]:
        tasks.append((data["user"]["avatar_src"], 100, 100))
        
    for r in data["roles"]:
        if r["avatar"]: tasks.append((r["avatar"], av_sz, av_sz))
        if r["attr"]: tasks.append((r["attr"], 26, 26))
        if r["weapon"]: tasks.append((r["weapon"], 84, 84))

    if tasks:
        with ThreadPoolExecutor(max_workers=8) as executor:
            for src, tw, th in tasks:
                executor.submit(_preload_image, src, tw, th)

    u_card = draw_user_card(data)
    b_card = draw_base_info_section(data)
    r_card = draw_role_grid_section(data)

    TOP_PAD = 20
    BOTTOM_PAD = 20
    GAP = 24
    
    total_h = TOP_PAD + u_card.height + GAP
    if b_card.height > 1: total_h += b_card.height + GAP
    if r_card.height > 1: total_h += r_card.height + GAP
    
    FOOTER_H = 0
    footer_img = None
    if data["footer_src"]:
        try:
            footer_img = _b64_img(data["footer_src"])
            fw, fh = footer_img.size
            FOOTER_H = int(fh * INNER_W / fw)
            footer_img = footer_img.resize((INNER_W, FOOTER_H), Image.LANCZOS)
            total_h += FOOTER_H
        except: pass
        
    total_h += BOTTOM_PAD

    canvas = Image.new("RGBA", (W, total_h), C_BG)
    if data["bg_src"]:
        try:
            bg = _b64_fit(data["bg_src"], W, total_h)
            canvas.alpha_composite(bg)
            
            # 磨砂玻璃效果，由于做了降维优化，现在它的速度是闪电级的！
            bg_blurred = _b64_fit(data["bg_src"], W, total_h, blur=True, blur_radius=15)
            mask = Image.new("L", (W, total_h), 80)
            canvas.paste(bg_blurred, (0,0), mask)
        except: pass

    y = TOP_PAD
    canvas.alpha_composite(u_card, (PAD, y))
    y += u_card.height + GAP

    if b_card.height > 1:
        canvas.alpha_composite(b_card, (PAD, y))
        y += b_card.height + GAP
        
    if r_card.height > 1:
        canvas.alpha_composite(r_card, (PAD, y))
        y += r_card.height + GAP

    if footer_img:
        canvas.alpha_composite(footer_img, (PAD, y - 10))

    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()