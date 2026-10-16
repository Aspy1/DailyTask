"""DeepSeek 余额查询适配（**唯一**实现）。

此前有两份：`api_service._fetch_deepseek_balance_sync`（返回 dict）与
`ai_service._fetch_deepseek_balance`（内联 HTTP，返回格式化字符串）。
现在统一到这里，两边都调用 `fetch_balance()`（CODE_STANDARDS Q-A3）。

契约：**永不抛异常**；失败返回 `{"error": <可读信息>, "error_kind": ...}`，
`error_kind ∈ {"config", "http", "network"}` 供调用方决定呈现方式
（例如 `ai_service` 对网络错误给空串、对 HTTP 错误给"查询失败"）。
"""

import logging
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

BALANCE_URL = "https://api.deepseek.com/user/balance"
PLACEHOLDER_KEY = "sk-..."


def fetch_balance(api_key: str, timeout: int = 5) -> dict[str, Any]:
    """查询 DeepSeek 余额；失败返回带 `error` 的 dict（不抛异常）。"""
    if not api_key or api_key.startswith(PLACEHOLDER_KEY):
        return {"error": "请先配置有效的 API Key", "error_kind": "config"}

    status = 0
    try:
        resp = requests.get(
            BALANCE_URL,
            headers={"Accept": "application/json", "Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError:
        logger.warning("DeepSeek 余额返回 HTTP %s", status)
        return {"error": f"HTTP {status}", "error_kind": "http"}
    except (OSError, ValueError, KeyError, TypeError) as e:
        logger.debug("DeepSeek 余额查询失败", exc_info=True)
        return {"error": str(e), "error_kind": "network"}

    infos = data.get("balance_infos", [])
    total = sum(float(i.get("total_balance", 0)) for i in infos)
    return {
        "total_balance": total,
        "currency": "CNY",
        "balance_infos": infos,
        "is_available": total > 0,
        "timestamp": datetime.now().isoformat(),
    }
