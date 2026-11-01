# 2026-11-01 全量验证原始输出

本目录保存可复核的**原始命令输出**，不是事后转述。

| 文件 | 命令 | 结果 |
|---|---|---|
| `pytest.txt` | `.venv/Scripts/python.exe -m pytest -q` | `895 passed` / exit 0 |
| `button_smoke.txt` | `.venv/Scripts/python.exe scripts/ui_button_smoke.py` | `131 clicked / 0 errors` / exit 0 |
| `walkthrough.txt` | `.venv/Scripts/python.exe scripts/ui_walkthrough.py` | `39/39` / exit 0 |
| `acceptance.txt` | `.venv/Scripts/python.exe scripts/acceptance_check.py` | `79/79`；真实 data 129 文件哈希一致 / exit 0 |
| `ui_render.txt` | `scripts/ui_render.py --out shots-modern` | `49 screenshots` / exit 0 |
| `visual_audit.txt` | `scripts/ui_visual_audit.py` | `18/18` / exit 0 |
| `gates.txt` | compileall / ruff / token / quality | 全部 exit 0；token 0 违规；quality 0 新增 |

## 截图识别证据

`screenshots/` 是从 `shots-modern/` 复制的**实际 Qt 截图**（offscreen + 系统字体），
不是原型图：

- `dialog-weather.png`：天气详情 360×366；三行预报完整显示
  `2026-11-02 多云 7°C ~ 15°C`、`2026-11-03 晴 8°C ~ 17°C`、
  `2026-11-04 小雨 雨量2.4mm 9°C ~ 14°C`；标题"实时天气"，无重复的"天气详情"。
- `light-narrow-expenses-ai.png`：990×638 + AI 展开；5 张汇总卡换行且全部在面板内；
  侧栏"记账"高亮；状态栏"天气: 8°C 小雨"；新增"支出"标签。
- `light-routines.png`：空态卡片 420px 阅读宽，说明两行不裁切，`+ 新增` 在卡内。
- `light-settings-0.5.png`：设置页中部；"保存"为主按钮、"发送测试邮件"为次按钮，
  天气统计/关闭开关可见。

`visual_audit.txt` 同时打印了天气每行标签的**实际文本与 isVisible**，以及窄窗汇总卡
`panel_width=545` 和 5 张卡的右边界，避免"只截了图但没识别内容"。

## 复跑方式

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/ui_button_smoke.py
.venv/Scripts/python.exe scripts/ui_walkthrough.py
.venv/Scripts/python.exe scripts/acceptance_check.py
QT_QPA_FONTDIR=C:\Windows\Fonts \
  .venv/Scripts/python.exe scripts/ui_render.py --out shots-modern
.venv/Scripts/python.exe scripts/ui_visual_audit.py
```
