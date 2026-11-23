"""空仓库条件下跑合成数据验收（模拟公仓 CI）。

用法：`.venv\\Scripts\\python.exe scripts/acceptance_synthetic_check.py`
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.acceptance_check as ac  # noqa: E402


def main() -> int:
    code = ac.main()
    print("FAILED:", [row[0] for row in ac.RESULTS if not row[1]])
    return code


if __name__ == "__main__":
    sys.exit(main())
