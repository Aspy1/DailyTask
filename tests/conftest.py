"""Pytest 全局配置。

- 把项目根与 tests/ 目录加入 sys.path，使 `import src...` / `import scripts.actions`
  和 `from helpers import ...` 在任意工作目录下都可用。
- 提供 `sandbox` fixture：把 actions.py 的数据目录重定向到临时目录，
  保证测试绝不触碰真实 data/。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent
for _p in (ROOT, TESTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import scripts.actions as actions  # noqa: E402


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """actions.py 的 DATA 指向 tmp_path，读写都发生在临时目录。"""
    monkeypatch.setattr(actions, "DATA", tmp_path)
    return tmp_path
