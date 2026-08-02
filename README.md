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

## 執行 / Run it

```
pip install -r requirements.txt -r requirements-dev.txt
python -m everliving.cli
```

API key 三選一(`.env` 已在 `.gitignore`,不會被 commit):

```powershell
# 1. 只在這個終端機視窗有效
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 2. 永久寫進使用者環境變數(設完要重開終端機)
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")

# 3. 複製 .env.example 成 .env 填進去(啟動時自動載入;真實環境變數優先)
```

或者裝 `ant` CLI 跑 `ant auth login`,SDK 會自動抓登入後的 profile,不用自己保管 key。

關掉再重開,第二次啟動時會先印出「這段時間發生的事」——這就是里程碑 0 要驗證的核心體驗。
離線期間不只是產生一段敘述:agent 的狀態會實際改變,而且通常會留下**一件在等你回應的事**。
你回應之後,下一次離線期間會接著發展下去。

Coming back isn't just reading a diary entry — the agent's state actually changed while you
were gone, and it's usually waiting on you for something. Answer it, and the next offline
period picks up from there.

**不想真的等一天**:`python -m everliving.cli --offline-hours 24` 直接假裝你已經離開 24 小時,馬上生成該期間的敘事。playtest 一次搞定,不用隔夜。

**看花了多少 token**:`python -m everliving.cli --cost-report` 印出每日用量(只存 token,不存金額——單價會變)。

跑測試:`python -m pytest -q`(不需要 API key,LLM 呼叫在測試裡是 mock 的)。

> 預設用最便宜的 Haiku,每次呼叫上限 512 tokens。要換模型設 `EVERLIVING_MODEL`。
> 真正的成本保險請自己到 Anthropic Console 幫這把 key 設 spending limit。

## 給協作 Agent / For collaborating agents

這個專案預期會有多家 AI agent(Claude Code、Codex、Qwen、Kimi、Grok…)協作開發。不管你是哪一家,先讀 [AGENTS.md](./AGENTS.md)。
This project expects multiple AI agents from different vendors (Claude Code, Codex, Qwen, Kimi, Grok, ...) to collaborate on it. Whichever one you are, read [AGENTS.md](./AGENTS.md) first — it's the vendor-neutral entry point, written in Chinese but any capable model can read it.
