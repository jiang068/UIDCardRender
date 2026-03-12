# 明日方舟：终末地 探索进度卡片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 引入工具函数并生成字体
from . import (
    F12, F14, F16, F18, F20, F24, F48,
    M12, M14, M16, M18,
    O16, O18,
    get_font, draw_text_mixed, _b64_img, _b64_fit
)

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

C_GREEN = (74, 222, 128, 255)
C_GRAY_TEXT = (85, 85, 85, 255)


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg": "", "end_logo": "", "avatar": "",
        "name": "未知用户", "uid": "", "level": "0", "world_level": "0", "create_time": "N/A",
        "domains": []
    }

    # 背景与 Logo
    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg"] = bg_el.get("src", "")
    logo_el = soup.select_one(".footer-logo")
    if logo_el: data["end_logo"] = logo_el.get("src", "")
        
    av_el = soup.select_one(".avatar img")
    if av_el: data["avatar"] = av_el.get("src", "")
        
    name_el = soup.select_one(".user-name")
    if name_el: data["name"] = name_el.get_text(strip=True)
    uid_el = soup.select_one(".user-uid")
    if uid_el: data["uid"] = uid_el.get_text(strip=True).replace("UID", "").strip()

    tags = soup.select(".info-tags .tag")
    if len(tags) >= 3:
        data["level"] = tags[0].select_one("strong").get_text(strip=True) if tags[0].select_one("strong") else "0"
        data["world_level"] = tags[1].select_one("strong").get_text(strip=True) if tags[1].select_one("strong") else "0"
        data["create_time"] = tags[2].select_one("strong").get_text(strip=True) if tags[2].select_one("strong") else "N/A"

    # 解析探索区域
    for dom_el in soup.select(".domain-section"):
        dt_el = dom_el.select_one(".domain-title")
        if not dt_el: continue
            
        lvl_str = "0"
        tag_el = dt_el.select_one(".tag strong")
        if tag_el:
            lvl_str = tag_el.get_text(strip=True)
            clone = BeautifulSoup(str(dt_el), "lxml").select_one(".domain-title")
            clone.select_one(".tag").decompose()
            name_str = clone.get_text(strip=True)
        else:
            name_str = dt_el.get_text(strip=True)

        levels = []
        for tr in dom_el.select("tbody tr"):
            tds = tr.select("td")
            if len(tds) < 5: continue
            
            def ext_cnt(td):
                counts = []
                for sp in td.select(".cell-count"):
                    c = int(sp.select_one(".cur").get_text(strip=True)) if sp.select_one(".cur") else 0
                    m = int(sp.select_one(".max").get_text(strip=True)) if sp.select_one(".max") else 0
                    counts.append((c, m))
                return counts

            c1 = ext_cnt(tds[1])[0] if ext_cnt(tds[1]) else (0,0)
            c2 = ext_cnt(tds[2])[0] if ext_cnt(tds[2]) else (0,0)
            c3 = ext_cnt(tds[3])[0] if ext_cnt(tds[3]) else (0,0)
            
            c4_arr = ext_cnt(tds[4])
            c4_1 = c4_arr[0] if len(c4_arr) > 0 else (0,0)
            c4_2 = c4_arr[1] if len(c4_arr) > 1 else (0,0)

            levels.append({
                "name": tds[0].get_text(strip=True),
                "trchest": c1,
                "puzzle": c2,
                "blackbox": c3,
                "equip": c4_1,
                "piece": c4_2
            })
            
        data["domains"].append({"name": name_str, "level": lvl_str, "levels": levels})

    return data


def draw_bg(canvas: Image.Image, w: int, h: int, bg_src: str):
    sw, sh = w // 10, h // 10
    cx, cy = int(sw * 0.5), int(sh * 0.2)
    grad = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    max_dist = math.hypot(max(cx, sw - cx), max(cy, sh - cy))
    
    for y in range(sh):
        for x in range(sw):
            dist = math.hypot(x - cx, y - cy)
            ratio = min(dist / max_dist, 1.0)
            r = int(34 + (15 - 34) * ratio)
            g = int(35 + (16 - 35) * ratio)
            b = int(40 + (20 - 40) * ratio)
            grad.putpixel((x, y), (r, g, b, 255))
            
    canvas.alpha_composite(grad.resize((w, h), Image.Resampling.LANCZOS))
    
    if bg_src:
        try:
            bg_img = _b64_fit(bg_src, w, h).convert("RGBA")
            bg_img.putalpha(Image.new("L", (w, h), 38)) # 15% opacity
            canvas.alpha_composite(bg_img)
        except Exception: pass

    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    grid_c = (255, 255, 255, 8)
    for x in range(0, w, 40): gd.line([(x, 0), (x, h)], fill=grid_c, width=1)
    for y in range(0, h, 40): gd.line([(0, y), (w, y)], fill=grid_c, width=1)
    
    mask = Image.new("L", (w, h), 255)
    md = ImageDraw.Draw(mask)
    fade_h = int(h * 0.4)
    for y in range(fade_h, h):
        alpha = int(255 * (1 - min((y - fade_h) / (h * 0.6), 1.0)))
        md.line([(0, y), (w, y)], fill=alpha)
    grid.putalpha(mask)
    canvas.alpha_composite(grid)


def draw_section_title(d: ImageDraw.ImageDraw, x: int, y: int, title_cn: str, title_en: str):
    d.line([(x, y), (x, y + 24)], fill=C_ACCENT, width=4)
    draw_text_mixed(d, (x + 12, y), title_cn, cn_font=F24, en_font=F24, fill=C_TEXT, dy_en=5)
    cn_w = int(F24.getlength(title_cn))
    draw_text_mixed(d, (x + 12 + cn_w + 10, y + 8), title_en, cn_font=F14, en_font=M14, fill=C_SUBTEXT, dy_en=3)
    return 36


def get_count_w(cur: int, mx: int) -> int:
    """计算单组 进度文本 占用的宽度"""
    return int(M18.getlength(str(cur))) + int(M18.getlength("/")) + int(M18.getlength(str(mx))) + 8

def draw_cell_count(d: ImageDraw.ImageDraw, x: int, y: int, cur: int, mx: int):
    """绘制单组进度 (居中起始 x)"""
    if mx == 0:
        c_col = m_col = C_GRAY_TEXT
    elif cur >= mx:
        c_col = C_GREEN
        m_col = (136, 136, 136, 255)
    else:
        c_col = C_ACCENT
        m_col = (136, 136, 136, 255)
        
    c_s, m_s = str(cur), str(mx)
    cw = int(M18.getlength(c_s))
    sw = int(M18.getlength("/"))
    
    draw_text_mixed(d, (x, y), c_s, cn_font=M18, en_font=M18, fill=c_col, dy_en=4)
    draw_text_mixed(d, (x + cw + 4, y), "/", cn_font=M18, en_font=M18, fill=(102,102,102,255), dy_en=4)
    draw_text_mixed(d, (x + cw + 4 + sw + 4, y), m_s, cn_font=M18, en_font=M18, fill=m_col, dy_en=4)


def render(html: str) -> bytes:
    data = parse_html(html)
    
    # ---------------- 1. 高度预计算 ----------------
    cur_y = PAD
    
    # Header Area
    cur_y += 100 + 25 + 30
    
    # Section Title
    cur_y += 24 + 15
    
    # Domains
    if not data["domains"]:
        cur_y += 90 # 暂无探索数据
    else:
        for dom in data["domains"]:
            cur_y += 36 # domain title
            cur_y += 50 # thead
            cur_y += len(dom["levels"]) * 50 # tbody tr
            cur_y += 10 # domain-section margin-bottom
            
    # Footer
    cur_y += 50
    total_h = max(cur_y, 800)
    
    # ---------------- 2. 实际绘制 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg(canvas, W, total_h, data["bg"])
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    
    # === Header ===
    d.rectangle([PAD, y, PAD + 100, y + 100], fill=(17, 17, 17, 255), outline=C_ACCENT, width=1)
    if data["avatar"]:
        try:
            # 修改头像贴图：增加一个矩形的裁剪而不是圆形以匹配模板
            av_img = _b64_fit(data["avatar"], 100, 100)
            canvas.paste(av_img, (PAD, y))
        except Exception: pass
        
    ux = PAD + 100 + 25
    draw_text_mixed(d, (ux, y + 5), data["name"], cn_font=F48, en_font=F48, fill=C_TEXT, dy_en=10)
    name_w = int(F48.getlength(data["name"]))
    
    if data["uid"]:
        uid_x = ux + name_w + 15
        uid_text = f"UID {data['uid']}"
        uid_w = int(M16.getlength(uid_text))
        d.rounded_rectangle([uid_x, y + 25, uid_x + uid_w + 16, y + 25 + 24], radius=4, fill=(255, 255, 255, 12))
        draw_text_mixed(d, (uid_x + 8, y + 28), uid_text, cn_font=M16, en_font=M16, fill=C_SUBTEXT, dy_en=3)
        
    tag_y = y + 65
    tx = ux
    def draw_tag(x, y, label, val, is_cn=False):
        lbl_f = F16 if is_cn else O16
        lbl_w = int(lbl_f.getlength(label))
        val_w = int(O18.getlength(val))
        tw = lbl_w + val_w + 5 + 24
        d.rectangle([x, y, x + tw, y + 28], fill=C_PANEL, outline=C_BORDER, width=1)
        draw_text_mixed(d, (x + 12, y + 4), label, cn_font=lbl_f, en_font=lbl_f, fill=(204, 204, 204, 255), dy_en=3)
        draw_text_mixed(d, (x + 12 + lbl_w + 5, y + 3), val, cn_font=O18, en_font=O18, fill=C_ACCENT, dy_en=3)
        return tw + 15
        
    tx += draw_tag(tx, tag_y, "LEVEL", data["level"])
    tx += draw_tag(tx, tag_y, "WORLD", data["world_level"])
    tx += draw_tag(tx, tag_y, "苏醒日", data["create_time"], is_cn=True)
    
    y += 100 + 25
    d.line([(PAD, y), (W - PAD, y)], fill=C_BORDER, width=1)
    y += 30
    
    # === Exploration ===
    draw_section_title(d, PAD, y, "区域探索", "EXPLORATION")
    y += 24 + 15
    
    if not data["domains"]:
        d.rectangle([PAD, y, PAD + INNER_W, y + 90], outline=C_BORDER, width=1)
        draw_text_mixed(d, (W//2 - 40, y + 35), "暂无探索数据", cn_font=F16, en_font=F16, fill=(102, 102, 102, 255), dy_en=3)
        y += 90
    else:
        # 表格列宽设定 (22%, 19.5% x4) => 202px, 179px, 179px, 179px, 181px
        cw = [202, 179, 179, 179, 181]
        cx = [PAD, PAD+202, PAD+381, PAD+560, PAD+739]
        
        for dom in data["domains"]:
            # Domain Title
            draw_text_mixed(d, (PAD, y + 5), dom["name"], cn_font=F24, en_font=F24, fill=C_TEXT, dy_en=5)
            nm_w = int(F24.getlength(dom["name"]))
            
            d.rectangle([PAD + nm_w + 10, y + 5, PAD + nm_w + 10 + 45, y + 30], fill=C_PANEL, outline=C_BORDER, width=1)
            draw_text_mixed(d, (PAD + nm_w + 16, y + 8), f"Lv.{dom['level']}", cn_font=F14, en_font=O16, fill=C_TEXT, dy_en=3)
            y += 36
            
            # Table Boundary
            tb_h = 50 + len(dom["levels"]) * 50
            d.rectangle([PAD, y, PAD + INNER_W, y + tb_h], outline=C_BORDER, width=1)
            
            # Thead
            d.rectangle([PAD, y, PAD + INNER_W, y + 50], fill=(255, 255, 255, 15))
            d.line([(PAD, y + 50), (PAD + INNER_W, y + 50)], fill=C_BORDER, width=1)
            
            headers = ["区域", "宝箱", "醚质", "协议", "装备 / 档案"]
            draw_text_mixed(d, (cx[0] + 20, y + 15), headers[0], cn_font=F18, en_font=F18, fill=(170, 170, 170, 255), dy_en=4)
            for i in range(1, 5):
                hw = int(F18.getlength(headers[i]))
                draw_text_mixed(d, (cx[i] + cw[i]//2 - hw//2, y + 15), headers[i], cn_font=F18, en_font=F18, fill=(170, 170, 170, 255), dy_en=4)
            y += 50
            
            # Tbody
            for r_idx, lv in enumerate(dom["levels"]):
                if r_idx % 2 != 0: # zebra: even child (index 1,3,5...)
                    d.rectangle([PAD, y, PAD + INNER_W, y + 50], fill=(255, 255, 255, 4))
                d.line([(PAD, y + 50), (PAD + INNER_W, y + 50)], fill=(255, 255, 255, 10), width=1)
                
                # Col 0 (Left align)
                draw_text_mixed(d, (cx[0] + 20, y + 14), lv["name"], cn_font=F20, en_font=F20, fill=(221, 221, 221, 255), dy_en=4)
                
                # Col 1-3 (Center)
                sets = [lv["trchest"], lv["puzzle"], lv["blackbox"]]
                for c_i in range(3):
                    cur, mx = sets[c_i]
                    tw = get_count_w(cur, mx)
                    draw_cell_count(d, cx[c_i+1] + cw[c_i+1]//2 - tw//2, y + 14, cur, mx)
                    
                # Col 4 (Dual center)
                c4_1, c4_2 = lv["equip"], lv["piece"]
                w_1 = get_count_w(c4_1[0], c4_1[1])
                w_2 = get_count_w(c4_2[0], c4_2[1])
                w_sep = int(M18.getlength(" | "))
                tot_w = w_1 + w_sep + w_2
                
                st_x = cx[4] + cw[4]//2 - tot_w//2
                draw_cell_count(d, st_x, y + 14, c4_1[0], c4_1[1])
                draw_text_mixed(d, (st_x + w_1, y + 14), " | ", cn_font=M18, en_font=M18, fill=(85, 85, 85, 255), dy_en=4)
                draw_cell_count(d, st_x + w_1 + w_sep, y + 14, c4_2[0], c4_2[1])
                
                y += 50
            y += 10 # domain gap
            
    # === Footer Logo ===
    if data["end_logo"]:
        try:
            logo = _b64_img(data["end_logo"])
            lw = 120
            lh = int(logo.height * (lw / logo.width))
            logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
            logo.putalpha(ImageChops.multiply(logo.split()[3], Image.new("L", (lw, lh), 76)))
            canvas.alpha_composite(logo, (W - 40 - lw, total_h - 20 - lh))
        except Exception: pass

    # 最终输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()