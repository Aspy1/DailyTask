# AI 助手参考资料

整理日期：2026-10-19。用于研究生活助手的执行、验收、返工、记忆与评估设计。

- **[AI助手专项审查.md](AI助手专项审查.md)**：当前代码问题、建议架构、改进顺序和回归场景。
- **[工程实践索引.md](工程实践索引.md)**：OpenAI、Anthropic 官方实践，单独标注为工程文章。
- **[下载清单.json](下载清单.json)**：来源 URL、下载日期、字节数、SHA-256、解析校验及页数。
- `papers/`：8 篇原文 PDF，全部下载并通过 PDF 解析；未改写原文。

## 论文清单

| 编号 | 完整论文名 | 年份/登记口径 | 本地原文 | 来源 |
|---|---|---|---|---|
| P01 | ReAct: Synergizing Reasoning and Acting in Language Models | ICLR 2023（预印本2022） | [PDF · 33页](papers/01_ReAct_2210.03629.pdf) | [arXiv](https://arxiv.org/abs/2210.03629) |
| P02 | Reflexion: Language Agents with Verbal Reinforcement Learning | NeurIPS 2023 | [PDF · 19页](papers/02_Reflexion_2303.11366.pdf) | [arXiv](https://arxiv.org/abs/2303.11366) |
| P03 | CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing | ICLR 2024（预印本2023） | [PDF · 78页](papers/03_CRITIC_2305.11738.pdf) | [arXiv](https://arxiv.org/abs/2305.11738) |
| P04 | Large Language Models Cannot Self-Correct Reasoning Yet | ICLR 2024（预印本2023） | [PDF · 17页](papers/04_Self_Correction_Limits_2310.01798.pdf) | [arXiv](https://arxiv.org/abs/2310.01798) |
| P05 | SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering | NeurIPS 2024 | [PDF · 118页](papers/05_SWE_agent_2405.15793.pdf) | [arXiv](https://arxiv.org/abs/2405.15793) |
| P06 | τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains | 首次预印本2024 | [PDF · 50页](papers/06_tau_bench_2406.12045.pdf) | [arXiv](https://arxiv.org/abs/2406.12045) |
| P07 | Agentless: Demystifying LLM-based Software Engineering Agents | 首次预印本2024 | [PDF · 25页](papers/07_Agentless_2407.01489.pdf) | [arXiv](https://arxiv.org/abs/2407.01489) |
| P08 | Why Do Multi-Agent LLM Systems Fail? | 首次预印本2025；MAST | [PDF · 47页](papers/08_MAST_2503.13657.pdf) | [arXiv](https://arxiv.org/abs/2503.13657) |

页数包括本地版本的附录。下载的是2026-10-19各来源提供的 PDF，不统一假定为会议定稿；上游可能更新，具体本地副本以清单中的 SHA-256 为准。

## 按问题阅读

| 遇到的问题 | 建议先读 | 应带着的问题 |
|---|---|---|
| 光说不做、提前结束 | P01、P06；专项审查A1 | 完成是否由真实状态证明？ |
| 出错后不返工 | P03、P04、P02 | 反馈是否来自外部证据？下一次尝试改变了什么？ |
| 工具调用格式不稳、错误信息难用 | P05 | 工具是否便于定位对象、恢复错误、验证结果？ |
| 复杂请求只完成一部分 | P06、工程实践索引 | 目标是否逐项保存、逐项验收？ |
| 重复犯错、下一轮忘记进度 | P02、工程实践索引 | 哪些事实必须独立于聊天历史保存？ |
| 想直接引入多个代理 | P07、P08 | 简单流程是否足够？验证责任是否反而分散？ |

建议先读 **P06 → P03 → P04**，直接对应本项目的状态验收和纠错；再读 P01/P05 改工具循环，最后看 P02/P07/P08 决定记忆与复杂度。

## 文件与使用说明

```text
AI助手参考资料/
├── AI助手专项审查.md
├── README.md
├── 工程实践索引.md
├── 下载清单.json
└── papers/
    ├── 01_ReAct_2210.03629.pdf
    ├── 02_Reflexion_2303.11366.pdf
    ├── 03_CRITIC_2305.11738.pdf
    ├── 04_Self_Correction_Limits_2310.01798.pdf
    ├── 05_SWE_agent_2405.15793.pdf
    ├── 06_tau_bench_2406.12045.pdf
    ├── 07_Agentless_2407.01489.pdf
    └── 08_MAST_2503.13657.pdf
```

论文版权及授权以原文和来源页为准，下载不改变原始授权。中文说明是围绕项目问题的摘要和设计推论，不是全文翻译；没有将论文特定实验结果直接当作本项目保证。
