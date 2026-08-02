# 進度紀錄

> 每次工作 session 結束前在這裡加一則新記錄。最新的放最上面。

---

## 2026-08-02 — 重新檢視整個規劃(重要)

Agent: Claude Opus 5(互動 session)

重新審視後,原本的規劃有三個問題,已修正:

**1. 瓶頸不是額度,是還沒被驗證的方向。**
里程碑 0 程式碼完成後,唯一擋著的是 H-1 真人 playtest,那是只有人類能做的事。但原本設計的每日排程是 planner 每天補 backlog + builder loop 到清空為止——這台機器的結構性誘因就是「一定要找到事做」,遲早會漂進里程碑 1 的範圍,違反設計文件第 250 行。
→ 已改:`AGENTS.md` 新增最高優先規則「今天沒事該做是正確結果」,planner 不再負責「讓 backlog 有貨」;`TASKS.md` 新增「目前卡在哪」區塊明列 in-scope 的工作類別。

**2. 目前的里程碑 0 可能不是一個公平的驗證。**
離線敘事是一次無狀態的 LLM 呼叫,產出 2-4 句散文。玩家讀完之後:世界沒有變、agent 沒得到或失去什麼、沒有任何需要玩家回應的懸念。明天打開會是另一段同樣沒有後果的散文。
但差異化主張是「**故事仍然會發生**」——日記不是故事。
風險:H-1 失敗時誤判成「核心賭注錯了」,其實只是實作太薄測不出賭注。**用壞的測試殺掉好的點子是這裡最貴的錯誤。**
→ 已記為 `TASKS.md` 的 **H-2**,等 H-1 的實際感受出來再決定要不要補「離線期間產生狀態變化與懸念」。目前**沒有**擅自實作。

**3. 設計文件要求的兩個數字一個都量不到。**
→ 已補 T0-10:`llm_calls` table 記錄每次呼叫的 model/input/output tokens,`--cost-report` 印每日用量。只存 token 不存金額(單價會變,token 是不會過期的事實)。

另外老實承認:AGENTS.md / TASKS.md / planner-builder 分工這整套多 agent 協作機制,對一個還沒驗證好不好玩的專案來說是過度建設,跟「先不碰 Unity/VR/金流」是同一個陷阱。已縮減其強制性,但保留檔案本身(多廠商協作仍是你要的)。

**這個 session 實際交付**:
- T0-9 `--offline-hours N`:直接假裝離開 N 小時,不用真的等隔夜就能跑 playtest(直接打瓶頸)
- T0-10 成本量測:`llm_calls` table + `log_usage()` + `--cost-report`
- 測試 32 passed。過程中既有的 `test_cli.py` 抓到 argparse 會誤讀 pytest 自己的 `-q`,已修
- 預設模型改成便宜的 Haiku,可用 `EVERLIVING_MODEL` 覆蓋

**下一步**:H-1 playtest(人類)。現在一次 session 就能跑完,不用隔夜。

**待人決定**:
- **H-1 playtest** — `python -m everliving.cli` 聊幾句 → 離開 → `--offline-hours 24` 讀敘事 → 想不想再打開?
- **H-2** — 如果感想是「還好」,先分清楚是賭注錯還是實作太薄(見上)
- 排程 agent 仍需先到 https://claude.ai/code/routines 連結 GitHub。但**建議等 H-1 有結論再建**——現在建了它也沒有合法的事情可做
- 舊 commit 的 history 重寫指令仍待人手動執行

---

## 2026-08-02 — T0-4/T0-5/T0-6/T0-8:里程碑 0 的 T0-* 全部完成

Agent: Claude Sonnet 5(互動 session,非排程)

- `src/everliving/offline.py`:`time_since_last_seen()`(算離線多久)、`generate_offline_narrative()`(一次 LLM 呼叫產生敘事,存成 `offline_narrative` 記憶事件)
- `cli.py` 接上完整流程:啟動時先算離線時間 → 有的話生成並印出敘事 → 進入互動迴圈 → `finally` 區塊保證離開時一定寫 `last_seen`(含 Ctrl+C/EOF)
- `tests/test_offline.py`:9 個測試,涵蓋時間差計算、時長格式化、敘事生成與記憶寫入、prompt 內容
- `tests/test_cli.py`:**端對端**測試,monkeypatch 掉 `AnthropicLLMClient` 跟 `input()`,實際跑兩次 `cli.main()` 模擬「關掉隔天打開」——第一次沒有敘事、第二次真的印出敘事。這是里程碑 0 核心體驗第一次被完整驗證過
- `requirements.txt`(`anthropic`)、`.env.example`、README 補執行說明
- 全部測試:`python -m pytest -q` → **22 passed**,不需要真的 API key

**里程碑 0 的 T0-1 ~ T0-8 全部 `done`。** 剩下唯一沒做的是 `TASKS.md` 裡的 **H-1 真人 playtest**——這個不能由 agent 代跑,需要人自己設定 `ANTHROPIC_API_KEY`、真的跑 `python -m everliving.cli`、關掉隔天(或至少過一段時間)重開,看看想不想回來看敘事。這是整個里程碑 0 唯一的成敗判準。

**下一步**:等人類完成 H-1 playtest 並給出「還想不想回來」的判斷。在那之前,agent(不管排程或互動)不應該提前規劃或動手做里程碑 1 的東西(多 agent)。

**待人決定**:
- **H-1 playtest**——上面說的,只有你能做。
- 排程 agent(everliving-planner / everliving-builder)還沒建成,需要先到 https://claude.ai/code/routines 連結 GitHub 帳號。
- 舊 commit(`122c070`/`4013c61`/`32e18cf`)的 history 重寫指令仍待人手動執行確認。

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
