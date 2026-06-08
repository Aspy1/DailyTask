# 开发避坑记录

记录本项目开发中遇到的典型错误及其修复方案。

## 1. clicked 信号传参数污染

**现象**: 点击"调整"按钮，传给 `_quick_arrange(days)` 的参数 `days` 变成 `False`，快照显示"未来False天"

**根因**: Qt `QPushButton.clicked` 信号自动传 `checked=False` 作为第一个参数，覆盖了函数默认参数

**修复**: 用 lambda 包裹
```python
# 错误
btn.clicked.connect(self._quick_arrange)
# 正确
btn.clicked.connect(lambda: self._quick_arrange())
```

## 2. `_file_path` → `file_path` 属性名错误

**现象**: `AttributeError: 'DailyLogModel' object has no attribute '_file_path'`

**根因**: `BaseJsonModel` 的属性名是 `file_path`，不是 `_file_path`

## 3. f-string 内花括号未转义

**现象**: Python 代码中 `{"action":"add_plan"}` 等 JSON 示例被 Python 当作 f-string 插值解析

**修复**: f-string 内的花括号必须双写 `{{"action":"add_plan"}}`

## 4. 分隔符变量编号混乱 (sep4 未定义)

**现象**: `UnboundLocalError: cannot access local variable 'sep4'`

**根因**: 在已有 sep1-sep4 的状态栏中插入新组件，只改了局部编号，后面的 sep4 仍引用旧变量名

**修复**: 添加新分隔符时使用独立命名 (如 `sep_exam`) 或整体重写该段

## 5. AI 输出"未知操作: xxx"

**现象**: AI 生成了 `replace_plans` 指令，但执行器报"未知操作"

**根因**: 系统提示词里文档化了该操作，但 `_exec_one` 方法中未注册对应的 elif 分支

**修复**: 确保 prompt 中提到的每个 action 都在执行器中实现

## 6. 信号冲突 (两个 handler 接同一信号)

**现象**: "快速安排"点击没反应

**根因**: `quick_adjust_requested` 信号被 `main_workspace._on_quick_adjust`（填充 AI 输入框）和 `main_window._on_quick_arrange`（直接发 AI）同时连接，产生竞争

**修复**: 新建独立信号 `arrange_requested`，不共享

## 7. 替换文本未精确匹配导致代码残留

**现象**: 多次 `content.replace(old, new)` 后文件越来越大，含大量死代码

**根因**: old_string 与文件中实际文本不完全一致（空格/换行差异），Python 静默跳过

**修复**: 用 git checkout 回滚干净版 → 用精确的行级替换 → py_compile 验证

## 8. execute_code 忘记 import os

**现象**: `NameError: name 'os' is not defined`

**根因**: 每次 `execute_code` 调用是独立 Python 进程，不共享之前的 import

**修复**: 每个 execute_code 块开头都写全 import

## 9. Windows bash (MSYS) 工具故障

**现象**: `write_file`/`patch`/`read_file`/`terminal` 全部报 exit code 126 "builtin: not found"

**根因**: w64devkit 缺少运行时 DLL

**应对**: 所有文件操作改用 `execute_code` 内的 Python `open()` 进行

## 10. 语法检查缺失导致连锁错误

**现象**: 改 A 文件 → 提交 → B 文件报错（因为依赖了 A 的改动）

**修复**: 每次改完后 `py_compile` 全量扫描 `src/**/*.py`
