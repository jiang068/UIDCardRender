# 鸣潮深塔卡片渲染器 v2 (PIL 版 · 复刻 HTML 样式)

from __future__ import annotations

import base64
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps
from . import F12, F18, F20, F22, F24, F28, F32, F36, F38, F42, F48, draw_text_mixed, M12, M14, M15, M16, M17, M18, M20, M22, M24, M26, M28, M30, M32, M34, M36, M38, M42, M48, M72


# 正则表达式预编译（提升循环内解析性能）

RE_PERIOD = re.compile(r"\d+")
RE_STARS = re.compile(r"(\d+)\s*/\s*(\d+)")
RE_BG_URL = re.compile(r"url\('(data:[^']+)'\)")
RE_CHAIN = re.compile(r"chain-(\d+)")

# 画布宽度

W = 1000          # 总宽
PAD = 40          # 左右内边距
INNER_W = W - PAD * 2   # 920


# 颜色

C_BG           = (15,  17,  21,  255)   # #0f1115
C_CARD_BG      = (25,  28,  34,  230)   # rgba(30,34,42,0.9) 近似
C_WHITE        = (255, 255, 255, 255)
C_GOLD         = (212, 177, 99,  255)   # #d4b163
C_GREY         = (109, 113, 122, 255)   # #6d717a
C_SECTION_BG   = (20,  22,  26,  153)   # rgba(20,22,26,0.6)
C_TOWER_TITLE  = (255, 255, 255, 255)
C_FLOOR_OVERLAY= (0,   0,   0,   120)   # 层背景暗化遮罩
C_ROLE_BG_DEF  = (42,  46,  53,  255)   # #2a2e35

# chain 右边框颜色（chain-1 ~ chain-6）；chain-0 用 #666
CHAIN_COLORS = {
    0: (102, 102, 102),   # #666  灰
    1: (100, 180, 255),   # 蓝
    2: (100, 220, 130),   # 绿
    3: (255, 180,  60),   # 橙
    4: (220,  80, 220),   # 紫
    5: (255,  80,  80),   # 红
    6: (255, 200,   1),   # 金
}


# 尺寸常量

USER_CARD_H    = 160    # 用户卡高度
SECTION_GAP    = 35     # 各区块间距
SECTION_PAD    = 25     # section-container 内边距
TOWER_HEADER_H = 90     # tower-header 高度
FLOOR_H        = 150    # floor-item 高度
FLOOR_GAP      = 6      # floor 间距
TOWER_GAP      = 8      # tower 间距
ROLE_MINI_W    = 125    # role-mini 宽
ROLE_MINI_H    = 125    # role-mini 高
ROLE_GAP       = 20     # role 间距
BORDER_RADIUS  = 12     # 圆角半径（通用）


# 从包中获取统一字体和常用字号变量（见 cards.XutheringWavesUID.__init__）

def _ty(font, text: str, box_h: int) -> int:
    """计算文字在高度为 box_h 的容器中垂直居中的 y 坐标（修正 PIL bbox top offset）。"""
    bb = font.getbbox(text)          # (left, top, right, bottom)
    text_h = bb[3] - bb[1]          # 实际渲染高度
    return (box_h - text_h) // 2 - bb[1] + 1   # +1 视觉微调


# 图片预加载与处理缓存

@lru_cache(maxsize=256)
def _b64_img(src: str) -> Image.Image:
    """'data:image/...;base64,XXX' 或纯 base64 → RGBA Image（已缓存）"""
    if "," in src:
        src = src.split(",", 1)[1]
    return Image.open(BytesIO(base64.b64decode(src))).convert("RGBA")

@lru_cache(maxsize=256)
def _b64_fit(src: str, w: int, h: int) -> Image.Image:
    """直接使用 PIL 原生 ImageOps.fit 加速裁剪和缩放"""
    return ImageOps.fit(_b64_img(src), (w, h), Image.Resampling.LANCZOS)


# 辅助：图形和蒙版预渲染缓存 (极大提升大量同尺寸 UI 的绘制性能)

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
                       x1: int, y1: int, r: int,
                       fill: tuple) -> None:
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    block = _get_rounded_rect_block(w, h, r, fill)
    canvas.alpha_composite(block, (x0, y0))

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
                     x1: int, y1: int,
                     left_rgba: tuple, right_rgba: tuple) -> None:
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    grad = _get_h_gradient(w, h, left_rgba, right_rgba)
    canvas.alpha_composite(grad, (x0, y0))

def _paste_rounded(canvas: Image.Image, img: Image.Image,
                   x: int, y: int, r: int = BORDER_RADIUS) -> None:
    w, h = img.size
    mask = _round_mask(w, h, r)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    canvas.paste(img, (x, y), mask)


# HTML 解析

def parse_html(html: str) -> dict:
    """从前端 HTML 提取所有绘图数据，返回结构化字典。"""
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
        if not val or not label:
            continue
        ltext = label.get_text(strip=True)
        vtext = val.get_text(strip=True)
        if "联觉" in ltext:
            account_level = vtext
        elif "索拉" in ltext:
            world_level = vtext

    # --- section header ---
    diff_tag   = soup.select_one(".section-title")
    period_tag = soup.select_one(".period-badge")
    diff_name  = diff_tag.get_text(strip=True) if diff_tag else "深境区"
    period     = 0
    if period_tag:
        m = RE_PERIOD.search(period_tag.get_text())
        period = int(m.group()) if m else 0
    date_tag = soup.select_one(".section-header div[style]")
    date_str = date_tag.get_text(strip=True) if date_tag else ""

    # --- 背景图（整张卡片背景） ---
    bg_src = ""
    bg_img = soup.select_one(".bg-image")
    if bg_img and bg_img.get("src", "").startswith("data:"):
        bg_src = bg_img["src"]

    # --- footer ---
    footer_src = ""
    fi = soup.select_one(".footer img")
    if fi and fi.get("src", "").startswith("data:"):
        footer_src = fi["src"]

    # --- 塔 ---
    towers = []
    for tower_el in soup.select(".tower-block"):
        title_el = tower_el.select_one(".tower-title")
        stars_el = tower_el.select_one(".tower-stars")
        tower_name = title_el.get_text(strip=True) if title_el else ""
        tower_star = tower_max_star = 0
        if stars_el:
            m = RE_STARS.search(stars_el.get_text())
            if m:
                tower_star, tower_max_star = int(m.group(1)), int(m.group(2))

        floors = []
        for floor_el in tower_el.select(".floor-item"):
            floor_bg_src = ""
            style = floor_el.get("style", "")
            m2 = RE_BG_URL.search(style)
            if m2:
                floor_bg_src = m2.group(1)

            fname_el = floor_el.select_one(".floor-name")
            floor_name = fname_el.get_text(strip=True) if fname_el else ""

            star_icons = floor_el.select(".star-icon")
            floor_star = len(star_icons)   # HTML 只渲染实际数量的 full/empty

            # 收集星星图的 src（前端可能会传 data: base64）
            star_srcs = [si.get("src", "") for si in star_icons]

            lit = 0
            for si in star_icons:
                src = si.get("src", "")
                if "star_full" in src or (src.startswith("data:") and lit < 3):
                    lit += 1
            floor_star = lit if lit > 0 else len(star_icons)

            roles = []
            for role_el in floor_el.select(".role-mini"):
                star_level = int(role_el.get("data-star", 4))
                img_el = role_el.select_one("img[alt='role']")
                role_img_src = img_el["src"] if img_el and img_el.get("src", "").startswith("data:") else ""
                level_el = role_el.select_one(".role-mini-level")
                chain_el = role_el.select_one(".role-mini-chain")
                level_str = level_el.get_text(strip=True) if level_el else "Lv.1"
                chain_str = chain_el.get_text(strip=True) if chain_el else "零链"
                chain_num = 0
                if chain_el:
                    for cls in chain_el.get("class", []):
                        m3 = RE_CHAIN.match(cls)
                        if m3:
                            chain_num = int(m3.group(1))
                roles.append({
                    "star_level":  star_level,
                    "img_src":     role_img_src,
                    "level_str":   level_str,
                    "chain_str":   chain_str,
                    "chain_num":   chain_num,
                })
            floors.append({
                "bg_src":    floor_bg_src,
                "name":      floor_name,
                "star":      floor_star,
                "star_srcs": star_srcs,
                "roles":     roles,
            })
        towers.append({
            "name":      tower_name,
            "star":      tower_star,
            "max_star":  tower_max_star,
            "floors":    floors,
        })

    return {
        "name":          name,
        "uid":           uid,
        "avatar_src":    avatar_src,
        "account_level": account_level,
        "world_level":   world_level,
        "diff_name":     diff_name,
        "period":        period,
        "date_str":      date_str,
        "bg_src":        bg_src,
        "footer_src":    footer_src,
        "towers":        towers,
    }


# Step 4 · 顶部用户卡

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
    draw_text_mixed(d, (tx, 28), data["name"], cn_font=F48, en_font=M48, fill=C_WHITE)
    uid_text = f"UID {data['uid']}"
    bbox = F22.getbbox(uid_text)
    uid_w = (bbox[2] - bbox[0]) + 24
    uid_h = 34
    uid_x = tx + F48.getlength(data["name"]) + 20
    uid_y = 36
    _draw_rounded_rect(card, int(uid_x), uid_y, int(uid_x + uid_w), uid_y + uid_h,
                       6, (0, 0, 0, 100))
    d.rectangle([int(uid_x), uid_y, int(uid_x + uid_w), uid_y + uid_h],
                outline=(212, 177, 99, 50), width=1)
    draw_text_mixed(d, (int(uid_x) + 12, uid_y + 5), uid_text, cn_font=F22, en_font=M22, fill=C_GOLD)

    sep_y = 88
    d.line([(tx, sep_y), (INNER_W - 30, sep_y)], fill=(255, 255, 255, 20), width=1)
    d.line([(tx, sep_y), (tx + 40, sep_y)], fill=C_GOLD, width=2)

    stat_y = sep_y + 10
    stats = []
    if data["account_level"]:
        stats.append((f"Lv.{data['account_level']}", "联觉等级"))
    if data["world_level"]:
        stats.append((f"Lv.{data['world_level']}", "索拉等级"))
    for i, (val, label) in enumerate(stats):
        sx = tx + i * 160
        draw_text_mixed(d, (sx, stat_y),      val,   cn_font=F28, en_font=M28, fill=C_WHITE)
        draw_text_mixed(d, (sx, stat_y + 34), label, cn_font=F12, en_font=M12, fill=C_GREY)

    return card


# Step 5 · Section header（难度标题 + period badge + 日期）

def draw_section_header(data: dict) -> Image.Image:
    H = 60
    img = Image.new("RGBA", (INNER_W, H), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    title = data["diff_name"]
    draw_text_mixed(d, (0, _ty(F36, title, H)), title, cn_font=F36, en_font=M36, fill=C_WHITE)
    title_w = int(F36.getlength(title))

    period_text = f"第{data['period']}期"
    period_w = int(F24.getlength(period_text)) + 24
    date_w   = int(F18.getlength(data["date_str"])) + 20 if data["date_str"] else 0
    right_x  = INNER_W - period_w - date_w - 30
    line_x0  = title_w + 20
    line_y   = H // 2
    _draw_h_gradient(img, line_x0, line_y - 1, right_x, line_y + 1,
                     (212, 177, 99, 204), (212, 177, 99, 0))

    pb_x = right_x + 10
    pb_y = (H - 34) // 2
    _draw_rounded_rect(img, pb_x, pb_y, pb_x + period_w, pb_y + 34,
                       6, (212, 177, 99, 38))
    d.rectangle([pb_x, pb_y, pb_x + period_w, pb_y + 34],
                outline=(212, 177, 99, 76), width=1)
    draw_text_mixed(d, (pb_x + 12, pb_y + _ty(F24, period_text, 34)), period_text, cn_font=F24, en_font=M24, fill=C_GOLD)

    if data["date_str"]:
     draw_text_mixed(d, (pb_x + period_w + 15, pb_y + _ty(F18, data["date_str"], 34)),
         data["date_str"], cn_font=F18, en_font=M18, fill=C_GREY)

    d.line([(0, H - 1), (INNER_W, H - 1)], fill=(255, 255, 255, 13), width=1)

    return img


# Step 6 · 单层绘制

def _draw_role_mini(role: dict) -> Image.Image:
    RW, RH = ROLE_MINI_W, ROLE_MINI_H
    card = Image.new("RGBA", (RW, RH), C_ROLE_BG_DEF)

    if role["img_src"]:
        try:
            av = _b64_fit(role["img_src"], RW, RH)
            rmask = _round_mask(RW, RH, BORDER_RADIUS)
            card.paste(av, (0, 0), rmask)
        except Exception:
            pass

    border_color = (212, 177, 99, 255) if role["star_level"] == 5 else (156, 39, 176, 255)
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, RW - 1, RH - 1], radius=BORDER_RADIUS,
                         outline=border_color, width=2)

    level_text = role["level_str"]
    lh = 26
    lw = int(F20.getlength(level_text)) + 16
    _draw_h_gradient(card, 0, 4, lw + 10, 4 + lh,
                     (0, 0, 0, 216), (0, 0, 0, 0))
    d.rectangle([0, 4, 3, 4 + lh], fill=(212, 177, 99, 255))
    draw_text_mixed(d, (6, 4 + _ty(F20, level_text, lh)), level_text, cn_font=F20, en_font=M20, fill=C_WHITE)

    chain_num  = role["chain_num"]
    chain_text = role["chain_str"]
    chain_col  = CHAIN_COLORS.get(chain_num, (102, 102, 102))
    text_col   = (230, 230, 230) if chain_num == 0 else chain_col
    cw = int(F20.getlength(chain_text)) + 20
    ch = 28
    cy = RH - ch - 2
    cx = RW - cw - 4          

    _draw_h_gradient(card, cx - 14, cy, RW, cy + ch,
                     (0, 0, 0, 0), (0, 0, 0, 235))
    d.rectangle([RW - 4, cy, RW - 1, cy + ch], fill=(*chain_col, 255))
    draw_text_mixed(d, (cx + 2, cy + _ty(F20, chain_text, ch)), chain_text, cn_font=F20, en_font=M20, fill=(*text_col, 255))

    return card

def draw_floor_item(floor: dict) -> Image.Image:
    FW, FH = INNER_W, FLOOR_H
    img = Image.new("RGBA", (FW, FH), (20, 22, 26, 255))

    if floor["bg_src"]:
        try:
            bg = _b64_fit(floor["bg_src"], FW, FH)
            fmask = _round_mask(FW, FH, BORDER_RADIUS)
            img.paste(bg, (0, 0), fmask)
        except Exception:
            pass

    ov = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    _draw_h_gradient(ov, 0, 0, FW // 2, FH, (0, 0, 0, 178), (0, 0, 0, 76))
    _draw_h_gradient(ov, FW // 2, 0, FW, FH, (0, 0, 0, 76),  (0, 0, 0, 178))
    img.alpha_composite(ov)

    d = ImageDraw.Draw(img)

    LEFT_W  = 160   
    RIGHT_W = 3 * ROLE_MINI_W + 2 * ROLE_GAP + 30  
    MID_W   = FW - LEFT_W - RIGHT_W

    draw_text_mixed(d, (30, _ty(F38, floor["name"], FH)),
        floor["name"], cn_font=F38, en_font=M38, fill=C_WHITE)

    # 星星逻辑 - 大尺寸 90px
    STAR_SZ      = 90
    stars_total_w = 3 * STAR_SZ + 2 * 8
    star_x0 = LEFT_W + (MID_W - stars_total_w) // 2
    star_srcs = floor.get("star_srcs", [])
    for i in range(3):
        sx = star_x0 + i * (STAR_SZ + 8)
        src = star_srcs[i] if i < len(star_srcs) else ""
        # 仅使用前端传入的 data:base64 图像；若不存在或解析失败则不绘制该星星
        if src:
            try:
                if src.startswith("data:") or "," in src:
                    simg = _b64_fit(src, STAR_SZ, STAR_SZ)
                    img.paste(simg, (sx, (FH - STAR_SZ) // 2), simg)
            except Exception:
                pass

    roles   = floor["roles"]
    n       = len(roles)
    used_w  = n * ROLE_MINI_W + max(n - 1, 0) * ROLE_GAP
    rx      = FW - 30 - used_w          
    ry      = (FH - ROLE_MINI_H) // 2
    for role in roles:
        rm = _draw_role_mini(role)
        img.alpha_composite(rm, (rx, ry))
        rx += ROLE_MINI_W + ROLE_GAP

    fmask2 = _round_mask(FW, FH, BORDER_RADIUS)
    out = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    out.paste(img, (0, 0), fmask2)
    ImageDraw.Draw(out).rounded_rectangle(
        [0, 0, FW - 1, FH - 1], radius=BORDER_RADIUS,
        outline=(255, 255, 255, 20), width=1)
    return out


# Step 7: draw_tower_block — 单个塔区块

def draw_tower_block(tower: dict) -> Image.Image:
    n_floors = len(tower["floors"])
    total_h = (TOWER_HEADER_H + TOWER_GAP
               + n_floors * FLOOR_H
               + max(n_floors - 1, 0) * FLOOR_GAP)

    img = Image.new("RGBA", (INNER_W, total_h), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    _draw_rounded_rect(img, 0, 0, INNER_W, TOWER_HEADER_H,
                       r=BORDER_RADIUS, fill=(25, 28, 34, 210))

    bar_h = TOWER_HEADER_H // 2
    bar_y = (TOWER_HEADER_H - bar_h) // 2
    d.rounded_rectangle([24, bar_y, 28, bar_y + bar_h],
                        radius=2, fill=C_GOLD)

    tx = 40
    draw_text_mixed(d, (tx, _ty(F36, tower["name"], TOWER_HEADER_H)), tower["name"], cn_font=F36, en_font=M36, fill=C_GOLD)

    star_str  = f"{tower['star']} / {tower['max_star']}"
    star_bbox = F28.getbbox(star_str)
    star_w    = star_bbox[2] - star_bbox[0]
    sx = INNER_W - 30 - star_w
    draw_text_mixed(d, (sx, _ty(F28, star_str, TOWER_HEADER_H)), star_str, cn_font=F28, en_font=M28, fill=C_WHITE)

    y = TOWER_HEADER_H + TOWER_GAP
    for floor in tower["floors"]:
        fi = draw_floor_item(floor)
        img.alpha_composite(fi, (0, y))
        y += FLOOR_H + FLOOR_GAP

    return img


# Step 8: render — 主入口，合成完整卡片，返回 JPEG bytes

def render(html: str) -> bytes:
    data = parse_html(html)

    user_card       = draw_user_card(data)
    section_header  = draw_section_header(data)
    tower_blocks    = [draw_tower_block(t) for t in data["towers"]]

    TOP_PAD         = 40          
    BOTTOM_PAD      = 20          
    PART_GAP        = 20          
    SECTION_H_GAP   = 18          
    TOWER_BLOCK_GAP = 28          
    FOOTER_GAP      = 10          
    SEC_BOT         = 16         

    total_h = TOP_PAD
    total_h += USER_CARD_H + PART_GAP
    total_h += section_header.height + SECTION_H_GAP
    for tb in tower_blocks:
        total_h += tb.height
    total_h += (len(tower_blocks) - 1) * TOWER_BLOCK_GAP if tower_blocks else 0

    FOOTER_H = 0
    footer_img = None
    if data.get("footer_src"):
        try:
            footer_img = _b64_img(data["footer_src"])
            fw_orig, fh_orig = footer_img.size
            FOOTER_H = int(fh_orig * INNER_W / fw_orig)
            footer_img = footer_img.resize((INNER_W, FOOTER_H), Image.LANCZOS)
        except Exception:
            footer_img = None

    total_h += SECTION_PAD + SEC_BOT
    if footer_img:
        total_h += FOOTER_GAP + FOOTER_H
    total_h += BOTTOM_PAD

    canvas = Image.new("RGBA", (W, total_h), C_BG)

    if data.get("bg_src"):
        try:
            bg = _b64_img(data["bg_src"])
            # 背景平铺改为高效的 ImageOps.fit 处理
            bg = ImageOps.fit(bg, (W, total_h), Image.Resampling.LANCZOS)
            dark = Image.new("RGBA", (W, total_h), (0, 0, 0, 140))
            canvas.alpha_composite(bg)
            canvas.alpha_composite(dark)
        except Exception:
            pass

    y = TOP_PAD
    SEC_OUTER = 8   

    _draw_rounded_rect(canvas,
                       PAD - SEC_OUTER, y,
                       PAD + INNER_W + SEC_OUTER, y + USER_CARD_H,
                       r=16, fill=(25, 28, 34, 230))
    canvas.alpha_composite(user_card, (PAD, y))
    y += USER_CARD_H + PART_GAP

    sec_container_h = (section_header.height + SECTION_H_GAP
                       + sum(tb.height for tb in tower_blocks)
                       + (len(tower_blocks) - 1) * TOWER_BLOCK_GAP
                       + SECTION_PAD + SEC_BOT)
    _draw_rounded_rect(canvas,
                       PAD - SEC_OUTER,            y - SECTION_PAD,
                       PAD + INNER_W + SEC_OUTER, y - SECTION_PAD + sec_container_h,
                       r=16, fill=(20, 22, 26, 140))

    canvas.alpha_composite(section_header, (PAD, y))
    y += section_header.height + SECTION_H_GAP

    for i, tb in enumerate(tower_blocks):
        canvas.alpha_composite(tb, (PAD, y))
        y += tb.height
        if i < len(tower_blocks) - 1:
            y += TOWER_BLOCK_GAP

    y += SECTION_PAD + SEC_BOT

    if footer_img:
        y += FOOTER_GAP
        canvas.alpha_composite(
            footer_img.convert("RGBA"), (PAD, y))
        y += FOOTER_H

    
    # 终末优化: 
    # 画布本身已经是一张有 C_BG 填色且 Alpha=255 的实心图层。
    # 丢掉原先需要计算 mask 合并的做法，直接强制 convert 转 RGB 去除透明层通道，性能立竿见影。
    
    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
