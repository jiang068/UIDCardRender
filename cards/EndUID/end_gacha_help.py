# 明日方舟：终末地 抽卡帮助卡片渲染器 (PIL 版)

from __future__ import annotations

import math
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 避免循环导入，直接引入工具函数并局部生成字体
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit,
    F12, F14, F16, F20, F36,
    M12, M13, M14, M15, M16
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
C_BORDER = (255, 255, 255, 38) # rgba(255,255,255,0.15)


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "bg_url": "", "end_logo": "",
        "prefix": "end",
    }
    
    bg_el = soup.select_one(".bg-layer img")
    if bg_el: data["bg_url"] = bg_el.get("src", "")
        
    logo_el = soup.select_one(".ef-logo")
    if logo_el: data["end_logo"] = logo_el.get("src", "")
        
    # 从代码块推断出 prefix 变量 (比如 "end导入抽卡记录" 取前缀 "end")
    cmd_example = soup.select_one(".code-block")
    if cmd_example:
        text = cmd_example.get_text(strip=True)
        if "导入抽卡记录" in text:
            data["prefix"] = text.split("导入抽卡记录")[0].strip()

    return data


def draw_bg(canvas: Image.Image, w: int, h: int, bg_src: str):
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
    
    if bg_src:
        try:
            bg_img = _b64_fit(bg_src, w, h).convert("RGBA")
            bg_img.putalpha(Image.new("L", (w, h), 25)) # opacity 0.1 
            canvas.alpha_composite(bg_img)
        except Exception: pass

    # 网格掩码
    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    grid_c = (38, 39, 44, 180)
    for x in range(0, w, 50): gd.line([(x, 0), (x, h)], fill=grid_c, width=1)
    for y in range(0, h, 50): gd.line([(0, y), (w, y)], fill=grid_c, width=1)
    
    mask = Image.new("L", (w, h), 255)
    md = ImageDraw.Draw(mask)
    fade_h = int(h * 0.3)
    for y in range(fade_h, h):
        alpha = int(255 * (1 - min((y - fade_h) / (h * 0.7), 1.0)))
        md.line([(0, y), (w, y)], fill=alpha)
    grid.putalpha(mask)
    canvas.alpha_composite(grid)


def render(html: str) -> bytes:
    data = parse_html(html)
    prefix = data["prefix"]
    
    # 扩大整体画布高度以容纳修复后的行距
    H = 1040
    canvas = Image.new("RGBA", (W, H), C_BG)
    draw_bg(canvas, W, H, data["bg_url"])
    d = ImageDraw.Draw(canvas)
    
    y = PAD
    
    # ================== Title Area ==================
    d.polygon([(PAD, y), (PAD + 6, y), (PAD + 3, y + 40), (PAD - 3, y + 40)], fill=C_ACCENT)
    draw_text_mixed(d, (PAD + 20, y + 2), "抽卡记录帮助", cn_font=F36, en_font=F36, fill=C_TEXT)
    title_w = int(F36.getlength("抽卡记录帮助"))
    # 英文减小字号对齐
    draw_text_mixed(d, (PAD + 20 + title_w + 10, y + 22), "// HELP GUIDE", cn_font=F14, en_font=M12, fill=C_SUBTEXT)
    y += 40 + 25
    
    def draw_section_bg(sx, sy, sh, border_left_color=None):
        sec = Image.new("RGBA", (INNER_W, sh), (255, 255, 255, 8))
        canvas.alpha_composite(sec, (sx, sy))
        d.rectangle([sx, sy, sx + INNER_W, sy + sh], outline=C_BORDER, width=1)
        if border_left_color:
            d.line([(sx, sy), (sx, sy + sh)], fill=border_left_color, width=3)
        d.line([(sx + INNER_W - 15, sy), (sx + INNER_W, sy)], fill=C_ACCENT, width=2)
        d.line([(sx + INNER_W, sy), (sx + INNER_W, sy + 15)], fill=C_ACCENT, width=2)

    # ================== STEP 01 ==================
    sec1_h = 400 # 增加高度避免内部元素拥挤
    draw_section_bg(PAD, y, sec1_h)
    draw_text_mixed(d, (PAD + 20, y + 20), ">> STEP 01: 获取数据", cn_font=F20, en_font=M16, fill=C_ACCENT)
    
    # 增加间距以防和 Tab 标签重叠 (从 55 增加到 80)
    sy = y + 80
    
    # General Tab
    pg_y = sy
    d.rectangle([PAD + 20, pg_y, W - PAD - 20, pg_y + 90], fill=(0, 0, 0, 51), outline=(255, 255, 255, 25), width=1)
    
    lx = PAD + 15
    d.polygon([(lx, pg_y), (lx + 160, pg_y), (lx + 155, pg_y - 25), (lx - 5, pg_y - 25)], fill=C_TEXT)
    draw_text_mixed(d, (lx + 5, pg_y - 20), "PLATFORM :: GENERAL", cn_font=F12, en_font=M12, fill=(0,0,0,255))
    
    py = pg_y + 15
    d.rectangle([PAD + 35, py, W - PAD - 35, py + 60], fill=(255, 230, 0, 12), outline=(255, 230, 0, 51), width=1)
    draw_text_mixed(d, (PAD + 50, py + 12), "方式一：自动获取", cn_font=F16, en_font=M14, fill=C_ACCENT)
    draw_text_mixed(d, (PAD + 185, py + 15), "// LOGGED-IN USERS", cn_font=F12, en_font=M12, fill=C_SUBTEXT)
    d.line([(PAD + 50, py + 35), (W - PAD - 50, py + 35)], fill=(255, 230, 0, 51), width=1)
    
    draw_text_mixed(d, (PAD + 50, py + 42), "如果已登录，无需提取链接，直接发送指令即可：", cn_font=F14, en_font=M12, fill=(221, 221, 221, 255))
    code_text1 = f"{prefix}导入抽卡记录"
    # 使用 F16 而不是 M15 来测量长度，避免中文算错宽度
    code1_w = int(F16.getlength(code_text1))
    d.rectangle([PAD + 350, py + 40, PAD + 350 + code1_w + 20, py + 65], fill=(0,0,0,255), outline=(51,51,51,255))
    d.line([(PAD + 350, py + 40), (PAD + 350, py + 65)], fill=C_ACCENT, width=3)
    # cn_font 强制换回支持中文的 F16
    draw_text_mixed(d, (PAD + 360, py + 43), code_text1, cn_font=F16, en_font=M14, fill=(221, 221, 221, 255))

    sy += 90 + 40
    
    # PC Tab
    pg_y = sy
    d.rectangle([PAD + 20, pg_y, W - PAD - 20, pg_y + 160], fill=(0, 0, 0, 51), outline=(255, 255, 255, 25), width=1)
    d.polygon([(lx, pg_y), (lx + 120, pg_y), (lx + 115, pg_y - 25), (lx - 5, pg_y - 25)], fill=C_TEXT)
    draw_text_mixed(d, (lx + 10, pg_y - 20), "PLATFORM :: PC", cn_font=F12, en_font=M12, fill=(0,0,0,255))
    
    col_y = pg_y + 15
    col_w1 = 360
    col_w2 = INNER_W - 40 - col_w1 - 15
    cx1 = PAD + 35
    cx2 = PAD + 35 + col_w1 + 15
    
    # 工具方式
    d.rectangle([cx1, col_y, cx1 + col_w1, col_y + 130], fill=(255, 255, 255, 5), outline=(255, 255, 255, 25))
    draw_text_mixed(d, (cx1 + 15, col_y + 12), "方式二：使用工具", cn_font=F16, en_font=M14, fill=C_TEXT)
    draw_text_mixed(d, (cx1 + 150, col_y + 15), "// TOOL", cn_font=F12, en_font=M12, fill=C_SUBTEXT)
    d.line([(cx1 + 15, col_y + 35), (cx1 + col_w1 - 15, col_y + 35)], fill=(255, 255, 255, 25), width=1)
    
    d.rectangle([cx1 + 15, col_y + 50, cx1 + 35, col_y + 68], fill=(255, 230, 0, 25))
    draw_text_mixed(d, (cx1 + 18, col_y + 52), "01", cn_font=F14, en_font=M12, fill=C_ACCENT)
    draw_text_mixed(d, (cx1 + 45, col_y + 51), "发送", cn_font=F14, en_font=M12, fill=(204, 204, 204, 255))
    
    cmd_tool = f"{prefix}抽卡工具"
    cmd_tool_w = int(F14.getlength(cmd_tool))
    draw_text_mixed(d, (cx1 + 75, col_y + 52), cmd_tool, cn_font=F14, en_font=M12, fill=C_ACCENT)
    draw_text_mixed(d, (cx1 + 75 + cmd_tool_w + 5, col_y + 51), "获取工具。", cn_font=F14, en_font=M12, fill=(204, 204, 204, 255))
    
    d.rectangle([cx1 + 15, col_y + 80, cx1 + 35, col_y + 98], fill=(255, 230, 0, 25))
    draw_text_mixed(d, (cx1 + 18, col_y + 82), "02", cn_font=F14, en_font=M12, fill=C_ACCENT)
    draw_text_mixed(d, (cx1 + 45, col_y + 81), "游戏内打开 寻访记录，运行工具提取。", cn_font=F14, en_font=M12, fill=(204, 204, 204, 255))
    
    # 手动方式
    d.rectangle([cx2, col_y, cx2 + col_w2, col_y + 130], fill=(255, 255, 255, 5), outline=(255, 255, 255, 25))
    draw_text_mixed(d, (cx2 + 15, col_y + 12), "方式三：手动获取", cn_font=F16, en_font=M14, fill=C_TEXT)
    draw_text_mixed(d, (cx2 + 150, col_y + 15), "// MANUAL", cn_font=F12, en_font=M12, fill=C_SUBTEXT)
    d.line([(cx2 + 15, col_y + 35), (cx2 + col_w2 - 15, col_y + 35)], fill=(255, 255, 255, 25), width=1)
    
    d.rectangle([cx2 + 15, col_y + 45, cx2 + 35, col_y + 63], fill=(255, 230, 0, 25))
    draw_text_mixed(d, (cx2 + 18, col_y + 47), "01", cn_font=F14, en_font=M12, fill=C_ACCENT)
    draw_text_mixed(d, (cx2 + 45, col_y + 46), "游戏内打开 寻访记录 页面。", cn_font=F14, en_font=M12, fill=(204, 204, 204, 255))
    
    d.rectangle([cx2 + 15, col_y + 70, cx2 + 35, col_y + 88], fill=(255, 230, 0, 25))
    draw_text_mixed(d, (cx2 + 18, col_y + 72), "02", cn_font=F14, en_font=M12, fill=C_ACCENT)
    draw_text_mixed(d, (cx2 + 45, col_y + 71), "打开日志：", cn_font=F14, en_font=M12, fill=(204, 204, 204, 255))
    draw_text_mixed(d, (cx2 + 115, col_y + 72), r"%USERPROFILE%\AppData\...", cn_font=F14, en_font=M12, fill=C_ACCENT)
    
    d.rectangle([cx2 + 15, col_y + 95, cx2 + 35, col_y + 113], fill=(255, 230, 0, 25))
    draw_text_mixed(d, (cx2 + 18, col_y + 97), "03", cn_font=F14, en_font=M12, fill=C_ACCENT)
    draw_text_mixed(d, (cx2 + 45, col_y + 96), "搜索 gacha_char 并复制整条链接。", cn_font=F14, en_font=M12, fill=(204, 204, 204, 255))

    y += sec1_h + 20
    
    # ================== STEP 02 ==================
    sec2_h = 100
    draw_section_bg(PAD, y, sec2_h, border_left_color=C_ACCENT)
    draw_text_mixed(d, (PAD + 20, y + 15), ">> STEP 02: 执行导入", cn_font=F20, en_font=M16, fill=C_ACCENT)
    
    draw_text_mixed(d, (PAD + 40, y + 45), "获得链接后（方式二/三），发送以下命令进行同步：", cn_font=F14, en_font=M12, fill=(204, 204, 204, 255))
    code_text2 = f"{prefix}导入抽卡记录 <粘贴链接>"
    code2_w = int(F16.getlength(code_text2))
    d.rectangle([PAD + 40, y + 65, PAD + 40 + code2_w + 20, y + 95], fill=(0,0,0,255), outline=(51,51,51,255))
    d.line([(PAD + 40, y + 65), (PAD + 40, y + 95)], fill=C_ACCENT, width=3)
    # cn_font 强制换回支持中文的 F16
    draw_text_mixed(d, (PAD + 50, y + 69), code_text2, cn_font=F16, en_font=M14, fill=(221, 221, 221, 255))
    
    y += sec2_h + 20

    # ================== CMD Table ==================
    sec3_h = 260 # 增加高度适配行数
    draw_section_bg(PAD, y, sec3_h)
    draw_text_mixed(d, (PAD + 20, y + 20), ">> 指令列表", cn_font=F20, en_font=M16, fill=C_ACCENT)
    
    ty = y + 55
    tx1 = PAD + 25
    tx2 = PAD + INNER_W // 2
    
    # Table Header
    draw_text_mixed(d, (tx1, ty), "COMMAND // 指令", cn_font=F14, en_font=M12, fill=C_SUBTEXT)
    draw_text_mixed(d, (tx2, ty), "DESCRIPTION // 说明", cn_font=F14, en_font=M12, fill=C_SUBTEXT)
    d.line([(tx1, ty + 25), (PAD + INNER_W - 25, ty + 25)], fill=C_ACCENT, width=2)
    
    # Table Rows
    cmds = [
        (f"{prefix}抽卡帮助", "查看此帮助页面"),
        (f"{prefix}导入抽卡记录 [链接]", "同步抽卡数据"),
        (f"{prefix}抽卡记录", "生成统计分析卡片"),
        (f"{prefix}导出/删除抽卡记录", "导出 JSON 或 清空记录"),
        (f"{prefix}抽卡工具", "获取 Windows 链接提取工具")
    ]
    
    ry = ty + 35
    for cmd, desc in cmds:
        # cn_font 换回 F16/F14，解决某某某用了英文字体显示错误的问题
        draw_text_mixed(d, (tx1, ry + 2), cmd, cn_font=F16, en_font=M14, fill=C_TEXT)
        draw_text_mixed(d, (tx2, ry + 2), desc, cn_font=F14, en_font=M12, fill=(170, 170, 170, 255))
        d.line([(tx1, ry + 30), (PAD + INNER_W - 25, ry + 30)], fill=(255, 255, 255, 12), width=1)
        ry += 32
        
    y += sec3_h + 20

    # ================== Note & Footer ==================
    d.rectangle([PAD, y, PAD + INNER_W, y + 60], fill=(255, 230, 0, 12))
    d.line([(PAD, y), (PAD, y + 60)], fill=C_SUBTEXT, width=3)
    draw_text_mixed(d, (PAD + 15, y + 10), "TIP:", cn_font=F14, en_font=M12, fill=C_TEXT)
    draw_text_mixed(d, (PAD + 55, y + 9), "提取的抽卡链接具有时效性，超时请重新打开游戏记录页刷新。", cn_font=F14, en_font=M12, fill=C_SUBTEXT)
    draw_text_mixed(d, (PAD + 55, y + 31), "每次导入操作会自动与现有数据进行合并，不会导致旧数据丢失。", cn_font=F14, en_font=M12, fill=C_SUBTEXT)
    
    if data["end_logo"]:
        try:
            logo = _b64_img(data["end_logo"])
            lh = 24
            lw = int(logo.width * (lh / logo.height))
            logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
            logo.putalpha(ImageChops.multiply(logo.split()[3], Image.new("L", (lw, lh), 153)))
            canvas.alpha_composite(logo, (W - PAD - 15 - lw, y + 18))
        except Exception: pass
        
    y += 60 + 20
    
    d.line([(PAD, y), (W - PAD, y)], fill=(255, 255, 255, 25), width=1)
    y += 10
    draw_text_mixed(d, (W - PAD - 330, y + 5), "Endfield Gacha Record // Help Module", cn_font=F12, en_font=M12, fill=C_SUBTEXT)

    # 最终输出
    out_rgb = Image.new("RGB", canvas.size, C_BG[:3])
    out_rgb.paste(canvas, mask=canvas.split()[3])
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()