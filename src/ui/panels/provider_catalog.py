"""AI 提供方目录（设置页下拉框的来源）。

从 `settings_panel.py` 抽出（那个文件需要保持在 800 行以内，Q-A1）。
纯数据，不依赖 Qt；加新提供方只改这里。
"""

from src.i18n.loader import tr

PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek", "endpoint": "https://api.deepseek.com",
        "model": "deepseek-chat", "key_placeholder": "sk-...",
        "key_url": "https://platform.deepseek.com",
    },
    "claude": {
        "name": "Claude (Anthropic)", "endpoint": "https://api.anthropic.com",
        "model": "claude-sonnet-4-20250514", "key_placeholder": "sk-ant-...",
        "key_url": "https://console.anthropic.com",
    },
    # 自定义端点：本地 / 自建 OpenAI 兼容服务（⚠ 端点必须以 `/v1` 结尾，少写会 404，
    # 界面只表现为"AI 没反应"）。URL / 模型名由用户在设置页自己填。
    "custom": {"name": tr("panel.settings.provider_custom"),
               "endpoint": "http://127.0.0.1:8000/v1",
               "model": "", "key_placeholder": tr("panel.settings.provider_key_hint"),
               "key_url": ""},
    # OpenCode Go（订阅制）：OpenAI 兼容端点 + 订阅 key。
    # ⚠ 必须用 /inference/go/... 这个地址；免费模型在**按量付费**端点会被
    # 403 FreeTierError 拦下（"free tier can only be used from within OpenCode"）。
    # 代码侧会自动补 x-opencode-session 与自定义 UA（见 ai_providers.provider_headers）。
    "opencode": {
        "name": "OpenCode Go", "endpoint": "https://opencode.ai/inference/go/openai/v1",
        "model": "longcat-2.5-preview-free", "key_placeholder": "sk-...",
        "key_url": "https://opencode.ai/console",
    },
}
