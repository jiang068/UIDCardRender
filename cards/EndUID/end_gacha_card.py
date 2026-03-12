# 明日方舟：终末地 抽卡记录卡片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# 避免循环导入，直接引入工具函数并局部生成字体
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit,
    F12, F14, F16, F26, F48,
    M10, M12, M14, M16,
    O16, O36, O38
)

# 画布基础属性
W = 1000
PAD = 50
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


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg_url": "", "illustration": "", "end_logo": "",
        "user": {"avatar": "", "name": "", "uid": "", "data_time": ""},
        "pools": []
    }

    # 背景、立绘、Logo
    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg_url"] = bg_el.get("src", "")
    
    ill_el = soup.select_one(".illustration-layer img")
    if ill_el: data["illustration"] = ill_el.get("src", "")
        
    logo_el = soup.select_one(".ef-logo")
    if logo_el: data["end_logo"] = logo_el.get("src", "")

    # 用户信息
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

    # 卡池区块
    for ps in soup.select(".pool-section"):
        title = ps.select_one(".pool-title").get_text(strip=True) if ps.select_one(".pool-title") else ""
        time_range = ps.select_one(".pool-time").get_text(strip=True) if ps.select_one(".pool-time") else ""
        
        empty_el = ps.select_one(".pool-empty")
        if empty_el:
            data["pools"].append({"title": title, "time": time_range, "empty": True})
            continue

        pool_data = {
            "title": title, "time": time_range, "empty": False,
            "stats": [], "six_stars": []
        }
        
        # 统计数据条
        for sc in ps.select(".stat-card"):
            num_el = sc.select_one(".stat-num")
            lbl_el = sc.select_one(".stat-label")
            if num_el and lbl_el:
                num_text = num_el.get_text(strip=True)
                lbl_text = lbl_el.get_text(strip=True)
                
                # 判断颜色类
                color_type = "normal"
                cls = num_el.get("class", [])
                if "pull-unlucky" in cls: color_type = "unlucky"
                elif "pull-lucky" in cls: color_type = "lucky"
                
                pool_data["stats"].append({"num": num_text, "label": lbl_text, "color": color_type})
                
        # 六星列表
        for item in ps.select(".six-star-item"):
            av_el = item.select_one(".six-star-img-box img:not(.up-tag)")
            av_src = av_el.get("src", "") if av_el else ""
            
            up_el = item.select_one(".up-tag")
            up_src = up_el.get("src", "") if up_el else ""
            
            pull_num_el = item.select_one(".pull-num")
            pull_num = pull_num_el.get_text(strip=True) if pull_num_el else ""
            
            color_type = "normal"
            if pull_num_el:
                cls = pull_num_el.get("class", [])
                if "pull-unlucky" in cls: color_type = "unlucky"
                elif "pull-lucky" in cls: color_type = "lucky"
                
            name_el = item.select_one(".six-star-name")
            name = name_el.get_text(strip=True) if name_el else ""
            
            pool_data["six_stars"].append({
                "avatar": av_src, "up_tag": up_src,
                "pull_num": pull_num, "color": color_type, "name": name
            })
            
        data["pools"].append(pool_data)

    return data


def draw_bg_and_illustration(canvas: Image.Image, data: dict, w: int, h: int):
    # 径向渐变
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

    # 网格掩码
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

    # 装饰大立绘 (右上角, 半透并带有复杂的淡出掩码)
    if data["illustration"]:
        try:
            ill = _b64_img(data["illustration"])
            iw, ih = 700, 800
            ill = ImageOps.fit(ill, (iw, ih), Image.Resampling.LANCZOS).convert("RGBA")
            
            # 创建向左和向下的混合透明遮罩
            ill_mask = Image.new("L", (iw, ih), 255)
            imd = ImageDraw.Draw(ill_mask)
            
            # 顶部 40% 向下透明过渡
            fade_start_y = int(ih * 0.4)
            for y in range(fade_start_y, ih):
                alpha = int(255 * (1 - min((y - fade_start_y) / (ih - fade_start_y), 1.0)))
                imd.line([(0, y), (iw, y)], fill=alpha)
                
            # 从右向左透明过渡 (整体淡入效果)
            for x in range(iw):
                alpha_x = int(255 * (x / iw))
                # 叠加 Y 和 X 的透明度
                for y in range(ih):
                    current_a = ill_mask.getpixel((x, y))
                    ill_mask.putpixel((x, y), int(current_a * (alpha_x / 255)))
                    
            ill.putalpha(ill_mask)
            
            # 给立绘添加一点阴影
            shadow = Image.new("RGBA", (iw, ih), (0,0,0,0))
            shadow.paste((0,0,0,128), ill.split()[3])
            shadow = shadow.filter(ImageFilter.GaussianBlur(8))
            
            ix, iy = w - iw + 100, 0
            canvas.alpha_composite(shadow, (ix - 10, iy))
            
            # 模拟 opacity 0.6
            ill_final = Image.new("RGBA", (w, h), (0,0,0,0))
            ill_final.paste(ill, (ix, iy))
            ill_final.putalpha(ImageChops.multiply(ill_final.split()[3], Image.new("L", (w, h), 153)))
            canvas.alpha_composite(ill_final)
            
        except Exception: pass


def render(html: str) -> bytes:
    data = parse_html(html)
    
    # ---------------- 1. 高度预计算 ----------------
    cur_y = PAD
    
    # Header
    cur_y += 100 + 40
    
    # Pools
    pool_data_h = []
    for pool in data["pools"]:
        ph = 25 * 2 # section padding
        ph += 26 + 12 + 5 # header title + pad_bottom + margin_bottom
        
        if pool["empty"]:
            ph += 40 + 20*2 # empty box height
        else:
            # Stats bar
            ph += 80 
            
            # Six Star Grid
            if pool["six_stars"]:
                ph += 15 # margin_top
                cols = 5
                gap = 12
                item_w = (INNER_W - 25*2 - gap*(cols-1)) // cols # inner grid
                item_h = item_w + 40 # img aspect 1:1 + info 40
                
                rows = math.ceil(len(pool["six_stars"]) / cols)
                ph += rows * item_h + max(0, rows-1)*gap
        
        pool_data_h.append(ph)
        cur_y += ph + 40 # 加上两个 pool 之间的 gap 40
        
    # Footer
    cur_y += 40 + 20 # footer border-top margin + padding
    total_h = max(cur_y + PAD, 800)
    
    # ---------------- 2. 实际绘制 ----------------
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    draw_bg_and_illustration(canvas, data, W, total_h)
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    
    # === Header ===
    aw = 100
    d.rectangle([PAD, y, PAD + aw, y + aw], fill=(17, 17, 17, 255), outline=(255, 255, 255, 51), width=2)
    # 头像左上角装饰角
    d.line([(PAD-5, y-3.5), (PAD+15, y-3.5)], fill=C_ACCENT, width=3)
    d.line([(PAD-3.5, y-5), (PAD-3.5, y+15)], fill=C_ACCENT, width=3)
    
    if data["user"]["avatar"]:
        try:
            av = _b64_fit(data["user"]["avatar"], aw, aw)
            canvas.paste(av, (PAD, y))
        except Exception: pass
        
    ux = PAD + aw + 25
    draw_text_mixed(d, (ux, y + 10), data["user"]["name"], cn_font=F48, en_font=F48, fill=C_TEXT)
    name_w = int(F48.getlength(data["user"]["name"]))
    
    if data["user"]["uid"]:
        uid_x = ux + name_w + 15
        uid_text = f"UID_{data['user']['uid']}"
        uid_w = int(M16.getlength(uid_text))
        d.rectangle([uid_x, y + 30, uid_x + uid_w + 16, y + 30 + 24], fill=(255, 230, 0, 25), outline=(255, 230, 0, 76), width=1)
        draw_text_mixed(d, (uid_x + 8, y + 32), uid_text, cn_font=M16, en_font=M16, fill=C_ACCENT)
        
    if data["user"]["data_time"]:
        draw_text_mixed(d, (ux, y + 68), f"// LAST_UPDATE: {data['user']['data_time']}", cn_font=M14, en_font=M14, fill=C_SUBTEXT)
        
    y += aw + 40
    
    # === Pools ===
    for idx, pool in enumerate(data["pools"]):
        ph = pool_data_h[idx]
        px = PAD
        
        # 绘制整个 Section 背景 (带左侧黄色强调边)
        d.rectangle([px, y, px + INNER_W, y + ph], fill=(20, 21, 24, 153), outline=(255, 255, 255, 20), width=1)
        d.rectangle([px, y, px + 4, y + ph], fill=C_ACCENT)
        
        ix, iy = px + 25, y + 25
        
        # Pool Header
        draw_text_mixed(d, (ix, iy - 2), pool["title"], cn_font=F26, en_font=F26, fill=C_TEXT)
        if pool["time"]:
            time_w = int(M14.getlength(pool["time"]))
            draw_text_mixed(d, (px + INNER_W - 25 - time_w, iy + 10), pool["time"], cn_font=M14, en_font=M14, fill=C_SUBTEXT)
            
        iy += 26 + 12
        d.line([(ix, iy), (px + INNER_W - 25, iy)], fill=(255, 255, 255, 25), width=1)
        iy += 5
        
        # Pool Content
        if pool["empty"]:
            d.rectangle([ix, iy, px + INNER_W - 25, iy + 80], fill=(255, 255, 255, 5), outline=(255, 255, 255, 25), width=1)
            draw_text_mixed(d, (ix + INNER_W//2 - 120, iy + 30), "NO DATA RECORDED // 暂无记录", cn_font=F14, en_font=M14, fill=C_SUBTEXT)
        else:
            # Stats Bar
            cols = 4
            stat_gap = 15
            stat_w = (INNER_W - 50 - stat_gap * (cols - 1)) // cols
            for s_idx, stat in enumerate(pool["stats"]):
                sx = ix + s_idx * (stat_w + stat_gap)
                d.rectangle([sx, iy, sx + stat_w, iy + 80], fill=(255, 255, 255, 7), outline=(255, 255, 255, 12), width=1)
                
                sc = PULL_COLORS.get(stat["color"], C_TEXT) if stat["num"] != "-" else C_SUBTEXT
                draw_text_mixed(d, (sx + 15, iy + 15), stat["num"], cn_font=O36, en_font=O36, fill=sc)
                draw_text_mixed(d, (sx + 15, iy + 55), stat["label"], cn_font=F12, en_font=M12, fill=C_SUBTEXT)
                
            iy += 80 + 15
            
            # Six Star Grid
            if pool["six_stars"]:
                cols = 5
                gap = 12
                item_w = (INNER_W - 50 - gap * (cols - 1)) // cols
                item_h = item_w + 40
                
                for s_idx, star in enumerate(pool["six_stars"]):
                    r, c = divmod(s_idx, cols)
                    sx = ix + c * (item_w + gap)
                    sy = iy + r * (item_h + gap)
                    
                    # 绘制带切角的六星卡片底色
                    clip_h = int(item_h * 0.88)
                    poly = [(sx, sy), (sx + item_w, sy), (sx + item_w, sy + clip_h), (sx + item_w - 12, sy + item_h), (sx, sy + item_h)]
                    d.polygon(poly, fill=(0, 0, 0, 153))
                    d.line([(sx, sy), (sx + item_w, sy)], fill=(255, 78, 32, 255), width=3) # 顶部橙色条
                    
                    # 头像区
                    if star["avatar"]:
                        try:
                            av = _b64_fit(star["avatar"], item_w, item_w)
                            canvas.paste(av, (sx, sy))
                        except Exception: pass
                    else:
                        d.rectangle([sx, sy, sx + item_w, sy + item_w], fill=(255, 255, 255, 12))
                        draw_text_mixed(d, (sx + item_w//2 - 25, sy + item_w//2 - 10), "NO IMG", cn_font=O16, en_font=O16, fill=(255,255,255,25))
                        
                    # 头像底部遮罩与拉拉拉渐变
                    grad_img = Image.new("RGBA", (item_w, int(item_w * 0.5)))
                    for gy in range(grad_img.height):
                        alpha = int(230 * (gy / grad_img.height))
                        ImageDraw.Draw(grad_img).line([(0, gy), (item_w, gy)], fill=(0, 0, 0, alpha))
                    canvas.alpha_composite(grad_img, (sx, sy + item_w - grad_img.height))
                    
                    # UP Tag
                    if star["up_tag"]:
                        try:
                            up = _b64_img(star["up_tag"])
                            uh = 60
                            uw = int(up.width * (uh / up.height))
                            up = up.resize((uw, uh), Image.Resampling.LANCZOS)
                            canvas.alpha_composite(up, (sx + item_w - uw - 3, sy + 3))
                        except Exception: pass
                        
                    # 抽数
                    pc = PULL_COLORS.get(star["color"], C_TEXT)
                    draw_text_mixed(d, (sx + item_w - int(O38.getlength(star["pull_num"])) - 5, sy + item_w - 40), star["pull_num"], cn_font=O38, en_font=O38, fill=pc)
                    
                    # 底部信息区
                    d.rectangle([sx, sy + item_w, sx + item_w, sy + item_h], fill=(255, 255, 255, 5))
                    d.line([(sx, sy + item_w), (sx + item_w, sy + item_w)], fill=(255, 255, 255, 12), width=1)
                    
                    name_w = int(F16.getlength(star["name"]))
                    draw_text_mixed(d, (sx + (item_w - name_w)//2, sy + item_w + 10), star["name"], cn_font=F16, en_font=F16, fill=(238, 238, 238, 255))

        y += ph + 40
        
    # === Footer ===
    d.line([(PAD, y), (W - PAD, y)], fill=(255, 255, 255, 25), width=1)
    y += 20
    draw_text_mixed(d, (W - PAD - 480, y + 12), "Endfield Gacha Record Analysis Module // Ver 1.0", cn_font=M12, en_font=M12, fill=C_SUBTEXT)
    
    if data["end_logo"]:
        try:
            logo = _b64_img(data["end_logo"])
            lh = 40
            lw = int(logo.width * (lh / logo.height))
            logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
            
            # 模拟 opacity 0.8
            logo.putalpha(ImageChops.multiply(logo.split()[3], Image.new("L", (lw, lh), 204)))
            canvas.alpha_composite(logo, (W - PAD - lw, y))
        except Exception: pass

    # 最终输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()