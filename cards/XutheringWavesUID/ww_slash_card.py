# 鸣潮海墟卡片渲染器 (PIL 版 · 极限提速版)

from __future__ import annotations

import base64
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops


# 尺寸与颜色常量

W = 1000          # 总宽
PAD = 40          # 左右内边距
INNER_W = W - PAD * 2   # 920

C_BG          = (15, 17, 21, 255)
C_WHITE       = (255, 255, 255, 255)
C_GOLD        = (212, 177, 99, 255)
C_GREY        = (109, 113, 122, 255)
C_ROLE_BG_DEF = (42, 46, 53, 255)

CHAIN_COLORS = {
    0: (102, 102, 102),   # #666
    1: (100, 180, 255),   # 蓝
    2: (100, 220, 130),   # 绿
    3: (255, 180, 60),    # 橙
    4: (220, 80, 220),    # 紫
    5: (255, 80, 80),     # 红
    6: (255, 200, 1),     # 金
}


from . import draw_text_mixed, M12, M14, M15, M16, M17, M18, M20, M22, M24, M26, M28, M30, M32, M34, M36, M38, M42, M48, M60, M72

# 使用包级统一字体对象（从包里导入以复用同一实例）
from . import F12, F14, F18, F20, F24, F28, F30, F40, F42, F56, F60,  _b64_img, _b64_fit, _round_mask

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    text_h = bb[3] - bb[1]
    return (box_h - text_h) // 2 - bb[1] + 1

def _draw_text_shadow(d: ImageDraw.ImageDraw, xy: tuple, text: str, font, fill, shadow=(0,0,0,150), offset=(0,2)):
    """Draw shadow + main text using mixed-font rendering.
    Infer matching mono font by font.size if available.
    """
    x, y = int(round(xy[0])), int(round(xy[1]))
    en_font = globals().get(f"M{getattr(font, 'size', None)}", None)
    draw_text_mixed(d, (x + offset[0], y + offset[1]), text, cn_font=font, en_font=en_font, fill=shadow)
    draw_text_mixed(d, (x, y), text, cn_font=font, en_font=en_font, fill=fill)


# 图片与蒙版处理由包级统一实现（只在包内缓存本地路径，避免 data: URI 导致内存增长）
# 预热函数仍然调用包级 _b64_fit
def _preload_image(src: str, w: int, h: int):
    """用于多线程并发预热的空跑函数（委托到包级 _b64_fit）"""
    if src:
        try:
            _b64_fit(src, w, h)
        except:
            pass


# 高性能渐变绘制

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, r: int, fill: tuple):
    x0i, y0i, x1i, y1i = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1i - x0i, y1i - y0i
    if w <= 0 or h <= 0:
        return
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

def _parse_color(color_str: str, default: tuple = (212, 177, 99)) -> tuple:
    color_str = color_str.strip().lower()
    if color_str.startswith("#"):
        c = color_str.lstrip("#")
        if len(c) == 3: c = "".join([x*2 for x in c])
        if len(c) == 6:
            return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    elif color_str.startswith("rgb"):
        m = re.findall(r'\d+', color_str)
        if len(m) >= 3:
            return (int(m[0]), int(m[1]), int(m[2]))
    return default


# HTML 解析

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg_src": "", "user": {}, "section": {}, "challenges": [], "footer_src": ""
    }

    bg = soup.select_one(".bg-layer .bg-image")
    if bg: data["bg_src"] = bg.get("src", "")

    data["user"]["name"] = soup.select_one(".user-name").get_text(strip=True) if soup.select_one(".user-name") else ""
    uid_tag = soup.select_one(".user-uid")
    data["user"]["uid"] = uid_tag.get_text(strip=True).replace("UID", "").strip() if uid_tag else ""
    av = soup.select_one(".avatar")
    data["user"]["avatar_src"] = av.get("src", "") if av else ""
    
    stats = []
    for item in soup.select(".user-stats .stat-item"):
        val = item.select_one(".stat-value")
        lbl = item.select_one(".stat-label")
        if val and lbl:
            stats.append({"val": val.get_text(strip=True), "label": lbl.get_text(strip=True)})
    data["user"]["stats"] = stats

    title = soup.select_one(".section-title")
    data["section"]["title"] = title.get_text(strip=True) if title else "冥歌海墟"
    period = soup.select_one(".period-badge")
    data["section"]["period"] = period.get_text(strip=True) if period else ""
    date = soup.select_one(".date-badge")
    data["section"]["date"] = date.get_text(strip=True) if date else ""

    for block in soup.select(".slash-block"):
        chal = {"header_bg": "", "id": "", "name": "", "score": "", "rank_img": "", "teams": []}
        
        header = block.select_one(".slash-header")
        if header and "style" in header.attrs:
            m = re.search(r"url\(['\"]?(data:[^'\"]+)['\"]?\)", header["style"])
            if m: chal["header_bg"] = m.group(1)
            
        sid = block.select_one(".slash-id")
        chal["id"] = sid.get_text(strip=True) if sid else ""
        sname = block.select_one(".slash-name")
        chal["name"] = sname.get_text(strip=True) if sname else ""
        sscore = block.select_one(".slash-score-text")
        chal["score"] = sscore.get_text(strip=True) if sscore else ""
        srank = block.select_one(".slash-rank-img")
        if srank: chal["rank_img"] = srank.get("src", "")

        for trow in block.select(".team-row"):
            team = {"bg": "", "watermark": "", "name": "", "score": "", "roles": [], "buff_img": "", "buff_color": ""}
            
            if "style" in trow.attrs:
                m = re.search(r"url\(['\"]?(data:[^'\"]+)['\"]?\)", trow["style"])
                if m: team["bg"] = m.group(1)
                
            wm = trow.select_one(".team-icon-watermark")
            if wm: team["watermark"] = wm.get("src", "")
            
            tname = trow.select_one(".team-name")
            team["name"] = tname.get_text(strip=True) if tname else ""
            tscore = trow.select_one(".team-score")
            team["score"] = tscore.get_text(strip=True) if tscore else ""

            for role_el in trow.select(".role-mini"):
                star = int(role_el.get("data-star", 4))
                img = role_el.select_one("img")
                src = img["src"] if img else ""
                lvl_el = role_el.select_one(".role-mini-level")
                lvl = lvl_el.get_text(strip=True) if lvl_el else "Lv.1"
                chain_el = role_el.select_one(".role-mini-chain")
                chain_str = chain_el.get_text(strip=True) if chain_el else "零链"
                chain_num = 0
                if chain_el:
                    for cls in chain_el.get("class", []):
                        m3 = re.match(r"chain-(\d+)", cls)
                        if m3: chain_num = int(m3.group(1))
                team["roles"].append({
                    "star_level": star, "img_src": src, "level_str": lvl,
                    "chain_str": chain_str, "chain_num": chain_num
                })

            bimg = trow.select_one(".buff-img")
            if bimg: team["buff_img"] = bimg.get("src", "")
            bstripe = trow.select_one(".buff-stripe")
            if bstripe and "style" in bstripe.attrs:
                m = re.search(r"background-color:\s*([^;]+)", bstripe["style"])
                if m: team["buff_color"] = m.group(1)
            
            chal["teams"].append(team)
            
        data["challenges"].append(chal)

    footer = soup.select_one(".footer img")
    if footer: data["footer_src"] = footer.get("src", "")

    return data


# 组件绘制

def _draw_role_mini(role: dict) -> Image.Image:
    RW, RH = 125, 125
    card = Image.new("RGBA", (RW, RH), C_ROLE_BG_DEF)

    if role["img_src"]:
        try:
            av = _b64_fit(role["img_src"], RW, RH)
            rmask = _round_mask(RW, RH, 12)
            card.paste(av, (0, 0), rmask)
        except: pass

    border_color = (212, 177, 99, 255) if role["star_level"] == 5 else (156, 39, 176, 255)
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, RW - 1, RH - 1], radius=12, outline=border_color, width=2)

    level_text = role["level_str"]
    lh = 26
    lw = int(F20.getlength(level_text)) + 16
    _draw_h_gradient(card, 0, 4, lw + 10, 4 + lh, (0, 0, 0, 216), (0, 0, 0, 0))
    d.rectangle([0, 4, 3, 4 + lh], fill=(212, 177, 99, 255))
    draw_text_mixed(d, (6, 4 + _ty(F20, level_text, lh)), level_text, cn_font=F20, en_font=M20, fill=C_WHITE)

    chain_num  = role["chain_num"]
    chain_text = role["chain_str"]
    chain_col  = CHAIN_COLORS.get(chain_num, (102, 102, 102))
    text_col   = (230, 230, 230) if chain_num == 0 else chain_col
    cw = int(F20.getlength(chain_text)) + 20
    ch = 28
    cy = RH - ch - 4
    cx = RW - cw - 4

    _draw_h_gradient(card, cx - 14, cy, RW, cy + ch, (0, 0, 0, 0), (0, 0, 0, 235))
    d.rectangle([RW - 4, cy, RW - 1, cy + ch], fill=(*chain_col, 255))
    draw_text_mixed(d, (cx + 2, cy + _ty(F20, chain_text, ch)), chain_text, cn_font=F20, en_font=M20, fill=(*text_col, 255))

    return card

def draw_user_card(data: dict) -> Image.Image:
    H = 160
    card = Image.new("RGBA", (INNER_W, H), (0, 0, 0, 0))
    
    _draw_v_gradient(card, 0, 0, INNER_W, H, (30, 34, 42, 230), (15, 17, 21, 242), r=16)
    _draw_rounded_rect(card, 0, 0, INNER_W, H, 16, (255,255,255,5))
    
    d = ImageDraw.Draw(card)
    draw_text_mixed(d, (INNER_W - 140, 20), "SLASH REPORT", cn_font=F14, en_font=M14, fill=(255,255,255,30))

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
        _draw_text_shadow(d, (sx, stat_y), st["val"], F30, C_WHITE)
        draw_text_mixed(d, (sx, stat_y + 36), st["label"], cn_font=F12, en_font=M12, fill=C_GREY)

    return card

def draw_slash_block(chal: dict) -> Image.Image:
    teams_h = len(chal["teams"]) * 150
    total_h = 120 + teams_h
    img = Image.new("RGBA", (INNER_W, total_h), (0,0,0,0))
    d = ImageDraw.Draw(img)

    if chal["header_bg"]:
        try:
            h_bg = _b64_fit(chal["header_bg"], INNER_W, 120)
            img.paste(h_bg, (0,0))
        except: pass

    id_text = chal["id"]
    text_len = len(id_text) # 判断位数

    if text_len == 1:
        hx = 38
    else:
        hx = 20

    _draw_text_shadow(d, (hx, 26), id_text, F60, C_WHITE)
    id_w = F60.getlength(id_text)
    _draw_text_shadow(d, (hx + id_w + 20, 42), chal["name"], F40, C_WHITE)

    hrx = INNER_W - 40
    if chal["score"]:
        sc_w = F24.getlength(chal["score"])
        hrx -= int(sc_w)
        _draw_text_shadow(d, (hrx, 48), chal["score"], F24, C_GOLD)
        
    if chal["rank_img"]:
        try:
            # 优化：不要对评级图标使用过大的降采样算法，直接简单读取以提速
            r_img = _b64_img(chal["rank_img"])
            rw, rh = r_img.size
            if rh > 0:
                target_h = 80
                target_w = int(rw * (target_h / rh))
                r_img = r_img.resize((target_w, target_h), Image.BILINEAR)
                img.alpha_composite(r_img, (int(hrx - target_w - 20), 20))
        except: pass

    y = 120
    _draw_rounded_rect(img, 0, y, INNER_W, total_h, 0, (30, 34, 42, 240))
    
    for team in chal["teams"]:
        row = Image.new("RGBA", (INNER_W, 150), (0,0,0,0))
        rd = ImageDraw.Draw(row)
        
        if team["bg"]:
            try:
                t_bg = _b64_fit(team["bg"], INNER_W, 150)
                row.alpha_composite(t_bg)
            except: pass
            
        if team["watermark"]:
            try:
                wm = _b64_fit(team["watermark"], 100, 100)
                row.alpha_composite(wm, (20, 25))
            except: pass
            
        _draw_text_shadow(rd, (160, 45), team["name"], F28, C_WHITE)
        _draw_text_shadow(rd, (160, 85), team["score"], F24, C_GOLD)
        
        rx = 360
        for role in team["roles"]:
            rm = _draw_role_mini(role)
            row.alpha_composite(rm, (rx, 12))
            rx += 125 + 20
            
        if team["buff_img"]:
            bx = INNER_W - 30 - 90
            _draw_rounded_rect(row, bx, 30, bx + 90, 30 + 90, 8, (0,0,0,150))
            try:
                b_img = _b64_fit(team["buff_img"], 90, 90)
                bmask = _round_mask(90, 90, 8)
                row.paste(b_img, (bx, 30), bmask)
            except: pass
            rd.rectangle([bx, 30 + 90 - 6, bx + 90, 30 + 90], fill=_parse_color(team["buff_color"]))

        img.alpha_composite(row, (0, y))
        y += 150

    fmask = _round_mask(INNER_W, total_h, 12)
    out = Image.new("RGBA", (INNER_W, total_h), (0,0,0,0))
    out.paste(img, (0,0), fmask)
    ImageDraw.Draw(out).rounded_rectangle([0,0, INNER_W-1, total_h-1], radius=12, outline=(255,255,255,20), width=1)
    
    return out


# 主渲染逻辑

def render(html: str) -> bytes:
    data = parse_html(html)

    # ── 并发预热缓存，消除单线程解码造成的 I/O 等待 ──
    tasks = []
    if data["user"]["avatar_src"]:
        tasks.append((data["user"]["avatar_src"], 100, 100))
        
    for c in data["challenges"]:
        if c["header_bg"]: tasks.append((c["header_bg"], INNER_W, 120))
        for t in c["teams"]:
            if t["bg"]: tasks.append((t["bg"], INNER_W, 150))
            if t["watermark"]: tasks.append((t["watermark"], 100, 100))
            if t["buff_img"]: tasks.append((t["buff_img"], 90, 90))
            for r in t["roles"]:
                if r["img_src"]: tasks.append((r["img_src"], 125, 125))

    if tasks:
        with ThreadPoolExecutor(max_workers=8) as executor:
            for src, tw, th in tasks:
                executor.submit(_preload_image, src, tw, th)

    u_card = draw_user_card(data)
    blocks = [draw_slash_block(c) for c in data["challenges"]]

    TOP_PAD = 40
    BOTTOM_PAD = 20
    GAP = 35
    
    sec_h = 60
    for b in blocks:
        sec_h += b.height + 25
    sec_h += 15
    
    total_h = TOP_PAD + u_card.height + GAP + sec_h + 30
    
    FOOTER_H = 0
    footer_img = None
    if data["footer_src"]:
        try:
            # 避免全屏预热失败导致串行，直接在这里快速处理
            footer_img = _b64_img(data["footer_src"])
            fw, fh = footer_img.size
            FOOTER_H = int(fh * INNER_W / fw)
            footer_img = footer_img.resize((INNER_W, FOOTER_H), Image.BILINEAR)
            total_h += FOOTER_H
        except: pass
        
    total_h += BOTTOM_PAD

    canvas = Image.new("RGBA", (W, total_h), C_BG)
    if data["bg_src"]:
        try:
            bg = _b64_fit(data["bg_src"], W, total_h)
            canvas.alpha_composite(bg)
        except: pass
        
    _draw_rounded_rect(canvas, 0, 0, W, total_h, 0, (0, 0, 0, 50))

    y = TOP_PAD
    canvas.alpha_composite(u_card, (PAD, y))
    y += u_card.height + GAP

    _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + sec_h, 16, (20, 22, 26, 153))
    
    d = ImageDraw.Draw(canvas)
    
    title = data["section"]["title"]
    _draw_text_shadow(d, (PAD + 30, y + 20), title, F30, C_WHITE)
    tw = F30.getlength(title)
    
    period = data["section"]["period"]
    date_str = data["section"]["date"]
    pw = F20.getlength(period) + 24 if period else 0
    dw = F18.getlength(date_str) + 15 if date_str else 0
    
    right_x = PAD + INNER_W - 30 - pw - dw
    _draw_h_gradient(canvas, int(PAD + 30 + tw + 20), y + 34, int(right_x), y + 36, (212, 177, 99, 204), (212, 177, 99, 0))
    
    px = right_x + 15
    if period:
        _draw_rounded_rect(canvas, px, y + 20, px + pw, y + 50, 6, (212, 177, 99, 38))
        d.rounded_rectangle([px, y + 20, px + pw, y + 50], radius=6, outline=(212, 177, 99, 76), width=1)
        draw_text_mixed(d, (px + 12, y + 20 + _ty(F20, period, 30)), period, cn_font=F20, en_font=M20, fill=C_GOLD)
    if date_str:
        draw_text_mixed(d, (px + pw + 15, y + 20 + _ty(F18, date_str, 30)), date_str, cn_font=F18, en_font=M18, fill=C_GREY)
        
    d.line([(PAD + 30, y + 60), (PAD + INNER_W - 30, y + 60)], fill=(255, 255, 255, 13), width=1)

    y += 85
    
    for b in blocks:
        canvas.alpha_composite(b, (PAD, y))
        y += b.height + 25

    if footer_img:
        y += 10
        canvas.alpha_composite(footer_img, (PAD, y))

    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()