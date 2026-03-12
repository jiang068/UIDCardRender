# 明日方舟：终末地 抽卡记录卡片渲染器 (PIL 版)

from __future__ import annotations

import math
import re
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageOps

# 避免循环导入，直接引入工具函数并局部生成字体
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit, _round_mask,
    F12, F14, F16, F22, F26, F40,
    M10, M12, M14, M16,
    O14, O16, O34, O38
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

# 抽卡欧非颜色
PULL_COLORS = {
    "lucky": (43, 210, 43, 255),    # #2bd22b
    "normal": (255, 255, 255, 255), # #ffffff
    "unlucky": (230, 58, 58, 255)   # #e63a3a
}

def _parse_progress_style(style_str: str) -> tuple[float, tuple]:
    prog = 0.0
    color = C_ACCENT
    if not style_str: return prog, color
    pm = re.search(r"width:\s*([\d\.]+)%", style_str)
    if pm: prog = float(pm.group(1))
    cm = re.search(r"background:\s*#([a-fA-F0-9]+)", style_str)
    if cm:
        hex_str = cm.group(1)
        if len(hex_str) == 3: hex_str = "".join(c+c for c in hex_str)
        if len(hex_str) == 6:
            color = (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16), 255)
    return prog, color

def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg_url": "", "illustration": "", "end_logo": "",
        "user": {"avatar": "", "name": "", "uid": "", "data_time": ""},
        "pools": []
    }
    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg_url"] = bg_el.get("src", "")
    ill_el = soup.select_one(".illustration-layer img")
    if ill_el: data["illustration"] = ill_el.get("src", "")
    logo_el = soup.select_one(".ef-logo")
    if logo_el: data["end_logo"] = logo_el.get("src", "")
    av_el = soup.select_one(".avatar-box img")
    if av_el: data["user"]["avatar"] = av_el.get("src", "")
    name_el = soup.select_one(".user-name")
    if name_el:
        clone = BeautifulSoup(str(name_el), "lxml").select_one(".user-name")
        for tag in clone.select("span"): tag.decompose()
        data["user"]["name"] = clone.get_text(strip=True)
    uid_el = soup.select_one(".uid-tag")
    if uid_el: data["user"]["uid"] = uid_el.get_text(strip=True).replace("UID_", "").strip()
    time_el = soup.select_one(".data-time")
    if time_el: data["user"]["data_time"] = time_el.get_text(strip=True).replace("LAST_UPDATE:", "").strip()

    for ps in soup.select(".pool-section"):
        title = ps.select_one(".pool-title").get_text(strip=True) if ps.select_one(".pool-title") else ""
        time_range = ps.select_one(".pool-time").get_text(strip=True) if ps.select_one(".pool-time") else ""
        empty_el = ps.select_one(".pool-empty")
        if empty_el:
            data["pools"].append({"title": title, "time": time_range, "empty": True})
            continue
        status_el = ps.select_one(".status-badge")
        status = status_el.get_text(strip=True) if status_el else ""
        rem_el = ps.select_one(".remaining-text")
        remaining = rem_el.get_text(strip=True) if rem_el else ""
        prog_el = ps.select_one(".progress-bar-fill")
        prog_val, prog_col = 0.0, C_ACCENT
        if prog_el:
            prog_val, prog_col = _parse_progress_style(prog_el.get("style", ""))
        is_merged = "merged" in ps.select_one(".stats-bar").get("class", [])
        pool_data = {
            "title": title, "time": time_range, "empty": False,
            "status": status, "remaining": remaining, "progress": prog_val, "color": prog_col,
            "is_merged": is_merged, "stats": [], "sub_pools": [], "six_stars": []
        }
        for sc in ps.select(".stat-card"):
            num_el = sc.select_one(".stat-num")
            lbl_el = sc.select_one(".stat-label")
            if num_el and lbl_el:
                color_type = "normal"
                cls = num_el.get("class", [])
                if "pull-unlucky" in cls: color_type = "unlucky"
                elif "pull-lucky" in cls: color_type = "lucky"
                pool_data["stats"].append({"num": num_el.get_text(strip=True), "label": lbl_el.get_text(strip=True), "color": color_type})
        for sp in ps.select(".sub-pool-chip"):
            pity_el = sp.select_one(".sp-pity")
            pity_col = "normal"
            if pity_el:
                cls = pity_el.get("class", [])
                if "pull-unlucky" in cls: pity_col = "unlucky"
                elif "pull-lucky" in cls: pity_col = "lucky"
            pool_data["sub_pools"].append({
                "name": sp.select_one(".sp-name").get_text(strip=True) if sp.select_one(".sp-name") else "",
                "stat": sp.select_one(".sp-stat").get_text(strip=True) if sp.select_one(".sp-stat") else "",
                "pity": pity_el.get_text(strip=True) if pity_el else "",
                "color": pity_col
            })
        for item in ps.select(".six-star-item"):
            av_el = item.select_one(".six-star-img-box img:not(.up-tag)")
            pull_num_el = item.select_one(".pull-num")
            color_type = "normal"
            if pull_num_el:
                cls = pull_num_el.get("class", [])
                if "pull-unlucky" in cls: color_type = "unlucky"
                elif "pull-lucky" in cls: color_type = "lucky"
            pool_data["six_stars"].append({
                "avatar": av_el.get("src", "") if av_el else "",
                "up_tag": item.select_one(".up-tag").get("src", "") if item.select_one(".up-tag") else "",
                "pool_label": item.select_one(".pool-label-tag").get_text(strip=True) if item.select_one(".pool-label-tag") else "",
                "pull_num": pull_num_el.get_text(strip=True) if pull_num_el else "",
                "color": color_type,
                "name": item.select_one(".six-star-name").get_text(strip=True) if item.select_one(".six-star-name") else ""
            })
        data["pools"].append(pool_data)
    return data

def draw_bg_and_illustration(canvas: Image.Image, data: dict, w: int, h: int):
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
    if data["bg_url"]:
        try:
            bg_img = _b64_fit(data["bg_url"], w, h).convert("RGBA")
            bg_img.putalpha(Image.new("L", (w, h), 25)) 
            canvas.alpha_composite(bg_img)
        except Exception: pass
    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    grid_c = (38, 39, 44, 180)
    for x in range(0, w, 40): gd.line([(x, 0), (x, h)], fill=grid_c, width=1)
    for y in range(0, h, 40): gd.line([(0, y), (w, y)], fill=grid_c, width=1)
    mask = Image.new("L", (w, h), 255)
    md = ImageDraw.Draw(mask)
    fade_h = int(h * 0.2)
    for y in range(fade_h, h):
        alpha = int(255 * (1 - min((y - fade_h) / (h * 0.8), 1.0)))
        md.line([(0, y), (w, y)], fill=alpha)
    grid.putalpha(mask)
    canvas.alpha_composite(grid)
    if data["illustration"]:
        try:
            ill = _b64_img(data["illustration"])
            iw, ih = 700, 800
            ill = ImageOps.fit(ill, (iw, ih), Image.Resampling.LANCZOS).convert("RGBA")
            ill_mask = Image.new("L", (iw, ih), 255)
            imd = ImageDraw.Draw(ill_mask)
            fade_start_y = int(ih * 0.4)
            for y in range(fade_start_y, ih):
                alpha = int(255 * (1 - min((y - fade_start_y) / (ih - fade_start_y), 1.0)))
                imd.line([(0, y), (iw, y)], fill=alpha)
            for x in range(iw):
                alpha_x = int(255 * (x / iw))
                for y in range(ih):
                    current_a = ill_mask.getpixel((x, y))
                    ill_mask.putpixel((x, y), int(current_a * (alpha_x / 255)))
            ill.putalpha(ill_mask)
            shadow = Image.new("RGBA", (iw, ih), (0,0,0,0))
            shadow.paste((0,0,0,128), ill.split()[3])
            shadow = shadow.filter(ImageFilter.GaussianBlur(8))
            ix, iy = w - iw + 100, 0
            canvas.alpha_composite(shadow, (ix - 10, iy))
            ill_final = Image.new("RGBA", (w, h), (0,0,0,0))
            ill_final.paste(ill, (ix, iy))
            ill_final.putalpha(ImageChops.multiply(ill_final.split()[3], Image.new("L", (w, h), 153)))
            canvas.alpha_composite(ill_final)
        except Exception: pass

def draw_status_row(d: ImageDraw.ImageDraw, x: int, y: int, status: str, remaining: str, progress: float, p_color: tuple, max_w: int):
    if status == '进行中': bg_c, bd_c, txt_c = (255, 230, 0, 38), (255, 230, 0, 76), C_ACCENT
    elif status == '已结束': bg_c, bd_c, txt_c = (255, 255, 255, 12), (255, 255, 255, 20), (102, 102, 102, 255)
    else: bg_c, bd_c, txt_c = (74, 158, 255, 38), (74, 158, 255, 76), (74, 158, 255, 255)
    st_w = int(F14.getlength(status)) + 24
    d.rounded_rectangle([x, y, x + st_w, y + 22], radius=3, fill=bg_c, outline=bd_c, width=1)
    draw_text_mixed(d, (x + 12, y + 2), status, cn_font=F14, en_font=M14, fill=txt_c, dy_en=3)
    curr_x = x + st_w + 10
    if remaining:
        rem_w = int(M14.getlength(remaining))
        draw_text_mixed(d, (curr_x, y + 3), remaining, cn_font=F14, en_font=M14, fill=(221, 221, 221, 255), dy_en=3)
        curr_x += rem_w + 10
    bar_w = max_w - (curr_x - x)
    if bar_w > 20:
        bar_y = y + 6
        d.rounded_rectangle([curr_x, bar_y, curr_x + bar_w, bar_y + 10], radius=4, fill=(26, 26, 26, 255), outline=(255,255,255,15), width=1)
        fill_w = int(bar_w * progress / 100)
        if fill_w > 0: d.rounded_rectangle([curr_x, bar_y, curr_x + fill_w, bar_y + 10], radius=4, fill=p_color)

def render(html: str) -> bytes:
    data = parse_html(html)
    cur_y = PAD + 85 + 25
    pool_data_h = []
    for pool in data["pools"]:
        ph = 20 * 2 + 26 + 10 + 10
        if pool["empty"]: ph += 56
        else:
            ph += 60
            if pool["sub_pools"]: ph += 30
            if pool["six_stars"]:
                ph += 15
                cols, gap = 5, 10
                item_w = (INNER_W - 20*2 - gap*(cols-1)) // cols
                rows = math.ceil(len(pool["six_stars"]) / cols)
                ph += rows * (item_w + 34) + max(0, rows-1)*gap
        pool_data_h.append(ph)
        cur_y += ph + 25 
    total_h = max(cur_y + PAD + 20, 600)
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg_and_illustration(canvas, data, W, total_h)
    d = ImageDraw.Draw(canvas)
    y = PAD
    aw = 85
    d.rectangle([PAD, y, PAD + aw, y + aw], fill=(17, 17, 17, 255), outline=(255, 255, 255, 51), width=2)
    d.line([(PAD-5, y-3.5), (PAD+15, y-3.5)], fill=C_ACCENT, width=3)
    d.line([(PAD-3.5, y-5), (PAD-3.5, y+15)], fill=C_ACCENT, width=3)
    if data["user"]["avatar"]:
        try: canvas.paste(_b64_fit(data["user"]["avatar"], aw, aw), (PAD, y))
        except Exception: pass
    ux = PAD + aw + 25
    draw_text_mixed(d, (ux, y + 10), data["user"]["name"], cn_font=F40, en_font=F40, fill=C_TEXT, dy_en=8)
    if data["user"]["uid"]:
        uid_x, uid_text = ux + int(F40.getlength(data["user"]["name"])) + 15, f"UID_{data['user']['uid']}"
        d.rectangle([uid_x, y + 25, uid_x + int(M16.getlength(uid_text)) + 16, y + 25 + 24], fill=(255, 230, 0, 25), outline=(255, 230, 0, 76), width=1)
        # === [上提] UID 数字上浮 ===
        draw_text_mixed(d, (uid_x + 8, y + 28), uid_text, cn_font=M16, en_font=M16, fill=C_ACCENT, dy_en=-4)
    if data["user"]["data_time"]:
        draw_text_mixed(d, (ux, y + 60), f"// LAST_UPDATE: {data['user']['data_time']}", cn_font=F14, en_font=M14, fill=C_SUBTEXT, dy_en=2)
    y += aw + 25
    for idx, pool in enumerate(data["pools"]):
        ph, px = pool_data_h[idx], PAD
        d.rectangle([px, y, px + INNER_W, y + ph], fill=(20, 21, 24, 153), outline=(255, 255, 255, 20), width=1)
        d.rectangle([px, y, px + 4, y + ph], fill=C_ACCENT)
        ix, iy = px + 20, y + 20
        draw_text_mixed(d, (ix, iy), pool["title"], cn_font=F22, en_font=F22, fill=C_TEXT, dy_en=4)
        if pool["time"]:
            draw_text_mixed(d, (px + INNER_W - 20 - int(M14.getlength(pool["time"])), iy + 6), pool["time"], cn_font=M14, en_font=M14, fill=C_SUBTEXT, dy_en=3)
        iy += 26 + 10
        d.line([(ix, iy), (px + INNER_W - 20, iy)], fill=(255, 255, 255, 25), width=1)
        iy += 10
        if pool["empty"]:
            d.rectangle([ix, iy, px + INNER_W - 20, iy + 56], fill=(255, 255, 255, 5), outline=(255, 255, 255, 25), width=1)
            draw_text_mixed(d, (ix + INNER_W//2 - 120, iy + 18), "NO DATA RECORDED // 暂无记录", cn_font=F14, en_font=M14, fill=C_SUBTEXT, dy_en=3)
        else:
            cols = 3 if pool["is_merged"] else 4
            stat_gap, stat_w = 10, (INNER_W - 40 - 10 * ((3 if pool["is_merged"] else 4) - 1)) // (3 if pool["is_merged"] else 4)
            for s_idx, stat in enumerate(pool["stats"]):
                sx = ix + s_idx * (stat_w + stat_gap)
                d.rectangle([sx, iy, sx + stat_w, iy + 60], fill=(255, 255, 255, 7), outline=(255, 255, 255, 12), width=1)
                # === [上提] 统计大数字上浮 (dy_en 改为负值) ===
                draw_text_mixed(d, (sx + 12, iy + 8), stat["num"], cn_font=O34, en_font=O34, fill=(PULL_COLORS.get(stat["color"], C_TEXT) if stat["num"] != "-" else C_SUBTEXT), dy_en=-8)
                draw_text_mixed(d, (sx + 12, iy + 40), stat["label"], cn_font=F12, en_font=M10, fill=C_SUBTEXT, dy_en=2)
            iy += 60 + 10
            if pool["sub_pools"]:
                sp_x = ix
                for sp in pool["sub_pools"]:
                    sp_w = int(F12.getlength(sp["name"])) + int(M12.getlength(sp["stat"])) + int(O14.getlength(sp["pity"])) + 36
                    d.rectangle([sp_x, iy, sp_x + sp_w, iy + 24], fill=(255, 255, 255, 10), outline=(255, 255, 255, 20), width=1)
                    tx = sp_x + 12
                    draw_text_mixed(d, (tx, iy + 4), sp["name"], cn_font=F12, en_font=F12, fill=C_TEXT, dy_en=2)
                    tx += int(F12.getlength(sp["name"])) + 6
                    draw_text_mixed(d, (tx, iy + 6), sp["stat"], cn_font=F12, en_font=M12, fill=C_SUBTEXT, dy_en=-2)
                    # === [上提] 子池距六星数字上浮 ===
                    draw_text_mixed(d, (tx + int(M12.getlength(sp["stat"])) + 6, iy + 4), sp["pity"], cn_font=F14, en_font=O14, fill=PULL_COLORS.get(sp["color"], C_TEXT), dy_en=0)
                    sp_x += sp_w + 8
                iy += 24 + 10
            if pool["status"]:
                draw_status_row(d, ix, iy, pool["status"], pool["remaining"], pool["progress"], pool["color"], INNER_W - 40)
                iy += 22 + 10
            if pool["six_stars"]:
                cols, gap = 5, 10
                item_w = (INNER_W - 40 - gap*(cols-1)) // cols
                for s_idx, star in enumerate(pool["six_stars"]):
                    r, c = divmod(s_idx, cols)
                    sx, sy = ix + c * (item_w + gap), iy + r * (item_w + 34 + gap)
                    poly = [(sx, sy), (sx + item_w, sy), (sx + item_w, sy + int((item_w + 34) * 0.88)), (sx + item_w - 12, sy + item_w + 34), (sx, sy + item_w + 34)]
                    d.polygon(poly, fill=(0, 0, 0, 153))
                    d.line([(sx, sy), (sx + item_w, sy)], fill=(255, 78, 32, 255), width=3) 
                    if star["avatar"]:
                        try: canvas.paste(_b64_fit(star["avatar"], item_w, item_w), (sx, sy))
                        except Exception: pass
                    grad_img = Image.new("RGBA", (item_w, int(item_w * 0.5)))
                    for gy in range(grad_img.height): ImageDraw.Draw(grad_img).line([(0, gy), (item_w, gy)], fill=(0, 0, 0, int(230 * (gy / grad_img.height))))
                    canvas.alpha_composite(grad_img, (sx, sy + item_w - grad_img.height))
                    if star["pool_label"]:
                        lw = int(F12.getlength(star["pool_label"])) + 12
                        d.rectangle([sx + 4, sy + 4, sx + 4 + lw, sy + 4 + 18], fill=(0, 0, 0, 191))
                        draw_text_mixed(d, (sx + 10, sy + 6), star["pool_label"], cn_font=F12, en_font=F12, fill=(221, 221, 221, 255), dy_en=2)
                    if star["up_tag"]:
                        try:
                            up = _b64_img(star["up_tag"])
                            uw = int(up.width * (60 / up.height))
                            canvas.alpha_composite(up.resize((uw, 60), Image.Resampling.LANCZOS), (sx + item_w - uw - 3, sy + 3))
                        except Exception: pass
                    # === [上提] 六星抽数上浮 ===
                    draw_text_mixed(d, (sx + item_w - int(O34.getlength(star["pull_num"])) - 5, sy + item_w - 38), star["pull_num"], cn_font=O34, en_font=O34, fill=PULL_COLORS.get(star["color"], C_TEXT), dy_en=-8)
                    d.rectangle([sx, sy + item_w, sx + item_w, sy + item_w + 34], fill=(255, 255, 255, 5))
                    d.line([(sx, sy + item_w), (sx + item_w, sy + item_w)], fill=(255, 255, 255, 12), width=1)
                    draw_text_mixed(d, (sx + (item_w - int(F14.getlength(star["name"])))//2, sy + item_w + 8), star["name"], cn_font=F14, en_font=F14, fill=(238, 238, 238, 255), dy_en=3)
        y += ph + 25
    fy = total_h - 40
    d.line([(PAD, fy - 20), (W - PAD, fy - 20)], fill=(255, 255, 255, 25), width=1)
    draw_text_mixed(d, (PAD, fy), "Endfield Gacha Record Analysis Module // Ver 1.0", cn_font=F12, en_font=M12, fill=C_SUBTEXT, dy_en=2)
    if data["end_logo"]:
        try:
            logo = _b64_img(data["end_logo"])
            lw = int(logo.width * (40 / logo.height))
            canvas.alpha_composite(logo.resize((lw, 40), Image.Resampling.LANCZOS), (W - PAD - lw, fy - 10))
        except Exception: pass
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()