# 2026-11-02 AI 助手 harness 门禁修复（Restart gate fast）

- 关联 issue：`ISSUE-0002-harness-ai`（状态 fix）
- 失败 finding：`Gate fast failed`，输出
  `'.venv' 不是内部或外部命令，也不是可运行的程序或批处理文件。`
- 范围：只修门禁执行路径与由此暴露的 CLI 管道编码；不改 AI 监督语义、不碰真实 `data/`。

## 1. 根因

Restart 的 gate 配置（issue front matter）是：

```yaml
gate:
  fast:
    - .venv/Scripts/python.exe
    - -m
    - pytest
    - -q
```

`apps/control-plane/src/gates/runner.ts` 在 Windows 上固定 `shell: true`，
于是命令交给 `cmd.exe`。cmd 把 `/` 当开关分隔符，将 `.venv/Scripts/python.exe`
解析成“命令 `.venv` + 参数 `/Scripts/python.exe`”，因此 34ms 就失败，pytest 根本没启动。

实测：

```text
cmd> .venv/Scripts/python.exe --version
'.venv' 不是内部或外部命令...
cmd> .venv\Scripts\python.exe --version
Python 3.14.9
```

不能改 `.restart` 状态（issue gate 配置）——修复必须在工作区内。

## 2. 修复

1. **新增 `.venv.cmd` 前向器**：cmd 解析 `.venv` 时会命中 `.venv.cmd`（目录不可执行），
   并把 `/Scripts/python.exe` 作为第一个参数传入。前向器剥掉这一段，转发给真正的
   `.venv\Scripts\python.exe`；反斜杠形式仍由 cmd 直接执行，前向器不参与。
2. **`scripts/actions.py` 管道输出强制 UTF-8**：gate 通过 cmd 启动时没有
   `PYTHONIOENCODING=utf-8`，`scripts/actions.py status` 子进程按 cp936 写管道，
   而 `tests/test_delegation.py` 按 UTF-8 解码 → `Test_delegate...` 失败。
   `_force_utf8_stdio()` 只在**非 TTY**（管道/重定向）时把 stdout/stderr 改成 UTF-8，
   交互式控制台保持原代码页。
3. **Q-P1 白名单**：`scripts/check_quality.py` 的 `TOP_FILES` 与 `CODE_STANDARDS.md`
   加入 `.venv.cmd`，避免提交后顶层文件检查变红。
4. **回归测试** `tests/test_gate_shim.py`：在 Windows 上直接通过 cmd 运行
   `.venv/Scripts/python.exe`（含 `-m pytest --version`），非 Windows skip。

## 3. 验证

| 命令 | 结果 |
| --- | --- |
| `cmd /c .venv/Scripts/python.exe --version` | Python 3.14.9 |
| `cmd /c .venv/Scripts/python.exe -m pytest -q` | **1077 passed**（修复前 1 failed） |
| `pytest -q tests/test_delegation.py::test_delegate_end_to_end_assembles_fragmented_reply` | 1 passed |
| `pytest -q tests/test_gate_shim.py` | 2 passed |
| `ruff check src scripts plugins tests` | All checks passed |
| `compileall -q src scripts tests plugins` | 退出码 0 |
| `scripts/check_ui_tokens.py --strict --check-px` | 112 文件，违规 0 |
| `scripts/check_quality.py --strict` | ✓ 全部通过 |

## 4. 残余风险

- `.venv.cmd` 是 Windows/cmd 的兼容层；Linux/macOS 不受影响（不执行 `.cmd`）。
- 前向器会把参数原样交给 Python；当前 gate 参数固定，不接收用户输入。
- 本轮只提交门禁修复文件；AI 监督整改的其余工作树改动保持原样，未混入本 commit。
