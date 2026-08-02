# 進度紀錄

> 每次工作 session 結束前在這裡加一則新記錄。最新的放最上面。

---

## 2026-08-02 — T0-3 / T0-7:互動迴圈 + 可 mock 的 LLM 介面

Agent: Claude Sonnet 5(互動 session,非排程)

- `src/everliving/llm.py`:`LLMClient` Protocol + `AnthropicLLMClient`(lazy import `anthropic`,測試不需要裝這個套件)
- `src/everliving/agent_loop.py`:`build_system_prompt()` 組 persona + `respond()` 一次對話回合(組 prompt → 呼叫 LLM → 把「玩家說」「我回答」各存一筆記憶事件)
- `src/everliving/cli.py`:`python -m everliving.cli` 的互動迴圈,啟動時 seed persona、用 `AnthropicLLMClient`,缺 API key 會印清楚的錯誤訊息而不是 stack trace
- `tests/conftest.py`:共用的 `conn`(記憶體 SQLite)、`fake_llm`(記錄每次呼叫的假 client)fixture,順手把 `test_db.py`/`test_persona.py` 裡重複的 `conn` fixture拿掉
- `tests/test_agent_loop.py`:4 個測試,涵蓋 system prompt 內容、回覆會寫回記憶、近期記憶會被帶進 prompt、未知 agent_id 會丟例外。`python -m pytest -q` 全過(11 passed)

**下一步**:T0-4(離線時間追蹤,接進 cli.py 的啟動/離開流程)→ T0-5(離線敘事生成)→ T0-6(上線讀敘事)。T0-4/T0-5/T0-6 有依賴順序,建議照順序做。

**待人決定**:同前一則——排程 agent 需要人到 https://claude.ai/code/routines 連結 GitHub;舊 commit 的 history 重寫指令待執行。

---

## 2026-08-02 — T0-1 / T0-2:schema + persona

Agent: Claude Sonnet 5(互動 session,非排程)

- 建立 `src/everliving/db.py`:SQLite schema(`agents`、`memory_events`、`player_state` 三張表)+ CRUD 函式(create_agent、get_agent、add_memory_event、get_recent_memory、set_last_seen/get_last_seen)
- 建立 `src/everliving/persona.py`:寫死一個原創角色「陌洲」(未來港城技師),`seed_default_agent()` 冪等寫入
- `tests/test_db.py`、`tests/test_persona.py`:7 個測試,涵蓋建立/查詢、記憶依時間排序與依 agent 隔離、last_seen 讀寫、persona seed 冪等性。`python -m pytest -q` 全過(7 passed)
- 加 `pyproject.toml`(pytest pythonpath 設定)、`requirements-dev.txt`

**下一步**:T0-3 互動迴圈(CLI 對話,呼叫 LLM 產生回應並寫入記憶)。這一步需要決定 LLM 呼叫怎麼包裝成可 mock 的介面(對應 T0-7),建議兩個一起做。

**待人決定**:
- 排程雲端 agent(everliving-planner / everliving-builder)建立失敗,因為 claude.ai 的 routine 平台需要另外連結 GitHub 帳號(跟本機 `gh` CLI 登入是分開的)。需要人到 https://claude.ai/code/routines 連結 GitHub 後,才能重建這兩個排程。
- 舊的 git commit(`122c070`/`4013c61`/`32e18cf`)裡還殘留已脫敏移除的商業策略/防濫用細節,已提供人類手動執行的 history 重寫指令(orphan branch + force push),尚待執行確認。

---

## 2026-08-02 — 專案啟動

- 建立 repo `everliving`,搬入既有設計文件
- 加入 `README.md`、`CLAUDE.md` 給後續協作 agent 用
- 設定每日自動排程,推進里程碑 0

**下一步**:開始寫里程碑 0 的最小原型——SQLite schema(agent 人設 + 事件記憶)、一個能對話的 agent、離線期間敘事生成的 LLM 呼叫。

**待人決定**:無
