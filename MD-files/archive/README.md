# archive/ — 归档区

放**不再参与开发、但需要留档**的东西。这里的内容不随发行版发布，也不属于
`Q-P3` 的代码分层。

## 为什么有 hermes-skill-life-assistant.md

它是一份**第三方 skill 文档**（Hermes Agent，2026-06-20 放进仓库根目录），
内容是"让 AI 直接读写 `data/` 下的 JSON"。

与项目规范冲突，因此**只归档、不启用**：

- **R-002**：数据写入只有两条合法路径 —— UI 走 `DataManager`/Model 的 `save()`（原子写），
  AI/TG 走 `scripts/actions.py`。该 skill 的"直接写 JSON"是第三条路径。
- **Q-E1**：它提到的 `settings.ini` 含明文密钥，不应被外部 skill 读取。

如果将来确实要用它，需要先把它改造成"经 `scripts/actions.py` 读写"，并同步
`Q-P1` 顶层白名单与本文件。
