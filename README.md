# everliving

> 你不在線時,你的 Agent 仍在世界裡活著;上線時讀到「我不在的這段期間發生了什麼」。

一個持續存在的虛擬世界,真人玩家與 AI Agent 共存。這是核心賭注,其餘都是延伸。

完整設計討論見 [AI大世界_設計文件.md](./AI大世界_設計文件.md)。

## 目前階段

**里程碑 0**(驗證核心賭注)進行中——見 [PROGRESS.md](./PROGRESS.md) 追蹤進度。

做:一個 Agent、一個玩家、記憶存 SQLite、離線期間用一次 LLM 呼叫生成敘事。
不做:世界地圖、多角色、前端、向量檢索。

## 給協作 Agent

這個專案預期會有多家 AI agent(Claude Code、Codex、Qwen、Kimi、Grok…)協作開發。不管你是哪一家,先讀 [AGENTS.md](./AGENTS.md)。
