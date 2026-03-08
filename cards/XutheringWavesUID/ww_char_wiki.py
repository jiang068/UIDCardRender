# 鸣潮角色图鉴 (Character Wiki) 卡片渲染器 (PIL 版)

from __future__ import annotations

import base64
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
from PIL import Image, ImageDraw, ImageFont, ImageOps


# 常量定义

W = 1000
PAD = 30
INNER_W = W - PAD * 2   # 940

C_BG = (15, 15, 19, 255)
C_WHITE = (255, 255, 255, 255)
C_DESC = (221, 221, 221, 255)  # #ddd
C_CARD_BG = (20, 20, 25, 216)  # rgba(20,20,25,0.85)
C_TEXT_SUB = (160, 160, 160, 255) # 对应 CSS 的 #a0a0a0


from . import draw_text_mixed, M12, M13, M14, M15, M16, M17, M18, M20, M22, M24, M26, M28, M30, M32, M34, M36, M38, M42, M48, M72, M80

# 使用包级统一字体对象（从包里导入以复用同一实例）
from . import F13, F13B, F14B, F16, F18B, F20, F20B, F24B, F28B, F80B
from . import _b64_img, _b64_fit, _round_mask

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1

def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines = []
    curr_line = ""
    for char in text:
        if font.getlength(curr_line + char) <= max_w:
            curr_line += char
        else:
            lines.append(curr_line)
            curr_line = char
    if curr_line:
        lines.append(curr_line)
    return lines

def parse_color(c_str: str, default=(212, 177, 99, 255)) -> tuple:
    c_str = c_str.strip().lower()
    if c_str.startswith("#"):
        c_str = c_str.lstrip("#")
        if len(c_str) == 3: c_str = "".join(c+c for c in c_str)
        if len(c_str) >= 6:
            r, g, b = int(c_str[0:2], 16), int(c_str[2:4], 16), int(c_str[4:6], 16)
            a = int(c_str[6:8], 16) if len(c_str) == 8 else 255
            return (r, g, b, a)
    if c_str.startswith("rgba"):
        m = re.match(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9.]+)\s*\)", c_str)
        if m: return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(float(m.group(4))*255))
    return default


# 图像加载与辅助函数 (由包级统一实现以避免本地重复缓存和内存泄漏)

def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, 
                       r: int, fill: tuple, outline=None, width=1) -> None:
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(block, (x0, y0))

def _paste_rounded(canvas: Image.Image, img: Image.Image, x: int, y: int, r: int):
    w, h = img.size
    canvas.paste(img, (x, y), _round_mask(w, h, r))

@lru_cache(maxsize=64)
def _get_h_gradient(w: int, h: int, left_rgba: tuple, right_rgba: tuple) -> Image.Image:
    grad = Image.new("RGBA", (w, 1))
    for xi in range(w):
        t = xi / max(w - 1, 1)
        grad.putpixel((xi, 0), (
            int(left_rgba[0] + (right_rgba[0] - left_rgba[0]) * t),
            int(left_rgba[1] + (right_rgba[1] - left_rgba[1]) * t),
            int(left_rgba[2] + (right_rgba[2] - left_rgba[2]) * t),
            int(left_rgba[3] + (right_rgba[3] - left_rgba[3]) * t)
        ))
    return grad.resize((w, h), Image.NEAREST)

@lru_cache(maxsize=64)
def _get_v_gradient(w: int, h: int, top_rgba: tuple, bottom_rgba: tuple) -> Image.Image:
    grad = Image.new("RGBA", (1, h))
    for yi in range(h):
        t = yi / max(h - 1, 1)
        grad.putpixel((0, yi), (
            int(top_rgba[0] + (bottom_rgba[0] - top_rgba[0]) * t),
            int(top_rgba[1] + (bottom_rgba[1] - top_rgba[1]) * t),
            int(top_rgba[2] + (bottom_rgba[2] - top_rgba[2]) * t),
            int(top_rgba[3] + (bottom_rgba[3] - top_rgba[3]) * t)
        ))
    return grad.resize((w, h), Image.NEAREST)


# 富文本排版引擎 (Rich Text Parser & Renderer)

def _render_rich_text(html_snippet: str, max_w: int, main_color: tuple) -> Image.Image:
    soup = BeautifulSoup(html_snippet, "html.parser")
    
    tokens = []
    for el in soup.descendants:
        if isinstance(el, NavigableString):
            txt = str(el)
            if txt:
                parts = re.split(r'(\n)', txt)
                for p in parts:
                    if p == '\n':
                        tokens.append({"type": "br"})
                    elif p.strip():
                        is_strong = el.parent.name in ['strong', 'b']
                        is_key = el.parent.name == 'span' and 'key-input' in el.parent.get('class', [])
                        
                        col = main_color if is_strong else C_DESC
                        col = main_color if is_key else col
                        
                        tokens.append({
                            "type": "text", 
                            "text": p, 
                            "color": col, 
                            "is_key": is_key
                        })
        elif el.name == 'img':
            src = el.get("src", "")
            if src.startswith("data:"):
                tokens.append({"type": "img", "src": src})
        elif el.name == 'br':
            tokens.append({"type": "br"})

    lines = []
    curr_line = []
    curr_x = 0
    LH = 32 
    
    for t in tokens:
        if t["type"] == "br":
            lines.append(curr_line)
            curr_line = []
            curr_x = 0
            continue
            
        if t["type"] == "img":
            iw, ih = 28, 28
            if curr_x + iw + 4 > max_w and curr_line:
                lines.append(curr_line)
                curr_line = []
                curr_x = 0
            curr_line.append({"type": "img", "src": t["src"], "w": iw, "h": ih, "px": curr_x + 2})
            curr_x += iw + 4
            continue
            
        if t["type"] == "text":
            words = t["text"]
            buf = ""
            font = F20B if t["is_key"] else F20
            
            for char in words:
                cw = font.getlength(buf + char)
                pad = 12 if t["is_key"] else 0
                
                if curr_x + cw + pad > max_w:
                    if buf:
                        curr_line.append({
                            "type": "text", "text": buf, "font": font, 
                            "color": t["color"], "w": font.getlength(buf) + pad, 
                            "px": curr_x, "is_key": t["is_key"]
                        })
                    lines.append(curr_line)
                    curr_line = []
                    curr_x = 0
                    buf = char
                else:
                    buf += char
                    
            if buf:
                pw = font.getlength(buf) + (12 if t["is_key"] else 0)
                curr_line.append({
                    "type": "text", "text": buf, "font": font, 
                    "color": t["color"], "w": pw, 
                    "px": curr_x, "is_key": t["is_key"]
                })
                curr_x += pw

    if curr_line:
        lines.append(curr_line)
        
    if not lines:
        return Image.new("RGBA", (max_w, 0))

    H = len(lines) * LH
    img = Image.new("RGBA", (max_w, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    
    cy = 0
    for row in lines:
        for it in row:
            if it["type"] == "img":
                try:
                    ic = _b64_fit(it["src"], it["w"], it["h"])
                    img.paste(ic, (int(it["px"]), cy + (LH - it["h"]) // 2))
                except: pass
            elif it["type"] == "text":
                if it["is_key"]:
                    kw = it["w"]
                    kh = 24
                    kx = int(it["px"])
                    ky = cy + (LH - kh) // 2
                    _draw_rounded_rect(img, kx, ky, kx + kw, ky + kh, 4, (255,255,255,38), outline=(255,255,255,51))
                    en_font = globals().get(f"M{getattr(it['font'], 'size', None)}", None)
                    draw_text_mixed(d, (kx + 6, ky + _ty(it["font"], it["text"], kh)), it["text"], cn_font=it["font"], en_font=en_font, fill=it["color"])
                else:
                    en_font = globals().get(f"M{getattr(it['font'], 'size', None)}", None)
                    draw_text_mixed(d, (int(it["px"]), cy + _ty(it["font"], it["text"], LH)), it["text"], cn_font=it["font"], en_font=en_font, fill=it["color"])
        cy += LH
        
    return img


# HTML 解析

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    
    style_text = soup.select_one("style").string if soup.select_one("style") else ""
    bg_m = re.search(r"background-image:\s*url\('([^']+)'\)", style_text)
    bg_url = bg_m.group(1) if bg_m else ""
    
    col_m = re.search(r"--main-color:\s*([^;]+);", style_text)
    main_color = parse_color(col_m.group(1), (212, 177, 99, 255)) if col_m else (212, 177, 99, 255)
    
    section = "skill"
    if soup.select_one(".section-title") and "共鸣链" in soup.select_one(".section-title").get_text():
        section = "chain"
    elif soup.select_one(".section-title") and "核心机制" in soup.select_one(".section-title").get_text():
        section = "forte"

    char_name = soup.select_one(".char-name").get_text(strip=True) if soup.select_one(".char-name") else ""
    rarity_icon = soup.select_one(".rarity-icon").get("src") if soup.select_one(".rarity-icon") else ""
    
    tags = soup.select(".info-tag")
    ele_icon = tags[0].select_one("img").get("src") if len(tags)>0 and tags[0].select_one("img") else ""
    ele_name = tags[0].select_one("span").get_text(strip=True) if len(tags)>0 and tags[0].select_one("span") else ""
    
    wpn_icon = tags[1].select_one("img").get("src") if len(tags)>1 and tags[1].select_one("img") else ""
    wpn_name = tags[1].select_one("span").get_text(strip=True) if len(tags)>1 and tags[1].select_one("span") else ""
    
    mats = []
    if len(tags) > 2:
        mats = [img.get("src") for img in tags[2].select("img") if img.get("src", "").startswith("data:")]

    stats = []
    for st in soup.select(".stat-item"):
        lb = st.select_one(".stat-label").get_text(strip=True) if st.select_one(".stat-label") else ""
        vl = st.select_one(".stat-value").get_text(strip=True) if st.select_one(".stat-value") else ""
        stats.append((lb, vl))

    portrait = soup.select_one(".char-portrait").get("src") if soup.select_one(".char-portrait") else ""
    footer = soup.select_one(".footer img").get("src") if soup.select_one(".footer img") else ""

    cards_data = []
    forte_features = []
    
    if section == "skill":
        for card in soup.select(".card-list > .card"):
            c_name = card.select_one(".card-title").get_text(strip=True) if card.select_one(".card-title") else ""
            c_sub = card.select_one(".card-subtitle").get_text(strip=True) if card.select_one(".card-subtitle") else ""
            c_icon = card.select_one(".card-icon").get("src") if card.select_one(".card-icon") and card.select_one(".card-icon").name == 'img' else ""
            desc_html = "".join(str(c) for c in card.select_one(".card-desc").contents) if card.select_one(".card-desc") else ""
            
            table_data = []
            thead = card.select_one(".rate-table thead tr")
            if thead:
                th_cols = [th.get_text(strip=True) for th in thead.select("th")]
                table_data.append(th_cols)
                for tr in card.select(".rate-table tbody tr"):
                    table_data.append([td.get_text(strip=True) for td in tr.select("td")])

            cards_data.append({
                "type": "skill", "name": c_name, "sub": c_sub, "icon": c_icon,
                "desc_html": desc_html, "table": table_data
            })
            
    elif section == "chain":
        for card in soup.select(".card-list > .card"):
            c_idx = card.select_one(".card-icon").get_text(strip=True) if card.select_one(".card-icon") else ""
            c_name = card.select_one(".card-title").get_text(strip=True) if card.select_one(".card-title") else ""
            desc_html = "".join(str(c) for c in card.select_one(".card-desc").contents) if card.select_one(".card-desc") else ""
            cards_data.append({
                "type": "chain", "idx": c_idx, "name": c_name, "desc_html": desc_html
            })
            
    elif section == "forte":
        feat_grid = soup.select_one(".features-grid")
        if feat_grid:
            forte_features = [f.get_text(strip=True) for f in feat_grid.select(".feature-item")]
            
        for card in soup.select(".card-list > .card:not(:has(.features-grid))"):
            c_name = card.select_one(".card-title").get_text(strip=True) if card.select_one(".card-title") else ""
            groups = []
            for fg in card.select(".forte-group"):
                desc_html = "".join(str(c) for c in fg.select_one(".card-desc").contents) if fg.select_one(".card-desc") else ""
                imgs = [img.get("src") for img in fg.select(".forte-img") if img.get("src", "").startswith("data:")]
                groups.append({"desc_html": desc_html, "imgs": imgs})
                
            cards_data.append({"type": "forte", "name": c_name, "groups": groups})

    return {
        "bg_url": bg_url, "main_color": main_color, "section": section,
        "char_name": char_name, "rarity_icon": rarity_icon,
        "ele_icon": ele_icon, "ele_name": ele_name,
        "wpn_icon": wpn_icon, "wpn_name": wpn_name,
        "mats": mats, "stats": stats, "portrait": portrait,
        "footer": footer,
        "cards": cards_data,
        "forte_features": forte_features
    }


# 渲染器

def draw_header(data: dict) -> Image.Image:
    H = 280
    img = Image.new("RGBA", (INNER_W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    d.line([(0, H-2), (INNER_W, H-2)], fill=(255, 255, 255, 25), width=2)
    
    cx, cy = 10, 40
    draw_text_mixed(d, (cx, cy), data["char_name"], cn_font=F80B, en_font=M80, fill=C_WHITE)
    cy += 80 + 10
    
    if data["rarity_icon"]:
        try:
            ri = _b64_fit(data["rarity_icon"], 180, 48)
            img.paste(ri, (cx, cy), ri)
            cy += 48 + 10
        except: pass
        
    tag_y = cy
    curr_x = cx
    
    # Element tag
    tag_h = 36
    ew = int(F18B.getlength(data["ele_name"]))
    _draw_rounded_rect(img, curr_x, tag_y, curr_x + 32 + 8 + ew + 16, tag_y + tag_h, 18, (0,0,0,153), outline=data["main_color"])
    if data["ele_icon"]:
        try:
            ei = _b64_fit(data["ele_icon"], 32, 32)
            img.paste(ei, (curr_x + 4, tag_y + 2), ei)
        except: pass
    draw_text_mixed(d, (curr_x + 40, tag_y + _ty(F18B, data["ele_name"], tag_h)), data["ele_name"], cn_font=F18B, en_font=M18, fill=C_WHITE)
    curr_x += 32 + 8 + ew + 16 + 15
    
    # Weapon tag
    ww = int(F18B.getlength(data["wpn_name"]))
    _draw_rounded_rect(img, curr_x, tag_y, curr_x + 32 + 8 + ww + 16, tag_y + tag_h, 18, (0,0,0,153), outline=data["main_color"])
    if data["wpn_icon"]:
        try:
            wi = _b64_fit(data["wpn_icon"], 32, 32)
            wi_inv = ImageOps.invert(wi.convert("RGB")).convert("RGBA")
            wi_inv.putalpha(wi.split()[3])
            img.paste(wi_inv, (curr_x + 4, tag_y + 2), wi_inv)
        except: pass
    draw_text_mixed(d, (curr_x + 40, tag_y + _ty(F18B, data["wpn_name"], tag_h)), data["wpn_name"], cn_font=F18B, en_font=M18, fill=C_WHITE)
    curr_x += 32 + 8 + ww + 16 + 15
    
    # Mats
    if data["mats"]:
        mw = len(data["mats"]) * 32 + max(0, len(data["mats"])-1) * 4
        _draw_rounded_rect(img, curr_x, tag_y, curr_x + mw + 16, tag_y + tag_h, 18, (0,0,0,153), outline=data["main_color"])
        mx = curr_x + 8
        for m_src in data["mats"]:
            try:
                mi = _b64_fit(m_src, 32, 32)
                _paste_rounded(img, mi, mx, tag_y + 2, 6)
                mx += 36
            except: pass

    # Right Portrait & Stats
    if data["portrait"]:
        try:
            p_img = _b64_img(data["portrait"])
            scale = 340 / p_img.height
            pw = int(p_img.width * scale)
            p_img = p_img.resize((pw, 340), Image.LANCZOS)
            
            pmask = Image.new("L", (pw, 340), 255)
            pd = ImageDraw.Draw(pmask)
            for y in range(int(340 * 0.8), 340):
                alpha = int(255 - (y - 340 * 0.8) / (340 * 0.2) * 255)
                pd.line([(0, y), (pw, y)], fill=alpha)
                
            img.paste(p_img, (INNER_W - 200 - pw, -20), pmask)
        except: pass
        
    sy = 40
    sx = INNER_W - 200
    for lb, vl in data["stats"]:
        _draw_rounded_rect(img, sx, sy, sx + 200, sy + 30, 4, (0,0,0,128))
        d.rectangle([sx, sy, sx + 4, sy + 30], fill=data["main_color"])
        draw_text_mixed(d, (sx + 12, sy + _ty(F13B, lb, 30)), lb, cn_font=F13B, en_font=M13, fill=C_TEXT_SUB)
        vw = int(F16.getlength(vl))
        draw_text_mixed(d, (sx + 200 - 12 - vw, sy + _ty(F16, vl, 30)), vl, cn_font=F16, en_font=M16, fill=C_WHITE)
        sy += 30 + 8

    return img

def draw_card_block(card: dict, main_color: tuple) -> Image.Image:
    pad = 20
    cw = INNER_W
    hdr_h = 32 
    
    desc_img = _render_rich_text(card["desc_html"], cw - pad*2, main_color)
    body_h = desc_img.height
    
    extra_h = 0
    table_img = None
    
    # -------------------------------------------------------------
    # 核心修改点：支持动态折行的表格引擎
    # -------------------------------------------------------------
    if card["type"] == "skill" and card.get("table"):
        rows = card["table"]
        tb_w = cw - pad * 2
        
        # 调整首列占比：减小至 20%，给右边数据流出更大空间
        col_w_0 = int(tb_w * 0.20)
        num_rest_cols = max(1, len(rows[0]) - 1)
        col_w_rest = (tb_w - col_w_0) // num_rest_cols
        
        # 中英文精确测宽函数，防止文字无法居中
        def get_mixed_width(text, cn_f, en_f):
            w = 0
            for ch in text:
                is_en = 'a' <= ch <= 'z' or 'A' <= ch <= 'Z' or '0' <= ch <= '9'
                w += (en_f if is_en else cn_f).getlength(ch)
            return int(w)
            
        # 强制换行函数
        def wrap_mixed(text, cn_f, en_f, max_w):
            lines = []
            curr_line = ""
            curr_w = 0
            for char in text:
                # 【修复】把 ch 改成了 char
                is_en = 'a' <= char <= 'z' or 'A' <= char <= 'Z' or '0' <= char <= '9'
                char_w = (en_f if is_en else cn_f).getlength(char)
                if curr_w + char_w <= max_w:
                    curr_line += char
                    curr_w += char_w
                else:
                    if curr_line: lines.append(curr_line)
                    curr_line = char
                    curr_w = char_w
            if curr_line: lines.append(curr_line)
            return lines

        # 1. 预计算所有格子的换行状态和行高
        wrapped_rows = []
        row_heights = []
        base_h = 36
        line_h = 16 # 单行文本高度
        
        for r_idx, row in enumerate(rows):
            f = F13B if r_idx == 0 else F13
            en_f = globals().get(f"M{f.size}")
            wrapped_cells = []
            max_lines = 1
            
            for c_idx, cell_txt in enumerate(row):
                w = col_w_0 if c_idx == 0 else col_w_rest
                if c_idx == len(row) - 1:
                    w = tb_w - col_w_0 - col_w_rest * (len(row)-2)
                    
                # 左右各留 5px padding，防止字贴脸
                max_text_w = max(10, w - 10)
                lines = wrap_mixed(cell_txt, f, en_f, max_text_w)
                if not lines: lines = [""]
                wrapped_cells.append(lines)
                max_lines = max(max_lines, len(lines))
                
            wrapped_rows.append(wrapped_cells)
            # 行高 = max(基础行高, 文本行数*行高 + 上下总padding 16)
            row_heights.append(max(base_h, max_lines * line_h + 16))
            
        tb_h = sum(row_heights)
        
        # 画布尺寸双向 +1，保证四边框严丝合缝
        table_img = Image.new("RGBA", (tb_w + 1, tb_h + 1), (0, 0, 0, 76))
        td = ImageDraw.Draw(table_img)
        
        # 2. 循环绘制内容
        curr_y = 0
        for r_idx, (wrapped_cells, row_h) in enumerate(zip(wrapped_rows, row_heights)):
            is_th = r_idx == 0
            
            # 交替斑马纹背景
            if r_idx % 2 != 0:
                td.rectangle([0, curr_y, tb_w - 1, curr_y + row_h - 1], fill=(255, 255, 255, 5))
                
            curr_x = 0
            for c_idx, lines in enumerate(wrapped_cells):
                w = col_w_0 if c_idx == 0 else col_w_rest
                if c_idx == len(wrapped_cells) - 1:
                    w = tb_w - curr_x
                    
                cell_rect = [curr_x, curr_y, curr_x + w - 1, curr_y + row_h - 1]
                td.rectangle(cell_rect, outline=(255, 255, 255, 20))
                
                if c_idx == 0:
                    td.rectangle(cell_rect, fill=(0, 0, 0, 25), outline=(255, 255, 255, 20))
                    
                f = F13B if is_th else F13
                col = main_color if is_th else (238, 238, 238, 255)
                en_f = globals().get(f"M{f.size}")
                
                total_text_h = len(lines) * line_h
                # Y 轴居中，微调 -1 修正基线视觉
                start_y = curr_y + (row_h - total_text_h) // 2 - 1 
                
                for i, line in enumerate(lines):
                    if c_idx == 0:
                        draw_text_mixed(td, (curr_x + 8, start_y + i * line_h), line, cn_font=f, en_font=en_f, fill=col)
                    else:
                        tw = get_mixed_width(line, f, en_f)
                        draw_text_mixed(td, (curr_x + (w - tw) // 2, start_y + i * line_h), line, cn_font=f, en_font=en_f, fill=col)
                        
                curr_x += w
            curr_y += row_h

        # 【终极补全】强行画一次大外框，彻底解决部分分辨率导致的底线消失
        td.rectangle([0, 0, tb_w, tb_h], outline=(255, 255, 255, 40))
        
        extra_h = 15 + tb_h
        
    H = pad * 2 + hdr_h + 12 + body_h + extra_h + 10
    
    img = Image.new("RGBA", (cw, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _draw_rounded_rect(img, 0, 0, cw, H, 6, C_CARD_BG, outline=(255,255,255,20))
    
    cy = pad
    d.line([(pad, cy + hdr_h), (cw - pad, cy + hdr_h)], fill=(255,255,255,25), width=1)
    
    hx = pad
    if card.get("icon") or card.get("idx"):
        if card.get("icon"):
            try:
                ic = _b64_fit(card["icon"], 28, 28)
                img.paste(ic, (hx, cy - 2), ic)
            except: pass
        elif card.get("idx"):
            draw_text_mixed(d, (hx, cy - 2), card["idx"], cn_font=F24B, en_font=M24, fill=C_WHITE)
        hx += 28 + 12
        
    draw_text_mixed(d, (hx, cy), card["name"], cn_font=F24B, en_font=M24, fill=main_color)
    
    if card.get("sub"):
        sw = int(F16.getlength(card["sub"]))
        _draw_rounded_rect(img, cw - pad - sw - 20, cy, cw - pad, cy + 24, 12, (255,255,255,20))
        draw_text_mixed(d, (cw - pad - sw - 10, cy + _ty(F16, card["sub"], 24)), card["sub"], cn_font=F16, en_font=M16, fill=C_TEXT_SUB)
        
    cy += hdr_h + 12
    
    img.alpha_composite(desc_img, (pad, cy))
    cy += body_h
    
    if table_img:
        cy += 15
        img.alpha_composite(table_img, (pad, cy))
        
    return img

def draw_forte_card(card: dict, main_color: tuple) -> Image.Image:
    pad = 20
    cw = INNER_W
    hdr_h = 32
    
    group_imgs = []
    for g in card["groups"]:
        d_img = _render_rich_text(g["desc_html"], cw - pad*2 - 30, main_color)
        gh = d_img.height
        
        im_objs = []
        for src in g["imgs"]:
            try:
                im = _b64_img(src)
                max_w = cw - pad*2 - 30
                if im.width > max_w:
                    sc = max_w / im.width
                    im = im.resize((max_w, int(im.height * sc)), Image.LANCZOS)
                im_objs.append(im)
            except: pass
            
        gh += sum(im.height for im in im_objs) + len(im_objs) * 10
        
        g_base = Image.new("RGBA", (cw - pad*2, gh + 30), (0,0,0,0))
        _draw_rounded_rect(g_base, 0, 0, cw - pad*2, gh + 30, 6, (255,255,255,8), outline=(255,255,255,13))
        
        gy = 15
        g_base.alpha_composite(d_img, (15, gy))
        gy += d_img.height + 10
        
        for io in im_objs:
            _paste_rounded(g_base, io, 15, gy, 4)
            ImageDraw.Draw(g_base).rounded_rectangle([15, gy, 15+io.width, gy+io.height], radius=4, outline=(255,255,255,25))
            gy += io.height + 10
            
        group_imgs.append(g_base)

    H = pad * 2 + hdr_h + 12 + sum(im.height for im in group_imgs) + max(0, len(group_imgs)-1) * 15
    
    img = Image.new("RGBA", (cw, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _draw_rounded_rect(img, 0, 0, cw, H, 6, C_CARD_BG, outline=(255,255,255,20))
    
    cy = pad
    d.line([(pad, cy + hdr_h), (cw - pad, cy + hdr_h)], fill=(255,255,255,25), width=1)
    draw_text_mixed(d, (pad, cy), card["name"], cn_font=F24B, en_font=M24, fill=main_color)
    cy += hdr_h + 12
    
    for gi in group_imgs:
        img.alpha_composite(gi, (pad, cy))
        cy += gi.height + 15
        
    return img

def draw_features_block(feats: list, main_color: tuple) -> Image.Image:
    if not feats: return Image.new("RGBA", (INNER_W, 0))
    
    pad = 20
    hdr_h = 32
    
    f_imgs = []
    for f in feats:
        fw = INNER_W - pad*2
        lines = _wrap_text(f, F20, fw - 40)
        fh = len(lines) * 30 + 28
        
        fim = Image.new("RGBA", (fw, fh), (0,0,0,0))
        fd = ImageDraw.Draw(fim)
        fim.alpha_composite(_get_h_gradient(fw, fh, (255,255,255,20), (255,255,255,5)), (0,0))
        fd.rectangle([0,0,4,fh], fill=main_color)
        
        fy = 14
        for l in lines:
            en_f = globals().get(f"M{getattr(F20, 'size', None)}", None)
            draw_text_mixed(fd, (20, fy), l, cn_font=F20, en_font=en_f, fill=C_WHITE)
            fy += 30
        f_imgs.append(fim)

    H = pad * 2 + hdr_h + 12 + sum(im.height for im in f_imgs) + max(0, len(f_imgs)-1) * 12
    
    img = Image.new("RGBA", (INNER_W, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    _draw_rounded_rect(img, 0, 0, INNER_W, H, 6, C_CARD_BG, outline=(255,255,255,20))
    
    cy = pad
    d.line([(pad, cy + hdr_h), (INNER_W - pad, cy + hdr_h)], fill=(255,255,255,25), width=1)
    draw_text_mixed(d, (pad, cy), "角色特点", cn_font=F24B, en_font=M24, fill=main_color)
    cy += hdr_h + 12
    
    for fim in f_imgs:
        img.alpha_composite(fim, (pad, cy))
        cy += fim.height + 12
        
    return img


# 主流程

def render(html: str) -> bytes:
    data = parse_html(html)
    
    # Header
    hdr_img = draw_header(data)
    
    # Section Title
    title_text = {"skill": "技能详情", "chain": "共鸣链", "forte": "核心机制"}.get(data["section"], "")
    s_title = Image.new("RGBA", (INNER_W, 40), (0,0,0,0))
    td = ImageDraw.Draw(s_title)
    td.rectangle([0, 6, 6, 34], fill=data["main_color"])
    draw_text_mixed(td, (15, 0), title_text, cn_font=F28B, en_font=M28, fill=data["main_color"])
    
    # Cards
    c_imgs = []
    if data["section"] == "forte" and data["forte_features"]:
        c_imgs.append(draw_features_block(data["forte_features"], data["main_color"]))
        
    for c in data["cards"]:
        if c["type"] == "forte":
            c_imgs.append(draw_forte_card(c, data["main_color"]))
        else:
            c_imgs.append(draw_card_block(c, data["main_color"]))
            
    # Footer
    FOOTER_H = 0
    f_img = None
    if data["footer"]:
        try:
            raw_f = _b64_img(data["footer"])
            scale = 18 / raw_f.height
            fw = int(raw_f.width * scale)
            FOOTER_H = 18
            f_img = raw_f.resize((fw, FOOTER_H), Image.LANCZOS)
        except: pass

    # Assemble
    total_h = PAD + hdr_img.height + 20 + s_title.height + 15
    total_h += sum(im.height for im in c_imgs) + max(0, len(c_imgs)-1) * 15
    total_h += (12 + FOOTER_H) if f_img else 0
    total_h += 12 # bottom padding
    
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    
    if data["bg_url"]:
        try:
            bg_base = _b64_img(data["bg_url"])
            bg_base = ImageOps.fit(bg_base, (W, total_h), Image.Resampling.LANCZOS)
            canvas.alpha_composite(bg_base)
            
            # Overlay
            td_overlay = _get_v_gradient(W, total_h, (15, 15, 19, 51), (15, 15, 19, 242))
            lr_overlay = _get_h_gradient(W, total_h, (78, 124, 255, 38), (78, 124, 255, 0))
            canvas.alpha_composite(td_overlay)
            canvas.alpha_composite(lr_overlay)
        except: pass

    cy = PAD
    canvas.alpha_composite(hdr_img, (PAD, cy))
    cy += hdr_img.height + 20
    
    canvas.alpha_composite(s_title, (PAD, cy))
    cy += s_title.height + 15
    
    for cim in c_imgs:
        canvas.alpha_composite(cim, (PAD, cy))
        cy += cim.height + 15
        
    if f_img:
        f_alpha = f_img.copy()
        f_alpha.putalpha(f_alpha.getchannel("A").point(lambda a: int(a * 0.6)))
        canvas.alpha_composite(f_alpha, ((W - f_img.width)//2, cy - 15 + 8))

    out_rgb = canvas.convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()