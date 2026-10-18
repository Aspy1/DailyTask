"""位置**同义说法**归一（用户用例表第 12 / 24 条）。

用户原话（第 24 条备注）："我认为搜索应该加模糊功能 比如外侧=外面=外边 但是衣柜=！柜子"。

所以这里的边界很硬：

1. **只归一真正的同义词**（桌子=桌面、外面=外边=外侧、衣柜N→衣柜左N）；
2. **衣柜 ≠ 柜子** —— 不做模糊/子串匹配，别把两组格位混起来；
3. 「外侧 / 外面 / 外边」按用户口径是**位置的位置**（写进 `notes`），
   归一是为了让"搜外面"也能命中 notes 里写着"外侧"的东西。
"""

from src.models.inventory import canonical_location


def _items(sandbox) -> list[dict]:
    import json

    path = sandbox / "inventory.json"
    return json.loads(path.read_text(encoding="utf-8"))["items"] if path.exists() else []


def _locations(sandbox) -> list[str]:
    import json

    path = sandbox / "inventory.json"
    return json.loads(path.read_text(encoding="utf-8")).get("locations", []) if path.exists() else []


def test_canonical_location_maps_only_true_synonyms() -> None:
    assert canonical_location("桌子") == "桌面"
    assert canonical_location("桌面") == "桌面"
    assert canonical_location("外面") == "外侧"
    assert canonical_location("外边") == "外侧"
    assert canonical_location("衣柜3") == "衣柜左3"
    # ⚠ 用户明确要求保留区别：柜子不是衣柜
    assert canonical_location("柜子1") == "柜子1"
    assert canonical_location("衣柜左1") == "衣柜左1"
    # 没登记的照原样返回，别自作主张
    assert canonical_location("药箱") == "药箱"
    assert canonical_location("") == ""


def test_add_item_stores_the_canonical_location(sandbox) -> None:
    """说"桌子"要存成"桌面"，否则词表会因为换个说法就分叉。"""
    from tests.helpers import run

    assert run('add_item --name "茶包" --quantity 20 --location "桌子"').startswith("OK")

    assert _items(sandbox)[0]["location"] == "桌面"
    assert "桌面" in _locations(sandbox)
    assert "桌子" not in _locations(sandbox), "同义说法不该进词表"


def test_update_item_canonicalizes_location(sandbox) -> None:
    from tests.helpers import run

    iid = run('add_item --name "茶包" --quantity 20').split()[2]
    run(f'update_item --id {iid} --location "桌子"')
    assert _items(sandbox)[0]["location"] == "桌面"


def test_add_location_canonicalizes_and_does_not_duplicate(sandbox) -> None:
    from tests.helpers import run

    run('add_location --name "桌子"')
    assert "桌面" in _locations(sandbox)
    assert "桌子" not in _locations(sandbox)


def test_lookup_by_synonym_finds_the_item(sandbox) -> None:
    from tests.helpers import run

    run('add_item --name "茶包" --quantity 20 --location "桌子"')
    out = run('lookup_item --location "桌子"')
    assert "FOUND" in out, out
    assert "茶包" in out


def test_lookup_by_wearside_synonym_finds_notes(sandbox) -> None:
    """「外侧」是"位置的位置"，写在 notes 里 —— 搜"外面"也该找得到。"""
    from tests.helpers import run

    run('add_item --name "被罩" --quantity 1 --location "衣柜3" --notes "外侧"')

    for word in ("外侧", "外面", "外边"):
        out = run(f'lookup_item --location "{word}"')
        assert "FOUND" in out, f"{word} 应该能找到：{out}"
        assert "被罩" in out


def test_wardrobe_and_cabinet_stay_distinct(sandbox) -> None:
    """用户红线：衣柜 ≠ 柜子。模糊匹配不能把这两组格位混起来。"""
    from tests.helpers import run

    run('add_item --name "被罩" --quantity 1 --location "衣柜1"')
    run('add_item --name "工具箱" --quantity 1 --location "柜子1"')

    assert "工具箱" not in run('lookup_item --location "衣柜1"')
    assert "被罩" not in run('lookup_item --location "柜子1"')

    # 衣柜没说哪一侧一律算左（用户口径）
    assert "被罩" in run('lookup_item --location "衣柜1"')
    assert "被罩" in run('lookup_item --location "衣柜左1"')
