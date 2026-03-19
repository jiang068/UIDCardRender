"""
cards.XutheringWavesUID
=======================
自动扫描本包内所有模块，并提供统一的 render(html) 分流入口。
新增卡片文件后无需修改此文件。
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

# ---------- 统一字体加载（供本包内所有卡片使用） ----------
_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
_FONT_CN_PATH = _ASSETS_DIR / "H7GBKHeavy.TTF"
_FONT_MONO_PATH = _ASSETS_DIR / "JetBrainsMono-Medium.ttf"
# 新增：日韩字体路径（请确保 assets 文件夹下有这两个文件，如果没有可以改成你实际使用的字体名）
_FONT_JP_PATH = _ASSETS_DIR / "NotoSansJP-Medium.ttf" 
_FONT_KR_PATH = _ASSETS_DIR / "NotoSansKR-Medium.ttf"


def get_font(size: int, bold: bool = False, family: Literal['cn', 'mono', 'jp', 'kr'] = 'cn') -> ImageFont.FreeTypeFont:
    """返回指定大小的字体。支持中、英等宽、日、韩四种 family。"""
    candidates: list[str] = []
    if family == 'cn':
        candidates = [str(_FONT_CN_PATH), "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    elif family == 'mono':
        candidates = [str(_FONT_MONO_PATH), "C:/Windows/Fonts/JetBrainsMono-Medium.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
    elif family == 'jp':
        candidates = [str(_FONT_JP_PATH), "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/msgothic.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    elif family == 'kr':
        candidates = [str(_FONT_KR_PATH), "C:/Windows/Fonts/malgun.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
        
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

# 预置常用字号
_COMMON_SIZES = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
                 22, 24, 26, 28, 30, 32, 34, 36, 38, 40,
                 42, 46, 48, 52, 56, 60, 72, 80]
for _s in _COMMON_SIZES:
    globals()[f"F{_s}"] = get_font(_s, family='cn')
    globals()[f"F{_s}B"] = globals()[f"F{_s}"]
    globals()[f"M{_s}"] = get_font(_s, family='mono')
    # 新增：预加载同尺寸的日韩字体变量 (Jxx, Kxx)
    globals()[f"J{_s}"] = get_font(_s, family='jp')
    globals()[f"K{_s}"] = get_font(_s, family='kr')


def find_font_file(family: Literal['cn', 'mono'] = 'cn') -> str | None:
    """返回第一个在本机/项目 assets 中存在的字体文件路径（不进行 truetype 加载），
    便于调试和确认实际会尝试加载哪个文件。
    """
    candidates = [str(_FONT_CN_PATH), "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"] if family == 'cn' else [str(_FONT_MONO_PATH), "C:/Windows/Fonts/JetBrainsMono-Medium.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
    for p in candidates:
        try:
            if Path(p).exists():
                return p
        except Exception:
            continue
    return None


def _is_cjk(ch: str) -> bool:
    """简单判断是否为中日韩统一表意文字/汉字等（用于分段渲染）。"""
    if not ch:
        return False
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF) or (0x3000 <= o <= 0x303F) or (0xFF00 <= o <= 0xFFEF)

# 【新增：定义判断纯英数字的函数】
def _is_pure_en_num(ch: str) -> bool:
    """判断是否为纯字母或数字，用于应用 Y 轴偏移。"""
    return 'a' <= ch <= 'z' or 'A' <= ch <= 'Z' or '0' <= ch <= '9'

# 【新增：判断韩文字符】
def _is_kr(ch: str) -> bool:
    o = ord(ch)
    # 覆盖主要韩文音节和字母组合
    return (0xAC00 <= o <= 0xD7AF) or (0x1100 <= o <= 0x11FF) or (0x3130 <= o <= 0x318F)

# 【新增：判断日文假名】
def _is_jp_kana(ch: str) -> bool:
    o = ord(ch)
    # 覆盖平假名和片假名
    return 0x3040 <= o <= 0x30FF

def draw_text_mixed(draw: ImageDraw.ImageDraw, xy: tuple, text: str,
                    cn_font: ImageFont.FreeTypeFont | None = None,
                    en_font: ImageFont.FreeTypeFont | None = None,
                    fill=(255, 255, 255, 255)) -> None:
    if cn_font is None: cn_font = F24
    if en_font is None: en_font = M24
    x, y = xy

    # 获取当前字体大小
    f_size_cn = getattr(cn_font, 'size', 24)
    f_size_en = getattr(en_font, 'size', 24)
    
    # 动态获取匹配尺寸的日韩字体
    jp_font = globals().get(f"J{f_size_cn}", cn_font)
    kr_font = globals().get(f"K{f_size_cn}", cn_font)

    # --- 核心改进：为不同语言定义 Y 轴动态偏移 (负数表示向上提) ---
    en_offset = -int(f_size_en * 0.20)
    jp_offset = -int(f_size_cn * 0.35)  # 日语假名偏低，向上提 35%
    kr_offset = -int(f_size_cn * 0.30)  # 韩语偏低，向上提 30%

    for ch in text:
        is_en = _is_pure_en_num(ch)
        
        # 智能分流判定与应用偏移
        if is_en:
            f = en_font
            draw_y = y + en_offset
        elif _is_kr(ch):
            f = kr_font
            draw_y = y + kr_offset
        elif _is_jp_kana(ch):
            f = jp_font
            draw_y = y + jp_offset
        else:
            # 汉字、标点符号等默认使用中文字体，不偏移
            f = cn_font
            draw_y = y
        
        draw.text((x, draw_y), ch, font=f, fill=fill)
        x += int(f.getlength(ch))


# ---------- 集中化的图像加载与缓存（只缓存来自磁盘的图片，data: URI/长 base64 不缓存） ----------
_BASE_DIR = Path(__file__).parent.parent


def _looks_like_base64(s: str) -> bool:
    if not s: return False
    # data: URIs explicitly considered base64
    if s.startswith('data:'): return True
    # 如果是非常长的纯 base64 字符串（无路径/协议）也视为直接解码的情况
    if len(s) > 200 and re.fullmatch(r'[A-Za-z0-9+/=\n\r]+', s):
        return True
    return False


@lru_cache(maxsize=16)
def _b64_img_from_path(p: str) -> Image.Image:
    # cached loader for local file paths only
    return Image.open(p).convert('RGBA')


def _b64_img(src: str) -> Image.Image:
    """Load an image from src.

    - If src is a data: URI or looks like a long base64 blob, decode immediately (no caching).
    - If src resolves to an existing local path (relative to project root or absolute), use
      a cached loader so repeated loads are fast.
    - Otherwise, fall back to decoding base64 directly (no caching).
    """
    if not src:
        raise ValueError('empty src')

    # direct base64 / data: URIs are not cached
    if _looks_like_base64(src):
        if ',' in src:
            src = src.split(',', 1)[1]
        return Image.open(BytesIO(base64.b64decode(src))).convert('RGBA')

    # try resolve as local path
    p = Path(src) if Path(src).is_absolute() else (_BASE_DIR / src)
    try:
        if p.exists():
            return _b64_img_from_path(str(p))
    except Exception:
        # if path checking fails, fallback to base64 decode
        pass

    # fallback: assume src is base64 content
    if ',' in src:
        src = src.split(',', 1)[1]
    return Image.open(BytesIO(base64.b64decode(src))).convert('RGBA')


@lru_cache(maxsize=32)
def _b64_fit_from_path(p: str, w: int, h: int) -> Image.Image:
    img = Image.open(p).convert('RGBA')
    return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)


def _b64_fit(src: str, w: int, h: int) -> Image.Image:
    # behave similarly to _b64_img regarding caching
    if not src:
        raise ValueError('empty src')
    if _looks_like_base64(src):
        if ',' in src: src = src.split(',', 1)[1]
        img = Image.open(BytesIO(base64.b64decode(src))).convert('RGBA')
        return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)

    p = Path(src) if Path(src).is_absolute() else (_BASE_DIR / src)
    try:
        if p.exists():
            return _b64_fit_from_path(str(p), w, h)
    except Exception:
        pass

    if ',' in src: src = src.split(',', 1)[1]
    img = Image.open(BytesIO(base64.b64decode(src))).convert('RGBA')
    return ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)


@lru_cache(maxsize=16)
def _round_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return mask

logger = logging.getLogger('unicon')

# ---------- 自动加载本包内所有子模块 ----------
_here = Path(__file__).parent
for _mi in pkgutil.iter_modules([str(_here)]):
    _mod = importlib.import_module(f"cards.XutheringWavesUID.{_mi.name}")
    globals()[_mi.name] = _mod


def clear_image_caches() -> list[str]:
    """Clear image-related lru_caches in child modules to avoid unbounded memory growth.

    This scans loaded submodules for common cache-backed helpers like `_b64_img` and
    `_b64_fit` and calls their `cache_clear()` if present. Returns a list of cleared
    symbol names for diagnostic purposes.
    """
    cleared: list[str] = []
    for name, mod in list(globals().items()):
        # only consider imported submodules (which are module objects)
        if not hasattr(mod, '__dict__'):
            continue
        try:
            for fn_name in ('_b64_img', '_b64_fit'):
                fn = getattr(mod, fn_name, None)
                if fn and hasattr(fn, 'cache_clear'):
                    try:
                        fn.cache_clear()
                        cleared.append(f"{name}.{fn_name}")
                    except Exception:
                        # best-effort: ignore failures per-module
                        continue
        except Exception:
            continue
    return cleared

# ---------- HTML → 模块 分流规则 ----------
# 每条规则：(关键字列表, 模块名, 日志标签)
# 按优先级从上到下匹配，命中即返回，不再继续。
_DISPATCH: list[tuple[list[str], str, str]] = [
    (['鸣潮伴行积分', 'COMPANION REWARD SYSTEM'],  'ww_reward_card',    '积分'),
    (['鸣潮海墟'],                                  'ww_slash_card',     '海墟'),
    (['鸣潮体力'],                                  'ww_stamina_card',   '体力'),
    (['鸣潮角色卡片', 'ROVER RESONANCE CARD'],      'ww_role_card',      '角色'),
    (['鸣潮深塔'],                                  'ww_abyss_card',     '深塔'),
    (['鸣潮全息战略'],                              'ww_challenge_card', '全息'),
    (['鸣潮角色别名' ],                   'ww_alias_card',     '别名'),
    (['鸣潮公告', 'ann-item'],                      'ww_ann_card',       '公告'),
    (['库洛币'],                                    'ww_bbs_coin',       '库洛币'),
    (['鸣潮探索度', 'SOLARIS EXPEDITION RECORD'],   'ww_explore_card',   '探索度'),
    (['Wuthering Waves Tower Wiki'],                'ww_challenge_wiki', '深塔图鉴'),
    (['Wuthering Waves Character Wiki'],            'ww_char_wiki',      '角色百科'),
    (['Wuthering Waves Item Wiki'],                 'ww_item_wiki',      '物品图鉴'),
    (['Wuthering Waves List Wiki', 'weapon-types-row'], 'ww_list_wiki',  '列表图鉴'),
    (['Wuthering Waves Matrix Wiki'],               'ww_matrix_card',    '深境矩阵'),
    (['Wuthering Waves Slash Wiki'],                'ww_slash_wiki',     '深渊深境'),
]


def render(html: str) -> bytes | None:
    """根据 HTML 内容特征分派到对应卡片渲染器。
    未命中任何规则时返回 None，由上层 cards.render 继续尝试其他子包。
    """
    for keywords, mod_name, label in _DISPATCH:
        if any(kw in html for kw in keywords):
            mod = globals().get(mod_name)
            if mod is None:
                raise RuntimeError(f'模块 {mod_name} 未加载，请检查文件是否存在')
            logger.info('dispatch -> %s (%s)', mod_name, label)
            return mod.render(html)
    return None
