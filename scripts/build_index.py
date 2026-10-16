"""Build search index for fuzzy matching — call after adding new courses/habits/items."""
import json
import sys
from pathlib import Path

# 让 `python scripts/build_index.py`（CWD = 仓库根）也能 import src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import semester_paths

DATA = Path(__file__).parent.parent / "data"


def build_index() -> None:
    index = {"courses": {}, "habits": {}, "items": {}}

    # Courses（按学期分文件：读**当前学期**那份）
    with open(semester_paths.resolve(DATA, "courses.json"), encoding="utf-8") as f:
        courses = json.load(f).get("courses", [])
    for c in courses:
        name = c["name"]
        # Generate abbreviations
        keys = {name.lower()}
        # Remove 课/程 suffix
        short = name.replace("课", "").replace("程", "")
        if short != name:
            keys.add(short.lower())
        # Split and add individual words
        for w in name.replace("(", " ").replace(")", " ").split():
            if len(w) >= 2:
                keys.add(w.lower())
        for k in keys:
            index["courses"].setdefault(k, []).append(name)

    # Habits
    with open(DATA / "habits.json", encoding="utf-8") as f:
        habits = json.load(f).get("habits", [])
    for h in habits:
        name = h["name"]
        keys = {name.lower()}
        for w in name.split():
            if len(w) >= 1:
                keys.add(w.lower())
        for k in keys:
            index["habits"].setdefault(k, []).append(name)

    with open(DATA / "search_index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"Index built: {len(index['courses'])} course keys, {len(index['habits'])} habit keys")

if __name__ == "__main__":
    build_index()
