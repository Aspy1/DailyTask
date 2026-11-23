# Hermes 微信接入

本机 Hermes v0.23.3 位于 `D:/Dev/hermes-agent`，独立配置与凭据位于
`D:/Dev/hermes-home`。模型使用内置 `opencode-go` 提供方与
`deepseek-v4.1-flash`，接口为 `https://opencode.ai/zen/go/v1`。
Go Key 由用户保存在 Hermes `.env` 的 `OPENCODE_GO_API_KEY`；不要粘贴到聊天或提交仓库。
项目的 `data/settings.ini` 不参与这项接入。

## 可用操作

| 工具 | 范围 |
|---|---|
| `daily_task_query` | 默认查询本机时间、当前学期、课程、作业状态和指定日期日程；`scope=inventory` 查询“有什么”物品与提醒，`scope=restock` 只查询待续费/补买提醒 |
| `daily_task_update` | 作业、课程、日程的新增/完成/修改；库存的新增 `add_item`、修改 `update_item`、消耗 `consume` |
| `daily_task_documents` | 列出和复制受支持的文档与图片，读写 UTF-8 的 TXT、Markdown、CSV、TSV、JSON |

桌面设置的「Hermes 微信网关」提供「启动 Hermes」和「重启 Hermes」。启动调用
`gateway run`，重启调用 `gateway run --replace`。桌面默认使用 `D:/Dev/hermes-home`，
也可由启动环境的 `HERMES_HOME` 指定安装位置。按钮回执表示进程已发起，微信连通性需由网关确认。
同一张卡片每 3 秒刷新网关状态。运行中的网关显示绿色「在线」，未运行显示灰色「离线」。
桌面会核对状态文件里的 PID 和进程启动时间，避免旧记录或 PID 被复用时误报。该指示反映网关运行状态，微信连通性另行确认。

启用文件工具时，在 Hermes 插件设置中填入 `document_dir` 的绝对路径，并把需要委托的
文档放进该目录。当前使用 `D:/Dev/hermes-home/documents`，这是 Hermes home 内专门允许的
文档子目录，文件工具无法访问同级的凭据或配置。只读写显式支持的格式，每份文本上限 512 KiB。覆盖已有内容
要先读取版本指纹，创建时使用 `revision=new`。PDF、Office 文件和常见图片可复制，单份上限
64 MiB，复制不覆盖同名目标。应用结构化数据继续通过
`daily_task_query` 和 `daily_task_update` 操作。

库存查询返回物品 ID、名称、数量/单位、分类、位置、备注、标签及可用的库存细节。数量可按整单位修改，
也可用 `consume` 按小单位扣减；修改名称、分类、分组、备注、标签、位置、库存阈值、会员、
到期/洗涤与账单字段后，桥接器逐字段回读验收。空备注、标签和分组可清除。

先查询再修改已有条目；课程名重复时需要明确目标。课程节次是 1–6 的**大节**，
区间首尾都包含。日程日期使用 `YYYY-MM-DD`，缺少必要时间信息时由助手询问。
修改课程只传待修改字段。没有修改作业、删数据、整日覆盖或远程恢复工具。

库存提醒只在用户提问并调用查询工具时返回；桌面端另有每日一次的补货/续费通知。
提醒只覆盖学校侧且未忽略低库存的物品：会员到期 7 日内或已过期时提示续费（自动续费也提示核对扣款），
以及预计即将用完、低库存或商品临期的补买提醒。会员查询不会读取私有联系人手机号。
删除物品需要交互审批，微信桥没有审批界面，因此不开放；课程、作业和日程也没有删除、整日覆盖或远程恢复工具。
写入返回 `ok`、`verification`、`coverage`、请求 ID 与可用时的快照 ID。
`verified_noop` 表示状态已经满足，不必再执行；`coverage` 表示实际核对的字段数，
不能将部分字段验收当作完整核验。超时、崩溃或缺少可信回执时，先查询核对，
禁止自动重试新增操作，以免重复创建。备份/恢复仍使用项目现有人工操作流程。

## 部署

### 微信定时提醒

Hermes Cron 使用独立的免模型任务，每 5 分钟检查作业，每 15 分钟检查考试。吃饭任务在
午饭和晚饭窗口每 5 分钟检查，与首页共用 11:40、16:40 和 90 分钟有效期规则。
作业 3 天和 6 小时提醒独立去重，考试在 14、7、3 天阈值合并提醒，吃饭每天每顿一次。
作业 3 天提醒跟随桌面总开关。桌面启动或保存设置时发布一份只包含开关值的本机状态。
考试、作业紧急提醒和吃饭规则不依赖该开关。正式任务只发到现有微信私聊。

任务通过 `scripts/hermes_reminders.py` 读取当前学期的业务数据。运行入口放在 Hermes
的 `scripts/`，去重账本放在 Hermes 的 `cron/`。没有命中时脚本保持安静。Hermes
网关需要在线才能投递。任务记录“已产出”后由 Hermes 负责发送，微信故障时以 Hermes
运行日志为准。

账本在产出时记录 `pending`。已安装的任务从 Hermes 运行账本关联唯一活动执行，
下一轮只按同一执行 ID 核对投递结果，确认后标记 `delivered`。
失败或等不到确认的批次进入 `uncertain`，需人工核对，脚本不重发。
排查时用 `ledger_states()` 查看历史确认情况。网关是否在线由独立进程探针判断。

仓库中的 `scripts/hermes_plugin/` 是插件源码。将其中四个文件（包括 `documents.py`）复制到
`D:/Dev/hermes-home/plugins/daily-task/`，保留原相对文件名，再运行：

```bash
export HERMES_HOME=D:/Dev/hermes-home
/d/Dev/hermes-home/bin/hermes.exe plugins validate D:/Dev/hermes-home/plugins/daily-task
/d/Dev/hermes-home/bin/hermes.exe plugins enable daily-task
/d/Dev/hermes-home/bin/hermes.exe plugins doctor daily-task --ci
```

在 Hermes 配置中设置 `plugins.entries.daily-task.settings.workspace` 为本仓库绝对路径，
`python` 为项目 `.venv/Scripts/python.exe` 的绝对路径。模型不能更改这些路径。
`data_dir` 默认 `<workspace>/data`，`instance_key` 默认沿用应用；二者仅供操作者做隔离测试。
启用插件后最后确认 `platform_toolsets.weixin` **仅含** `daily_task`，
防止启用流程自动增补其它工具集。独立工作目录本身不构成系统文件沙箱。
本机将 `tools.tool_search.enabled` 设为 `off`，直接向模型展示这两个工具，
避免为两项业务能力再经过工具搜索代理。

微信保持仅扫码账号私聊、群聊关闭。填好 Key 后启动：

```bash
export HERMES_HOME=D:/Dev/hermes-home
/d/Dev/hermes-home/bin/hermes.exe gateway run
```

插件和提示更新后重启网关，并在微信发送 `/new` 开始新会话。
插件部署副本需要在源码变更后重新复制；项目桥接脚本每次调用启动新进程，读取当前源码。
桌面应用已启动时，委派接受端使用其内存中的代码，更新 `actions.py` 后应重启桌面应用。
数据变更通过应用委派后的刷新或现有 3 秒轮询显示；这与 Python/UI 代码热重载不同。
本次接入不设置开机自启动。

## 隔离验收

所有写入测试使用 `sandbox`，子进程同时设置临时 `LIFE_ASSISTANT_DATA_DIR` 和
唯一 `LIFE_ASSISTANT_SINGLE_INSTANCE_KEY`，防止被真实应用的通信通道接走。
覆盖真实 CLI 写入、委派参数解析、字段保持、写前备份、只读查询、
敏感参数脱敏、未知操作拒绝、特殊字符字面量、部分验收及超时不重试。
当前工作区插件源码已扩展库存查询、库存新增/修改/消耗和续费/补买提醒。部署副本在源码变更后
必须重新复制并重启网关。2026-11-21 已更新部署副本的 `tools.py`；`plugins validate` 与
`plugins doctor --ci` 均通过。插件已启用，Weixin 工具集仅配置 `daily_task`，工作区与项目虚拟环境
路径也与本仓库一致。

微信此前已完成不调用模型的收发测试。2026-11-21 又通过官方原生 AIAgent，使用真实 Go
凭据及 `deepseek-v4.1-flash`，在隔离数据目录完成查询、新增课程、修改教室、新增作业、
新增日程和最终回读；共调用七次业务工具。正式微信网关已以前台方式启动并连接；尚未
通过微信发送业务写入，需用户发 `/new` 后完成最后的消息路径确认。

2026-11-21 重新验收后，Hermes 网关状态由旧的残留运行标记修复为 ready/running；
Weixin 状态为 configured。当前是手动运行的网关，不是 Windows 服务；桌面应用中没有微信窗口，
因此部署后的微信消息收发尚待用户从手机发送一次只读的“查询有什么”确认。没有对真实库存做试写。

参考：OpenCode Go 官方文档、Hermes v0.23.3 的插件 API 与 `actions.py` 源码。
