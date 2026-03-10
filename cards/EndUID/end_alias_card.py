# 明日方舟：终末地 角色别名卡片渲染器 (PIL 版)

from __future__ import annotations

from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# 从 __init__.py 导入字体与工具函数
from . import (
    F12, F16, F32, M12, M16, M32,
    O12, O16, O32,
    get_font, draw_text_mixed, _b64_img, _b64_fit, _round_mask
)

# 画布基础属性 (宽度固定，高度自适应)
W = 600
PAD = 25
C_BG = (15, 17, 21, 255)
C_GOLD = (212, 177, 99, 255)
C_WHITE = (255, 255, 255, 255)


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg_url": "",
        "logo_url": "",
        "avatar_url": "",
        "char_name": "未知角色",
        "alias_list": []
    }

    bg = soup.select_one(".bg-image")
    if bg: data["bg_url"] = bg.get("src", "")
    
    logo = soup.select_one(".logo")
    if logo: data["logo_url"] = logo.get("src", "")
    
    avatar = soup.select_one(".avatar")
    if avatar: data["avatar_url"] = avatar.get("src", "")
    
    name_el = soup.select_one(".char-name")
    if name_el: data["char_name"] = name_el.get_text(strip=True)
    
    for item in soup.select(".alias-item"):
        text = item.get_text(strip=True)
        if text: data["alias_list"].append(text)
        
    return data


def draw_alias_grid(d: ImageDraw.ImageDraw, items: list[str], start_x: int, start_y: int, max_w: int) -> int:
    """
    流式布局绘制别名标签，自动换行。
    返回绘制完成后的总高度。
    """
    x, y = start_x, start_y
    line_h = 32
    gap_x, gap_y = 8, 8
    
    for i, alias in enumerate(items):
        # 估算文字宽度 (这里统一用 F16，如果有纯英文可用 M16 精确计算)
        text_w = int(F16.getlength(alias))
        item_w = text_w + 28  # 左右 padding 14*2
        item_h = line_h
        
        # 换行判断
        if x + item_w > start_x + max_w:
            x = start_x
            y += item_h + gap_y
            
        # 第一个标签高亮样式
        if i == 0:
            bg_c = (212, 177, 99, 38)   # rgba(212, 177, 99, 0.15)
            border_c = (212, 177, 99, 102) # rgba(212, 177, 99, 0.4)
            text_c = (255, 255, 255, 255)
        else:
            bg_c = (255, 255, 255, 20)  # rgba(255, 255, 255, 0.08)
            border_c = (255, 255, 255, 25) # rgba(255, 255, 255, 0.1)
            text_c = (238, 238, 238, 255)  # #eee
            
        d.rounded_rectangle([x, y, x + item_w, y + item_h], radius=6, fill=bg_c, outline=border_c, width=1)
        # 文字微调居中
        draw_text_mixed(d, (x + 14, y + 5), alias, cn_font=F16, en_font=M16, fill=text_c, dy_cn=-1)
        
        x += item_w + gap_x
        
    return y + line_h - start_y


def render(html: str) -> bytes:
    data = parse_html(html)
    
    # --- 1. 预计算高度 ---
    # 模拟一个 ImageDraw 去测算别名网格的高度
    temp_img = Image.new("RGBA", (1, 1))
    temp_d = ImageDraw.Draw(temp_img)
    grid_start_y = 0
    grid_max_w = W - PAD * 2 - 50 # 减去主卡片内边距 25*2
    grid_h = draw_alias_grid(temp_d, data["alias_list"], 0, grid_start_y, grid_max_w)
    
    header_h = 120 # padding 20*2 + avatar 80
    body_pad_top = 20
    body_pad_bot = 20
    label_h = 14 + 12 # 标签高度 + margin-bottom 12
    
    main_card_h = header_h + body_pad_top + label_h + grid_h + body_pad_bot
    total_h = PAD + main_card_h + PAD
    total_h = max(total_h, 300) # 给个最小高度保底
    
    # --- 2. 创建画布与底层背景 ---
    canvas = Image.new("RGBA", (W, total_h), C_BG)
    if data["bg_url"]:
        try:
            bg_img = _b64_fit(data["bg_url"], W, total_h)
            canvas.alpha_composite(bg_img)
            # 背景全局压暗层
            dark_layer = Image.new("RGBA", (W, total_h), (0, 0, 0, 102))
            canvas.alpha_composite(dark_layer)
        except Exception: pass
        
    d = ImageDraw.Draw(canvas)
    
    # Logo
    if data["logo_url"]:
        try:
            logo = _b64_img(data["logo_url"])
            lw = 140
            lh = int(logo.height * (lw / logo.width))
            logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
            canvas.alpha_composite(logo, (W - PAD - lw, PAD))
        except Exception: pass

    # --- 3. 绘制主卡片 (Main Card) ---
    mc_x, mc_y = PAD, PAD
    mc_w = W - PAD * 2
    
    # 毛玻璃背景底色
    mc_bg = Image.new("RGBA", (mc_w, main_card_h), (30, 34, 42, 153))
    mc_mask = Image.new("L", (mc_w, main_card_h), 0)
    ImageDraw.Draw(mc_mask).rounded_rectangle([0, 0, mc_w, main_card_h], radius=16, fill=255)
    
    mc_layer = Image.new("RGBA", (W, total_h), (0,0,0,0))
    mc_layer.paste(mc_bg, (mc_x, mc_y), mc_mask)
    canvas.alpha_composite(mc_layer)
    
    # 卡片边框
    d.rounded_rectangle([mc_x, mc_y, mc_x + mc_w, mc_y + main_card_h], radius=16, outline=(255, 255, 255, 25), width=1)
    
    # 顶部金线
    d.line([(mc_x + mc_w//2 - 100, mc_y + 1), (mc_x + mc_w//2 + 100, mc_y + 1)], fill=(212, 177, 99, 204), width=3)

    # --- 4. Header ---
    hx, hy = mc_x, mc_y
    # Header 渐变模拟 (简单用半透色块替代)
    d.rounded_rectangle([hx, hy, hx + mc_w, hy + header_h], radius=16, fill=(255, 255, 255, 12))
    d.line([(hx, hy + header_h - 1), (hx + mc_w, hy + header_h - 1)], fill=(255, 255, 255, 20), width=1)
    
    # Avatar
    ax, ay = hx + 25, hy + 20
    aw = 80
    d.ellipse([ax, ay, ax + aw, ay + aw], fill=(34, 34, 34, 255), outline=(212, 177, 99, 76), width=2)
    
    if data["avatar_url"]:
        try:
            av_img = _b64_fit(data["avatar_url"], aw, aw)
            av_mask = Image.new("L", (aw, aw), 0)
            ImageDraw.Draw(av_mask).ellipse([0, 0, aw, aw], fill=255)
            canvas.paste(av_img, (ax, ay), av_mask)
        except Exception: pass
        
    # Avatar 装饰环 (简单的 45度倾斜金边视觉效果)
    d.arc([ax - 4, ay - 4, ax + aw + 4, ay + aw + 4], start=225, end=315, fill=C_GOLD, width=2)
    d.arc([ax - 4, ay - 4, ax + aw + 4, ay + aw + 4], start=315, end=225+360, fill=(255, 255, 255, 25), width=1)
    
    # Header Info
    tx = ax + aw + 20
    ty = hy + 30
    draw_text_mixed(d, (tx, ty), "END FIELD", cn_font=O12, en_font=O12, fill=C_GOLD)
    draw_text_mixed(d, (tx, ty + 18), data["char_name"], cn_font=F32, en_font=O32, fill=C_WHITE)

    # --- 5. Content Body ---
    bx, by = mc_x, hy + header_h
    # Body 背景色
    body_bg = Image.new("RGBA", (mc_w, main_card_h - header_h), (0, 0, 0, 51))
    # 为 body 底部制作带圆角的 mask，防止颜色溢出卡片圆角
    body_mask = Image.new("L", (mc_w, main_card_h - header_h), 0)
    ImageDraw.Draw(body_mask).rounded_rectangle([0, -16, mc_w, main_card_h - header_h], radius=16, fill=255)
    
    body_layer = Image.new("RGBA", (W, total_h), (0,0,0,0))
    body_layer.paste(body_bg, (bx, by), body_mask)
    canvas.alpha_composite(body_layer)
    
    # 标签 (ALIASES)
    lx, ly = bx + 25, by + 20
    d.rectangle([lx, ly + 2, lx + 3, ly + 16], fill=C_GOLD)
    draw_text_mixed(d, (lx + 11, ly), "ALIASES", cn_font=M12, en_font=M12, fill=(170, 170, 170, 255))
    
    # 网格
    draw_alias_grid(d, data["alias_list"], lx, ly + label_h, grid_max_w)

    # --- 输出 ---
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()