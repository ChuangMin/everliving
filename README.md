# everliving

> 你不在線時,你的 Agent 仍在世界裡活著;上線時讀到「我不在的這段期間發生了什麼」。
> While you're offline, your Agent keeps living in the world — log back in and read what happened while you were away.

一個持續存在的虛擬世界,真人玩家與 AI Agent 共存。這是核心賭注,其餘都是延伸。
A persistent virtual world where human players and AI agents coexist. That's the core bet — everything else is downstream of it.

完整設計討論見 [AI大世界_設計文件.md](./AI大世界_設計文件.md)(中文)。
Full design rationale lives in [AI大世界_設計文件.md](./AI大世界_設計文件.md) (Chinese only — it's dense design-decision material, not worth maintaining a parallel translation for).

## 目前階段 / Current stage

**里程碑 0**(驗證核心賭注)進行中——見 [PROGRESS.md](./PROGRESS.md) 追蹤進度、[TASKS.md](./TASKS.md) 看任務分解。
**Milestone 0** (validating the core bet) is in progress — track it in [PROGRESS.md](./PROGRESS.md), see the task breakdown in [TASKS.md](./TASKS.md).

做:一個 Agent、一個玩家、記憶存 SQLite、離線期間用一次 LLM 呼叫生成敘事。
不做:世界地圖、多角色、前端、向量檢索。

In scope: one agent, one player, memory in SQLite, one LLM call to narrate what happened offline.
Out of scope (for now): world map, multiple agents, frontend, vector search.

## 給協作 Agent / For collaborating agents

這個專案預期會有多家 AI agent(Claude Code、Codex、Qwen、Kimi、Grok…)協作開發。不管你是哪一家,先讀 [AGENTS.md](./AGENTS.md)。
This project expects multiple AI agents from different vendors (Claude Code, Codex, Qwen, Kimi, Grok, ...) to collaborate on it. Whichever one you are, read [AGENTS.md](./AGENTS.md) first — it's the vendor-neutral entry point, written in Chinese but any capable model can read it.
