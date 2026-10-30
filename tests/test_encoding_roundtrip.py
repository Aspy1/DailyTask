"""中文经由 `actions.py` 写入后必须**原样**存下来（不许变成 `????`）。

为什么单独一条：2026-10-20 的课程表乱码，就是"中文参数走错入口"留下的 `????????` ✗。
`run_in_process()` 是 **AI 那条写入路径** —— 它要是吞中文，AI 记的每一件中文物品都会乱码 ✗✗。
（已用探针确认现在是对的 ✓，这条防止回退。）
"""



def test_actions_path_preserves_chinese(sandbox) -> None:
    from scripts.actions import run_in_process

    out = run_in_process('add_item --name "布洛芬" --category "日常消耗品" '
                         '--quantity 1 --location "床头柜"')
    assert out.startswith("OK"), out

    import json
    from pathlib import Path

    data = json.loads((Path(sandbox) / "inventory.json").read_text(encoding="utf-8"))
    item = data["items"][0]
    assert item["name"] == "布洛芬", f"名字被写坏：{item['name']!r}"
    assert item["category"] == "日常消耗品"
    assert item["location"] == "床头柜"
    assert "?" not in item["name"] + item["category"] + item["location"]


def test_course_path_preserves_chinese(sandbox) -> None:
    """课程那几个字段（名字 / 教师 / 地点）同样要原样存住。"""
    import json
    from pathlib import Path

    from scripts.actions import run_in_process

    out = run_in_process('add_course --name "形式语言与自动机" --day 2 '
                         '--weeks 4-11 --slots 1-1 --location "33楼310" --teacher "王鑫"')
    assert out.startswith("OK"), out

    semester = json.loads((Path(sandbox) / "semesters.json").read_text(encoding="utf-8"))
    sem = semester["current_semester"]
    data = json.loads((Path(sandbox) / "semesters" / sem / "courses.json")
                      .read_text(encoding="utf-8"))
    course = data["courses"][0]
    assert course["name"] == "形式语言与自动机"
    assert course["teacher"] == "王鑫"
    assert course["time_slots"][0]["location"] == "33楼310"
    assert "?" not in json.dumps(course, ensure_ascii=False)
