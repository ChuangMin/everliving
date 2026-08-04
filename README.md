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
pip install -e ".[dev]"
python -m everliving.web      # 網頁版(建議)——會自動開瀏覽器
```

或者純命令列:

```
python -m everliving.cli
```

**兩個入口跑的是同一套核心迴圈與同一個 `everliving.db`**,差別只在介面。網頁版多了一件事:一個跟著現實時間變化的港城場景(天色、潮位都會動),而潮汐正好是這個世界的時鐘。

網頁版只綁 `127.0.0.1`,同網段的其他機器連不進來——這個行程握著會花錢的 API key。

```
python -m everliving.web --offline-hours 24   # 跟 CLI 同一個意思
python -m everliving.web --port 8770 --no-browser
```

安裝一次就好(`-e` 是可編輯安裝,改程式碼不用重裝)。裝完之後在任何資料夾都能跑。

> ⚠️ `everliving.db` 會建在**你執行指令的那個資料夾**。想接續同一個世界,就固定在同一個資料夾跑——換位置等於開了一個全新的世界,agent 會什麼都不記得。

API key 三選一(`.env` 已在 `.gitignore`,不會被 commit):

```powershell
# 1. 只在這個終端機視窗有效
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 2. 永久寫進使用者環境變數(設完要重開終端機)
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")

# 3. 複製 .env.example 成 .env 填進去(啟動時自動載入;真實環境變數優先)
```

或者裝 `ant` CLI 跑 `ant auth login`,SDK 會自動抓登入後的 profile,不用自己保管 key。

### 換供應商 / Switching providers

不想被單一帳號的額度卡住的話,還有幾個選擇。**注意 `grok` 和 `groq` 是不同的服務,名字只差一個字母**:

| provider | 是什麼 | 需要的環境變數 |
|---|---|---|
| `anthropic` | Claude(預設) | `ANTHROPIC_API_KEY` |
| `groq` | Groq —— 高速跑開源模型的推論服務,有免費額度 | `GROQ_API_KEY` |
| `grok` | xAI 的 Grok 模型 | `XAI_API_KEY` |
| `ollama` | 本機 Ollama —— **不用 key、不用網路、每次呼叫 $0** | (不需要) |

```powershell
$env:GROQ_API_KEY = "gsk_..."
python -m everliving.cli --provider groq
```

或在 `.env` 裡設 `EVERLIVING_PROVIDER=groq` 省掉每次打參數(網頁版和 CLI 都吃這個變數)。模型 ID 用 `EVERLIVING_MODEL` 覆蓋——各家的 ID 會變,404 的時候去對應的 console 查目前有哪些。

**Groq 上的模型實測**(用真的離線模擬 prompt 比較過,見 `PROGRESS.md`):`qwen/qwen3.6-27b` 的繁中文筆和懸念設計明顯最好,所以是預設值。`openai/gpt-oss-120b` 可用但狀態鍵名會跑成英文;`llama-3.3-70b-versatile` 敘事偏流水帳。

**本機 Ollama**(`--provider ollama`)是唯一**不會因為帳號問題而壞掉**的路:沒有 key、沒有帳單、沒有過期。
先確定 Ollama 在跑(`ollama serve`),然後:

```powershell
ollama pull qwen3.6            # 預設值;或用你已經有的模型
python -m everliving.web --provider ollama
```

模型用 `EVERLIVING_MODEL` 或 `--provider ollama` 搭配環境變數換掉,例如 `$env:EVERLIVING_MODEL = "qwen2.5:7b"`。

**取捨要先知道**:大模型跑在 CPU 上會非常慢(`ollama ps` 的 `size_vram: 0` 就表示沒吃到 GPU)。
一次離線敘事要等好幾分鐘的話,**它會變成跟壞掉的 API key 一樣的門檻**——H-1 就是被門檻擋掉的,
所以寧可換小模型把速度換回來。文筆跟慢到不想開之間,這個專案已經知道哪一個先殺死測試。

**選擇一律是明示的,不會自動偵測**:偷偷換模型等於偷偷改變 playtest 在量什麼。

### 出事的時候去哪裡看 / Logs

每一趟都會寫 `everliving.log`(UTF-8;`--log-file` 可以換路徑)。裡面有:

- 啟動用的 provider、model、port
- 每個請求的路徑跟耗時
- 每次 LLM 呼叫的 model、秒數、input/output token
- 失敗的完整原因(例如 `AuthenticationError: ... API key is invalid`),意外的例外連 traceback

```
2026-08-04 23:53:16 INFO  everliving.web | 啟動 — provider=groq model=qwen/qwen3.6-27b port=8773
2026-08-04 23:53:23 INFO  everliving.llm | Groq ← qwen/qwen3.6-27b in 2.1s (in=230 out=860)
```

**API key 永遠不會進到 log 裡。** 玩家講的話跟 prompt 也不會——那是玩家的東西,
要看得加 `--debug` 明示打開。**日誌是 gitignore 的**,不會不小心 commit 出去。

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
