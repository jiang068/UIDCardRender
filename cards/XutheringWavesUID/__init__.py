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

# ---------- 统一字体加载（供本包内所有卡片使用） ----------
_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
_FONT_CN_PATH = _ASSETS_DIR / "H7GBKHeavy.TTF"
_FONT_MONO_PATH = _ASSETS_DIR / "JetBrainsMono-Medium.ttf"


def get_font(size: int, bold: bool = False, family: Literal['cn', 'mono'] = 'cn') -> ImageFont.FreeTypeFont:
    """返回指定大小的字体。
    - family='cn' 使用中文字体（优先 assets/H7GBKHeavy.TTF）
    - family='mono' 使用等宽英数字字体（优先 assets/JetBrainsMono-Medium.ttf）
    - bold: 如果为 True，暂时映射到同一字体文件（项目中未提供单独的 bold 字体），仅保留变量名兼容性。
    当 assets 中字体文件不可用时会回退到系统常见字体或 PIL 默认字体。
    """
    # NOTE: bold 参数在没有专门 bold 字体文件时不改变所选文件，保证 FxxB 变量存在且可用。
    candidates: list[str] = []
    if family == 'cn':
        candidates = [str(_FONT_CN_PATH), "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    else:
        candidates = [str(_FONT_MONO_PATH), "C:/Windows/Fonts/JetBrainsMono-Medium.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    # 最后退回到 PIL 内建默认字体（尺寸无法设置）
    return ImageFont.load_default()

# 预置常用字号和对应的 bold 变量（FxxB），以及对应的等宽英数字体 Mxx。
# 这里列出 repo 中常见/需要兼容的字号，保证旧代码中引用的变量名存在。
_COMMON_SIZES = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
                 22, 24, 26, 28, 30, 32, 34, 36, 38, 40,
                 42, 46, 48, 52, 56, 60, 72, 80]
for _s in _COMMON_SIZES:
    globals()[f"F{_s}"] = get_font(_s)
    # bold 变量名仍然映射到同一字体对象，保证兼容性（变量存在且可用）
    globals()[f"F{_s}B"] = globals()[f"F{_s}"]
    # 同尺寸的等宽英数字体
    globals()[f"M{_s}"] = get_font(_s, family='mono')


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

def draw_text_mixed(draw: ImageDraw.ImageDraw, xy: tuple, text: str,
                    cn_font: ImageFont.FreeTypeFont | None = None,
                    en_font: ImageFont.FreeTypeFont | None = None,
                    fill=(255, 255, 255, 255)) -> None:
    if cn_font is None: cn_font = F24
    if en_font is None: en_font = M24
    x, y = xy

    # --- 核心改进：动态计算 Y 轴偏移 ---
    # 获取当前英文字号大小
    f_size = getattr(en_font, 'size', 24)
    
    # 比例系数：根据视觉测试，JetBrains Mono 通常需要上提字号的 5% ~ 8%
    # 这里我们取一个中间值 0.07。
    # 这样：18px 提 ~1.2px；72px 提 ~5px。实现大字提得多，小字提得少。
    dynamic_offset = -int(f_size * 0.2) 

    for ch in text:
        is_en = _is_pure_en_num(ch)
        f = en_font if is_en else cn_font
        
        # 应用动态偏移
        draw_y = y + dynamic_offset if is_en else y
        
        draw.text((x, draw_y), ch, font=f, fill=fill)
        x += int(f.getlength(ch))

logger = logging.getLogger('unicon')

# ---------- 自动加载本包内所有子模块 ----------
_here = Path(__file__).parent
for _mi in pkgutil.iter_modules([str(_here)]):
    _mod = importlib.import_module(f"cards.XutheringWavesUID.{_mi.name}")
    globals()[_mi.name] = _mod

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
    (['鸣潮角色别名', 'ALIASES'],                   'ww_alias_card',     '别名'),
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
