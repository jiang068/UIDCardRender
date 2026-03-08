# 鸣潮伴行积分卡片渲染器 (PIL 版 · 复刻 HTML 样式)

from __future__ import annotations

import base64
import math
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageChops

# 使用包级统一字体对象与混排引擎
from . import F12, F14, F16, F18, F20, F22, F24, F26, F28, F30, F32, F38, F42, F52, F60
from . import M12, M14, M16, M18, M20, M22, M24, M26, M28, M30, M32, M38, M42, M52, M60
from . import draw_text_mixed, _b64_img, _b64_fit, _round_mask

# 尺寸与颜色常量
W = 1000
PAD = 20
INNER_W = W - PAD * 2

C_BG          = (15, 17, 21, 255)
C_WHITE       = (255, 255, 255, 255)
C_GOLD        = (212, 177, 99, 255)
C_GREY        = (109, 113, 122, 255)
C_DARK_BG     = (20, 22, 26, 120)

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    text_h = bb[3] - bb[1]
    return (box_h - text_h) // 2 - bb[1] + 1

def _draw_text_shadow(d: ImageDraw.ImageDraw, xy: tuple, text: str, cn_font, en_font, fill, shadow=(0,0,0,150), offset=(0,2)):
    x, y = int(round(xy[0])), int(round(xy[1]))
    draw_text_mixed(d, (x + offset[0], y + offset[1]), text, cn_font=cn_font, en_font=en_font, fill=shadow)
    draw_text_mixed(d, (x, y), text, cn_font=cn_font, en_font=en_font, fill=fill)

# 图像加载/缓存由包级实现提供（只缓存本地路径），本模块委托包级函数以避免 data: URI 被本地缓存

# 高性能绘制工具
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

# HTML 解析 (保持原样)
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {"bg_src": "", "user": {}, "summary": {}, "char_items": [], "wpn_items": [], "rules": [], "notes": [], "footer_src": ""}
    bg = soup.select_one(".bg-layer .bg-image")
    if bg: data["bg_src"] = bg.get("src", "")
    data["user"]["name"] = soup.select_one(".user-name").get_text(strip=True) if soup.select_one(".user-name") else ""
    uid_tag = soup.select_one(".user-uid")
    data["user"]["uid"] = uid_tag.get_text(strip=True).replace("UID", "").strip() if uid_tag else ""
    av = soup.select_one(".avatar")
    data["user"]["avatar_src"] = av.get("src", "") if av and "src" in av.attrs else ""
    stats = []
    for item in soup.select(".user-stats .stat-item"):
        val, lbl = item.select_one(".stat-value"), item.select_one(".stat-label")
        if val and lbl: stats.append({"val": val.get_text(strip=True), "label": lbl.get_text(strip=True)})
    data["user"]["stats"] = stats
    ts = soup.select_one(".total-score-value")
    data["summary"]["total_score"] = ts.get_text(strip=True) if ts else "0"
    bd_data = []
    for item in soup.select(".score-breakdown .breakdown-item"):
        lbl, val = item.select_one(".breakdown-label"), item.select_one(".breakdown-value")
        if not lbl or not val: continue
        tokens = []
        for child in val.contents:
            if child.name == "span": tokens.append({"text": child.get_text(strip=True), "cls": child.get("class", [])})
            elif getattr(child, "name", None) is None and str(child).strip(): tokens.append({"text": str(child).strip(), "cls": ["final-score"]})
        bd_data.append({"label": lbl.get_text(strip=True), "is_full": "full-width" in item.get("class", []), "tokens": tokens})
    data["summary"]["breakdowns"] = bd_data
    prog_fill = soup.select_one(".progress-fill")
    data["summary"]["prog_pct"] = float(re.search(r"width:\s*([\d.]+)%", prog_fill["style"]).group(1)) if prog_fill and "style" in prog_fill.attrs else 0
    miles = []
    for m in soup.select(".milestone"):
        left_pct = float(re.search(r"left:\s*([\d.]+)%", m["style"]).group(1)) if "style" in m.attrs else 0
        r_el = m.select_one(".reward")
        miles.append({"left": left_pct, "reached": "reached" in m.get("class", []), "label": m.select_one(".label").get_text(strip=True) if m.select_one(".label") else "", "reward": r_el.get_text(strip=True) if r_el else "", "is_last": "right:0" in (r_el["style"].replace(" ", "") if r_el and "style" in r_el.attrs else "")})
    data["summary"]["milestones"] = miles
    def parse_grid(sel):
        res = []
        sec = soup.select_one(sel)
        if not sec: return res
        for card in sec.select(".item-card"):
            res.append({"icon": card.select_one(".item-icon").get("src", "") if card.select_one(".item-icon") else "", "name": card.select_one(".item-name").get_text(strip=True) if card.select_one(".item-name") else "", "detail": card.select_one(".item-detail").get_text(strip=True) if card.select_one(".item-detail") else "", "score": card.select_one(".item-score").get_text(strip=True) if card.select_one(".item-score") else ""})
        return res
    grid_sections = soup.select(".items-section")
    for sec in grid_sections:
        title = sec.select_one(".section-title").get_text()
        if "共鸣者" in title: data["char_items"] = parse_grid(".items-section:has(:-soup-contains('共鸣者'))")
        if "武器" in title: data["wpn_items"] = parse_grid(".items-section:has(:-soup-contains('武器'))")
    cols = soup.select(".disclaimer-col")
    if len(cols) >= 2:
        for li in cols[0].select("li"): data["rules"].append(li.get_text(strip=True))
        for li in cols[1].select("li"): data["notes"].append(li.get_text(strip=True))
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
    deco_txt = "C O M P A N I O N   R E W A R D   S Y S T E M"
    draw_text_mixed(d, (INNER_W - 320, 25), deco_txt, cn_font=F14, en_font=M14, fill=(255,255,255,30))

    av_x, av_y, AV_SIZE = 40, 25, 110
    if data["user"]["avatar_src"]:
        try:
            av_img = _b64_fit(data["user"]["avatar_src"], AV_SIZE, AV_SIZE)
            card.paste(av_img, (av_x, av_y), _round_mask(AV_SIZE, AV_SIZE, AV_SIZE//2))
        except: _draw_rounded_rect(card, av_x, av_y, av_x+AV_SIZE, av_y+AV_SIZE, AV_SIZE//2, (51,51,51,255))
    else: _draw_rounded_rect(card, av_x, av_y, av_x+AV_SIZE, av_y+AV_SIZE, AV_SIZE//2, (51,51,51,255))
    d.arc([av_x - 8, av_y - 8, av_x + AV_SIZE + 8, av_y + AV_SIZE + 8], start=135, end=225, fill=C_GOLD, width=3)

    tx = av_x + AV_SIZE + 30
    _draw_text_shadow(d, (tx, 30), data["user"]["name"], F52, M52, C_WHITE)
    uid_str = f"UID {data['user']['uid']}"
    uid_w = int(F24.getlength(uid_str)) + 24
    uid_x = tx + int(F52.getlength(data["user"]["name"])) + 20
    _draw_rounded_rect(card, uid_x, 42, uid_x + uid_w, 42 + 36, 6, (0,0,0,100))
    d.rounded_rectangle([uid_x, 42, uid_x + uid_w, 42 + 36], radius=6, outline=(212,177,99,50), width=1)
    draw_text_mixed(d, (uid_x + 12, 42 + _ty(F24, uid_str, 36)), uid_str, cn_font=F24, en_font=M24, fill=C_GOLD)

    d.line([(tx, 92), (tx + 40, 92)], fill=C_GOLD, width=2)
    d.line([(tx + 40, 92), (INNER_W - 40, 92)], fill=(255,255,255,20), width=1)

    # 【修复溢出】：上提 stat_y，并压缩数值与标签的间距
    stat_y = 98 
    for i, st in enumerate(data["user"]["stats"]):
        sx = tx + i * 160
        _draw_gradient_text(card, (sx, stat_y), st["val"], M38, (255,255,255,255), C_GOLD)
        draw_text_mixed(d, (sx, stat_y + 38), st["label"], cn_font=F16, en_font=M16, fill=C_GREY)
    return card

def draw_score_summary(data: dict) -> Image.Image:
    H = 260
    img = Image.new("RGBA", (INNER_W, H), (0,0,0,0))
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, C_DARK_BG)
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, (255,255,255,10))
    d = ImageDraw.Draw(img)
    ts_w, ts_h = 240, 110
    _draw_h_gradient(img, 20, 20, 20 + ts_w, 20 + ts_h, (212, 177, 99, 40), (30, 34, 42, 80), r=12)
    d.rounded_rectangle([20, 20, 20 + ts_w, 20 + ts_h], radius=12, outline=(212,177,99,80), width=1)
    draw_text_mixed(d, (20 + (ts_w - int(F18.getlength("伴行积分总分")))//2, 35), "伴行积分总分", cn_font=F18, en_font=M18, fill=(170,170,170,255))
    _draw_gradient_text(img, (20 + (ts_w - int(F60.getlength(data["summary"]["total_score"])))//2, 55), data["summary"]["total_score"], M60, (255,255,255,255), C_GOLD)
    bd_x, bd_w = 20 + ts_w + 20, INNER_W - (20 + ts_w + 20) - 20
    for i, (bd, ry) in enumerate(zip(data["summary"]["breakdowns"][:3], [20, 80, 80])):
        bx = bd_x if i == 0 else bd_x + (i-1) * ((bd_w - 10) // 2 + 10)
        bw = bd_w if i == 0 else (bd_w - 10) // 2
        _draw_rounded_rect(img, bx, ry, bx + bw, ry + 50, 8, (35,38,45,130))
        d.rectangle([bx, ry, bx + 3, ry + 50], fill=C_GOLD)
        draw_text_mixed(d, (bx + 15, ry + _ty(F20, bd.get("label", ""), 50)), bd.get("label", ""), cn_font=F20, en_font=M20, fill=(221,221,221,255))
        cx = bx + bw - 15
        for token in reversed(bd["tokens"]):
            txt, cls = token["text"], token["cls"]
            if "tag" in cls:
                tw = int(F14.getlength(txt)) + 12
                cx -= tw
                _draw_rounded_rect(img, cx, ry + 12, cx + tw, ry + 38, 4, (212,177,99,40))
                draw_text_mixed(d, (cx + 6, ry + _ty(F14, txt, 50)), txt, cn_font=F14, en_font=M14, fill=C_GOLD)
            else:
                tw = int(F28.getlength(txt)) if "sub-score" not in cls else int(F26.getlength(txt))
                cx -= tw
                draw_text_mixed(d, (cx, ry + _ty(F28, txt, 50)), txt, cn_font=F28, en_font=M28, fill=C_GOLD if "sub-score" not in cls else (220,220,220,255))
            cx -= 8
    d.line([(20, 145), (INNER_W - 20, 145)], fill=(255,255,255,25), width=1)
    draw_text_mixed(d, (20, 160), "当前解锁进度", cn_font=F20, en_font=M20, fill=(170,170,170,255))
    pb_y, pb_x, pb_w = 225, 50, INNER_W - 100
    _draw_rounded_rect(img, pb_x, pb_y, pb_x + pb_w, pb_y + 6, 3, (255,255,255,25))
    if data["summary"]["prog_pct"] > 0: _draw_rounded_rect(img, pb_x, pb_y, pb_x + int(pb_w * (data["summary"]["prog_pct"] / 100)), pb_y + 6, 3, C_GOLD)
    for m in data["summary"]["milestones"]:
        mx = pb_x + int(pb_w * (m["left"] / 100))
        d.ellipse([mx-7, pb_y+3-7, mx+7, pb_y+3+7], fill=C_GOLD if m["reached"] else (51,51,51,255), outline=C_WHITE if m["reached"] else (102,102,102,255), width=2)
        lw = int(F16.getlength(m["label"]))
        draw_text_mixed(d, (mx-lw//2, pb_y+18), m["label"], cn_font=F16, en_font=M16, fill=C_GOLD if m["reached"] else (136,136,136,255))
        rw, ry = int(F16.getlength(m["reward"])), pb_y - 42
        rx = mx - rw - 10 if m["is_last"] else mx - rw//2
        _draw_rounded_rect(img, rx-10, ry-6, rx+rw+10, ry+16+6, 4, (20,20,25,240) if m["reached"] else (0,0,0,200))
        d.rounded_rectangle([rx-10, ry-6, rx+rw+10, ry+16+6], radius=4, outline=(212,177,99,180) if m["reached"] else (255,255,255,40), width=1)
        draw_text_mixed(d, (rx, ry), m["reward"], cn_font=F16, en_font=M16, fill=C_WHITE if m["reached"] else (204,204,204,255))
    return img

def draw_items_grid(title: str, items: list) -> Image.Image:
    if not items: return Image.new("RGBA", (1,1))
    cols, card_h = 5, 180
    rows = math.ceil(len(items) / cols)
    card_w = (INNER_W - 40 - (cols - 1) * 10) // cols
    img = Image.new("RGBA", (INNER_W, 60 + rows * card_h + (rows - 1) * 10 + 20), (0,0,0,0))
    _draw_rounded_rect(img, 0, 0, INNER_W, img.height, 12, C_DARK_BG)
    _draw_rounded_rect(img, 0, 0, INNER_W, img.height, 12, (255,255,255,10))
    d = ImageDraw.Draw(img)
    _draw_text_shadow(d, (20, 20), title, F22, M22, C_WHITE)
    d.line([(20, 55), (INNER_W - 20, 55)], fill=(212,177,99,76), width=2)
    y = 70
    for r in range(rows):
        x = 20
        for c in range(cols):
            idx = r * cols + c
            if idx >= len(items): break
            it = items[idx]
            c_img = Image.new("RGBA", (card_w, card_h), (0,0,0,0))
            _draw_rounded_rect(c_img, 0, 0, card_w, card_h, 8, (35,38,45,130))
            cd = ImageDraw.Draw(c_img)
            if it["icon"]:
                try: c_img.paste(_b64_fit(it["icon"], 76, 76), ((card_w-76)//2, 15), _round_mask(76, 76, 6))
                except: pass
            nm = it["name"]
            while F22.getlength(nm) > card_w - 10: nm = nm[:-2] + "…"
            _draw_text_shadow(cd, ((card_w - int(F22.getlength(nm)))//2, 99), nm, F22, M22, (240,240,240,255))
            draw_text_mixed(cd, ((card_w - int(F14.getlength(it["detail"])))//2, 127), it["detail"], cn_font=F14, en_font=M14, fill=(150,150,150,255))
            draw_text_mixed(cd, ((card_w - int(F26.getlength(it["score"])))//2, 147), it["score"], cn_font=F26, en_font=M26, fill=C_GOLD)
            img.alpha_composite(c_img, (x, y))
            x += card_w + 10
        y += card_h + 10
    return img

def draw_disclaimer(data: dict) -> Image.Image:
    # 【修复横线侵入】：增加总高度确保不压字，并优化横线位置
    H = 220 
    img = Image.new("RGBA", (INNER_W, H), (0,0,0,0))
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, C_DARK_BG)
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, (255,255,255,10))
    d = ImageDraw.Draw(img)
    col_w = (INNER_W - 60) // 2
    for i, (title, items, start_x) in enumerate(zip(["计分规则", "特别说明"], [data["rules"], data["notes"]], [20, 40 + col_w])):
        d.rectangle([start_x, 24, start_x+3, 44], fill=C_GOLD)
        draw_text_mixed(d, (start_x+12, 20), title, cn_font=F24, en_font=M24, fill=C_GOLD)
        y = 55
        for item in items:
            draw_text_mixed(d, (start_x, y), "•", cn_font=F14, en_font=M14, fill=(102,102,102,255))
            draw_text_mixed(d, (start_x+10, y), item, cn_font=F14, en_font=M14, fill=(170,170,170,255))
            y += 24
    
    # 【横线位置微调】：改为固定距离底部的安全位置
    line_y = H - 45
    d.line([(20, line_y), (INNER_W-20, line_y)], fill=(255,255,255,13), width=1)
    bottom_txt = "本积分计算数据非来自官方，可能与最终游戏内积分有出入，最终解释权归库洛所有。"
    draw_text_mixed(d, ((INNER_W - int(F14.getlength(bottom_txt)))//2, line_y + 10), bottom_txt, cn_font=F14, en_font=M14, fill=(102,102,102,255))
    return img

# 主渲染逻辑
def render(html: str) -> bytes:
    data = parse_html(html)
    u_card, sum_card, dis_card = draw_user_card(data), draw_score_summary(data), draw_disclaimer(data)
    c_grid, w_grid = draw_items_grid("共鸣者积分明细", data.get("char_items", [])), draw_items_grid("武器积分明细", data.get("wpn_items", []))
    
    TOP_PAD, BOTTOM_PAD, GAP = 20, 20, 20
    total_h = TOP_PAD + u_card.height + GAP + sum_card.height + GAP
    if c_grid.height > 1: total_h += c_grid.height + GAP
    if w_grid.height > 1: total_h += w_grid.height + GAP
    total_h += dis_card.height + GAP
    
    footer_img, FOOTER_H = None, 0
    if data["footer_src"]:
        try:
            footer_img = _b64_img(data["footer_src"])
            FOOTER_H = int(footer_img.height * INNER_W / footer_img.width)
            footer_img = footer_img.resize((INNER_W, FOOTER_H), Image.LANCZOS)
            total_h += FOOTER_H
        except: pass
    total_h += BOTTOM_PAD

    canvas = Image.new("RGBA", (W, total_h), C_BG)
    if data["bg_src"]:
        try: canvas.alpha_composite(_b64_fit(data["bg_src"], W, total_h))
        except: pass
    _draw_rounded_rect(canvas, 0, 0, W, total_h, 0, (0, 0, 0, 40))

    y = TOP_PAD
    canvas.alpha_composite(u_card, (PAD, y)); y += u_card.height + GAP
    canvas.alpha_composite(sum_card, (PAD, y)); y += sum_card.height + GAP
    if c_grid.height > 1: canvas.alpha_composite(c_grid, (PAD, y)); y += c_grid.height + GAP
    if w_grid.height > 1: canvas.alpha_composite(w_grid, (PAD, y)); y += w_grid.height + GAP
    canvas.alpha_composite(dis_card, (PAD, y)); y += dis_card.height + GAP
    if footer_img: canvas.alpha_composite(footer_img, (PAD, y - 10))

    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()