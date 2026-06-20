"""Build search index for fuzzy matching — call after adding new courses/habits/items."""
import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

def build_index():
    index = {"courses": {}, "habits": {}, "items": {}}

    # Courses
    courses = json.load(open(DATA / "courses.json", encoding="utf-8")).get("courses", [])
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
    habits = json.load(open(DATA / "habits.json", encoding="utf-8")).get("habits", [])
    for h in habits:
        name = h["name"]
        keys = {name.lower()}
        for w in name.split():
            if len(w) >= 1:
                keys.add(w.lower())
        for k in keys:
            index["habits"].setdefault(k, []).append(name)

    json.dump(index, open(DATA / "search_index.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"Index built: {len(index['courses'])} course keys, {len(index['habits'])} habit keys")

if __name__ == "__main__":
    build_index()
