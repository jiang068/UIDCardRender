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
