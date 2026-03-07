# cards package
# 递归扫描 cards/ 下所有子包：
#   - 叶子模块注入到 cards 命名空间（支持 from cards import ww_xxx）
#   - 子包若暴露 render(html) 则自动注册到顶层分流链
# 新增子文件夹或卡片文件无需修改此文件。
from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

logger = logging.getLogger('unicon')

# 按发现顺序收集各子包的 render 函数
_sub_renders: list = []

def _load_subpackages(pkg_name: str, pkg_dir: Path) -> None:
    for mod_info in pkgutil.iter_modules([str(pkg_dir)]):
        full_name = f"{pkg_name}.{mod_info.name}"
        if mod_info.ispkg:
            sub = importlib.import_module(full_name)
            # 若子包暴露了 render，加入分流链
            if callable(getattr(sub, 'render', None)):
                _sub_renders.append(sub.render)
            # 继续递归（加载子包内的叶子模块到 cards 命名空间）
            _load_subpackages(full_name, pkg_dir / mod_info.name)
        else:
            mod = importlib.import_module(full_name)
            globals()[mod_info.name] = mod

_load_subpackages("cards", Path(__file__).parent)


def render(html: str) -> bytes:
    """顶层分流入口：依次尝试各子包的 render，第一个命中的返回结果。"""
    for sub_render in _sub_renders:
        result = sub_render(html)
        if result is not None:
            return result
    raise ValueError('未能匹配任何卡片渲染器，请检查 HTML 内容或在对应子包补充分流规则')
