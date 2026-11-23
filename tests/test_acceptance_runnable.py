"""验收脚本自身的两个**可执行性**前提（审计 2026-11-21 P1 的复跑门槛）。

这两个问题都会让验收"跑不起来"，而跑不起来的门禁等于没有门禁：

1. 用户开着真实应用时，默认命名的单实例管道会被它接走 → 脚本被误判成"第二实例"
   并主动中止（`ARCHITECTURE` §3 已规定测试用 `LIFE_ASSISTANT_SINGLE_INSTANCE_KEY`）；
2. Windows 控制台默认 cp936，回执里的 `¥` / 中文截图路径会让 `print` 抛
   `UnicodeEncodeError`，脚本死在半途（`check_quality.py` 同一处理）。
"""

import inspect
import sys

import scripts.acceptance_check as ac


def test_acceptance_uses_an_isolated_instance_pipe() -> None:
    """⭐ 脚本必须换一条**独立管道**，否则无法与正在运行的应用共存。"""
    lines = [line.strip() for line in inspect.getsource(ac.main).splitlines()
             if line.strip() and not line.strip().startswith("#")]
    assignment = 'os.environ["LIFE_ASSISTANT_SINGLE_INSTANCE_KEY"]'

    assert any(line.startswith(assignment) for line in lines), "验收脚本没有换独立管道"
    # 必须在 `import src.app` **之前**赋值：key 在模块导入时求值
    assign_at = next(i for i, line in enumerate(lines) if line.startswith(assignment))
    import_at = next(i for i, line in enumerate(lines) if line.startswith("import src.app"))
    assert assign_at < import_at, "环境变量必须在 import src.app 之前设置"


def test_acceptance_keeps_the_pipe_unique_per_process() -> None:
    """同名管道并行跑两份验收会互相抢连接 → 用 pid 生成唯一名字。"""
    source = inspect.getsource(ac.main)

    assert "getpid()" in source


def test_acceptance_forces_utf8_console_output() -> None:
    """`¥` 在 cp936 下不可编码 —— 脚本必须先 reconfigure。"""
    assert callable(ac._configure_stdout)

    source = inspect.getsource(ac.main)
    assert "_configure_stdout()" in source


def test_acceptance_can_run_on_the_real_window() -> None:
    """⭐ 手册 §4.4 要求"在实际可见窗口复跑" —— 平台必须是**参数**，不能写死。

    这里钉住的是"脚本不该替用户决定只在离屏跑"：原来 `QT_QPA_PLATFORM` 被硬编码成
    `offscreen`，于是"真实窗口复跑"永远做不了（那成了脚本的假设，不是环境限制）。
    """
    source = inspect.getsource(ac.main)

    assert '"--platform"' in source, "缺 --platform 参数"
    assert 'os.environ["QT_QPA_PLATFORM"] = args.platform' in source, \
        "平台必须来自参数"
    assert 'os.environ["QT_QPA_PLATFORM"] = "offscreen"' not in source, \
        "平台被写死了"


def test_second_instance_subprocess_inherits_the_platform() -> None:
    """真实窗口模式下，第二实例子进程必须同平台 —— 否则那条断言没验证到东西。"""
    source = inspect.getsource(ac.main)

    assert 'os.environ.get("QT_QPA_PLATFORM", "offscreen")' in source, \
        "子进程没有沿用当前平台"
    assert 'os.environ["QT_QPA_PLATFORM"] = "offscreen"\\n        sys.path' not in source, \
        "子进程仍写死 offscreen"


def test_real_render_section_covers_dpi_focus_and_paint() -> None:
    """§1b 必须覆盖手册点名的四件事：DPI / 激活 / 焦点 / 真实绘制。"""
    source = inspect.getsource(ac.main)

    for token in ("devicePixelRatio", "isActiveWindow", "focusWidget",
                  "nextInFocusChain", "grab()"):
        assert token in source, f"§1b 缺 {token}"
    # 激活要等一轮事件循环（Windows 下立刻断言会误报 False）
    assert "QEventLoop" in source


def test_configure_stdout_is_safe_to_call_twice(capsys) -> None:
    """可重复调用（测试环境已经替换过流，不能因此抛异常）。"""
    ac._configure_stdout()
    ac._configure_stdout()

    # 编码能写 `¥` 就够了：cp936 下这一行会直接抛 UnicodeEncodeError
    sys.stdout.write("¥ 80/80\n")
    assert "¥" in capsys.readouterr().out


def test_teardown_stops_what_the_script_started() -> None:
    """脚本自己拉起的 App 必须收尾：否则 QTimer/QThread 让解释器退不干净。"""
    assert callable(ac._teardown)

    source = inspect.getsource(ac.main)
    assert "_teardown(app)" in source
