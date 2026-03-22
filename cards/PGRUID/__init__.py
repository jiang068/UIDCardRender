"""
cards.PGRUID
=======================
自动扫描本包内所有模块，并提供统一的 render(html) 分流入口。
新增 PGR 卡片文件后无需修改此文件，只需在 _DISPATCH 列表中注册即可。
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
import urllib.request
from pathlib import Path
from typing import Literal

from PIL import ImageFont, Image, ImageOps, ImageDraw, ImageChops
from io import BytesIO
import base64
import re
from functools import lru_cache

# ---------- 统一字体加载（供本包内所有卡片使用） ----------
_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
_FONT_CN_PATH = _ASSETS_DIR / "H7GBKHeavy.TTF"
_FONT_MONO_PATH = _ASSETS_DIR / "JetBrainsMono-Medium.ttf"
_FONT_JP_PATH = _ASSETS_DIR / "NotoSansJP-Medium.ttf" 
_FONT_KR_PATH = _ASSETS_DIR / "NotoSansKR-Medium.ttf"
_FONT_EMOJI_PATH = _ASSETS_DIR / "NotoEmoji-Regular.ttf"

def get_font(size: int, bold: bool = False, family: Literal['cn', 'mono', 'jp', 'kr', 'emoji'] = 'cn') -> ImageFont.FreeTypeFont:
    candidates: list[str] = []
    if family == 'cn':
        candidates = [str(_FONT_CN_PATH), "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    elif family == 'mono':
        candidates = [str(_FONT_MONO_PATH), "C:/Windows/Fonts/JetBrainsMono-Medium.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
    elif family == 'jp':
        candidates = [str(_FONT_JP_PATH), "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/msgothic.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    elif family == 'kr':
        candidates = [str(_FONT_KR_PATH), "C:/Windows/Fonts/malgun.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    elif family == 'emoji':
        candidates = [str(_FONT_EMOJI_PATH), "C:/Windows/Fonts/seguiemj.ttf", "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"]
        
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

# 预置常用字号
_COMMON_SIZES = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
                 22, 24, 26, 28, 30, 32, 34, 36, 38, 40,
                 42, 44, 46, 48, 52, 56, 60, 72, 80]
for _s in _COMMON_SIZES:
    globals()[f"F{_s}"] = get_font(_s, family='cn')
    globals()[f"F{_s}B"] = globals()[f"F{_s}"]
    globals()[f"M{_s}"] = get_font(_s, family='mono')
    globals()[f"J{_s}"] = get_font(_s, family='jp')
    globals()[f"K{_s}"] = get_font(_s, family='kr')
    globals()[f"E{_s}"] = get_font(_s, family='emoji')

def _is_pure_en_num(ch: str) -> bool:
    return 'a' <= ch <= 'z' or 'A' <= ch <= 'Z' or '0' <= ch <= '9'

def _is_kr(ch: str) -> bool:
    o = ord(ch)
    return (0xAC00 <= o <= 0xD7AF) or (0x1100 <= o <= 0x11FF) or (0x3130 <= o <= 0x318F)

def _is_jp_kana(ch: str) -> bool:
    o = ord(ch)
    return 0x3040 <= o <= 0x30FF

def draw_text_mixed(draw: ImageDraw.ImageDraw, xy: tuple, text: str,
                    cn_font: ImageFont.FreeTypeFont | None = None,
                    en_font: ImageFont.FreeTypeFont | None = None,
                    fill=(255, 255, 255, 255)) -> None:
    if cn_font is None: cn_font = globals()['F24']
    if en_font is None: en_font = globals()['M24']
    x, y = xy

    f_size_cn = getattr(cn_font, 'size', 24)
    f_size_en = getattr(en_font, 'size', 24)
    
    jp_font = globals().get(f"J{f_size_cn}", cn_font)
    kr_font = globals().get(f"K{f_size_cn}", cn_font)

    en_offset = -int(f_size_en * 0.10)
    jp_offset = -int(f_size_cn * 0.35)
    kr_offset = -int(f_size_cn * 0.30)

    for ch in text:
        is_en = _is_pure_en_num(ch)
        if is_en:
            f, draw_y = en_font, y + en_offset
        elif _is_kr(ch):
            f, draw_y = kr_font, y + kr_offset
        elif _is_jp_kana(ch):
            f, draw_y = jp_font, y + jp_offset
        else:
            f, draw_y = cn_font, y
        
        draw.text((x, draw_y), ch, font=f, fill=fill)
        x += int(f.getlength(ch))

# ---------- 图像处理模块 ----------
_BASE_DIR = Path(__file__).parent.parent
logger = logging.getLogger('unicon')

def _looks_like_base64(s: str) -> bool:
    if not s: return False
    if s.startswith('data:'): return True
    if s.startswith('base64://'): return True
    if len(s) > 200: return True
    return False

def _clean_b64_string(src: str) -> str:
    if src.startswith('base64://'):
        return src.replace('base64://', '', 1)
    if ',' in src:
        return src.split(',', 1)[1]
    return src

def _fetch_http_image(url: str) -> Image.Image | None:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=5)
        return Image.open(BytesIO(resp.read())).convert('RGBA')
    except Exception as e:
        logger.error(f"Failed to fetch image {url}: {e}")
        return None

@lru_cache(maxsize=16)
def _b64_img_from_path(p: str) -> Image.Image:
    return Image.open(p).convert('RGBA')

@lru_cache(maxsize=32)
def _b64_fit_from_path(p: str, w: int, h: int) -> Image.Image:
    img = Image.open(p).convert('RGBA')
    return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)

def _resolve_path(src: str) -> Path | None:
    """
    【核心修复】路径探测器
    兼容前端的后缀欺骗：如果原后缀文件不存在，主动探测同名的 .webp 文件
    """
    p = Path(src) if Path(src).is_absolute() else (_BASE_DIR / src)
    
    # 1. 优先找原文件 (Windows 环境下未被删除的 png 等)
    if p.exists():
        return p
        
    # 2. 如果原文件不在了 (Linux 上的常态)，主动将后缀切换为 .webp 去寻找
    webp_p = p.with_suffix('.webp')
    if webp_p.exists():
        return webp_p
        
    return None

def _b64_img(src: str) -> Image.Image:
    if not src: raise ValueError('empty src')
        
    if src.startswith('http://') or src.startswith('https://'):
        img = _fetch_http_image(src)
        if img: return img
        raise ValueError(f"Failed to fetch network image {src}")
        
    if _looks_like_base64(src):
        b64_data = _clean_b64_string(src)
        return Image.open(BytesIO(base64.b64decode(b64_data))).convert('RGBA')
        
    # 调用路径探测器
    p = _resolve_path(src)
    if p:
        try:
            return _b64_img_from_path(str(p))
        except Exception: pass
    
    # 终极兜底
    b64_data = _clean_b64_string(src)
    return Image.open(BytesIO(base64.b64decode(b64_data))).convert('RGBA')


def _b64_fit(src: str, w: int, h: int) -> Image.Image:
    if not src: raise ValueError('empty src')
        
    if src.startswith('http://') or src.startswith('https://'):
        img = _fetch_http_image(src)
        if img: return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)
        raise ValueError(f"Failed to fetch network image {src}")
        
    if _looks_like_base64(src):
        b64_data = _clean_b64_string(src)
        img = Image.open(BytesIO(base64.b64decode(b64_data))).convert('RGBA')
        return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)
        
    # 调用路径探测器
    p = _resolve_path(src)
    if p:
        try:
            return _b64_fit_from_path(str(p), w, h)
        except Exception: pass
    
    # 终极兜底
    b64_data = _clean_b64_string(src)
    img = Image.open(BytesIO(base64.b64decode(b64_data))).convert('RGBA')
    return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)

@lru_cache(maxsize=16)
def _round_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return mask


# ---------- 公共绘图组件 (UI Drawing Helpers) ----------
def _ty(font, text: str, box_h: int) -> int:
    bb = font.getbbox(text)
    return (box_h - (bb[3] - bb[1])) // 2 - bb[1] + 1

def _draw_rounded_rect(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, r: int, fill: tuple, outline=None, width=1):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(block).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(block, (x0, y0))

def _draw_v_gradient(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, top_rgba: tuple, bottom_rgba: tuple, r: int = 0):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    base = Image.new("RGBA", (1, 2))
    base.putpixel((0, 0), top_rgba)
    base.putpixel((0, 1), bottom_rgba)
    grad = base.resize((w, h), Image.BILINEAR)
    if r > 0:
        mask = _round_mask(w, h, r)
        grad.putalpha(ImageChops.multiply(grad.getchannel('A'), mask))
    canvas.alpha_composite(grad, (x0, y0))

def _draw_h_gradient(canvas: Image.Image, x0: int|float, y0: int|float, x1: int|float, y1: int|float, left_rgba: tuple, right_rgba: tuple, r: int = 0):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0: return
    base = Image.new("RGBA", (2, 1))
    base.putpixel((0, 0), left_rgba)
    base.putpixel((1, 0), right_rgba)
    grad = base.resize((w, h), Image.BILINEAR)
    if r > 0:
        mask = _round_mask(w, h, r)
        grad.putalpha(ImageChops.multiply(grad.getchannel('A'), mask))
    canvas.alpha_composite(grad, (x0, y0))

def _draw_clipped_rect(canvas: Image.Image, x: int|float, y: int|float, w: int|float, h: int|float, fill: tuple, outline=None, clip_size: int = 12):
    x, y, w, h = int(round(x)), int(round(y)), int(round(w)), int(round(h))
    if w <= 0 or h <= 0: return
    block = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(block)
    points = [
        (0, 0), (w, 0),
        (w, h - clip_size), (w - clip_size, h),
        (0, h)
    ]
    d.polygon(points, fill=fill, outline=outline)
    canvas.alpha_composite(block, (x, y))

def truncate_text(text: str, font, max_w: int) -> str:
    if font.getlength(text) <= max_w:
        return text
    for i in range(len(text)-1, 0, -1):
        if font.getlength(text[:i] + "...") <= max_w:
            return text[:i] + "..."
    return "..."

def _invert_rgba_image(img: Image.Image) -> Image.Image:
    r, g, b, a = img.split()
    rgb = Image.merge('RGB', (r, g, b))
    inv = ImageOps.invert(rgb)
    ir, ig, ib = inv.split()
    return Image.merge('RGBA', (ir, ig, ib, a))


# ---------- 战双公共 Header 解析与渲染逻辑 ----------
def parse_common_header(soup, html: str) -> dict:
    data = {}
    bg_match = re.search(r"background-image:\s*url\(['\"]?(data:[^'\"]+)['\"]?\)", html)
    data['contentBgB64'] = bg_match.group(1) if bg_match else ""

    h_bg = soup.select_one('.header-bg')
    data['headerBgB64'] = h_bg['src'] if h_bg and h_bg.has_attr('src') else ""
    av = soup.select_one('.avatar-img')
    data['avatarB64'] = av['src'] if av else ""
    av_box = soup.select_one('.avatar-box')
    data['avatarBoxB64'] = av_box['src'] if av_box else ""
    
    hn = soup.select_one('.header-name')
    data['roleName'] = hn.get_text(strip=True) if hn else ""
    
    ll = soup.select_one('.level-label')
    data['rank_label'] = ll.get_text(strip=True) if ll else "勋阶"
    lv = soup.select_one('.level-val')
    data['rank_val'] = lv.get_text(strip=True) if lv else "0"
    
    bottom_spans = soup.select('.header-row-bottom span')
    data['serverName'] = bottom_spans[0].get_text(strip=True) if len(bottom_spans)>0 else ""
    
    raw_id = bottom_spans[-1].get_text(strip=True) if len(bottom_spans)>2 else ""
    data['roleId'] = raw_id.replace("ID:", "").replace("ID", "").strip()

    t_bg = soup.select_one('.section-title-bar img')
    data['titleBgB64'] = t_bg['src'] if t_bg else ""
    
    return data

def draw_common_header(canvas: Image.Image, draw: ImageDraw.ImageDraw, data: dict, pad: int, inner_w: int, y: int) -> int:
    H_H = 200
    h_img = Image.new("RGBA", (inner_w, H_H), (0,0,0,0))
    hd = ImageDraw.Draw(h_img)
    
    _draw_rounded_rect(h_img, 0, 0, inner_w, H_H, 8, (20,25,35,255))
    if data.get('headerBgB64'):
        try:
            hbg = _b64_fit(data['headerBgB64'], inner_w, H_H)
            h_img.paste(hbg, (0,0), _round_mask(inner_w, H_H, 8))
        except: pass

    av_w, av_h = 170, 170
    av_x, av_y = 30, (H_H - av_h)//2
    
    if data.get('avatarBoxB64'):
        try:
            abox = _b64_fit(data['avatarBoxB64'], av_w, av_h)
            h_img.alpha_composite(abox, (av_x, av_y))
        except: pass

    if data.get('avatarB64'):
        try:
            aimg = _b64_fit(data['avatarB64'], 120, 120)
            cmask = Image.new("L", (120, 120), 0)
            ImageDraw.Draw(cmask).ellipse([0,0,119,119], fill=255)
            h_img.paste(aimg, (av_x + 25, av_y + 25), cmask)
        except: pass

    info_x = av_x + av_w + 20
    F44, M44 = globals()['F44'], globals()['M44']
    draw_text_mixed(hd, (info_x, av_y + 20), data.get('roleName', ''), cn_font=F44, en_font=M44, fill=(255,255,255,255))
    name_w = int(F44.getlength(data.get('roleName', '')))
    
    rank_x = info_x + name_w + 16
    rank_label = data.get('rank_label', '勋阶')
    rank_val = data.get('rank_val', '0')
    F22, M22 = globals()['F22'], globals()['M22']
    
    # 动态计算 label 和 val 的宽度
    label_w = int(F22.getlength(rank_label))
    val_w = int(F22.getlength(rank_val))
    gap = 6 # 对应 HTML CSS 中 .level-label 的 margin-right: 6px
    
    # 动态计算外框总宽度: 左 padding + label 宽度 + 间距 + val 宽度 + 右 padding
    box_w = 14 + label_w + gap + val_w + 14 
    
    _draw_rounded_rect(h_img, rank_x, av_y + 30, rank_x + box_w, av_y + 65, 4, (25,30,40,204), outline=(80,100,120,153))
    draw_text_mixed(hd, (rank_x + 14, av_y + 30 + _ty(F22, rank_label, 35)), rank_label, cn_font=F22, en_font=M22, fill=(155,174,194,255))
    
    # val 的 x 坐标也改为动态计算的起始位置
    val_x = rank_x + 14 + label_w + gap
    draw_text_mixed(hd, (val_x, av_y + 30 + _ty(F22, rank_val, 35)), rank_val, cn_font=F22, en_font=M22, fill=(229,141,60,255))

    bottom_y = av_y + 100
    F24, M24 = globals()['F24'], globals()['M24']
    draw_text_mixed(hd, (info_x, bottom_y), data.get('serverName', ''), cn_font=F24, en_font=M24, fill=(140,158,181,255))
    sw = int(F24.getlength(data.get('serverName', '')))
    draw_text_mixed(hd, (info_x + sw + 4, bottom_y), "|", cn_font=F24, en_font=M24, fill=(74,90,117,255))
    draw_text_mixed(hd, (info_x + sw + 20, bottom_y), f"ID:{data.get('roleId', '')}", cn_font=F24, en_font=M24, fill=(140,158,181,255))

    canvas.alpha_composite(h_img, (pad, y))
    return y + H_H + 20

def draw_title_bar(canvas: Image.Image, draw: ImageDraw.ImageDraw, title: str, title_bg_b64: str, pad: int, inner_w: int, y: int) -> int:
    T_H = 60
    _draw_v_gradient(canvas, pad, y, pad + inner_w, y + T_H, (24, 45, 75, 255), (15, 25, 45, 255), r=6)
    if title_bg_b64:
        try:
            tbg = _b64_fit(title_bg_b64, inner_w, T_H)
            canvas.paste(tbg, (pad, y), _round_mask(inner_w, T_H, 6))
        except: pass
    F26, M26 = globals()['F26'], globals()['M26']
    draw_text_mixed(draw, (pad + 24, y + _ty(F26, title, T_H)), title, cn_font=F26, en_font=M26, fill=(255,255,255,255))
    return y + T_H + 20


# ---------- 模块自动注册 ----------
_here = Path(__file__).parent
for _mi in pkgutil.iter_modules([str(_here)]):
    _mod = importlib.import_module(f"cards.PGRUID.{_mi.name}")
    globals()[_mi.name] = _mod

# ---------- HTML → 模块 分流规则 ----------
_DISPATCH: list[tuple[list[str], str, str]] = [
    (['战双体力', '日程助手'], 'pgr_mr_card', '战双每日'),
    (['我的资料', '角色信息'], 'pgr_roleinfo', '战双卡片'),
    (['战双角色面板', '战斗参数'], 'pgr_char_card', '战双角色面板'),
    (['战双幻痛囚笼', '幻痛囚笼'], 'pgr_cage', '战双幻痛囚笼'),
    (['战双纷争战区', '纷争战区'], 'pgr_area', '战双纷争战区'),
    (['战双涂装列表', '角色涂装', '武器涂装'], 'pgr_fashion', '战双涂装列表'),
    (['战双资源看板', '半年资源总览'], 'pgr_resource', '战双资源看板'),
    (['战双诺曼复兴战', '诺曼复兴战'], 'pgr_stronghold', '战双矿区复兴战'),
    (['战双历战映射', '历战映射'], 'pgr_transfinite', '战双历战映射'),
    (['PGRUID 更新记录'], 'pgr_update_log', '战双更新记录'),
]

def render(html: str) -> bytes | None:
    for keywords, mod_name, label in _DISPATCH:
        if any(kw in html for kw in keywords):
            mod = globals().get(mod_name)
            if mod is None: raise RuntimeError(f'模块 {mod_name} 未加载，请检查文件是否存在')
            logger.info('PGR dispatch -> %s (%s)', mod_name, label)
            return mod.render(html)
    return None