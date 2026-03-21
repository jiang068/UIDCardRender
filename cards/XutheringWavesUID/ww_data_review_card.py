# 库街区年度航行报告 卡片渲染器 (PIL 版)

from __future__ import annotations

import base64
import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageChops

# 导入包级统一资源
from . import (
    F13, F14, F15, F16, F18, F20, F22, F24, F28, F30, F32, F36, F42, F72,
    M13, M14, M15, M16, M18, M20, M22, M24, M28, M30, M32, M36, M42, M72,
    draw_text_mixed, _b64_img, _b64_fit, _round_mask, _is_pure_en_num, _is_jp_kana, _is_kr
)

# --- 尺寸与颜色常量 ---
W = 750
PAD = 20
INNER_W = W - PAD * 2  # 710

C_BG = (240, 244, 248, 255)         # #f0f4f8
C_SEC_BG = (255, 255, 255, 255)     # #ffffff
C_SEC_BORDER = (237, 242, 247, 255) # #edf2f7

COLORS = {
    'hl-red': (255, 71, 87, 255),
    'hl-blue': (30, 144, 255, 255),
    'hl-green': (46, 213, 115, 255),
    'hl-orange': (255, 165, 2, 255),
    'hl-purple': (156, 136, 255, 255),
    'hl-pink': (255, 107, 129, 255),
    'default': (44, 62, 80, 255),       # #2c3e50
    'sub': (149, 165, 166, 255),        # #95a5a6
}

# --- 基础绘图辅助函数 ---
def _draw_rounded_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, r: int, fill: tuple):
    w, h = int(x1 - x0), int(y1 - y0)
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill)
    canvas.alpha_composite(block, (int(x0), int(y0)))

def _draw_v_gradient(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, top_rgba: tuple, bottom_rgba: tuple, r: int = 0):
    w, h = int(x1 - x0), int(y1 - y0)
    if w <= 0 or h <= 0: return
    grad_1d = Image.new("RGBA", (1, h))
    for yi in range(h):
        t = yi / max(h - 1, 1)
        color = tuple(int(top_rgba[i] + (bottom_rgba[i] - top_rgba[i]) * t) for i in range(4))
        grad_1d.putpixel((0, yi), color)
    grad = grad_1d.resize((w, h), Image.NEAREST)
    if r > 0:
        mask = _round_mask(w, h, r)
        new_a = ImageChops.multiply(grad.split()[3], mask)
        grad.putalpha(new_a)
    canvas.alpha_composite(grad, (int(x0), int(y0)))

def measure_mixed_text(text: str, cn_font, en_font) -> int:
    """精准测量混排文本宽度"""
    w = 0
    f_size_cn = getattr(cn_font, 'size', 24)
    jp_font = globals().get(f"J{f_size_cn}", cn_font)
    kr_font = globals().get(f"K{f_size_cn}", cn_font)
    for ch in text:
        if _is_pure_en_num(ch): w += int(en_font.getlength(ch))
        elif _is_kr(ch): w += int(kr_font.getlength(ch))
        elif _is_jp_kana(ch): w += int(jp_font.getlength(ch))
        else: w += int(cn_font.getlength(ch))
    return w

def get_hl_color(element) -> tuple:
    cls = element.get('class', [])
    for c in cls:
        if c in COLORS: return COLORS[c]
    return COLORS['default']

def get_fonts(font_type: str):
    mapping = {
        'base': (F20, M20),
        'hl': (F22, M22),
        'sub': (F16, M16),
        'bold': (F22, M22),
        'medium': (F32, M32),
        'big': (F42, M42),
    }
    return mapping.get(font_type, (F20, M20))

# --- 富文本解析器 ---
def parse_rich_text(element):
    """解析带有 <br> 和 <span> 高亮的富文本行"""
    lines = []
    current_line = []
    for el in element.children:
        if el.name == 'br':
            lines.append(current_line)
            current_line = []
        elif el.name == 'span':
            text = el.get_text(strip=True)
            if not text: continue
            color = get_hl_color(el)
            cls = el.get('class', [])
            font_type = 'base'
            if 'big-number' in cls: font_type = 'big'
            elif 'medium-number' in cls: font_type = 'medium'
            elif 'tool-names' in cls or 'forum-names' in cls: font_type = 'bold'
            elif 'sub-text' in cls: font_type = 'sub'
            elif color != COLORS['default']: font_type = 'hl'
            current_line.append({'text': text, 'color': color, 'type': font_type})
        elif isinstance(el, str):
            text = str(el).strip()
            if text:
                current_line.append({'text': text, 'color': COLORS['default'], 'type': 'base'})
    if current_line:
        lines.append(current_line)
    return lines

# --- HTML DOM 结构解析 ---
def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    data = {'user': {}, 'sections': [], 'card_b64': '', 'footer_b64': ''}
    
    # 顶部用户栏
    av = soup.select_one('.user-avatar-large')
    data['user']['avatar'] = av['src'] if av else ''
    name = soup.select_one('.user-name-large')
    data['user']['name'] = name.get_text(strip=True) if name else ''
    logo = soup.select_one('.header-logo-small')
    data['user']['logo'] = logo['src'] if logo else ''

    # 遍历主要内容卡片区块
    for sec in soup.select('.section'):
        sec_data = []
        for child in sec.children:
            if child.name is None: continue
            cls = child.get('class', [])
            
            if 'section-text' in cls:
                sec_data.append({'type': 'rich_text', 'lines': parse_rich_text(child)})
            elif 'sub-text' in cls:
                sec_data.append({'type': 'sub_text', 'text': child.get_text(strip=True)})
            elif 'percent-row' in cls:
                num = child.select_one('.percent-number').get_text(strip=True) if child.select_one('.percent-number') else "0"
                sec_data.append({'type': 'percent', 'val': num})
            elif 'interact-block' in cls:
                items = []
                for item in child.select('.interact-item'):
                    lbl = item.select_one('.interact-label').get_text(strip=True) if item.select_one('.interact-label') else ""
                    n_tag = item.select_one('.interact-name')
                    c_tag = item.select_one('.interact-count')
                    name_txt = n_tag.get_text(strip=True) if n_tag else ''
                    count_txt = c_tag.get_text(strip=True) if c_tag else ''
                    color = get_hl_color(n_tag) if n_tag else (get_hl_color(c_tag) if c_tag else COLORS['hl-blue'])
                    items.append({'label': lbl, 'name': name_txt, 'count': count_txt, 'color': color})
                sec_data.append({'type': 'interact', 'items': items})
            elif 'stats-grid' in cls:
                items = []
                for item in child.select('.stat-card'):
                    lbl = item.select_one('.stat-card-label').get_text(strip=True) if item.select_one('.stat-card-label') else ""
                    val_tag = item.select_one('.stat-card-value')
                    val = val_tag.get_text(strip=True) if val_tag else "0"
                    unit = item.select_one('.stat-card-unit').get_text(strip=True) if item.select_one('.stat-card-unit') else ""
                    color = get_hl_color(val_tag) if val_tag else COLORS['hl-blue']
                    items.append({'label': lbl, 'val': val, 'unit': unit, 'color': color})
                sec_data.append({'type': 'stats', 'items': items})
            elif 'badge-row' in cls:
                badges = []
                for b in child.select('.badge'):
                    is_kw = 'keyword-badge' in b.get('class', [])
                    badges.append({'text': b.get_text(strip=True), 'is_kw': is_kw})
                sec_data.append({'type': 'badges', 'badges': badges})
            elif 'likes-summary' in cls:
                items = []
                for item in child.select('.likes-item'):
                    lbls = item.select('.likes-label')
                    tag = item.select_one('.likes-tag')
                    val_tag = item.select_one('.likes-value')
                    items.append({
                        'tag': tag.get_text(strip=True) if tag else '',
                        'lbl1': lbls[0].get_text(strip=True) if len(lbls)>0 else '',
                        'val': val_tag.get_text(strip=True) if val_tag else "0",
                        'lbl2': lbls[1].get_text(strip=True) if len(lbls)>1 else '',
                        'color': get_hl_color(val_tag) if val_tag else COLORS['hl-red']
                    })
                sec_data.append({'type': 'likes', 'items': items})
            elif 'summary-name' in cls:
                sec_data.append({'type': 'summary_name', 'text': child.get_text(strip=True)})
            elif 'summary-sub' in cls:
                sec_data.append({'type': 'summary_sub', 'text': child.get_text(strip=True)})

        if sec_data:
            data['sections'].append(sec_data)

    img = soup.select_one('.card-image img')
    data['card_b64'] = img['src'] if img else ''
    ftr = soup.select_one('.footer img')
    data['footer_b64'] = ftr['src'] if ftr else ''

    return data


# --- 主渲染逻辑 ---
def render(html: str) -> bytes:
    data = parse_html(html)
    
    # 动态画布游标计算，先创建一个极高的透明底图，最后进行裁剪
    MAX_H = 5000
    canvas = Image.new("RGBA", (W, MAX_H), C_BG)
    d = ImageDraw.Draw(canvas)
    
    y = 0

    # ================= Header (用户栏) =================
    H_H = 118
    # 底部背景
    d.rectangle([0, y, W, y + H_H], fill=(18, 18, 18, 255))
    _draw_v_gradient(canvas, 0, y, W, y + H_H, (40, 40, 40, 255), (18, 18, 18, 255))
    
    # 头像
    if data['user']['avatar']:
        try:
            av = _b64_fit(data['user']['avatar'], 70, 70)
            rmask = _round_mask(70, 70, 35)
            canvas.paste(av, (30, y + 24), rmask)
            d.ellipse([29, y + 23, 101, y + 95], outline=(255, 255, 255, 150), width=2)
        except: pass

    # 名字与标签
    draw_text_mixed(d, (118, y + 30), data['user']['name'], cn_font=F24, en_font=M24, fill=(255,255,255,255))
    
    tag_text = "库街区年度航行报告"
    tag_w = F13.getlength(tag_text) + 20
    _draw_rounded_rect(canvas, 118, y + 66, 118 + tag_w, y + 88, 4, (255, 255, 255, 30))
    draw_text_mixed(d, (128, y + 70), tag_text, cn_font=F13, en_font=M13, fill=(255,255,255,200))

    # Logo
    if data['user']['logo']:
        try:
            logo_img = _b64_img(data['user']['logo'])
            lw, lh = logo_img.size
            if lh > 0:
                t_w = int(lw * (36 / lh))
                logo_img = logo_img.resize((t_w, 36), Image.BILINEAR)
                canvas.alpha_composite(logo_img, (W - 30 - t_w, y + (H_H - 36)//2))
        except: pass
    
    y += H_H + 16

    # ================= 各卡片区块 =================
    for sec in data['sections']:
        # 使用透明暂存图层单独绘制内容，以获取区块动态高度
        sec_img = Image.new("RGBA", (INNER_W, 1000), (0,0,0,0))
        sd = ImageDraw.Draw(sec_img)
        sy = 20  # Section 顶部内边距
        
        for block in sec:
            # 1. 富文本 (自动换行、高亮混排)
            if block['type'] == 'rich_text':
                for line in block['lines']:
                    if not line: continue
                    # 计算当前行最大字号，用于基线对齐
                    max_size = max(getattr(get_fonts(c['type'])[0], 'size', 20) for c in line)
                    line_w = sum(measure_mixed_text(c['text'], *get_fonts(c['type'])) for c in line)
                    cx = INNER_W // 2 - line_w // 2
                    for c in line:
                        f_cn, f_en = get_fonts(c['type'])
                        cur_sz = getattr(f_cn, 'size', 20)
                        y_offset = (max_size - cur_sz) // 2  # 简易垂直居中
                        draw_text_mixed(sd, (cx, sy + y_offset), c['text'], f_cn, f_en, c['color'])
                        cx += measure_mixed_text(c['text'], f_cn, f_en)
                    sy += max_size + 12
                sy += 6

            # 2. 次要灰色小字
            elif block['type'] == 'sub_text':
                w = measure_mixed_text(block['text'], F16, M16)
                draw_text_mixed(sd, (INNER_W//2 - w//2, sy), block['text'], F16, M16, COLORS['sub'])
                sy += 26

            # 3. 超大百分比
            elif block['type'] == 'percent':
                w1 = measure_mixed_text(block['val'], F72, M72)
                w2 = measure_mixed_text('%', F36, M36)
                cx = INNER_W // 2 - (w1 + w2 + 4) // 2
                draw_text_mixed(sd, (cx, sy), block['val'], F72, M72, COLORS['hl-red'])
                draw_text_mixed(sd, (cx + w1 + 4, sy + 36), "%", F36, M36, COLORS['hl-red'])
                sy += 86

            # 4. 互动双列 (最常互动的人)
            elif block['type'] == 'interact':
                count = len(block['items'])
                if count > 0:
                    gap = 12
                    item_w = (INNER_W - gap * (count - 1)) // count
                    ix = 0
                    max_h = 0
                    for it in block['items']:
                        item_h = 100 if it['name'] else 76
                        max_h = max(max_h, item_h)
                        _draw_rounded_rect(sec_img, ix, sy, ix + item_w, sy + item_h, 12, (248, 250, 252, 255))
                        sd.rounded_rectangle([ix, sy, ix + item_w, sy + item_h], radius=12, outline=C_SEC_BORDER, width=1)
                        
                        lw = measure_mixed_text(it['label'], F14, M14)
                        draw_text_mixed(sd, (ix + item_w//2 - lw//2, sy + 14), it['label'], F14, M14, COLORS['sub'])
                        
                        if it['name']:
                            nw = measure_mixed_text(it['name'], F22, M22)
                            draw_text_mixed(sd, (ix + item_w//2 - nw//2, sy + 38), it['name'], F22, M22, it['color'])
                            cw = measure_mixed_text(it['count'], F28, M28)
                            draw_text_mixed(sd, (ix + item_w//2 - cw//2, sy + 66), it['count'], F28, M28, it['color'])
                        else:
                            cw = measure_mixed_text(it['count'], F28, M28)
                            draw_text_mixed(sd, (ix + item_w//2 - cw//2, sy + 40), it['count'], F28, M28, it['color'])
                        ix += item_w + gap
                    sy += max_h + 12

            # 5. 三列数据网格 (点赞、收藏等)
            elif block['type'] == 'stats':
                count = 3
                gap = 10
                item_w = (INNER_W - gap * 2) // count
                ix = 0
                for it in block['items']:
                    _draw_rounded_rect(sec_img, ix, sy, ix + item_w, sy + 80, 12, (248, 250, 252, 255))
                    sd.rounded_rectangle([ix, sy, ix + item_w, sy + 80], radius=12, outline=C_SEC_BORDER, width=1)
                    
                    lw = measure_mixed_text(it['label'], F14, M14)
                    draw_text_mixed(sd, (ix + item_w//2 - lw//2, sy + 14), it['label'], F14, M14, COLORS['sub'])
                    
                    vw = measure_mixed_text(it['val'], F30, M30)
                    uw = measure_mixed_text(it['unit'], F14, M14)
                    tot_w = vw + uw + 2
                    draw_text_mixed(sd, (ix + item_w//2 - tot_w//2, sy + 40), it['val'], F30, M30, it['color'])
                    draw_text_mixed(sd, (ix + item_w//2 - tot_w//2 + vw + 2, sy + 54), it['unit'], F14, M14, COLORS['sub'])
                    
                    ix += item_w + gap
                sy += 92

            # 6. Likes 收发
            elif block['type'] == 'likes':
                count = len(block['items'])
                if count > 0:
                    gap = 12
                    item_w = (INNER_W - gap * (count - 1)) // count
                    ix = 0
                    for it in block['items']:
                        _draw_rounded_rect(sec_img, ix, sy, ix + item_w, sy + 110, 12, (248, 250, 252, 255))
                        sd.rounded_rectangle([ix, sy, ix + item_w, sy + 110], radius=12, outline=C_SEC_BORDER, width=1)
                        
                        tw = measure_mixed_text(it['tag'], F14, M14)
                        draw_text_mixed(sd, (ix + item_w//2 - tw//2, sy + 16), it['tag'], F14, M14, COLORS['sub'])
                        l1w = measure_mixed_text(it['lbl1'], F13, M13)
                        draw_text_mixed(sd, (ix + item_w//2 - l1w//2, sy + 36), it['lbl1'], F13, M13, COLORS['sub'])
                        vw = measure_mixed_text(it['val'], F36, M36)
                        draw_text_mixed(sd, (ix + item_w//2 - vw//2, sy + 56), it['val'], F36, M36, it['color'])
                        l2w = measure_mixed_text(it['lbl2'], F13, M13)
                        draw_text_mixed(sd, (ix + item_w//2 - l2w//2, sy + 88), it['lbl2'], F13, M13, COLORS['sub'])
                        
                        ix += item_w + gap
                    sy += 122

            # 7. Summary 特殊排版
            elif block['type'] == 'summary_name':
                w = measure_mixed_text(block['text'], F22, M22)
                draw_text_mixed(sd, (INNER_W//2 - w//2, sy), block['text'], F22, M22, COLORS['hl-blue'])
                sy += 28
            elif block['type'] == 'summary_sub':
                w = measure_mixed_text(block['text'], F15, M15)
                draw_text_mixed(sd, (INNER_W//2 - w//2, sy), block['text'], F15, M15, COLORS['sub'])
                sy += 26
            elif block['type'] == 'badges':
                sy += 6
                # 简单居中流式排版
                b_heights = []
                b_widths = []
                for b in block['badges']:
                    b_font = F18 if b['is_kw'] else F15
                    bw = measure_mixed_text(b['text'], b_font, b_font) + (48 if b['is_kw'] else 40)
                    b_widths.append(bw)
                    b_heights.append(42 if b['is_kw'] else 36)
                
                total_w = sum(b_widths) + 10 * (len(b_widths) - 1)
                bx = INNER_W//2 - total_w//2
                for i, b in enumerate(block['badges']):
                    bh = b_heights[i]
                    # 渐变背景胶囊
                    if b['is_kw']:
                        _draw_v_gradient(sec_img, bx, sy, bx + b_widths[i], sy + bh, (243, 156, 18, 255), (230, 126, 34, 255), r=bh//2)
                        draw_text_mixed(sd, (bx + 24, sy + 10), b['text'], F18, M18, (255,255,255,255))
                    else:
                        _draw_v_gradient(sec_img, bx, sy, bx + b_widths[i], sy + bh, (52, 152, 219, 255), (41, 128, 185, 255), r=bh//2)
                        draw_text_mixed(sd, (bx + 20, sy + 8), b['text'], F15, M15, (255,255,255,255))
                    bx += b_widths[i] + 10
                sy += max(b_heights) + 16 if b_heights else 0

        # 获取当前区块渲染总高
        sec_h = sy + 20
        # 在主画布绘制白底和淡淡的阴影边框
        _draw_rounded_rect(canvas, PAD, y + 2, PAD + INNER_W, y + sec_h + 2, 16, (0, 0, 0, 10))
        _draw_rounded_rect(canvas, PAD, y, PAD + INNER_W, y + sec_h, 16, C_SEC_BG)
        d.rounded_rectangle([PAD, y, PAD + INNER_W, y + sec_h], radius=16, outline=C_SEC_BORDER, width=1)
        
        # 将局部图层贴上来
        canvas.alpha_composite(sec_img.crop((0, 0, INNER_W, sec_h)), (PAD, y))
        y += sec_h + 14

    # ================= 底部长图 (如果有) =================
    if data['card_b64']:
        try:
            c_img = _b64_img(data['card_b64'])
            cw, ch = c_img.size
            if ch > 0:
                target_w = INNER_W
                target_h = int(ch * (target_w / cw))
                c_img = c_img.resize((target_w, target_h), Image.LANCZOS)
                
                # 为图片增加圆角和阴影
                img_bg = Image.new("RGBA", (target_w, target_h), (0,0,0,0))
                _draw_rounded_rect(canvas, PAD, y+4, PAD+target_w, y+target_h+4, 12, (0,0,0,15))
                rmask = _round_mask(target_w, target_h, 12)
                img_bg.paste(c_img, (0, 0), rmask)
                canvas.alpha_composite(img_bg, (PAD, y))
                y += target_h + 20
        except: pass

    # ================= Footer 结束语 =================
    y += 10
    if data['footer_b64']:
        try:
            f_img = _b64_img(data['footer_b64'])
            fw, fh = f_img.size
            if fh > 0:
                t_h = int(fh * (W / fw))
                f_img = f_img.resize((W, t_h), Image.BILINEAR)
                canvas.alpha_composite(f_img, (0, y))
                y += t_h
        except: pass
    else:
        text = "Generated by GsUidCore · Wuthering Waves"
        tw = F14.getlength(text)
        draw_text_mixed(d, (W//2 - tw//2, y + 10), text, cn_font=F14, en_font=M14, fill=(150,150,150,255))
        y += 40

    # 裁剪到最终高度并输出
    out_rgb = canvas.crop((0, 0, W, y)).convert("RGB")
    buf = BytesIO()
    out_rgb.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()