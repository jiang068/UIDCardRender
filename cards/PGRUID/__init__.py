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
_FONT_EMOJI_PATH = _ASSETS_DIR / "NotoEmoji-Regular.ttf" # 新增 Emoji 字体路径

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
    globals()[f"E{_s}"] = get_font(_s, family='emoji') # 注入 E 系列 Emoji 字体

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
    if cn_font is None: cn_font = F24
    if en_font is None: en_font = M24
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

def _b64_img(src: str) -> Image.Image:
    if not src: raise ValueError('empty src')
        
    if src.startswith('http://') or src.startswith('https://'):
        img = _fetch_http_image(src)
        if img: return img
        raise ValueError(f"Failed to fetch network image {src}")
        
    if _looks_like_base64(src):
        b64_data = _clean_b64_string(src)
        return Image.open(BytesIO(base64.b64decode(b64_data))).convert('RGBA')
        
    p = Path(src) if Path(src).is_absolute() else (_BASE_DIR / src)
    try:
        if p.exists(): return _b64_img_from_path(str(p))
    except Exception: pass
    
    b64_data = _clean_b64_string(src)
    return Image.open(BytesIO(base64.b64decode(b64_data))).convert('RGBA')

@lru_cache(maxsize=32)
def _b64_fit_from_path(p: str, w: int, h: int) -> Image.Image:
    img = Image.open(p).convert('RGBA')
    return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)

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
        
    p = Path(src) if Path(src).is_absolute() else (_BASE_DIR / src)
    try:
        if p.exists(): return _b64_fit_from_path(str(p), w, h)
    except Exception: pass
    
    b64_data = _clean_b64_string(src)
    img = Image.open(BytesIO(base64.b64decode(b64_data))).convert('RGBA')
    return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)

@lru_cache(maxsize=16)
def _round_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return mask

_here = Path(__file__).parent
for _mi in pkgutil.iter_modules([str(_here)]):
    _mod = importlib.import_module(f"cards.PGRUID.{_mi.name}")
    globals()[_mi.name] = _mod

# ---------- HTML → 模块 分流规则 ----------
_DISPATCH: list[tuple[list[str], str, str]] = [
    (['战双体力', '日程助手'], 'mr_card', '战双每日'),
    (['我的资料', '角色信息'], 'pgr_roleinfo', '战双卡片'),
    (['战双角色面板', '战斗参数'], 'pgr_char_card', '战双角色面板'),
    (['战双幻痛囚笼', '幻痛囚笼'], 'pgr_cage', '战双幻痛囚笼'),
    (['战双纷争战区', '纷争战区'], 'pgr_area', '战双纷争战区'),
    (['战双涂装列表', '角色涂装', '武器涂装'], 'pgr_fashion', '战双涂装列表'),
    (['战双资源看板', '半年资源总览'], 'pgr_resource', '战双资源看板'),
    (['战双诺曼复兴战', '诺曼复兴战'], 'pgr_stronghold', '战双复兴战'),
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