# 战双幻痛囚笼 卡片渲染器 (PIL 极致性能榨干版)

from __future__ import annotations

import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 从同一包内导入统一资源
from . import (
    F14, F16, F20, F22, F24, F26, F28, F30, F44,
    M14, M16, M20, M22, M24, M26, M28, M30, M44,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask
)

# --- 尺寸与颜色常量 ---
W = 1000
PAD = 40
INNER_W = W - PAD * 2  # 920

C_BG_PAGE = (226, 235, 245, 255)    # #e2ebf5
C_PRIMARY = (24, 107, 181, 255)     # #186bb5
C_TEXT_DARK = (51, 51, 51, 255)     # #333333
C_TEXT_GRAY = (102, 102, 102, 255)  # #666666
C_BG_LIGHT = (240, 246, 250, 255)   # #f0f6fa
C_BORDER = (210, 224, 235, 255)     # #d2e0eb
C_ACCENT_RED = (231, 76, 60, 255)   # #e74c3c

def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1

def _draw_rounded_rect(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, r: int, fill: tuple):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill)
    canvas.alpha_composite(block, (x0, y0))

# 【性能黑科技】：2像素插值拉伸法生成垂直渐变，耗时趋近于0
def _draw_v_gradient(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, top_rgba: tuple, bottom_rgba: tuple, r: int = 0):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    
    # 只建立 1x2 像素的微缩图
    base = Image.new("RGBA", (1, 2))
    base.putpixel((0, 0), top_rgba)
    base.putpixel((0, 1), bottom_rgba)
    
    # 强行双线性插值放大，底层 C 代码瞬间生成完美渐变
    grad = base.resize((w, h), Image.BILINEAR)
    
    if r > 0:
        mask = _round_mask(w, h, r)
        grad.putalpha(ImageChops.multiply(grad.getchannel('A'), mask))
    canvas.alpha_composite(grad, (x0, y0))

# 【性能黑科技】：2像素插值拉伸法生成水平渐变，耗时趋近于0
def _draw_h_gradient(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, left_rgba: tuple, right_rgba: tuple, r: int = 0):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    
    # 只建立 2x1 像素的微缩图
    base = Image.new("RGBA", (2, 1))
    base.putpixel((0, 0), left_rgba)
    base.putpixel((1, 0), right_rgba)
    
    # 强行双线性插值放大
    grad = base.resize((w, h), Image.BILINEAR)
    
    if r > 0:
        mask = _round_mask(w, h, r)
        grad.putalpha(ImageChops.multiply(grad.getchannel('A'), mask))
    canvas.alpha_composite(grad, (x0, y0))

# --- DOM 解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    data = {'bosses': []}

    # 背景
    bg_match = re.search(r"background-image:\s*url\(['\"]?(data:[^'\"]+)['\"]?\)", html)
    data['contentBgB64'] = bg_match.group(1) if bg_match else ""

    # Header
    h_bg = soup.select_one('.header-bg')
    data['headerBgB64'] = h_bg['src'] if h_bg and h_bg.has_attr('src') else ""
    av = soup.select_one('.avatar-img')
    data['avatarB64'] = av['src'] if av else ""
    av_box = soup.select_one('.avatar-box')
    data['avatarBoxB64'] = av_box['src'] if av_box else ""
    
    data['roleName'] = soup.select_one('.header-name').get_text(strip=True) if soup.select_one('.header-name') else ""
    data['rank'] = soup.select_one('.level-val').get_text(strip=True) if soup.select_one('.level-val') else "0"
    
    bottom_spans = soup.select('.header-row-bottom span')
    data['serverName'] = bottom_spans[0].get_text(strip=True) if len(bottom_spans)>0 else ""
    raw_id = bottom_spans[-1].get_text(strip=True) if len(bottom_spans)>2 else ""
    data['roleId'] = raw_id.replace("ID:", "").replace("ID", "").strip()

    # Title Bar
    t_bg = soup.select_one('.section-title-bar img')
    data['titleBgB64'] = t_bg['src'] if t_bg else ""

    # Summary
    a_icon = soup.select_one('.area-icon')
    data['areaIconB64'] = a_icon['src'] if a_icon else ""
    data['challengeArea'] = soup.select_one('.summary-info h2').get_text(strip=True) if soup.select_one('.summary-info h2') else ""
    data['challengeLevel'] = soup.select_one('.summary-info p').get_text(strip=True).replace("等级:", "").strip() if soup.select_one('.summary-info p') else ""
    
    stats = soup.select('.summary-stats .score-hl')
    data['totalPoint'] = stats[0].get_text(strip=True) if len(stats)>0 else "0"
    data['totalChallengeTimes'] = stats[1].get_text(strip=True) if len(stats)>1 else "0"

    # Boss Groups
    for bg in soup.select('.boss-group'):
        boss = {'weaknesses': [], 'stages': []}
        
        b_avatar = bg.select_one('.boss-avatar img')
        boss['iconB64'] = b_avatar['src'] if b_avatar else ""
        boss['name'] = bg.select_one('.boss-name').get_text(strip=True) if bg.select_one('.boss-name') else ""
        boss['totalPoint'] = bg.select_one('.boss-total-score span').get_text(strip=True) if bg.select_one('.boss-total-score span') else "0"

        for w_row in bg.select('.weakness-row'):
            for w_name, w_icon in zip(w_row.select('.weakness-name'), w_row.select('.weakness-icon')):
                boss['weaknesses'].append({
                    'name': w_name.get_text(strip=True),
                    'iconB64': w_icon['src'] if w_icon else ""
                })

        for st in bg.select('.stage-item'):
            stage = {'team': []}
            stage['stageName'] = st.select_one('.stage-difficulty').get_text(strip=True) if st.select_one('.stage-difficulty') else ""
            
            s_vals = st.select('.stage-details .val')
            stage['point'] = s_vals[0].get_text(strip=True) if len(s_vals)>0 else "0"
            
            time_text = s_vals[1].parent.get_text(strip=True) if len(s_vals)>1 else ""
            stage['autoFight'] = "自动" in time_text
            stage['fightTime'] = re.sub(r'[^\d]', '', s_vals[1].get_text(strip=True)) if len(s_vals)>1 else "0"

            for av_card in st.select('.avatar-card'):
                c_img = av_card.select_one('img')
                c_grade = av_card.select_one('.avatar-grade')
                is_plus = av_card.select_one('.plus-mark') is not None
                
                grade_class = 'none'
                if c_grade:
                    cls = c_grade.get('class', [])
                    if 'grade-sss-plus' in cls: grade_class = 'sss-plus'
                    elif 'grade-sss' in cls: grade_class = 'sss'
                    elif 'grade-ss' in cls: grade_class = 'ss'
                
                stage['team'].append({
                    'iconB64': c_img['src'] if c_img else "",
                    'gradeDisplay': c_grade.get_text(strip=True).replace("+", "") if c_grade else "",
                    'isPlus': is_plus,
                    'gradeClass': grade_class
                })
            boss['stages'].append(stage)

        data['bosses'].append(boss)

    return data


# --- 主渲染逻辑 ---
def render(html: str) -> bytes:
    data = parse_html(html)
    
    MAX_H = 6000
    canvas = Image.new("RGBA", (W, MAX_H), C_BG_PAGE)
    if data['contentBgB64']:
        try:
            bg_img = _b64_img(data['contentBgB64'])
            bg_img = ImageOps.fit(bg_img, (W, MAX_H), Image.LANCZOS)
            canvas.alpha_composite(bg_img)
        except: pass

    d = ImageDraw.Draw(canvas)
    y = PAD

    # --- Header ---
    H_H = 200
    h_img = Image.new("RGBA", (INNER_W, H_H), (0,0,0,0))
    hd = ImageDraw.Draw(h_img)
    
    _draw_rounded_rect(h_img, 0, 0, INNER_W, H_H, 8, (20,25,35,255))
    if data['headerBgB64']:
        try:
            hbg = _b64_fit(data['headerBgB64'], INNER_W, H_H)
            h_img.paste(hbg, (0,0), _round_mask(INNER_W, H_H, 8))
        except: pass

    av_w, av_h = 170, 170
    av_x, av_y = 30, (H_H - av_h)//2
    
    # 头像框底层
    if data['avatarBoxB64']:
        try:
            abox = _b64_fit(data['avatarBoxB64'], av_w, av_h)
            h_img.alpha_composite(abox, (av_x, av_y))
        except: pass

    # 头像顶层
    if data['avatarB64']:
        try:
            aimg = _b64_fit(data['avatarB64'], 120, 120)
            cmask = Image.new("L", (120, 120), 0)
            ImageDraw.Draw(cmask).ellipse([0,0,119,119], fill=255)
            h_img.paste(aimg, (av_x + 25, av_y + 25), cmask)
        except: pass

    info_x = av_x + av_w + 20
    draw_text_mixed(hd, (info_x, av_y + 20), data['roleName'], cn_font=F44, en_font=M44, fill=(255,255,255,255))
    name_w = int(F44.getlength(data['roleName']))
    
    rank_x = info_x + name_w + 16
    rank_val = data['rank']
    val_w = int(F22.getlength(rank_val))
    box_w = 64 + val_w + 14 
    
    _draw_rounded_rect(h_img, rank_x, av_y + 30, rank_x + box_w, av_y + 65, 4, (25,30,40,204))
    hd.rounded_rectangle([rank_x, av_y + 30, rank_x + box_w, av_y + 65], radius=4, outline=(80,100,120,153), width=1)
    draw_text_mixed(hd, (rank_x + 14, av_y + 30 + _ty(F22, "勋阶", 35)), "勋阶", cn_font=F22, en_font=M22, fill=(155,174,194,255))
    draw_text_mixed(hd, (rank_x + 64, av_y + 30 + _ty(F22, rank_val, 35)), rank_val, cn_font=F22, en_font=M22, fill=(229,141,60,255))

    bottom_y = av_y + 100
    draw_text_mixed(hd, (info_x, bottom_y), data['serverName'], cn_font=F24, en_font=M24, fill=(140,158,181,255))
    sw = int(F24.getlength(data['serverName']))
    draw_text_mixed(hd, (info_x + sw + 4, bottom_y), "|", cn_font=F24, en_font=M24, fill=(74,90,117,255))
    draw_text_mixed(hd, (info_x + sw + 20, bottom_y), f"ID:{data['roleId']}", cn_font=F24, en_font=M24, fill=(140,158,181,255))

    canvas.alpha_composite(h_img, (PAD, y))
    y += H_H + 20

    # --- Title Bar ---
    T_H = 60
    # 极速渐变调用
    _draw_v_gradient(canvas, PAD, y, PAD + INNER_W, y + T_H, (24, 45, 75, 255), (15, 25, 45, 255), r=6)
    if data['titleBgB64']:
        try:
            tbg = _b64_fit(data['titleBgB64'], INNER_W, T_H)
            canvas.paste(tbg, (PAD, y), _round_mask(INNER_W, T_H, 6))
        except: pass
    draw_text_mixed(d, (PAD + 24, y + _ty(F26, "幻痛囚笼", T_H)), "幻痛囚笼", cn_font=F26, en_font=M26, fill=(255,255,255,255))
    y += T_H + 20

    # --- Summary ---
    S_H = 120
    _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + S_H, 6, C_BG_LIGHT)
    d.rounded_rectangle([PAD, y, PAD + INNER_W, y + S_H], radius=6, outline=C_BORDER, width=1)
    
    if data['areaIconB64']:
        try:
            a_icon = _b64_fit(data['areaIconB64'], 60, 70)
            canvas.alpha_composite(a_icon, (PAD + 34, y + (S_H - 70)//2))
        except: pass
    
    draw_text_mixed(d, (PAD + 118, y + 30), data['challengeArea'], cn_font=F30, en_font=M30, fill=C_TEXT_DARK)
    draw_text_mixed(d, (PAD + 118, y + 68), f"等级: {data['challengeLevel']}", cn_font=F20, en_font=M20, fill=C_TEXT_GRAY)

    rw = int(F28.getlength(data['totalChallengeTimes']))
    draw_text_mixed(d, (PAD + INNER_W - 34 - rw, y + 68), data['totalChallengeTimes'], cn_font=F28, en_font=M28, fill=C_PRIMARY)
    draw_text_mixed(d, (PAD + INNER_W - 34 - rw - 110, y + 72), "挑战次数: ", cn_font=F22, en_font=M22, fill=C_TEXT_GRAY)

    rw2 = int(F28.getlength(data['totalPoint']))
    draw_text_mixed(d, (PAD + INNER_W - 34 - rw2, y + 26), data['totalPoint'], cn_font=F28, en_font=M28, fill=C_PRIMARY)
    draw_text_mixed(d, (PAD + INNER_W - 34 - rw2 - 110, y + 30), "讨伐总值: ", cn_font=F22, en_font=M22, fill=C_TEXT_GRAY)
    y += S_H + 20

    # --- Boss Groups ---
    for boss in data['bosses']:
        b_img = Image.new("RGBA", (INNER_W, 2000), (0,0,0,0))
        bd = ImageDraw.Draw(b_img)

        # Boss Header
        BH_H = 160
        _draw_rounded_rect(b_img, 0, 0, INNER_W, BH_H, 0, C_BG_LIGHT)
        
        if boss['iconB64']:
            try:
                b_icon = _b64_fit(boss['iconB64'], 306, 160)
                b_img.paste(b_icon, (0, 0))
                # 极速横向渐变羽化效果 (左透明，右底色)
                _draw_h_gradient(b_img, 153, 0, 306, 160, (240, 246, 250, 0), (240, 246, 250, 255))
            except: pass
            
        bd.rectangle([0, BH_H - 3, INNER_W, BH_H], fill=C_PRIMARY)

        # 右侧对齐文字排版
        name_w = int(F28.getlength(boss['name']))
        draw_text_mixed(bd, (INNER_W - 24 - name_w, 24), boss['name'], cn_font=F28, en_font=M28, fill=C_TEXT_DARK)
        
        score_w = int(F26.getlength(boss['totalPoint']))
        lbl_w = int(F20.getlength("讨伐总值: "))
        tx = INNER_W - 24 - score_w
        draw_text_mixed(bd, (tx, 66), boss['totalPoint'], cn_font=F26, en_font=M26, fill=C_PRIMARY)
        draw_text_mixed(bd, (tx - lbl_w, 70), "讨伐总值: ", cn_font=F20, en_font=M20, fill=C_TEXT_GRAY)
        
        if boss['weaknesses']:
            # 动态计算总宽度，确保整体靠右对齐
            w_total_w = 0
            for w in boss['weaknesses']:
                w_total_w += 24 + 6 + int(F16.getlength(w['name'])) + 12
            w_total_w -= 12 
            
            wx = INNER_W - 24 - w_total_w
            for w in boss['weaknesses']:
                if w['iconB64']:
                    try:
                        w_icon = _b64_fit(w['iconB64'], 24, 24)
                        b_img.alpha_composite(w_icon, (wx, 108))
                    except: pass
                draw_text_mixed(bd, (wx + 30, 110), w['name'], cn_font=F16, en_font=M16, fill=C_TEXT_GRAY)
                wx += 24 + 6 + int(F16.getlength(w['name'])) + 12

        by = BH_H
        
        # Stages Items
        for idx, stage in enumerate(boss['stages']):
            ST_H = 142
            _draw_rounded_rect(b_img, 0, by, INNER_W, by + ST_H, 0, (255, 255, 255, 255))
            if idx < len(boss['stages']) - 1:
                bd.line([(0, by + ST_H - 1), (INNER_W, by + ST_H - 1)], fill=(238, 238, 238, 255), width=1)
            
            # 难度方块
            _draw_rounded_rect(b_img, 20, by + 16, 130, by + 126, 4, (93, 103, 115, 255))
            tw = int(F26.getlength(stage['stageName']))
            draw_text_mixed(bd, (20 + (110 - tw)//2, by + 16 + _ty(F26, stage['stageName'], 110)), stage['stageName'], cn_font=F26, en_font=M26, fill=(255, 255, 255, 255))
            
            # 数据详情
            draw_text_mixed(bd, (154, by + 34), "讨伐值: ", cn_font=F24, en_font=M24, fill=C_TEXT_GRAY)
            draw_text_mixed(bd, (154 + int(F24.getlength("讨伐值: ")), by + 30), stage['point'], cn_font=F28, en_font=M28, fill=C_PRIMARY)
            
            draw_text_mixed(bd, (154, by + 76), "耗时: ", cn_font=F24, en_font=M24, fill=C_TEXT_GRAY)
            time_w = int(F28.getlength(f"{stage['fightTime']}S"))
            draw_text_mixed(bd, (154 + int(F24.getlength("耗时: ")), by + 72), f"{stage['fightTime']}S", cn_font=F28, en_font=M28, fill=C_PRIMARY)
            
            if stage['autoFight']:
                draw_text_mixed(bd, (154 + int(F24.getlength("耗时: ")) + time_w + 4, by + 76), " · 自动", cn_font=F24, en_font=M24, fill=C_TEXT_GRAY)

            # 队伍卡片（向左排列，右对齐）
            tx = INNER_W - 20
            for char in reversed(stage['team']):
                tx -= 140
                _draw_rounded_rect(b_img, tx, by + 16, tx + 140, by + 156, 4, (240, 240, 240, 255))
                if char['iconB64']:
                    try:
                        c_img = _b64_fit(char['iconB64'], 140, 140)
                        b_img.paste(c_img, (tx, by + 16), _round_mask(140, 140, 4))
                    except: pass
                bd.rounded_rectangle([tx, by + 16, tx + 140, by + 156], radius=4, outline=(224, 229, 235, 255), width=2)
                
                # 评级颜色
                g_col = (255, 255, 255, 255)
                if char['gradeClass'] == 'sss-plus': g_col = (255, 152, 0, 255)
                elif char['gradeClass'] == 'sss': g_col = (230, 194, 90, 255)
                elif char['gradeClass'] == 'ss': g_col = (211, 47, 47, 255)

                draw_text_mixed(bd, (tx + 6, by + 22), char['gradeDisplay'], cn_font=F20, en_font=M20, fill=g_col)
                if char['isPlus']:
                    pw = int(F20.getlength(char['gradeDisplay']))
                    draw_text_mixed(bd, (tx + 6 + pw + 2, by + 18), "+", cn_font=F14, en_font=M14, fill=g_col)
                
                tx -= 10 # 间隔
            
            by += ST_H

        # 合成大卡片
        b_final = b_img.crop((0, 0, INNER_W, by))
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + by, 6, (255, 255, 255, 255))
        canvas.paste(b_final, (PAD, y), _round_mask(INNER_W, by, 6))
        d.rounded_rectangle([PAD, y, PAD + INNER_W, y + by], radius=6, outline=C_BORDER, width=1)
        
        y += by + 20

    # 一刀裁剪，最终输出
    out_rgb = canvas.crop((0, 0, W, y + 20)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()