"""基准产物的**归档**必须可复核（`PERFORMANCE_WORKFLOW.md` §5「保留原始样本」）。

手册要求"保留原始样本"、"报告记录基准 SHA、环境、命令和结果"。只存汇总
（中位 / P95）不够 —— P95 的秩、最大值、失败分布都在**逐次样本**里，
所以 `archive()` 必须把 `durations_ms` 一起落盘。

这里钉住四件事：

1. `archive()` 写出环境指纹 + 提交号 + 逐次样本；
2. `write_manifest()` 生成"每份产物是干什么的"清单（不留下无人认领的 json）；
3. **仓库里现有的产物**都带 `raw_samples`（报告引用的数字可复核）；
4. 报告里引用的档位在产物里真的存在（50k 缺口不许再出现）。
"""

import json
from pathlib import Path

import pytest

import scripts.perf_bench as bench


def test_measure_can_restore_real_mutation_before_each_iteration() -> None:
    states = []

    def prepare() -> None:
        states.append("pending")

    def complete() -> None:
        assert states[-1] == "pending"
        states[-1] = "completed"

    sample = bench.measure(complete, label="complete", repeat=3, warmup=2,
                           before_each=prepare)
    assert states == ["completed"] * 5
    assert len(sample.durations_ms) == 3
    assert sample.failures == 0

PERF_DATA = Path(__file__).resolve().parent.parent / "dev-logs" / "perf-data"


def _sample(values: list[float], label: str = "demo") -> bench.Sample:
    sample = bench.Sample(label=label)
    sample.durations_ms = values
    return sample


def test_archive_writes_environment_and_raw_samples(tmp_path, monkeypatch) -> None:
    """⭐ 归档必须含：环境指纹、提交号、逐次耗时。"""
    monkeypatch.setattr(bench, "ARTIFACT_DIR", tmp_path)
    payload = {"tiers": {"1000": [{"label": "x"}]}}
    samples = {"1000/x": _sample([1.0, 2.0, 3.0])}

    target = bench.archive("demo", payload, samples=samples)
    document = json.loads(target.read_text(encoding="utf-8"))

    assert document["environment"]["commit"]
    assert document["environment"]["python"]
    assert document["results"] == payload
    raw = document["raw_samples"]["1000/x"]
    assert raw["durations_ms"] == [1.0, 2.0, 3.0]
    assert raw["n"] == 3


def test_archive_survives_without_samples(tmp_path, monkeypatch) -> None:
    """没有逐次样本时也要能写（有些场景只有汇总）。"""
    monkeypatch.setattr(bench, "ARTIFACT_DIR", tmp_path)

    target = bench.archive("bare", {"ok": True})

    document = json.loads(target.read_text(encoding="utf-8"))
    assert "raw_samples" not in document
    assert document["results"] == {"ok": True}


def test_manifest_lists_every_artifact(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(bench, "ARTIFACT_DIR", tmp_path)
    bench.archive("alpha", {"a": 1})
    bench.archive("beta", {"b": 2})

    manifest = bench.write_manifest()

    text = manifest.read_text(encoding="utf-8")
    assert "alpha.json" in text and "beta.json" in text
    assert "不要手工编辑" in text


@pytest.mark.skipif(not PERF_DATA.is_dir(), reason="仓库里没有 perf-data")
def test_committed_artifacts_carry_raw_samples() -> None:
    """⭐ 仓库里已归档的产物都必须带逐次样本（否则"可复核"是空话）。"""
    missing = []
    for path in sorted(PERF_DATA.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if not document.get("raw_samples"):
            missing.append(path.name)
    assert not missing, f"这些产物只有汇总、没有原始样本：{missing}"


@pytest.mark.skipif(not PERF_DATA.is_dir(), reason="仓库里没有 perf-data")
def test_committed_artifacts_cover_the_three_tiers() -> None:
    """手册 §1.2 要求三档都测 —— 报告引用的档位必须在产物里找得到。"""
    panel = json.loads((PERF_DATA / "panel-lazy-construction.json")
                       .read_text(encoding="utf-8"))
    baseline = json.loads((PERF_DATA / "baseline-scenarios.json")
                          .read_text(encoding="utf-8"))

    assert {"1000", "10000", "50000"} <= set(panel["results"]["tiers"]), \
        "面板对照缺档位（50k 缺口不许再出现）"
    assert {"1000", "10000", "50000"} <= set(baseline["results"]["tiers"])


@pytest.mark.skipif(not PERF_DATA.is_dir(), reason="仓库里没有 perf-data")
def test_memory_and_decision_inputs_are_archived() -> None:
    """内存与方案 C 决策的输入也必须落盘（报告 §8/§9 引用它们）。"""
    memory = json.loads((PERF_DATA / "memory-panels.json").read_text(encoding="utf-8"))
    sqlite = json.loads((PERF_DATA / "sqlite-comparison.json")
                        .read_text(encoding="utf-8"))

    assert "steady" in memory["results"] and "idle" in memory["results"]
    assert "10000" in sqlite["results"]["tiers"]


REPORT = Path(__file__).resolve().parent.parent / "dev-logs" \
    / "2026-11-23-性能改造对比报告.md"


def _report_text() -> str:
    """读报告并归一化减号：文档用排版减号 `−`，代码格式化出 ASCII `-`。"""
    return REPORT.read_text(encoding="utf-8").replace("\u2212", "-")


@pytest.mark.skipif(not (PERF_DATA / "sqlite-comparison.json").exists(),
                    reason="仓库里没有 perf-data")
def test_report_quotes_the_archived_sqlite_numbers() -> None:
    """⭐ 报告里的数字必须能在归档里找到（否则报告与产物会各自漂移）。

    这条守卫来自一次真实偏差：§3.3 的表格曾引用**上一轮**的测量
    （39.47/98.68 ms），而归档里是 40.93/101.69 ms —— 结论没变，但数字对不上，
    复核的人会以为产物被换过。
    """
    text = _report_text()
    tiers = json.loads((PERF_DATA / "sqlite-comparison.json")
                       .read_text(encoding="utf-8"))["results"]["tiers"]

    missing = []
    for row in tiers["10000"]:
        for key in ("baseline", "candidate"):
            value = f"{row[key]['median_ms']:.2f} ms"
            if value not in text:
                missing.append(f"{row['label']} {key}={value}")
        p95 = f"{row['p95_improvement_pct']:+.1f}%"
        if p95 not in text:
            missing.append(f"{row['label']} P95={p95}")
    assert not missing, f"报告里的数字与归档不一致：{missing}"


@pytest.mark.skipif(not (PERF_DATA / "memory-panels.json").exists(),
                    reason="仓库里没有 perf-data")
def test_report_quotes_the_archived_memory_numbers() -> None:
    text = _report_text()
    memory = json.loads((PERF_DATA / "memory-panels.json")
                        .read_text(encoding="utf-8"))["results"]

    missing = []
    for section in ("steady", "idle"):
        part = memory[section]
        for key in ("eager", "lazy"):
            value = f"{part[key]['private_commit_mb']} MiB"
            if value not in text:
                missing.append(f"{section}.{key}={value}")
        delta = f"{part['delta_mb']:+.1f} MiB"
        if delta not in text:
            missing.append(f"{section}.delta={delta}")
    assert not missing, f"报告里的内存数字与归档不一致：{missing}"


@pytest.mark.skipif(not (PERF_DATA / "panel-lazy-construction.json").exists(),
                    reason="仓库里没有 perf-data")
def test_report_quotes_the_archived_panel_numbers() -> None:
    """三档面板表里的数字也必须对得上（50k 缺口关闭后新加的）。"""
    text = _report_text()
    tiers = json.loads((PERF_DATA / "panel-lazy-construction.json")
                       .read_text(encoding="utf-8"))["results"]["tiers"]

    missing = []
    for tier in ("1000", "10000", "50000"):
        for row in tiers[tier]:
            value = f"{row['baseline']['median_ms']:.2f} ms"
            if value not in text:
                missing.append(f"{tier} {row['label']} base={value}")
    assert not missing, f"报告里的面板数字与归档不一致：{missing}"
