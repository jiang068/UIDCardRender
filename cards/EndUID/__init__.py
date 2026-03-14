"""
cards.EndUID
=======================
自动扫描本包内所有模块，并提供统一的 render(html) 分流入口。
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Literal

from PIL import ImageFont
from PIL import Image, ImageOps, ImageDraw
from io import BytesIO
import base64
import re
from functools import lru_cache

# ---------- 统一字体加载 ----------
_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
_FONT_CN_PATH = _ASSETS_DIR / "H7GBKHeavy.TTF"
_FONT_EN_PATH = _ASSETS_DIR / "Oswald-Medium.ttf"
# --- [新增] Emoji 字体路径 ---
_FONT_EMOJI_PATH = _ASSETS_DIR / "NotoEmoji-Regular.ttf" 

def get_font(size: int, bold: bool = False, family: Literal['cn', 'mono', 'oswald'] = 'cn') -> ImageFont.FreeTypeFont:
    candidates: list[str] = []
    if family == 'cn':
        candidates = [str(_FONT_CN_PATH), "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]
    else:
        candidates = [str(_FONT_EN_PATH), "C:/Windows/Fonts/arialbd.ttf"]
        
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

# --- [新增] 专门的 Emoji 字体加载函数 ---
def get_emoji_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        str(_FONT_EMOJI_PATH),
        "C:/Windows/Fonts/seguiemj.ttf",
        "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
        "/usr/share/fonts/noto/NotoEmoji-Regular.ttf",
        "/usr/share/fonts/google-noto-emoji/NotoEmoji-Regular.ttf"
    ]
    for p in candidates:
        try:
            if Path(p).exists():
                return ImageFont.truetype(p, size)
        except Exception:
            continue
    # 如果找不到 Emoji 字体，降级回普通中文字体
    return get_font(size, family='cn')

# 预置常用字号和对应的 bold 变量（FxxB），以及对应的等宽英数字体 Mxx 和 英文数字字体 Oxx。
_COMMON_SIZES = [
    10, 12, 13, 14, 15, 16, 18, 20, 22, 24, 26, 28, 30, 
    32, 34, 36, 38, 40, 42, 48, 52, 56, 60, 64, 72, 80, 96, 100, 160
]

for _s in _COMMON_SIZES:
    globals()[f"F{_s}"] = get_font(_s, family='cn')
    globals()[f"F{_s}B"] = globals()[f"F{_s}"]
    globals()[f"M{_s}"] = get_font(_s, family='mono')
    globals()[f"O{_s}"] = get_font(_s, family='oswald') 

def find_font_file(family: Literal['cn', 'mono', 'oswald'] = 'cn') -> str | None:
    if family == 'cn':
        candidates = [str(_FONT_CN_PATH), "C:/Windows/Fonts/msyh.ttc"]
    else:
        candidates = [str(_FONT_EN_PATH), "C:/Windows/Fonts/arialbd.ttf"]
        
    for p in candidates:
        try:
            if Path(p).exists():
                return p
        except Exception:
            continue
    return None

def _is_pure_en_num(ch: str) -> bool:
    return 'a' <= ch <= 'z' or 'A' <= ch <= 'Z' or '0' <= ch <= '9' or ch in ' _-//:.'

def draw_text_mixed(draw: ImageDraw.ImageDraw, xy: tuple, text: str,
                    cn_font: ImageFont.FreeTypeFont | None = None,
                    en_font: ImageFont.FreeTypeFont | None = None,
                    fill=(255, 255, 255, 255),
                    dy_cn: int = 0,
                    dy_en: int = 0) -> None:
    """全局混合文字渲染，并提供微调参数"""
    if cn_font is None: cn_font = F24
    if en_font is None: en_font = M24
    x, y = xy

    cn_size = getattr(cn_font, 'size', 24)
    en_size = getattr(en_font, 'size', 24)
    
    # 将全局偏移减弱到 10% (0.10)，避免矫枉过正，并加上外部传入的微调值
    cn_offset = int(cn_size * 0.15) + dy_cn
    en_offset = -int(en_size * 0.15) + dy_en

    for ch in text:
        is_en = _is_pure_en_num(ch)
        f = en_font if is_en else cn_font
        draw_y = y + (en_offset if is_en else cn_offset)
        draw.text((x, draw_y), ch, font=f, fill=fill)
        x += int(f.getlength(ch))

# ---------- 图像加载与缓存 ----------
_BASE_DIR = Path(__file__).parent.parent

def _looks_like_base64(s: str) -> bool:
    if not s: return False
    if s.startswith('data:'): return True
    if len(s) > 200 and re.fullmatch(r'[A-Za-z0-9+/=\n\r]+', s): return True
    return False

@lru_cache(maxsize=16)
def _b64_img_from_path(p: str) -> Image.Image:
    return Image.open(p).convert('RGBA')

def _b64_img(src: str) -> Image.Image:
    if not src: raise ValueError('empty src')
    if _looks_like_base64(src):
        if ',' in src: src = src.split(',', 1)[1]
        return Image.open(BytesIO(base64.b64decode(src))).convert('RGBA')
    p = Path(src) if Path(src).is_absolute() else (_BASE_DIR / src)
    try:
        if p.exists(): return _b64_img_from_path(str(p))
    except Exception: pass
    if ',' in src: src = src.split(',', 1)[1]
    return Image.open(BytesIO(base64.b64decode(src))).convert('RGBA')

@lru_cache(maxsize=32)
def _b64_fit_from_path(p: str, w: int, h: int) -> Image.Image:
    img = Image.open(p).convert('RGBA')
    return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)

def _b64_fit(src: str, w: int, h: int) -> Image.Image:
    if not src: raise ValueError('empty src')
    if _looks_like_base64(src):
        if ',' in src: src = src.split(',', 1)[1]
        img = Image.open(BytesIO(base64.b64decode(src))).convert('RGBA')
        return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)
    p = Path(src) if Path(src).is_absolute() else (_BASE_DIR / src)
    try:
        if p.exists(): return _b64_fit_from_path(str(p), w, h)
    except Exception: pass
    if ',' in src: src = src.split(',', 1)[1]
    img = Image.open(BytesIO(base64.b64decode(src))).convert('RGBA')
    return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)

@lru_cache(maxsize=16)
def _round_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return mask

logger = logging.getLogger('unicon')

# ---------- 自动加载子模块 ----------
_here = Path(__file__).parent
for _mi in pkgutil.iter_modules([str(_here)]):
    _mod = importlib.import_module(f"cards.EndUID.{_mi.name}")
    globals()[_mi.name] = _mod

def clear_image_caches() -> list[str]:
    cleared: list[str] = []
    for name, mod in list(globals().items()):
        if not hasattr(mod, '__dict__'): continue
        try:
            for fn_name in ('_b64_img', '_b64_fit'):
                fn = getattr(mod, fn_name, None)
                if fn and hasattr(fn, 'cache_clear'):
                    try:
                        fn.cache_clear()
                        cleared.append(f"{name}.{fn_name}")
                    except Exception: continue
        except Exception: continue
    return cleared

# ---------- HTML → 模块 分流规则 ----------
_DISPATCH: list[tuple[list[str], str, str]] = [
    (['Endfield Daily', '每日监控协议'], 'end_daily_card', '终末地日常'),
    (['终末地公告', 'ann-card-id', 'detail-avatar'], 'end_ann_card', '终末地公告'),
    (['EndUID 更新记录', 'UPDATE LOG', 'log-emoji'], 'end_update_log', '终末地更新日志'),
    (['Endfield Player Card', 'char-left-info'], 'end_card', '终末地名片'),
    (['Endfield Build Card', 'spaceship-section'], 'end_build', '终末地建设'),
    (['终末地角色别名',  'alias-grid'], 'end_alias_card', '终末地别名'),
    (['Endfield Explore Card', '区域探索', 'explore-table'], 'end_explore', '终末地探索进度'),
    (['Endfield Gacha Help', '抽卡记录帮助', 'STEP 01: 获取数据'], 'end_gacha_help', '终末地抽卡帮助'),
    (['Endfield Gacha Record'], 'end_gacha_card', '终末地抽卡记录'),
    (['Endfield Character Card', 'char-info-left'], 'end_char_card', '终末地角色卡片'),
    (['Endfield Character Wiki', 'stats-table', 'feature-card'], 'end_wiki_char', '终末地角色图鉴'),
    (['Endfield Weapon Wiki', 'weapon-img-small'], 'end_wiki_weapon', '终末地武器图鉴'),
    (['卡池信息', 'CURRENT BANNERS', 'banner-card'], 'end_wiki_gacha', '终末地卡池信息'),
    (['page-subtitle', 'group-section' ], 'end_wiki_list', '终末地图鉴列表'),
    (['Endfield Calendar', '活动日历', 'pool-grid'], 'end_calendar', '终末地活动日历'),
]

def render(html: str) -> bytes | None:
    for keywords, mod_name, label in _DISPATCH:
        if any(kw in html for kw in keywords):
            mod = globals().get(mod_name)
            if mod is None:
                raise RuntimeError(f'模块 {mod_name} 未加载，请检查文件是否存在')
            logger.info('dispatch -> %s (%s)', mod_name, label)
            return mod.render(html)
    return None