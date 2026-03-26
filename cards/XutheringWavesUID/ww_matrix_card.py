# cards/XutheringWavesUID/ww_matrix_card.py
from __future__ import annotations
import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageOps

from . import (
    F12, F14, F16, F18, F20, F24, F28, F30, F32, F34, F42, F46,
    M14, M16, M18, M20, M24, M28, M30, M34,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask, _is_pure_en_num
)

# --------------------------------------------------
# 绘图辅助函数
# --------------------------------------------------
def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, r: int, fill: tuple, outline: tuple = None, width: int = 1):
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(block, (x0, y0))

def _calc_mixed_w(text: str, cn_font, en_font) -> int:
    if not text: return 0
    w = 0
    for ch in str(text):
        if _is_pure_en_num(ch): w += en_font.getlength(ch)
        else: w += cn_font.getlength(ch)
    return int(w)

def _draw_h_gradient(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, left_rgba: tuple, right_rgba: tuple, r: int = 0):
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    base = Image.new("RGBA", (2, 1))
    base.putpixel((0, 0), left_rgba)
    base.putpixel((1, 0), right_rgba)
    grad = base.resize((w, h), Image.Resampling.BILINEAR)
    if r > 0:
        mask = _round_mask(w, h, r)
        grad.putalpha(ImageDraw.ImageChops.multiply(grad.getchannel('A'), mask))
    canvas.alpha_composite(grad, (x0, y0))

def parse_color(c_str: str, default=(255,255,255,255)) -> tuple:
    if not c_str: return default
    c_str = c_str.strip()
    if c_str.startswith('#'):
        c_str = c_str.lstrip('#')
        if len(c_str) == 3: c_str = ''.join(c*2 for c in c_str)
        return tuple(int(c_str[i:i+2], 16) for i in (0, 2, 4)) + (255,)
    m = re.search(r'rgba?\(([^)]+)\)', c_str)
    if m:
        parts = [p.strip() for p in m.group(1).split(',')]
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        a = int(float(parts[3]) * 255) if len(parts) >= 4 else 255
        return (r, g, b, a)
    return default

SCORE_COLORS = {
    'score-grey': (138, 138, 138, 255),
    'score-green': (76, 175, 80, 255),
    'score-white': (255, 255, 255, 255),
    'score-purple': (206, 147, 216, 255),
    'score-gold': (255, 213, 79, 255),
    'score-red': (255, 82, 82, 255),
    'score-rainbow': (255, 120, 180, 255) # 简化彩虹色为亮粉色
}

# --------------------------------------------------
# DOM 解析
# --------------------------------------------------
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    data = {'is_detail': soup.select_one('.overview-area') is not None}
    
    # 基础与头部信息
    data['bg_url'] = soup.select_one('.bg-image')['src'] if soup.select_one('.bg-image') else ""
    data['avatar_url'] = soup.select_one('.avatar')['src'] if soup.select_one('.avatar') else ""
    data['user_name'] = soup.select_one('.user-name').get_text(strip=True) if soup.select_one('.user-name') else ""
    
    uid_node = soup.select_one('.user-uid')
    data['user_id'] = uid_node.get_text(strip=True).replace('UID', '').strip() if uid_node else ""
    
    stats = soup.select('.stat-value')
    data['level'] = stats[0].get_text(strip=True) if len(stats) > 0 else "0"
    data['world_level'] = stats[1].get_text(strip=True) if len(stats) > 1 else "0"
    
    footer = soup.select_one('.footer img')
    data['footer_b64'] = footer['src'] if footer else ""

    data['modes'] = []
    
    # 提取共鸣链颜色变量 (如果有)
    style_text = soup.select_one('style').get_text() if soup.select_one('style') else ""
    chain_colors = {0: (170, 170, 170, 255)}
    for i in range(1, 7):
        m = re.search(rf'\.chain-{i}\s*\{{[^}}]*border-right-color:\s*([^;}}]+)', style_text)
        chain_colors[i] = parse_color(m.group(1)) if m else (212, 177, 99, 255)
    data['chain_colors'] = chain_colors

    # ================= 详情模式解析 =================
    if data['is_detail']:
        for sec in soup.select('.section-container'):
            mode = {'teams': []}
            mode['mode_name'] = sec.select_one('.section-title').get_text(strip=True) if sec.select_one('.section-title') else ""
            date_node = sec.select_one('.date-badge')
            mode['date'] = date_node.get_text(strip=True) if date_node else ""
            
            oa = sec.select_one('.overview-area')
            if oa:
                obg = oa.select_one('.overview-bg')
                mode['overview_bg'] = obg['src'] if obg else ""
                rimg = oa.select_one('.rank-detail-img')
                mode['rank_detail_url'] = rimg['src'] if rimg else ""
                
                score_node = oa.select_one('.score-num')
                mode['score'] = score_node.get_text(strip=True) if score_node else "0"
                mode['score_color_key'] = next((c for c in score_node.get('class', []) if c.startswith('score-')), 'score-white') if score_node else 'score-white'
                
                p_text = oa.select('.progress-text span')
                if len(p_text) >= 2:
                    mode['progress_text'] = p_text[1].get_text(strip=True)
                else:
                    mode['progress_text'] = "0/0"
                    
                p_fill = oa.select_one('.progress-bar-fill')
                if p_fill and 'width:' in p_fill.get('style', ''):
                    pct_str = re.search(r'width:\s*([\d\.]+)%', p_fill.get('style'))
                    mode['progress_pct'] = float(pct_str.group(1)) if pct_str else 0.0
                else:
                    mode['progress_pct'] = 0.0

            for tm in sec.select('.team-item'):
                team = {'roles': []}
                
                team['round'] = tm.select_one('.round-area span').get_text(strip=True) if tm.select_one('.round-area span') else "1"
                team['pass_boss'] = tm.select_one('.boss-count').get_text(strip=True) if tm.select_one('.boss-count') else "0"
                total_node = tm.select_one('.boss-total')
                team['boss_total'] = total_node.get_text(strip=True).replace('/', '') if total_node else "0"
                
                b_icon = tm.select_one('.boss-icon')
                team['boss_icon'] = b_icon['src'] if b_icon else ""
                
                bf_icon = tm.select_one('.buff-area img')
                team['buff_icon'] = bf_icon['src'] if bf_icon else ""
                
                sc_node = tm.select_one('.team-score-value')
                team['score'] = sc_node.get_text(strip=True).replace('+', '') if sc_node else "0"
                
                for rl in tm.select('.role-mini'):
                    role = {}
                    img = rl.select_one('img')
                    role['icon'] = img['src'] if img else ""
                    
                    lvl = rl.select_one('.role-mini-level')
                    role['level'] = lvl.get_text(strip=True).replace('Lv.', '') if lvl else ""
                    
                    chn = rl.select_one('.role-mini-chain')
                    if chn:
                        role['chain_name'] = chn.get_text(strip=True)
                        ck = next((c for c in chn.get('class', []) if c.startswith('chain-')), 'chain-0')
                        role['chain_idx'] = int(ck.replace('chain-', '')) if ck.replace('chain-', '').isdigit() else 0
                    else:
                        role['chain_name'] = ""
                        role['chain_idx'] = 0
                        
                    team['roles'].append(role)
                    
                mode['teams'].append(team)
            data['modes'].append(mode)

    # ================= 摘要模式解析 =================
    else:
        sc = soup.select_one('.section-container')
        if sc:
            data['main_title'] = sc.select_one('.section-title').get_text(strip=True) if sc.select_one('.section-title') else "终焉矩阵"
            date_node = sc.select_one('.date-badge')
            data['main_date'] = date_node.get_text(strip=True) if date_node else ""
            
            for row in sc.select('.mode-row'):
                mode = {}
                r_img = row.select_one('.mode-rank-img')
                mode['rank_img_url'] = r_img['src'] if r_img else ""
                
                spans = row.select('.mode-text span')
                mode['mode_name'] = spans[0].get_text(strip=True) if len(spans) > 0 else ""
                mode['score'] = spans[1].get_text(strip=True) if len(spans) > 1 else "0"
                
                rw_icon = row.select_one('.reward-icon')
                mode['reward_icon'] = rw_icon['src'] if rw_icon else ""
                
                rw_text = row.select_one('.reward-text')
                mode['reward_text'] = rw_text.get_text(strip=True) if rw_text else ""
                
                data['modes'].append(mode)

    return data


# --------------------------------------------------
# 渲染核心逻辑
# --------------------------------------------------
def render(html: str) -> bytes:
    data = parse_html(html)
    W = 1000
    PAD = 40
    INNER_W = W - PAD * 2

    # 预估高度
    H = 800
    if data['is_detail']:
        for m in data['modes']:
            H += 80 + 170 + len(m['teams']) * 120 + 40
    else:
        H += 80 + len(data['modes']) * 140 + 40
    
    canvas = Image.new("RGBA", (W, H), (15, 17, 21, 255))
    
    # 绘制全局背景图
    if data['bg_url']:
        try:
            bg_img = _b64_fit(data['bg_url'], W, H)
            canvas.alpha_composite(bg_img, (0, 0))
        except: pass
    
    # 绘制 15% 黑色遮罩
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 38))
    canvas.alpha_composite(overlay, (0, 0))
    
    d = ImageDraw.Draw(canvas)
    y = PAD

    # --- 1. 顶部用户卡片 ---
    UH = 150
    _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + UH, 16, (20, 24, 30, 230), outline=(255, 255, 255, 30))
    
    # 头像
    if data['avatar_url']:
        try:
            av_img = _b64_fit(data['avatar_url'], 100, 100)
            canvas.paste(av_img, (PAD + 40, y + 25), _round_mask(100, 100, 50))
        except: pass
        d.ellipse([PAD + 37, y + 22, PAD + 143, y + 128], outline=(42, 46, 53, 255), width=3)
    
    draw_text_mixed(d, (PAD + INNER_W - 140, y + 20), "MATRIX REPORT", F14, M14, fill=(255, 255, 255, 50))
    
    info_x = PAD + 170
    draw_text_mixed(d, (info_x, y + 25), data['user_name'], F42, M24, fill=(255, 255, 255, 255))
    nw = _calc_mixed_w(data['user_name'], F42, M24)
    
    _draw_rounded_rect(canvas, info_x + nw + 20, y + 36, info_x + nw + 20 + _calc_mixed_w(f"UID {data['user_id']}", F20, M20) + 24, y + 68, 6, (0, 0, 0, 102), outline=(212, 177, 99, 50))
    draw_text_mixed(d, (info_x + nw + 32, y + 40), f"UID {data['user_id']}", F20, M20, fill=(212, 177, 99, 255))
    
    d.line([(info_x, y + 80), (info_x + 500, y + 80)], fill=(255, 255, 255, 20), width=1)
    d.line([(info_x, y + 80), (info_x + 40, y + 80)], fill=(212, 177, 99, 255), width=2)
    
    draw_text_mixed(d, (info_x, y + 95), data['level'], F30, M30, fill=(255, 255, 255, 255))
    draw_text_mixed(d, (info_x, y + 128), "联觉等级", F12, M14, fill=(109, 113, 122, 255))
    
    draw_text_mixed(d, (info_x + 120, y + 95), data['world_level'], F30, M30, fill=(255, 255, 255, 255))
    draw_text_mixed(d, (info_x + 120, y + 128), "索拉等级", F12, M14, fill=(109, 113, 122, 255))
    
    y += UH + 30

    # --- 2. 根据模式执行对应绘制逻辑 ---
    if data['is_detail']:
        # 【详情模式】
        for mode in data['modes']:
            sy = y
            _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + 2000, 12, (15, 17, 21, 115), outline=(255, 255, 255, 15)) # 背景框预分配，后续裁剪
            
            # Header
            draw_text_mixed(d, (PAD + 20, sy + 16), mode['mode_name'], F28, M28, fill=(255, 255, 255, 255))
            tw = _calc_mixed_w(mode['mode_name'], F28, M28)
            _draw_h_gradient(canvas, PAD + 20 + tw + 16, sy + 30, PAD + INNER_W - 120, sy + 32, (212, 177, 99, 204), (212, 177, 99, 0))
            if mode['date']:
                dw = _calc_mixed_w(mode['date'], F18, M18)
                draw_text_mixed(d, (PAD + INNER_W - 20 - dw, sy + 22), mode['date'], F18, M18, fill=(136, 136, 136, 255))
            d.line([(PAD, sy + 58), (PAD + INNER_W, sy + 58)], fill=(255, 255, 255, 12), width=1)
            
            cy = sy + 68
            
            # Overview Area
            _draw_rounded_rect(canvas, PAD + 14, cy, PAD + INNER_W - 14, cy + 150, 10, (10, 14, 18, 255), outline=(43, 64, 77, 204))
            if mode['overview_bg']:
                try:
                    obg = _b64_fit(mode['overview_bg'], INNER_W - 28, 150)
                    canvas.paste(obg, (PAD + 14, cy), _round_mask(INNER_W - 28, 150, 10))
                except: pass
            
            # 遮罩
            _draw_h_gradient(canvas, PAD + 14, cy, PAD + INNER_W - 14, cy + 150, (10, 14, 18, 51), (10, 14, 18, 128), r=10)
            
            if mode['rank_detail_url']:
                try:
                    rimg = _b64_fit(mode['rank_detail_url'], 300, 300)
                    canvas.alpha_composite(rimg, (PAD + 14 - 40, cy - 75))
                except: pass
            
            score_color = SCORE_COLORS.get(mode['score_color_key'], (255, 255, 255, 255))
            sw = _calc_mixed_w(mode['score'], F46, M46) # F46 for Oslwald approximation
            draw_text_mixed(d, (PAD + INNER_W - 38 - sw, cy + 20), mode['score'], F46, M46, fill=score_color)
            lw = _calc_mixed_w("累计积分", F28, M28)
            draw_text_mixed(d, (PAD + INNER_W - 38 - sw - 10 - lw, cy + 32), "累计积分", F28, M28, fill=(255, 255, 255, 255))
            
            draw_text_mixed(d, (PAD + INNER_W - 200, cy + 90), "挑战进度", F24, M24, fill=(255, 255, 255, 255))
            pw = _calc_mixed_w(mode['progress_text'], F24, M24)
            draw_text_mixed(d, (PAD + INNER_W - 38 - pw, cy + 90), mode['progress_text'], F24, M24, fill=(255, 255, 255, 255))
            
            # 进度条
            bar_w = INNER_W - 300 - 38
            bar_x = PAD + 300
            _draw_rounded_rect(canvas, bar_x, cy + 124, bar_x + bar_w, cy + 132, 4, (50, 64, 75, 204))
            if mode['progress_pct'] > 0:
                fill_w = int(bar_w * mode['progress_pct'] / 100)
                _draw_h_gradient(canvas, bar_x, cy + 124, bar_x + fill_w, cy + 132, (212, 177, 99, 255), (255, 243, 185, 255), r=4)
            
            cy += 160
            
            # Team Items
            for team in mode['teams']:
                _draw_rounded_rect(canvas, PAD + 14, cy, PAD + INNER_W - 14, cy + 110, 8, (30, 42, 55, 165), outline=(255, 255, 255, 15))
                _draw_h_gradient(canvas, PAD + 14, cy, PAD + 17, cy + 110, (212, 177, 99, 128), (212, 177, 99, 0), r=2)
                
                # 序号
                draw_text_mixed(d, (PAD + 38, cy + 34), f"{team['round']:02d}", F34, M34, fill=(255, 255, 255, 255))
                
                # Roles
                rx = PAD + 120
                for role in team['roles']:
                    _draw_rounded_rect(canvas, rx, cy + 11, rx + 88, cy + 99, 8, (42, 46, 53, 255), outline=(255, 255, 255, 25))
                    if role['icon']:
                        try:
                            ic = _b64_fit(role['icon'], 88, 88)
                            canvas.paste(ic, (rx, cy + 11), _round_mask(88, 88, 8))
                        except: pass
                    
                    if role['level']:
                        _draw_h_gradient(canvas, rx, cy + 14, rx + 45, cy + 34, (0, 0, 0, 216), (0, 0, 0, 0))
                        d.line([(rx, cy + 14), (rx, cy + 34)], fill=(212, 177, 99, 255), width=2)
                        draw_text_mixed(d, (rx + 4, cy + 16), f"Lv.{role['level']}", F14, M14, fill=(255, 255, 255, 255))
                    
                    if role['chain_name']:
                        c_col = data['chain_colors'].get(role['chain_idx'], (170, 170, 170, 255))
                        cw = _calc_mixed_w(role['chain_name'], F14, M14)
                        _draw_h_gradient(canvas, rx + 88 - cw - 12, cy + 99 - 22, rx + 88, cy + 99 - 2, (0, 0, 0, 0), (0, 0, 0, 230))
                        d.line([(rx + 88 - 2, cy + 99 - 22), (rx + 88 - 2, cy + 99 - 2)], fill=c_col, width=2)
                        draw_text_mixed(d, (rx + 88 - cw - 6, cy + 99 - 20), role['chain_name'], F14, M14, fill=c_col)

                    rx += 98

                # Divider
                dx = PAD + INNER_W - 350
                d.line([(dx, cy + 25), (dx, cy + 85)], fill=(255, 255, 255, 25), width=2)
                
                # Buff & Boss
                if team['buff_icon']:
                    try:
                        bf = _b64_fit(team['buff_icon'], 56, 56)
                        _draw_rounded_rect(canvas, dx + 24, cy + 27, dx + 80, cy + 83, 6, (115, 140, 163, 51))
                        canvas.alpha_composite(bf, (dx + 24, cy + 27))
                    except: pass
                
                bx = dx + 105
                draw_text_mixed(d, (bx, cy + 20), f"第 {team['round']} 轮", F20, M20, fill=(255, 255, 255, 255))
                
                _draw_rounded_rect(canvas, bx, cy + 50, bx + 100, cy + 82, 16, (255, 255, 255, 30))
                if team['boss_icon']:
                    try:
                        bc = _b64_fit(team['boss_icon'], 38, 38)
                        canvas.alpha_composite(bc, (bx - 8, cy + 47))
                    except: pass
                draw_text_mixed(d, (bx + 35, cy + 52), team['pass_boss'], F20, M20, fill=(255, 255, 255, 255))
                draw_text_mixed(d, (bx + 35 + _calc_mixed_w(team['pass_boss'], F20, M20), cy + 52), f"/{team['boss_total']}", F20, M20, fill=(138, 138, 138, 255))
                
                # Score
                sc_w = _calc_mixed_w(f"+{team['score']}", F34, M34)
                draw_text_mixed(d, (PAD + INNER_W - 38 - sc_w, cy + 34), f"+{team['score']}", F34, M34, fill=(255, 255, 255, 255))

                cy += 120
            
            # 修剪当前 section 背景框
            d.line([(0,0),(0,0)], fill=0) # dummy
            y = cy + 10

    else:
        # 【摘要模式】
        if data['modes']:
            sy = y
            _draw_rounded_rect(canvas, PAD, sy, PAD + INNER_W, sy + 2000, 12, (15, 17, 21, 115), outline=(255, 255, 255, 15))
            
            # Header
            draw_text_mixed(d, (PAD + 24, sy + 16), data.get('main_title', '终焉矩阵'), F28, M28, fill=(255, 255, 255, 255))
            tw = _calc_mixed_w(data.get('main_title', '终焉矩阵'), F28, M28)
            _draw_h_gradient(canvas, PAD + 24 + tw + 16, sy + 30, PAD + INNER_W - 120, sy + 32, (212, 177, 99, 204), (212, 177, 99, 0))
            if data['main_date']:
                dw = _calc_mixed_w(data['main_date'], F18, M18)
                draw_text_mixed(d, (PAD + INNER_W - 24 - dw, sy + 22), data['main_date'], F18, M18, fill=(136, 136, 136, 255))
            d.line([(PAD, sy + 58), (PAD + INNER_W, sy + 58)], fill=(255, 255, 255, 12), width=1)
            
            cy = sy + 58
            for i, mode in enumerate(data['modes']):
                if i > 0:
                    d.line([(PAD + 28, cy), (PAD + INNER_W - 28, cy)], fill=(255, 255, 255, 10), width=1)
                
                if mode['rank_img_url']:
                    try:
                        rimg = _b64_fit(mode['rank_img_url'], 90, 90)
                        canvas.alpha_composite(rimg, (PAD + 28, cy + 24))
                    except: pass
                
                draw_text_mixed(d, (PAD + 138, cy + 48), mode['mode_name'], F32, M32 if 'M32' in globals() else M34, fill=(212, 177, 99, 255))
                mw = _calc_mixed_w(mode['mode_name'], F32, M34)
                draw_text_mixed(d, (PAD + 138 + mw + 14, cy + 38), mode['score'], F46, M46 if 'M46' in globals() else M34, fill=(212, 177, 99, 255))
                
                rw_w = _calc_mixed_w(mode['reward_text'], F32, M34)
                tx = PAD + INNER_W - 28 - rw_w
                draw_text_mixed(d, (tx, cy + 48), mode['reward_text'], F32, M34, fill=(212, 177, 99, 255))
                
                if mode['reward_icon']:
                    try:
                        rwic = _b64_fit(mode['reward_icon'], 48, 48)
                        canvas.alpha_composite(rwic, (tx - 62, cy + 40))
                    except: pass
                
                cy += 138
                
            y = cy + 10

    # --- 3. 底部 Footer ---
    if data['footer_b64']:
        try:
            ft = _b64_img(data['footer_b64'])
            fw, fh = ft.size
            if fw > W:
                ft = ft.resize((W, int(fh * W / fw)), Image.Resampling.LANCZOS)
            canvas.alpha_composite(ft, ((W - ft.width) // 2, y))
            y += ft.height
        except: pass

    # 格式化导出并预留边距
    FINAL_PAD = 40 
    out_rgb = canvas.crop((0, 0, W, y + FINAL_PAD)).convert('RGB')
    
    buf = BytesIO()
    out_rgb.save(buf, format='JPEG', quality=92, optimize=True)
    return buf.getvalue()