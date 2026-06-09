插件系统说明

位置: ./plugins/<plugin_name>/

约定:
- IsOpen.able: 表示插件启用
- IsOpen.able.disable: 表示插件禁用（将文件重命名为带 .disable 即可）
- plugin.py: 可选，定义 `register(api)` 函数。通过 `api.register_panel(name, factory)` 注册面板。

工厂函数签名:
- `(settings, ai_service, data_manager, parent=None) -> QWidget`

运行时行为:
- 程序启动时扫描 `./plugins` 子文件夹，导入 `plugin.py`（尽量容错）。
- 所有插件都会列出在设置页面的“插件”卡片中，可以在程序内启用/禁用（通过重命名 IsOpen.able 文件实现）。
- 被启用的插件其面板可从设置页面打开（作为独立窗口）。

示例:
- `plugins/pomodoro/` 提供一个番茄钟面板用于测试插件系统。

注意事项:
- 插件代码不应假设主程序的内部实现；应通过传入的 `settings`、`ai_service`、`data_manager` 使用受限接口。
- 插件异常不会阻塞主程序，但当前实现不会热插拔所有功能，建议在更改配置后重启以保证一致性。
