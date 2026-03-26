# cards/XutheringWavesUID/ww_matrix_card.py
from __future__ import annotations
import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageOps, ImageChops
from functools import lru_cache

# 从统一包中动态获取字体和核心方法
from . import (
    get_font, draw_text_mixed, _b64_img, _b64_fit, _round_mask, _is_pure_en_num
)

# --------------------------------------------------
# 工具缓存与绘图辅助
# --------------------------------------------------
@lru_cache(maxsize=32)
def f_cn(size: int): return get_font(size, family='cn')

@lru_cache(maxsize=32)
def f_en(size: int): return get_font(size, family='mono')

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
        grad.putalpha(ImageChops.multiply(grad.getchannel('A'), mask))
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
    'score-rainbow': (255, 120, 180, 255)
}

# --------------------------------------------------
# DOM 深度解析
# --------------------------------------------------
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    # 核心判断：是否有 overview-area 判定为详情页
    data = {'is_detail': soup.select_one('.overview-area') is not None}
    
    # 1. 基础全局背景与底部
    data['bg_url'] = soup.select_one('.bg-image')['src'] if soup.select_one('.bg-image') else ""
    footer = soup.select_one('.footer img')
    data['footer_b64'] = footer['src'] if footer else ""

    # 2. 顶部 User Card 数据
    data['avatar_url'] = soup.select_one('.avatar')['src'] if soup.select_one('.avatar') else ""
    data['user_name'] = soup.select_one('.user-name').get_text(strip=True) if soup.select_one('.user-name') else ""
    uid_node = soup.select_one('.user-uid')
    data['user_id'] = uid_node.get_text(strip=True).replace('UID', '').strip() if uid_node else ""
    stats = soup.select('.stat-value')
    data['level'] = stats[0].get_text(strip=True) if len(stats) > 0 else "0"
    data['world_level'] = stats[1].get_text(strip=True) if len(stats) > 1 else "0"

    # 3. 解析共鸣链颜色映射 (CSS vars)
    style_text = soup.select_one('style').get_text() if soup.select_one('style') else ""
    chain_colors = {0: (170, 170, 170, 255)}
    for i in range(1, 7):
        m = re.search(rf'\.chain-{i}\s*\{{[^}}]*border-right-color:\s*([^;}}]+)', style_text)
        chain_colors[i] = parse_color(m.group(1)) if m else (212, 177, 99, 255)
    data['chain_colors'] = chain_colors

    data['modes'] = []
    
    # ================= 详情页解析 =================
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
                mode['progress_text'] = p_text[1].get_text(strip=True) if len(p_text) >= 2 else "0/0"
                    
                p_fill = oa.select_one('.progress-bar-fill')
                if p_fill and 'width:' in p_fill.get('style', ''):
                    pct_str = re.search(r'width:\s*([\d\.]+)%', p_fill.get('style'))
                    mode['progress_pct'] = float(pct_str.group(1)) if pct_str else 0.0
                else:
                    mode['progress_pct'] = 0.0

            for tm in sec.select('.team-item'):
                team = {'roles': []}
                # 【修复安全提取轮次】
                round_span = tm.select_one('.round-area span')
                team['round'] = round_span.get_text(strip=True) if round_span else "1"
                
                boss_count = tm.select_one('.boss-count')
                team['pass_boss'] = boss_count.get_text(strip=True) if boss_count else "0"
                
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

    # ================= 摘要页解析 =================
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
    
    # 尺寸设定
    W = 1000
    PAD = 40
    INNER_W = W - PAD * 2

    # 1. 动态预计算卡片总高度
    H = PAD
    H += 150 + 30 # User Card 高度 + margin
    if data['is_detail']:
        for m in data['modes']:
            # Header(56) + Overview_margin(10) + Overview(150) + List_padTop(6) + Teams * (110 + 10) + List_padBot(10)
            sec_h = 56 + 10 + 150 + 6 + len(m['teams']) * 120 + 10
            H += sec_h + 30 
    else:
        if data['modes']:
            # Header(56) + Modes * 138 (24 pad + 90 img + 24 pad)
            sec_h = 56 + len(data['modes']) * 138
            H += sec_h + 30
            
    # 预留底部 Footer 与边距
    H += 100 
    
    # 2. 构建底板
    canvas = Image.new("RGBA", (W, H), (15, 17, 21, 255))
    if data['bg_url']:
        try:
            bg_img = _b64_img(data['bg_url']).resize((W, H), Image.Resampling.LANCZOS)
            canvas.alpha_composite(bg_img, (0, 0))
        except: pass
    
    # 15% 黑色遮罩
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 38))
    canvas.alpha_composite(overlay, (0, 0))
    d = ImageDraw.Draw(canvas)
    y = PAD

    # --------------------------------------------------
    # 绘制：User Card
    # --------------------------------------------------
    UH = 150
    _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + UH, 16, (20, 24, 30, 230), outline=(255, 255, 255, 30))
    
    if data['avatar_url']:
        try:
            av_img = _b64_fit(data['avatar_url'], 100, 100)
            canvas.paste(av_img, (PAD + 40, y + 25), _round_mask(100, 100, 50))
        except: pass
        d.ellipse([PAD + 37, y + 22, PAD + 143, y + 128], outline=(42, 46, 53, 255), width=3)
    
    draw_text_mixed(d, (PAD + INNER_W - 140, y + 20), "MATRIX REPORT", f_en(14), f_en(14), fill=(255, 255, 255, 50))
    
    info_x = PAD + 170
    draw_text_mixed(d, (info_x, y + 25), data['user_name'], f_cn(42), f_en(42), fill=(255, 255, 255, 255))
    nw = _calc_mixed_w(data['user_name'], f_cn(42), f_en(42))
    
    uid_str = f"UID {data['user_id']}"
    uw = _calc_mixed_w(uid_str, f_cn(20), f_en(20))
    _draw_rounded_rect(canvas, info_x + nw + 20, y + 36, info_x + nw + 20 + uw + 24, y + 68, 6, (0, 0, 0, 102), outline=(212, 177, 99, 50))
    draw_text_mixed(d, (info_x + nw + 32, y + 40), uid_str, f_cn(20), f_en(20), fill=(212, 177, 99, 255))
    
    d.line([(info_x, y + 80), (info_x + 500, y + 80)], fill=(255, 255, 255, 20), width=1)
    d.line([(info_x, y + 80), (info_x + 40, y + 80)], fill=(212, 177, 99, 255), width=2)
    
    draw_text_mixed(d, (info_x, y + 95), data['level'], f_en(30), f_en(30), fill=(255, 255, 255, 255))
    draw_text_mixed(d, (info_x, y + 128), "联觉等级", f_cn(12), f_cn(12), fill=(109, 113, 122, 255))
    draw_text_mixed(d, (info_x + 120, y + 95), data['world_level'], f_en(30), f_en(30), fill=(255, 255, 255, 255))
    draw_text_mixed(d, (info_x + 120, y + 128), "索拉等级", f_cn(12), f_cn(12), fill=(109, 113, 122, 255))
    
    y += UH + 30

    # --------------------------------------------------
    # 绘制：详情模式 (Detail)
    # --------------------------------------------------
    if data['is_detail']:
        for mode in data['modes']:
            teams_count = len(mode['teams'])
            sec_h = 56 + 10 + 150 + 6 + teams_count * 120 + 10
            
            # 基础背景框
            _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + sec_h, 12, (15, 17, 21, 115), outline=(255, 255, 255, 15))
            
            # Header
            draw_text_mixed(d, (PAD + 20, y + 16), mode['mode_name'], f_cn(28), f_en(28), fill=(255, 255, 255, 255))
            tw = _calc_mixed_w(mode['mode_name'], f_cn(28), f_en(28))
            _draw_h_gradient(canvas, PAD + 20 + tw + 16, y + 30, PAD + INNER_W - 120, y + 32, (212, 177, 99, 204), (212, 177, 99, 0))
            if mode['date']:
                dw = _calc_mixed_w(mode['date'], f_cn(18), f_en(18))
                draw_text_mixed(d, (PAD + INNER_W - 20 - dw, y + 22), mode['date'], f_cn(18), f_en(18), fill=(136, 136, 136, 255))
            d.line([(PAD, y + 56), (PAD + INNER_W, y + 56)], fill=(255, 255, 255, 12), width=1)
            
            # == Overview Area 沙盒渲染 ==
            ov_w, ov_h = INNER_W - 28, 150
            ov_y = y + 56 + 10
            ov_sandbox = Image.new("RGBA", (ov_w, ov_h), (0, 0, 0, 0))
            ov_d = ImageDraw.Draw(ov_sandbox)
            
            # Ov Bg + Mask
            _draw_rounded_rect(ov_sandbox, 0, 0, ov_w, ov_h, 10, (10, 14, 18, 255), outline=(43, 64, 77, 204))
            if mode['overview_bg']:
                try:
                    obg = _b64_fit(mode['overview_bg'], ov_w, ov_h)
                    ov_sandbox.paste(obg, (0, 0), _round_mask(ov_w, ov_h, 10))
                except: pass
            _draw_h_gradient(ov_sandbox, 0, 0, ov_w, ov_h, (10, 14, 18, 51), (10, 14, 18, 128), r=10)
            
            if mode['rank_detail_url']:
                try:
                    rimg = _b64_img(mode['rank_detail_url']).resize((400, 400), Image.Resampling.LANCZOS)
                    ov_sandbox.alpha_composite(rimg, (-80, -125))
                except: pass
            
            # 右侧比分与进度区
            score_col = SCORE_COLORS.get(mode['score_color_key'], (255, 255, 255, 255))
            sc_w = _calc_mixed_w(mode['score'], f_en(44), f_en(44))
            draw_text_mixed(ov_d, (ov_w - 24 - sc_w, 20), mode['score'], f_en(44), f_en(44), fill=score_col)
            lw = _calc_mixed_w("累计积分", f_cn(28), f_en(28))
            draw_text_mixed(ov_d, (ov_w - 24 - sc_w - 10 - lw, 32), "累计积分", f_cn(28), f_en(28), fill=(255, 255, 255, 255))
            
            draw_text_mixed(ov_d, (ov_w - 200, 90), "挑战进度", f_cn(24), f_en(24), fill=(255, 255, 255, 255))
            pw = _calc_mixed_w(mode['progress_text'], f_en(24), f_en(24))
            draw_text_mixed(ov_d, (ov_w - 24 - pw, 90), mode['progress_text'], f_en(24), f_en(24), fill=(255, 255, 255, 255))
            
            # 进度条
            bar_w = ov_w - 300 - 24
            bar_x = 300
            _draw_rounded_rect(ov_sandbox, bar_x, 124, bar_x + bar_w, 132, 4, (50, 64, 75, 204))
            if mode['progress_pct'] > 0:
                fill_w = int(bar_w * mode['progress_pct'] / 100)
                _draw_h_gradient(ov_sandbox, bar_x, 124, bar_x + fill_w, 132, (212, 177, 99, 255), (255, 243, 185, 255), r=4)
            
            ov_final = Image.new("RGBA", (ov_w, ov_h), (0,0,0,0))
            ov_final.paste(ov_sandbox, (0,0), _round_mask(ov_w, ov_h, 10))
            canvas.alpha_composite(ov_final, (PAD + 14, ov_y))
            
            # == Team Items 列表 ==
            ty = ov_y + 150 + 6
            for team in mode['teams']:
                tm_w, tm_h = INNER_W - 28, 110
                tm_box = Image.new("RGBA", (tm_w, tm_h), (0,0,0,0))
                td = ImageDraw.Draw(tm_box)
                
                _draw_rounded_rect(tm_box, 0, 0, tm_w, tm_h, 8, (30, 42, 55, 165), outline=(255, 255, 255, 15))
                _draw_h_gradient(tm_box, 0, 0, 3, tm_h, (212, 177, 99, 128), (212, 177, 99, 0), r=2)
                
                # 【核心修复】安全格式化字符补齐轮次
                round_str = str(team['round']).zfill(2)
                draw_text_mixed(td, (24, 34), round_str, f_en(34), f_en(34), fill=(255, 255, 255, 255))
                
                # Fake Arrow Line
                td.line([(86, 45), (96, 55), (86, 65)], fill=(255,255,255, 90), width=2, joint="curve")
                
                # Roles
                rx = 118
                for role in team['roles']:
                    _draw_rounded_rect(tm_box, rx, 11, rx + 88, 99, 8, (42, 46, 53, 255), outline=(255, 255, 255, 25))
                    if role['icon']:
                        try:
                            ic = _b64_fit(role['icon'], 88, 88)
                            tm_box.paste(ic, (rx, 11), _round_mask(88, 88, 8))
                        except: pass
                    if role['level']:
                        _draw_h_gradient(tm_box, rx, 14, rx + 45, 34, (0, 0, 0, 216), (0, 0, 0, 0))
                        td.line([(rx, 14), (rx, 34)], fill=(212, 177, 99, 255), width=2)
                        draw_text_mixed(td, (rx + 4, 16), f"Lv.{role['level']}", f_en(14), f_en(14), fill=(255, 255, 255, 255))
                    
                    if role['chain_name']:
                        c_col = data['chain_colors'].get(role['chain_idx'], (170, 170, 170, 255))
                        cw = _calc_mixed_w(role['chain_name'], f_cn(14), f_en(14))
                        _draw_h_gradient(tm_box, rx + 88 - cw - 12, 99 - 22, rx + 88, 99 - 2, (0, 0, 0, 0), (0, 0, 0, 230))
                        td.line([(rx + 88 - 2, 99 - 22), (rx + 88 - 2, 99 - 2)], fill=c_col, width=2)
                        draw_text_mixed(td, (rx + 88 - cw - 6, 99 - 20), role['chain_name'], f_cn(14), f_en(14), fill=c_col)
                    rx += 118

                # Divider & Buff/Boss
                dx = tm_w - 350
                td.line([(dx, 25), (dx, 85)], fill=(255, 255, 255, 25), width=2)
                
                if team['buff_icon']:
                    try:
                        bf = _b64_fit(team['buff_icon'], 56, 56)
                        _draw_rounded_rect(tm_box, dx + 24, 27, dx + 80, 83, 6, (115, 140, 163, 51))
                        tm_box.alpha_composite(bf, (dx + 24, 27))
                    except: pass
                
                bx = dx + 105
                draw_text_mixed(td, (bx, 20), f"第 {team['round']} 轮", f_cn(24), f_en(24), fill=(255, 255, 255, 255))
                _draw_rounded_rect(tm_box, bx, 50, bx + 100, 82, 16, (255, 255, 255, 30))
                if team['boss_icon']:
                    try:
                        bc = _b64_fit(team['boss_icon'], 38, 38)
                        tm_box.alpha_composite(bc, (bx - 8, 47))
                    except: pass
                
                pb_w = _calc_mixed_w(team['pass_boss'], f_en(24), f_en(24))
                draw_text_mixed(td, (bx + 35, 52), team['pass_boss'], f_en(24), f_en(24), fill=(255, 255, 255, 255))
                draw_text_mixed(td, (bx + 35 + pb_w, 52), f"/{team['boss_total']}", f_en(24), f_en(24), fill=(138, 138, 138, 255))
                
                # Score
                sc_str = f"+{team['score']}"
                ts_w = _calc_mixed_w(sc_str, f_en(34), f_en(34))
                draw_text_mixed(td, (tm_w - 24 - ts_w, 34), sc_str, f_en(34), f_en(34), fill=(255, 255, 255, 255))
                
                canvas.alpha_composite(tm_box, (PAD + 14, ty))
                ty += 120
                
            y += sec_h + 30

    # --------------------------------------------------
    # 绘制：摘要模式 (Summary)
    # --------------------------------------------------
    else:
        if data['modes']:
            sec_h = 56 + len(data['modes']) * 138
            _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + sec_h, 12, (15, 17, 21, 115), outline=(255, 255, 255, 15))
            
            # Header
            title = data.get('main_title', '终焉矩阵')
            draw_text_mixed(d, (PAD + 24, y + 16), title, f_cn(28), f_en(28), fill=(255, 255, 255, 255))
            tw = _calc_mixed_w(title, f_cn(28), f_en(28))
            _draw_h_gradient(canvas, PAD + 24 + tw + 16, y + 30, PAD + INNER_W - 120, y + 32, (212, 177, 99, 204), (212, 177, 99, 0))
            if data['main_date']:
                dw = _calc_mixed_w(data['main_date'], f_cn(18), f_en(18))
                draw_text_mixed(d, (PAD + INNER_W - 24 - dw, y + 22), data['main_date'], f_cn(18), f_en(18), fill=(136, 136, 136, 255))
            d.line([(PAD, y + 56), (PAD + INNER_W, y + 56)], fill=(255, 255, 255, 12), width=1)
            
            cy = y + 56
            for i, mode in enumerate(data['modes']):
                if i > 0:
                    d.line([(PAD + 28, cy), (PAD + INNER_W - 28, cy)], fill=(255, 255, 255, 10), width=1)
                
                if mode['rank_img_url']:
                    try:
                        rimg = _b64_fit(mode['rank_img_url'], 90, 90)
                        canvas.alpha_composite(rimg, (PAD + 28, cy + 24))
                    except: pass
                
                draw_text_mixed(d, (PAD + 138, cy + 50), mode['mode_name'], f_cn(32), f_en(32), fill=(212, 177, 99, 255))
                mw = _calc_mixed_w(mode['mode_name'], f_cn(32), f_en(32))
                draw_text_mixed(d, (PAD + 138 + mw + 14, cy + 40), mode['score'], f_en(50), f_en(50), fill=(212, 177, 99, 255))
                
                rw_w = _calc_mixed_w(mode['reward_text'], f_cn(32), f_en(32))
                tx = PAD + INNER_W - 28 - rw_w
                draw_text_mixed(d, (tx, cy + 50), mode['reward_text'], f_cn(32), f_en(32), fill=(212, 177, 99, 255))
                
                if mode['reward_icon']:
                    try:
                        rwic = _b64_fit(mode['reward_icon'], 48, 48)
                        canvas.alpha_composite(rwic, (tx - 62, cy + 45))
                    except: pass
                
                cy += 138
                
            y += sec_h + 30

    # --------------------------------------------------
    # 底部 Footer 输出
    # --------------------------------------------------
    y -= 10
    if data['footer_b64']:
        try:
            ft = _b64_img(data['footer_b64'])
            fw, fh = ft.size
            if fw > W:
                ft = ft.resize((W, int(fh * W / fw)), Image.Resampling.LANCZOS)
            canvas.alpha_composite(ft, ((W - ft.width) // 2, y))
            y += ft.height
        except: pass

    y -= 20
    FINAL_PAD = 40 
    
    out_rgb = canvas.crop((0, 0, W, y + FINAL_PAD)).convert('RGB')
    buf = BytesIO()
    out_rgb.save(buf, format='JPEG', quality=92, optimize=True)
    return buf.getvalue()