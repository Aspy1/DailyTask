# WebView2 周视图迁移准备

首批范围是一个可选的只读周视图。PySide6 保留主窗口、桌面流程及原生周视图。Python 继续负责学期、周次、数据和通知。对照样本采用合成数据。

## 1. 核对环境并生成对照页

本机已确认 .NET SDK 10.0.402、Windows Desktop Runtime 10.0.13，以及注册表记录的 Evergreen Runtime 158.0.4370.33。注册表只能证明已登记，仍须通过宿主初始化确认可用。部署时优先使用 Evergreen，运行时缺失时保留 Qt 入口。 [Microsoft 运行时检测与分发](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)

从 Git Bash 在仓库根执行。命令只生成两份自包含合成页面。

```bash
./.venv/Scripts/python.exe scripts/perf_week_web.py --export-fixtures .pytest_cache/webview2-fixtures
QT_QPA_PLATFORM=windows ./.venv/Scripts/python.exe scripts/perf_week_web.py
```

两份页面具有不同数据，标题分别变为 `week-ready-0` 和 `week-ready-1` 时表示 DOM 已构造并经过两次动画帧回调。它是可跨引擎比较的就绪代理，另用可见窗口验证实际显示、后续输入和焦点。

## 2. 独立宿主实验

仓库内的独立探针已锁定官方 SDK 1.0.4370.26。用以下命令构建和运行。第二个参数是独立的浏览器用户数据目录，换新目录可试验首次建档。

```bash
export DOTNET_CLI_HOME="$PWD/.pytest_cache/webview2-dotnet"
export NUGET_PACKAGES="$PWD/.pytest_cache/webview2-nuget"
export NUGET_HTTP_CACHE_PATH="$PWD/.pytest_cache/webview2-nuget-http"
export DOTNET_GENERATE_ASPNET_CERTIFICATE=false DOTNET_CLI_TELEMETRY_OPTOUT=1
dotnet build scripts/webview2_probe/WebView2Probe.csproj -c Release --nologo
./scripts/webview2_probe/bin/Release/net10.0-windows/WebView2Probe.exe .pytest_cache/webview2-fixtures .pytest_cache/webview2-profile
```

本机探针已构建和运行。一次从宿主计时开始到首周就绪约 2.47 秒，预热后 10 次换页中位数 13.0 ms，P95 18.6 ms。该试跑只确认独立宿主和夹具可用，尚缺空闲进程树内存、重复冷启动、同条件对照和 Qt 嵌入测试。

1. 用独立 WPF 宿主扩大样本，覆盖 Runtime 初始化、离线加载本地两页、标题回执、失败退出。给每次独立冷启动使用明确的用户数据目录策略，区分首次建档与重复启动。 [Microsoft WPF 快速入门](https://learn.microsoft.com/en-us/microsoft-edge/webview2/get-started/wpf)
2. 记录宿主启动、CoreWebView2 初始化、首周就绪、后续换周和失败时间。每次导航等好当前标记再发下一次，连续换周另测请求竞争与错误恢复。Qt Widgets、Qt WebEngine、WebView2 用同样的数据、窗口和 DPI，测按需启动与进程树内存。首周则同时报告从启动到就绪的总时间。
3. 独立 WPF 窗口用于比较引擎和验证 SDK。进入 Qt 嵌入试验时另验 Win32 子窗口宿主方式与 PySide6 的 HWND 生命周期，重点验证 DPI、缩放、键盘焦点、Tab、层叠和退出。嵌入成本单独测量。

## 3. 进入应用前的接口与回退

- **页面来源**。使用固定本地来源与打包资源，将生产 UI、样式和合成基准夹具分离。主机校验来源、消息格式和字段大小。外部导航交给系统浏览器，限制弹窗、下载和权限请求。 [加载本地内容](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/working-with-local-content) · [WebView2 安全实践](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/security)
- **只读契约**。第一批消息包括页面就绪与渲染回执。宿主提供当前周的完整快照，按 `request_id` 和学期、周次版本丢弃旧响应。课程名称、地点和备注使用文本节点。周切换由宿主提供数据，随后在已加载页面内更新并单独测量该路径。
- **启用方式**。先默认使用 Qt，实验开关按需创建单个 WebView2。Runtime 缺失、导航失败、响应超时或渲染进程失败时恢复 Qt 当前周。关闭视图只回收本应用创建的宿主与环境，避免影响共用浏览器进程。
- **准入**。首次打开周视图的额外等待上限为 **250 ms**。在同一机器、同一数据和同一窗口条件下，从用户触发切换计时到周视图内容可见且可以交互，比较 WebView2 与原生 Qt 的 P95。若采用预热，额外验收应用冷启动和进程树内存。通过预算及两主题、窄窗口、高 DPI、键盘、离线和故障回退验收后，再接入可关闭的只读试点。当前嵌入探针一次到就绪标记约 2.52 秒，暂保留原生周视图。 [Microsoft 性能指南](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/performance)
