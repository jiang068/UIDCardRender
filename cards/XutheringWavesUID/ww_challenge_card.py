# 鸣潮全息战略卡片渲染器 (PIL 版)

from __future__ import annotations

import base64
import math
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps


# 正则表达式预编译

RE_DIFFICULTY = re.compile(r"难度\s*(\d+)\s*/\s*(\d+)")
RE_BG_URL = re.compile(r"url\('(data:[^']+)'\)")
RE_CHAIN = re.compile(r"chain-(\d+)")


# 路径

ASSET = Path(__file__).parent.parent / "assets" / "abyss"


# 画布宽度与颜色

W = 1000          
PAD = 20          # 这里的 padding 改成了 20 (根据 HTML .container { padding: 20px; })
INNER_W = W - PAD * 2   # 960

C_BG           = (15,  17,  21,  255)
C_WHITE        = (255, 255, 255, 255)
C_GOLD         = (212, 177, 99,  255)
C_GREY         = (109, 113, 122, 255)
C_ROLE_BG_DEF  = (42,  46,  53,  255)

CHAIN_COLORS = {
    0: (102, 102, 102),
    1: (100, 180, 255),
    2: (100, 220, 130),
    3: (255, 180,  60),
    4: (220,  80, 220),
    5: (255,  80,  80),
    6: (255, 200,   1),
}


# 尺寸常量

USER_CARD_H    = 160
SECTION_GAP    = 35
SECTION_PAD    = 30     # 左右内边距
GRID_GAP       = 20
ITEM_W         = (INNER_W - SECTION_PAD * 2 - GRID_GAP) // 2  # 440px
ITEM_H         = 194    # Header(64) + Body(130)

ROLE_MINI_SZ   = 80
ROLE_GAP       = 10


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

F10  = _load_font(10, bold=True)
F12  = _load_font(12, bold=True)
F14  = _load_font(14, bold=True)
F18  = _load_font(18)
F20  = _load_font(20, bold=True)
F22  = _load_font(22)
F24  = _load_font(24, bold=True)
F28  = _load_font(28, bold=True)
F30  = _load_font(30, bold=True)
F36  = _load_font(36, bold=True)
F48  = _load_font(48, bold=True)

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    text_h = bb[3] - bb[1]
    return (box_h - text_h) // 2 - bb[1] + 1


# 图片预处理与缓存

@lru_cache(maxsize=256)
def _b64_img(src: str) -> Image.Image:
    if "," in src:
        src = src.split(",", 1)[1]
    return Image.open(BytesIO(base64.b64decode(src))).convert("RGBA")

@lru_cache(maxsize=256)
def _b64_fit(src: str, w: int, h: int) -> Image.Image:
    return ImageOps.fit(_b64_img(src), (w, h), Image.Resampling.LANCZOS)

@lru_cache(maxsize=64)
def _round_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return mask

@lru_cache(maxsize=64)
def _get_rounded_rect_block(w: int, h: int, r: int, fill: tuple) -> Image.Image:
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill)
    return block

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int,
                       x1: int, y1: int, r: int, fill: tuple) -> None:
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    canvas.alpha_composite(_get_rounded_rect_block(w, h, r, fill), (x0, y0))

@lru_cache(maxsize=64)
def _get_h_gradient(w: int, h: int, left_rgba: tuple, right_rgba: tuple) -> Image.Image:
    grad_1d = Image.new("RGBA", (w, 1))
    for xi in range(w):
        t = xi / max(w - 1, 1)
        r = int(left_rgba[0] + (right_rgba[0] - left_rgba[0]) * t)
        g = int(left_rgba[1] + (right_rgba[1] - left_rgba[1]) * t)
        b = int(left_rgba[2] + (right_rgba[2] - left_rgba[2]) * t)
        a = int(left_rgba[3] + (right_rgba[3] - left_rgba[3]) * t)
        grad_1d.putpixel((xi, 0), (r, g, b, a))
    return grad_1d.resize((w, h), Image.NEAREST)

def _draw_h_gradient(canvas: Image.Image, x0: int, y0: int,
                     x1: int, y1: int, left_rgba: tuple, right_rgba: tuple) -> None:
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    canvas.alpha_composite(_get_h_gradient(w, h, left_rgba, right_rgba), (x0, y0))


# 解析 HTML

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    # --- 用户卡 ---
    name      = (soup.select_one(".user-name")  or soup).get_text(strip=True) if soup.select_one(".user-name")  else ""
    uid_raw   = soup.select_one(".user-uid")
    uid       = uid_raw.get_text(strip=True).replace("UID", "").strip() if uid_raw else ""
    avatar_src = ""
    av = soup.select_one(".avatar-container img.avatar, img.avatar")
    if av and av.get("src", "").startswith("data:"):
        avatar_src = av["src"]

    account_level = ""
    world_level   = ""
    for item in soup.select(".stat-item"):
        val   = item.select_one(".stat-value")
        label = item.select_one(".stat-label")
        if not val or not label: continue
        ltext = label.get_text(strip=True)
        vtext = val.get_text(strip=True)
        if "联觉" in ltext: account_level = vtext
        elif "索拉" in ltext: world_level = vtext

    # --- section header ---
    date_tag = soup.select_one(".section-header div[style]")
    date_str = date_tag.get_text(strip=True) if date_tag else ""

    # --- 背景与页脚 ---
    bg_src = ""
    bg_img = soup.select_one(".bg-image")
    if bg_img and bg_img.get("src", "").startswith("data:"):
        bg_src = bg_img["src"]

    footer_src = ""
    fi = soup.select_one(".footer img")
    if fi and fi.get("src", "").startswith("data:"):
        footer_src = fi["src"]

    # --- 全息挑战列表 ---
    challenges = []
    for item_el in soup.select(".challenge-item"):
        bname = item_el.select_one(".boss-name")
        blevel = item_el.select_one(".boss-level")
        boss_name = bname.get_text(strip=True) if bname else ""
        boss_level = blevel.get_text(strip=True).replace("Lv.", "").strip() if blevel else ""

        diff_el = item_el.select_one(".difficulty-badge")
        boss_diff = max_diff = 0
        if diff_el:
            m = RE_DIFFICULTY.search(diff_el.get_text())
            if m:
                boss_diff, max_diff = int(m.group(1)), int(m.group(2))
        
        time_el = item_el.select_one(".time-value")
        pass_time = time_el.get_text(strip=True) if time_el else ""

        bimg = item_el.select_one(".boss-img")
        boss_icon_url = bimg["src"] if bimg and bimg.get("src", "").startswith("data:") else ""

        roles = []
        for r_el in item_el.select(".role-mini"):
            star = int(r_el.get("data-star", 4))
            rimg = r_el.select_one("img")
            img_src = rimg["src"] if rimg and rimg.get("src", "").startswith("data:") else ""
            
            lvl_el = r_el.select_one(".role-mini-level")
            level_str = lvl_el.get_text(strip=True).replace("Lv.", "") if lvl_el else "1"
            
            chain_el = r_el.select_one(".role-chain")
            chain_str = chain_el.get_text(strip=True) if chain_el else "零链"
            chain_num = 0
            if chain_el:
                for cls in chain_el.get("class", []):
                    mc = RE_CHAIN.match(cls)
                    if mc: chain_num = int(mc.group(1))
            
            roles.append({
                "star": star,
                "img_src": img_src,
                "level": level_str,
                "chain_str": chain_str,
                "chain_num": chain_num
            })

        challenges.append({
            "boss_name": boss_name,
            "boss_level": boss_level,
            "boss_difficulty": boss_diff,
            "max_difficulty": max_diff,
            "pass_time": pass_time,
            "boss_icon_url": boss_icon_url,
            "roles": roles
        })

    return {
        "name":          name,
        "uid":           uid,
        "avatar_src":    avatar_src,
        "account_level": account_level,
        "world_level":   world_level,
        "date_str":      date_str,
        "bg_src":        bg_src,
        "footer_src":    footer_src,
        "challenges":    challenges,
    }


# 绘制区域

def draw_user_card(data: dict) -> Image.Image:
    H = USER_CARD_H
    card = Image.new("RGBA", (INNER_W, H), (0, 0, 0, 0))
    d    = ImageDraw.Draw(card)

    _draw_h_gradient(card, INNER_W - 280, 0, INNER_W, H // 2,
                     (212, 177, 99, 0), (212, 177, 99, 35))

    AV_SIZE = 100
    av_x = 25
    av_y = (H - AV_SIZE) // 2
    av_mask = Image.new("L", (AV_SIZE, AV_SIZE), 0)
    ImageDraw.Draw(av_mask).ellipse([0, 0, AV_SIZE - 1, AV_SIZE - 1], fill=255)
    av_bg = Image.new("RGBA", (AV_SIZE, AV_SIZE), (34, 34, 34, 255))
    card.paste(av_bg, (av_x, av_y), av_mask)
    if data["avatar_src"]:
        try:
            av_img = _b64_fit(data["avatar_src"], AV_SIZE, AV_SIZE)
            card.paste(av_img, (av_x, av_y), av_mask)
        except Exception:
            pass
    d.ellipse([av_x - 4, av_y - 4, av_x + AV_SIZE + 4, av_y + AV_SIZE + 4],
              outline=(212, 177, 99, 160), width=2)

    tx = av_x + AV_SIZE + 30
    d.text((tx, 28), data["name"], font=F48, fill=C_WHITE)
    
    uid_text = f"UID {data['uid']}"
    uid_w = F22.getlength(uid_text) + 24
    uid_h = 34
    uid_x = tx + F48.getlength(data["name"]) + 20
    uid_y = 36
    _draw_rounded_rect(card, int(uid_x), uid_y, int(uid_x + uid_w), uid_y + uid_h, 6, (0, 0, 0, 100))
    d.rectangle([int(uid_x), uid_y, int(uid_x + uid_w), uid_y + uid_h], outline=(212, 177, 99, 50), width=1)
    d.text((int(uid_x) + 12, uid_y + 5), uid_text, font=F22, fill=C_GOLD)

    # 装饰文字
    deco_text = "CHALLENGE REPORT"
    d.text((INNER_W - 30 - F14.getlength(deco_text), 20), deco_text, font=F14, fill=(255, 255, 255, 25))

    sep_y = 88
    d.line([(tx, sep_y), (INNER_W - 30, sep_y)], fill=(255, 255, 255, 20), width=1)
    d.line([(tx, sep_y), (tx + 40, sep_y)], fill=C_GOLD, width=2)

    stat_y = sep_y + 10
    stats = []
    if data["account_level"]: stats.append((f"Lv.{data['account_level']}", "联觉等级"))
    if data["world_level"]: stats.append((f"Lv.{data['world_level']}", "索拉等级"))
    
    for i, (val, label) in enumerate(stats):
        sx = tx + i * 160
        d.text((sx, stat_y), val, font=F28, fill=C_WHITE)
        d.text((sx, stat_y + 34), label, font=F12, fill=C_GREY)

    return card

def draw_section_header(date_str: str) -> Image.Image:
    H = 60
    img = Image.new("RGBA", (INNER_W - SECTION_PAD*2, H), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    title = "全息战略"
    d.text((0, _ty(F30, title, H)), title, font=F30, fill=C_WHITE)
    title_w = int(F30.getlength(title))

    date_w   = int(F18.getlength(date_str)) + 20 if date_str else 0
    right_x  = img.width - date_w
    line_x0  = title_w + 20
    line_y   = H // 2
    
    _draw_h_gradient(img, line_x0, line_y - 1, right_x, line_y + 1,
                     (212, 177, 99, 204), (212, 177, 99, 0))

    if date_str:
        d.text((right_x + 10, _ty(F18, date_str, H)), date_str, font=F18, fill=C_GREY)

    d.line([(0, H - 1), (img.width, H - 1)], fill=(255, 255, 255, 13), width=1)
    return img

def _draw_qx_role_mini(role: dict) -> Image.Image:
    """全息专属 80x80 圆角角色小卡"""
    SZ = ROLE_MINI_SZ
    card = Image.new("RGBA", (SZ, SZ), C_ROLE_BG_DEF)

    if role["img_src"]:
        try:
            av = _b64_fit(role["img_src"], SZ, SZ)
            rmask = _round_mask(SZ, SZ, 8)
            card.paste(av, (0, 0), rmask)
        except Exception:
            pass

    border_color = (212, 177, 99, 255) if role["star"] == 5 else (156, 39, 176, 255)
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, SZ - 1, SZ - 1], radius=8, outline=border_color, width=1)

    # 左上等级
    lvl_txt = f"Lv.{role['level']}"
    lw = int(F12.getlength(lvl_txt)) + 10
    lh = 16
    _draw_h_gradient(card, 0, 4, lw + 10, 4 + lh, (0, 0, 0, 216), (0, 0, 0, 0))
    d.rectangle([0, 4, 2, 4 + lh], fill=C_GOLD)
    d.text((4, 4 + _ty(F12, lvl_txt, lh)), lvl_txt, font=F12, fill=C_WHITE)

    # 右下命座
    chain_num  = role["chain_num"]
    chain_text = role["chain_str"]
    chain_col  = CHAIN_COLORS.get(chain_num, (102, 102, 102))
    text_col   = (230, 230, 230) if chain_num == 0 else chain_col
    cw = int(F12.getlength(chain_text)) + 12
    ch = 16
    cy = SZ - ch - 4
    cx = SZ - cw - 3
    
    _draw_h_gradient(card, cx - 10, cy, SZ, cy + ch, (0, 0, 0, 0), (0, 0, 0, 230))
    d.rectangle([SZ - 3, cy, SZ, cy + ch], fill=(*chain_col, 255))
    d.text((cx + 2, cy + _ty(F12, chain_text, ch)), chain_text, font=F12, fill=(*text_col, 255))

    return card

def draw_challenge_item(ch: dict) -> Image.Image:
    img = Image.new("RGBA", (ITEM_W, ITEM_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 背景
    _draw_rounded_rect(img, 0, 0, ITEM_W, ITEM_H, 14, (35, 40, 48, 178)) # 渐变简化处理为实底+透明

    # --- Header (高度 64) ---
    _draw_h_gradient(img, 0, 0, ITEM_W, 64, (0, 0, 0, 76), (0, 0, 0, 0))
    d.line([(0, 64), (ITEM_W, 64)], fill=(255, 255, 255, 10), width=1)
    
    d.text((18, 10), ch["boss_name"], font=F24, fill=C_WHITE)
    d.text((18, 40), f"Lv.{ch['boss_level']}", font=F14, fill=C_GOLD)

    # 右侧时间与难度
    time_val = ch["pass_time"]
    tw = int(F24.getlength(time_val))
    time_x = ITEM_W - 18 - tw
    d.text((time_x, 14), "TIME", font=F10, fill=C_GOLD)
    d.text((time_x, 26), time_val, font=F24, fill=C_WHITE)

    diff_txt = f"难度 {ch['boss_difficulty']}/{ch['max_difficulty']}"
    dw = int(F20.getlength(diff_txt)) + 16
    dx = time_x - 15 - dw
    _draw_rounded_rect(img, dx, 16, dx + dw, 44, 4, (255, 255, 255, 13))
    d.rectangle([dx, 16, dx + dw, 44], outline=(255, 255, 255, 25), width=1)
    d.text((dx + 8, 16 + _ty(F20, diff_txt, 28)), diff_txt, font=F20, fill=(170, 170, 170, 255))

    # --- Body (64 ~ 194) ---
    b_img_sz = (130, 100)
    b_img_y = 64 + 15
    _draw_rounded_rect(img, 18, b_img_y, 18 + b_img_sz[0], b_img_y + b_img_sz[1], 10, (30, 30, 30, 255))
    if ch["boss_icon_url"]:
        try:
            boss_av = _b64_fit(ch["boss_icon_url"], *b_img_sz)
            # 直接生成圆角遮罩并贴图，完美解决
            b_mask = _round_mask(b_img_sz[0], b_img_sz[1], 10)
            img.paste(boss_av, (18, b_img_y), b_mask)
        except Exception as e:
            print(f"Boss 图片渲染失败: {e}")
    d.rounded_rectangle([18, b_img_y, 18 + b_img_sz[0], b_img_y + b_img_sz[1]], radius=10, outline=(255, 255, 255, 20), width=1)

    # 角色队伍
    roles = ch["roles"]
    rx = ITEM_W - 18 - (len(roles) * ROLE_MINI_SZ + max(0, len(roles) - 1) * ROLE_GAP)
    ry = b_img_y + (100 - ROLE_MINI_SZ) // 2
    for role in roles:
        rm = _draw_qx_role_mini(role)
        img.alpha_composite(rm, (rx, ry))
        rx += ROLE_MINI_SZ + ROLE_GAP

    # 整体外边框
    d.rounded_rectangle([0, 0, ITEM_W - 1, ITEM_H - 1], radius=14, outline=(255, 255, 255, 15), width=1)
    return img


# 主渲染逻辑

def render(html: str) -> bytes:
    data = parse_html(html)

    user_card = draw_user_card(data)
    sec_hdr   = draw_section_header(data["date_str"])
    
    ch_imgs = [draw_challenge_item(c) for c in data["challenges"]]

    # 布局计算
    rows = math.ceil(len(ch_imgs) / 2)
    grid_h = rows * ITEM_H + max(0, rows - 1) * GRID_GAP

    SEC_OUTER  = 0
    FOOTER_GAP = 10
    BOTTOM_PAD = 20

    # 容器高度计算 (section)
    sec_inner_h = sec_hdr.height + 25 + grid_h + 10 # 25 是 hdr 和 grid 的间距
    sec_total_h = SECTION_PAD + sec_inner_h + 25

    total_h = PAD + USER_CARD_H + SECTION_GAP + sec_total_h

    FOOTER_H = 0
    footer_img = None
    if data.get("footer_src"):
        try:
            footer_img = _b64_img(data["footer_src"])
            fw_orig, fh_orig = footer_img.size
            FOOTER_H = int(fh_orig * INNER_W / fw_orig)
            footer_img = footer_img.resize((INNER_W, FOOTER_H), Image.LANCZOS)
            total_h += FOOTER_GAP + FOOTER_H
        except Exception:
            pass

    total_h += BOTTOM_PAD

    # 画布生成
    canvas = Image.new("RGBA", (W, total_h), C_BG)

    if data.get("bg_src"):
        try:
            bg = _b64_img(data["bg_src"])
            bg = ImageOps.fit(bg, (W, total_h), Image.Resampling.LANCZOS)
            dark = Image.new("RGBA", (W, total_h), (0, 0, 0, 140))
            canvas.alpha_composite(bg)
            canvas.alpha_composite(dark)
        except Exception: pass

    y = PAD

    # 1. User Card (无透明框外扩，对齐 960)
    _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + USER_CARD_H, 16, (25, 28, 34, 230))
    canvas.alpha_composite(user_card, (PAD, y))
    y += USER_CARD_H + SECTION_GAP

    # 2. Section Container
    _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + sec_total_h, 16, (20, 22, 26, 153))
    
    # Header
    sec_inner_y = y + SECTION_PAD
    canvas.alpha_composite(sec_hdr, (PAD + SECTION_PAD, sec_inner_y))
    
    # Grid
    grid_y_start = sec_inner_y + sec_hdr.height + 25
    for i, ch_img in enumerate(ch_imgs):
        col = i % 2
        row = i // 2
        ix = PAD + SECTION_PAD + col * (ITEM_W + GRID_GAP)
        iy = grid_y_start + row * (ITEM_H + GRID_GAP)
        canvas.alpha_composite(ch_img, (ix, iy))
    
    y += sec_total_h

    # 3. Footer
    if footer_img:
        y += FOOTER_GAP
        canvas.alpha_composite(footer_img.convert("RGBA"), (PAD, y))

    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
