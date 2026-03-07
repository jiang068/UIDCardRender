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


# 尺寸与颜色常量

W = 1000
PAD = 20
INNER_W = W - PAD * 2

C_BG          = (15, 17, 21, 255)
C_WHITE       = (255, 255, 255, 255)
C_GOLD        = (212, 177, 99, 255)
C_GREY        = (109, 113, 122, 255)
C_DARK_BG     = (20, 22, 26, 120)


# 字体加载

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    FONT_FILE = Path(__file__).parent.parent.parent / "assets" / "H7GBKHeavy.TTF"
    candidates = [
        str(FONT_FILE),
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(str(p), size)
        except Exception:
            continue
    return ImageFont.load_default()

F12 = _load_font(12)
F14 = _load_font(14)
F16 = _load_font(16, bold=True)
F18 = _load_font(18, bold=True)
F20 = _load_font(20, bold=True)
F22 = _load_font(22, bold=True)
F24 = _load_font(24, bold=True)
F26 = _load_font(26, bold=True)
F28 = _load_font(28, bold=True)
F30 = _load_font(30, bold=True)
F32 = _load_font(32, bold=True)
F38 = _load_font(38, bold=True)
F42 = _load_font(42, bold=True)
F52 = _load_font(52, bold=True)
F60 = _load_font(60, bold=True)

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    text_h = bb[3] - bb[1]
    return (box_h - text_h) // 2 - bb[1] + 1

def _draw_text_shadow(d: ImageDraw.ImageDraw, xy: tuple, text: str, font, fill, shadow=(0,0,0,150), offset=(0,2)):
    x, y = int(round(xy[0])), int(round(xy[1]))
    d.text((x + offset[0], y + offset[1]), text, font=font, fill=shadow)
    d.text((x, y), text, font=font, fill=fill)


# 图像处理缓存

@lru_cache(maxsize=256)
def _b64_img(src: str) -> Image.Image:
    if src.startswith("data:"):
        if "," in src:
            src = src.split(",", 1)[1]
        return Image.open(BytesIO(base64.b64decode(src))).convert("RGBA")
    else:
        base_dir = Path(__file__).parent.parent
        p = Path(src) if Path(src).is_absolute() else base_dir / src
        if p.exists():
            return Image.open(p).convert("RGBA")
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



# HTML 解析

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg_src": "", "user": {}, "summary": {}, "char_items": [], "wpn_items": [], 
        "rules": [], "notes": [], "footer_src": ""
    }

    bg = soup.select_one(".bg-layer .bg-image")
    if bg: data["bg_src"] = bg.get("src", "")

    # User
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

    # Summary
    ts = soup.select_one(".total-score-value")
    data["summary"]["total_score"] = ts.get_text(strip=True) if ts else "0"
    
    bd_items = soup.select(".score-breakdown .breakdown-item")
    bd_data = []
    for item in bd_items:
        lbl = item.select_one(".breakdown-label")
        val = item.select_one(".breakdown-value")
        if not lbl or not val: continue
        
        is_full = "full-width" in item.get("class", [])
        
        # 安全、精准地解析各个颜色的 tokens 列表
        tokens = []
        for child in val.contents:
            if child.name == "span":
                tokens.append({"text": child.get_text(strip=True), "cls": child.get("class", [])})
            elif getattr(child, "name", None) is None: 
                s = str(child).strip()
                if s: tokens.append({"text": s, "cls": ["final-score"]})
                
        bd_data.append({
            "label": lbl.get_text(strip=True),
            "is_full": is_full,
            "tokens": tokens
        })
    data["summary"]["breakdowns"] = bd_data
    
    # Progress
    prog_fill = soup.select_one(".progress-fill")
    prog_pct = 0
    if prog_fill and "style" in prog_fill.attrs:
        m = re.search(r"width:\s*([\d.]+)%", prog_fill["style"])
        if m: prog_pct = float(m.group(1))
    data["summary"]["prog_pct"] = prog_pct
    
    miles = []
    for m in soup.select(".milestone"):
        left_pct = 0
        if "style" in m.attrs:
            mat = re.search(r"left:\s*([\d.]+)%", m["style"])
            if mat: left_pct = float(mat.group(1))
            
        r_el = m.select_one(".reward")
        miles.append({
            "left": left_pct,
            "reached": "reached" in m.get("class", []),
            "label": m.select_one(".label").get_text(strip=True) if m.select_one(".label") else "",
            "reward": r_el.get_text(strip=True) if r_el else "",
            "is_last": "right:0" in (r_el["style"].replace(" ", "") if r_el and "style" in r_el.attrs else "")
        })
    data["summary"]["milestones"] = miles

    # Grids
    def parse_grid(sel):
        res = []
        sec = soup.select_one(sel)
        if not sec: return res
        for card in sec.select(".item-card"):
            img = card.select_one(".item-icon")
            nm = card.select_one(".item-name")
            dt = card.select_one(".item-detail")
            sc = card.select_one(".item-score")
            res.append({
                "icon": img.get("src", "") if img else "",
                "name": nm.get_text(strip=True) if nm else "",
                "detail": dt.get_text(strip=True) if dt else "",
                "score": sc.get_text(strip=True) if sc else ""
            })
        return res
        
    grid_sections = soup.select(".items-section")
    if len(grid_sections) >= 1:
        for sec in grid_sections:
            title = sec.select_one(".section-title").get_text()
            if "共鸣者" in title:
                data["char_items"] = parse_grid(".items-section:has(:-soup-contains('共鸣者'))")
            if "武器" in title:
                data["wpn_items"] = parse_grid(".items-section:has(:-soup-contains('武器'))")

    # Disclaimer
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
    # 拉大顶部修饰文字间距，贴近原图质感
    deco_txt = "C O M P A N I O N   R E W A R D   S Y S T E M"
    d.text((INNER_W - 320, 25), deco_txt, font=F14, fill=(255,255,255,30))

    av_x, av_y = 40, 25
    AV_SIZE = 110
    if data["user"]["avatar_src"]:
        try:
            av_img = _b64_fit(data["user"]["avatar_src"], AV_SIZE, AV_SIZE)
            rmask = _round_mask(AV_SIZE, AV_SIZE, AV_SIZE//2)
            card.paste(av_img, (av_x, av_y), rmask)
        except: 
            _draw_rounded_rect(card, av_x, av_y, av_x+AV_SIZE, av_y+AV_SIZE, AV_SIZE//2, (51,51,51,255))
    else:
        _draw_rounded_rect(card, av_x, av_y, av_x+AV_SIZE, av_y+AV_SIZE, AV_SIZE//2, (51,51,51,255))
        
    d.arc([av_x - 8, av_y - 8, av_x + AV_SIZE + 8, av_y + AV_SIZE + 8], start=0, end=360, fill=(255,255,255,20), width=1)
    d.arc([av_x - 8, av_y - 8, av_x + AV_SIZE + 8, av_y + AV_SIZE + 8], start=135, end=225, fill=C_GOLD, width=3)

    tx = av_x + AV_SIZE + 30
    _draw_text_shadow(d, (tx, 30), data["user"]["name"], F52, C_WHITE)
    
    uid_str = f"UID {data['user']['uid']}"
    uid_w = F24.getlength(uid_str) + 24
    uid_x = tx + F52.getlength(data["user"]["name"]) + 20
    _draw_rounded_rect(card, uid_x, 42, uid_x + uid_w, 42 + 36, 6, (0,0,0,100))
    d.rounded_rectangle([uid_x, 42, uid_x + uid_w, 42 + 36], radius=6, outline=(212,177,99,50), width=1)
    d.text((uid_x + 12, 42 + _ty(F24, uid_str, 36)), uid_str, font=F24, fill=C_GOLD)

    d.line([(tx, 95), (tx + 40, 95)], fill=C_GOLD, width=2)
    d.line([(tx + 40, 95), (INNER_W - 40, 95)], fill=(255,255,255,20), width=1)

    stat_y = 105
    for i, st in enumerate(data["user"]["stats"]):
        sx = tx + i * 160
        _draw_gradient_text(card, (sx, stat_y), st["val"], F38, C_WHITE, C_GOLD)
        d.text((sx, stat_y + 44), st["label"], font=F16, fill=C_GREY)

    return card


def draw_score_summary(data: dict) -> Image.Image:
    H = 260
    img = Image.new("RGBA", (INNER_W, H), (0,0,0,0))
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, C_DARK_BG)
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, (255,255,255,10))
    d = ImageDraw.Draw(img)

    # -- Left Total Score --
    ts_w, ts_h = 240, 110
    _draw_h_gradient(img, 20, 20, 20 + ts_w, 20 + ts_h, (212, 177, 99, 40), (30, 34, 42, 80), r=12)
    d.rounded_rectangle([20, 20, 20 + ts_w, 20 + ts_h], radius=12, outline=(212,177,99,80), width=1)
    
    d.text((20 + (ts_w - F18.getlength("伴行积分总分"))//2, 35), "伴行积分总分", font=F18, fill=(170,170,170,255))
    ts_val = data["summary"]["total_score"]
    _draw_gradient_text(img, (20 + (ts_w - F60.getlength(ts_val))//2, 55), ts_val, F60, C_WHITE, C_GOLD)

    # -- Right Breakdowns --
    bd_x = 20 + ts_w + 20
    bd_w = INNER_W - bd_x - 20
    
    bd1 = data["summary"]["breakdowns"][0] if len(data["summary"]["breakdowns"]) > 0 else {"tokens":[]}
    bd2 = data["summary"]["breakdowns"][1] if len(data["summary"]["breakdowns"]) > 1 else {"tokens":[]}
    bd3 = data["summary"]["breakdowns"][2] if len(data["summary"]["breakdowns"]) > 2 else {"tokens":[]}

    # Row 1 (Full)
    row_y = 20
    _draw_rounded_rect(img, bd_x, row_y, bd_x + bd_w, row_y + 50, 8, (35,38,45,130))
    d.rectangle([bd_x, row_y, bd_x + 3, row_y + 50], fill=C_GOLD)
    d.text((bd_x + 15, row_y + _ty(F20, bd1.get("label", ""), 50)), bd1.get("label", ""), font=F20, fill=(221,221,221,255))
    
    cx = bd_x + bd_w - 15
    for token in reversed(bd1["tokens"]):
        txt = token["text"]
        cls = token["cls"]
        if "tag" in cls:
            tw = F14.getlength(txt) + 12
            cx -= tw
            _draw_rounded_rect(img, cx, row_y + 12, cx + tw, row_y + 38, 4, (212,177,99,40))
            d.text((cx + 6, row_y + _ty(F14, txt, 50)), txt, font=F14, fill=C_GOLD)
            cx -= 8
        elif "op-arrow" in cls:
            tw = F22.getlength(txt)
            cx -= tw
            d.text((cx, row_y + _ty(F22, txt, 50)), txt, font=F22, fill=C_GOLD)
            cx -= 8
        elif "op" in cls:
            tw = F20.getlength(txt)
            cx -= tw
            d.text((cx, row_y + _ty(F20, txt, 50)), txt, font=F20, fill=(150,150,150,255))
            cx -= 8
        elif "sub-score" in cls:
            tw = F26.getlength(txt)
            cx -= tw
            # 还原图二：这里的子分数是淡灰色
            d.text((cx, row_y + _ty(F26, txt, 50)), txt, font=F26, fill=(220,220,220,255))
            cx -= 8
        else: # final-score
            tw = F30.getlength(txt)
            cx -= tw
            # 还原图二：总分是金色
            d.text((cx, row_y + _ty(F30, txt, 50)), txt, font=F30, fill=C_GOLD)
            cx -= 8

    # Row 2 (Half + Half)
    hw = (bd_w - 10) // 2
    for i, bd in enumerate([bd2, bd3]):
        bx = bd_x + i * (hw + 10)
        row_y = 80
        _draw_rounded_rect(img, bx, row_y, bx + hw, row_y + 50, 8, (35,38,45,130))
        d.rectangle([bx, row_y, bx + 3, row_y + 50], fill=C_GOLD)
        d.text((bx + 15, row_y + _ty(F20, bd.get("label", ""), 50)), bd.get("label", ""), font=F20, fill=(221,221,221,255))
        
        cx = bx + hw - 15
        for token in reversed(bd.get("tokens", [])):
            txt = token["text"]
            cls = token["cls"]
            if "tag" in cls:
                tw = F14.getlength(txt) + 12
                cx -= tw
                _draw_rounded_rect(img, cx, row_y + 12, cx + tw, row_y + 38, 4, (212,177,99,40))
                d.text((cx + 6, row_y + _ty(F14, txt, 50)), txt, font=F14, fill=C_GOLD)
                cx -= 8
            else:
                tw = F28.getlength(txt)
                cx -= tw
                d.text((cx, row_y + _ty(F28, txt, 50)), txt, font=F28, fill=C_GOLD)
                cx -= 8

    # -- Bottom Progress Bar --
    d.line([(20, 145), (INNER_W - 20, 145)], fill=(255,255,255,25), width=1)
    d.text((20, 160), "当前解锁进度", font=F20, fill=(170,170,170,255))

    pb_y = 225
    pb_x = 50
    pb_w = INNER_W - 100
    _draw_rounded_rect(img, pb_x, pb_y, pb_x + pb_w, pb_y + 6, 3, (255,255,255,25))
    
    pct = data["summary"]["prog_pct"]
    fill_w = max(0, int(pb_w * (pct / 100)))
    if fill_w > 0:
        _draw_rounded_rect(img, pb_x, pb_y, pb_x + fill_w, pb_y + 6, 3, C_GOLD)
    
    # Milestones
    for m in data["summary"]["milestones"]:
        mx = pb_x + int(pb_w * (m["left"] / 100))
        # Dot
        c_fill = C_GOLD if m["reached"] else (51,51,51,255)
        c_out  = C_WHITE if m["reached"] else (102,102,102,255)
        d.ellipse([mx - 7, pb_y + 3 - 7, mx + 7, pb_y + 3 + 7], fill=c_fill, outline=c_out, width=2)
        
        # Label
        l_col = C_GOLD if m["reached"] else (136,136,136,255)
        lw = F16.getlength(m["label"])
        d.text((mx - lw//2, pb_y + 18), m["label"], font=F16, fill=l_col)
        
        # Reward
        rw = F16.getlength(m["reward"])
        
        # 精准对齐里程碑的边缘，调整上下预留距离
        if m["is_last"]:
            rx = mx - rw - 10
        elif m["left"] == 10:
            rx = mx - rw//2
        else:
            rx = mx - rw//2
            
        ry = pb_y - 42
        
        r_bg = (20,20,25,240) if m["reached"] else (0,0,0,200)
        r_out = (212,177,99,180) if m["reached"] else (255,255,255,40)
        
        b_px, b_py = 10, 6
        _draw_rounded_rect(img, rx - b_px, ry - b_py, rx + rw + b_px, ry + 16 + b_py, 4, r_bg)
        d.rounded_rectangle([rx - b_px, ry - b_py, rx + rw + b_px, ry + 16 + b_py], radius=4, outline=r_out, width=1)
        
        rc = C_WHITE if m["reached"] else (204,204,204,255)
        d.text((rx, ry), m["reward"], font=F16, fill=rc)

    return img


def draw_items_grid(title: str, items: list) -> Image.Image:
    if not items: return Image.new("RGBA", (1,1))
    
    cols = 5
    rows = math.ceil(len(items) / cols)
    card_w = (INNER_W - 40 - (cols - 1) * 10) // cols
    
    # 增加卡片高度以容纳更大的图片和宽松排版 (完美复刻图二)
    card_h = 180
    
    H = 40 + 20 + rows * card_h + (rows - 1) * 10 + 20
    img = Image.new("RGBA", (INNER_W, H), (0,0,0,0))
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, C_DARK_BG)
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, (255,255,255,10))
    
    d = ImageDraw.Draw(img)
    _draw_text_shadow(d, (20, 20), title, F22, C_WHITE)
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
            _draw_rounded_rect(c_img, 0, 0, card_w, card_h, 8, (255,255,255,13))
            cd = ImageDraw.Draw(c_img)
            
            # Icon：由原来的 64 增加到 76
            icon_sz = 76
            icon_y = 15
            if it["icon"]:
                try:
                    ic = _b64_fit(it["icon"], icon_sz, icon_sz)
                    _draw_rounded_rect(c_img, (card_w-icon_sz)//2, icon_y, (card_w+icon_sz)//2, icon_y+icon_sz, 6, (0,0,0,100))
                    cmask = _round_mask(icon_sz, icon_sz, 6)
                    c_img.paste(ic, ((card_w-icon_sz)//2, icon_y), cmask)
                except: pass
                
            nm = it["name"]
            while F22.getlength(nm) > card_w - 10 and len(nm) > 1:
                nm = nm[:-2] + "…"
            nm_w = F22.getlength(nm)
            _draw_text_shadow(cd, ((card_w - nm_w)//2, icon_y + icon_sz + 8), nm, F22, (240,240,240,255))
            
            dt_w = F14.getlength(it["detail"])
            cd.text(((card_w - dt_w)//2, icon_y + icon_sz + 36), it["detail"], font=F14, fill=(150,150,150,255))
            
            sc_w = F26.getlength(it["score"])
            cd.text(((card_w - sc_w)//2, icon_y + icon_sz + 56), it["score"], font=F26, fill=C_GOLD)
            
            img.alpha_composite(c_img, (x, y))
            x += card_w + 10
        y += card_h + 10
        
    return img


def draw_disclaimer(data: dict) -> Image.Image:
    H = 200
    img = Image.new("RGBA", (INNER_W, H), (0,0,0,0))
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, C_DARK_BG)
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 12, (255,255,255,10))
    d = ImageDraw.Draw(img)
    
    col_w = (INNER_W - 40 - 20) // 2
    
    # Left Col
    d.rectangle([20, 24, 23, 44], fill=C_GOLD) # 金色竖条高度贴合文字
    d.text((32, 20), "计分规则", font=F24, fill=C_GOLD)
    y = 55
    for r in data["rules"]:
        d.text((20, y), "•", font=F14, fill=(102,102,102,255))
        d.text((30, y), r, font=F14, fill=(170,170,170,255)) # 缩紧了与圆点的距离
        y += 24
        
    # Right Col
    rx = 20 + col_w + 20
    d.rectangle([rx, 24, rx+3, 44], fill=C_GOLD)
    d.text((rx+12, 20), "特别说明", font=F24, fill=C_GOLD)
    y = 55
    for n in data["notes"]:
        d.text((rx, y), "•", font=F14, fill=(102,102,102,255))
        d.text((rx+10, y), n, font=F14, fill=(170,170,170,255))
        y += 24
        
    d.line([(20, H-40), (INNER_W-20, H-40)], fill=(255,255,255,13), width=1)
    d.text(((INNER_W - F14.getlength("本积分计算数据非来自官方，可能与最终游戏内积分有出入，最终解释权归库洛所有。"))//2, H-30), 
           "本积分计算数据非来自官方，可能与最终游戏内积分有出入，最终解释权归库洛所有。", font=F14, fill=(102,102,102,255))
           
    return img


# 主渲染逻辑

def render(html: str) -> bytes:
    data = parse_html(html)

    # 预构建区块
    u_card   = draw_user_card(data)
    sum_card = draw_score_summary(data)
    c_grid   = draw_items_grid("共鸣者积分明细", data.get("char_items", []))
    w_grid   = draw_items_grid("武器积分明细", data.get("wpn_items", []))
    dis_card = draw_disclaimer(data)

    # 高度计算
    TOP_PAD = 20
    BOTTOM_PAD = 20
    GAP = 20
    
    total_h = TOP_PAD + u_card.height + GAP + sum_card.height + GAP
    if c_grid.height > 1: total_h += c_grid.height + GAP
    if w_grid.height > 1: total_h += w_grid.height + GAP
    total_h += dis_card.height + GAP
    
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

    # 画布组合
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    if data["bg_src"]:
        try:
            bg = _b64_fit(data["bg_src"], W, total_h)
            canvas.alpha_composite(bg)
        except: pass
        
    _draw_rounded_rect(canvas, 0, 0, W, total_h, 0, (0, 0, 0, 40))

    y = TOP_PAD
    canvas.alpha_composite(u_card, (PAD, y))
    y += u_card.height + GAP

    canvas.alpha_composite(sum_card, (PAD, y))
    y += sum_card.height + GAP

    if c_grid.height > 1:
        canvas.alpha_composite(c_grid, (PAD, y))
        y += c_grid.height + GAP
        
    if w_grid.height > 1:
        canvas.alpha_composite(w_grid, (PAD, y))
        y += w_grid.height + GAP

    canvas.alpha_composite(dis_card, (PAD, y))
    y += dis_card.height + GAP

    if footer_img:
        canvas.alpha_composite(footer_img, (PAD, y - 10))

    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
