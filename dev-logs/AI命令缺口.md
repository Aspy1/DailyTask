# AI 命令缺口 — 待同步清单

> 目的：记录 model 层已有但 actions.py / SYSTEM_PROMPT / TG bot skill 尚未暴露的命令。
> 统一在此登记，批量修改时避免遗漏。

## 同步矩阵

| 命令 | model | actions.py | SYSTEM_PROMPT | TG skill | 备注 |
|---|---|---|---|---|---|
| add_item | ✅ | ✅ | ✅ | ❌ | cmd 缺 `--tags` 参数 |
| update_item | ✅ | ✅ | ✅ | ❌ | |
| delete_item | ✅ | ✅ | ✅ | ❌ | |
| lookup_item | ✅ | ✅ | ✅ | ❌ | |
| need_restock | ✅ | ✅ | ✅ | ❌ | |
| consume | ✅ | ❌ | ❌ | ❌ | 消耗 N 次（洗发水用一次减量） |
| remaining_doses | ✅ | ❌ | ❌ | ❌ | 查询剩余可用次数 |
| all_tags | ✅ | ❌ | ❌ | ❌ | 列出所有标签（AI 可读 _build_inventory_list） |
| stock_count | ✅ | ❌ | ❌ | ❌ | 充足物品数量（AI 可读 status） |

## 已发现的具体缺口

### 1. TG bot skill 缺少物品段
- **文件**: `~/.hermes/skills/life-assistant-data/SKILL.md`
- **缺失**: add_item, update_item, delete_item, lookup_item, need_restock 全部不在关键词表里
- **影响**: TG 端无法管理库存

### 2. cmd_add_item 缺 --tags
- **文件**: `scripts/actions.py` → `cmd_add_item()`
- **现状**: argparse 已定义 `--tags` 参数，但函数体未写入 item dict
- **影响**: AI 添加物品时不能同时设标签

### 3. consume 命令不存在
- **文件**: `scripts/actions.py`
- **现状**: model 有 `InventoryModel.consume(iid, amount)` 但 actions.py 无 `cmd_consume`
- **影响**: AI 不能记录消耗（"洗发水用了一次"）

## 修改时需同步的 4 个位置

改任何一条命令后必须检查：
1. `scripts/actions.py` — argparse 定义 + handler + run_in_process 的 _defaults
2. `src/services/ai_service.py` — SYSTEM_PROMPT_BASE 可用命令列表
3. `~/.hermes/skills/life-assistant-data/SKILL.md` — TG bot 关键词表
4. `scripts/actions.py` — main() + run_in_process 两处 handlers 注册
