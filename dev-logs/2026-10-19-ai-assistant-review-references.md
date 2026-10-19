# AI 助手专项审查与参考资料

日期：2026-10-19。性质：文档和公开论文归档；未修改产品功能。

## 涉及文件

- `MD-files/AI助手参考资料/AI助手专项审查.md`
- 同目录 `README.md`、`工程实践索引.md`、`下载清单.json`、`papers/*.pdf`
- 根目录 `README.md`：增加资料目录入口。

## 变更

- 将 AI 助手审查整理为可长期保存的文档，明确基线 `945b778`、代码事实、设计建议及验收场景。
- 收集 ReAct、Reflexion、CRITIC、自纠错局限、SWE-agent、τ-bench、Agentless、MAST 八篇论文。
- PDF 来自公开 arXiv 来源；保留来源、日期、字节数、SHA-256 与解析页数。
- 将学术论文与 OpenAI/Anthropic 工程实践分开索引，避免混淆证据类型。
- `papers/.gitattributes` 显式将 PDF 作为二进制，避免 Git 将部分 PDF 误判为文本并检查其内部空白。

## 验证

- 八份响应均为有效 PDF 头且内容大小合理；pypdf 成功解析八份文档、页数及首页文本；校验 SHA-256。
- Markdown 本地链接、UTF-8 无 BOM、清单文件和 PDF 一致性在交付前检查。
- 本次只新增参考文档/原文及索引，不重跑已通过的产品测试，不接触真实 settings.ini 和用户 JSON。

## 关联与边界

- 关联上一轮专项讨论：执行、验收、返工与统一收尾。
- 新机制尚未实现，未修改 ARCHITECTURE 中的现状描述或 CODE_STANDARDS 的规范。
- 用户既有 `data/daily_logs.json`、`data/inventory.json` 修改保留，不纳入本次提交。
