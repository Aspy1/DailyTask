"""审计 P1：验收必须能用**合成数据**跑（公仓 CI 里 `data/` 不存在）。

复现（静态审查）：`acceptance_check.py` 把真实业务数据复制到固定临时目录，
递归哈希真实数据目录时**没有排除设置文件** → 拿含密钥的 `settings.ini` 当测试输入。
验收也不是"缺数据就跑不完"，而是本地与公仓 CI 各用各的数据、结论不可比。
"""

import json

import scripts.acceptance_check as ac


def test_digest_skips_the_secret_settings_file(tmp_path) -> None:
    """⭐ 哈希**不得**包含 `settings.ini`（那里面有真实密钥）。"""
    (tmp_path / "tasks.json").write_text('{"_version": 1}', encoding="utf-8")
    (tmp_path / "settings.ini").write_text("[Email]\npassword = 真实密钥\n", encoding="utf-8")

    digest = ac.digest_dir(tmp_path)

    assert "tasks.json" in digest
    assert not any("settings.ini" in key for key in digest), digest


def test_synthetic_seed_covers_two_semesters(tmp_path, monkeypatch) -> None:
    """合成工厂要覆盖：两学期 + 按学期三件套 + 共享的库存 / 记账。"""
    monkeypatch.setattr(ac, "SANDBOX", tmp_path)
    ac._seed_synthetic()

    registry = json.loads((tmp_path / "semesters.json").read_text(encoding="utf-8"))
    assert len(registry["semesters"]) == 2
    assert registry["current_semester"] == "sem_001"
    for name in ("courses.json", "tasks.json", "exams.json"):
        assert (tmp_path / "semesters" / "sem_001" / name).is_file(), name
    assert (tmp_path / "inventory.json").is_file()
    assert (tmp_path / "expenses.json").is_file()


def test_synthetic_files_load_in_the_real_models(tmp_path, monkeypatch) -> None:
    """合成数据必须能被**真实模型**加载（不是随便编的形状）。"""
    from src.models.course import CourseModel
    from src.models.exam import ExamModel
    from src.models.expense import ExpenseModel
    from src.models.inventory import InventoryModel
    from src.models.semester_registry import SemesterRegistry
    from src.models.task import TaskModel

    monkeypatch.setattr(ac, "SANDBOX", tmp_path)
    ac._seed_synthetic()
    folder = tmp_path / "semesters" / "sem_001"

    registry = SemesterRegistry(tmp_path / "semesters.json")
    assert [s["id"] for s in registry.semesters] == ["sem_001", "sem_002"]
    assert len(CourseModel(folder / "courses.json", registry).courses) == 1
    assert len(TaskModel(folder / "tasks.json").tasks) == 1
    assert len(ExamModel(folder / "exams.json").exams) == 1
    assert len(InventoryModel(tmp_path / "inventory.json").items) == 1
    assert ExpenseModel(tmp_path / "expenses.json").records == []


def test_build_sandbox_uses_synthetic_even_when_real_data_is_present(tmp_path, monkeypatch) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "semesters.json").write_text('{"private": true}', encoding="utf-8")
    monkeypatch.setattr(ac, "REAL_DATA", real)
    monkeypatch.setattr(ac, "SANDBOX", tmp_path / "sandbox")
    monkeypatch.setattr(ac, "SHOTS", tmp_path / "sandbox" / "shots")

    ac.build_sandbox()

    assert (tmp_path / "sandbox" / "semesters.json").is_file()
    assert "private" not in json.loads((tmp_path / "sandbox" / "semesters.json").read_text(encoding="utf-8"))
    assert (tmp_path / "sandbox" / "shots").is_dir()
