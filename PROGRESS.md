# 進度紀錄

> 每次工作 session 結束前在這裡加一則新記錄。最新的放最上面。

---

## 2026-08-02 — 加上 Grok 供應商支援

Agent: Claude Opus 5(互動 session)

Anthropic 額度還沒入帳,人類選擇加 Grok 當替代來源,不要被單一帳號的額度卡住 H-1。

- `GrokLLMClient`:走 xAI 的 OpenAI 相容端點(`https://api.x.ai/v1`),用 `openai` SDK。需要 `XAI_API_KEY`。
- `make_client(provider)` 工廠 + `--provider` 參數 + `EVERLIVING_PROVIDER` 環境變數。
- **選擇一律明示,不做自動偵測**。「哪邊有額度就用哪邊」聽起來方便,但偷偷換模型等於偷偷改變 playtest 在量什麼——H-1 要判斷的是敘事有沒有打中你,那個判斷跟哪個模型寫的直接相關。
- 錯誤對應抽成共用的 `translate_sdk_error()`。兩個 SDK 的例外階層剛好一模一樣,連 `AuthenticationError` 是 `APIStatusError` 子類別這個陷阱都一樣,不該複製兩份。
- 兩個形狀差異要處理:Anthropic 用 `system=` 參數,OpenAI 形狀要把它塞進 messages 當 system 角色;Anthropic 是 `usage.input_tokens`,OpenAI 是 `usage.prompt_tokens`。成本記錄兩邊都照常運作。
- 缺 `XAI_API_KEY` 時自己先擋下來——否則 OpenAI SDK 會報「找不到 OPENAI_API_KEY」,叫人去找一個根本不相干的變數。

測試 83 passed(新增 15 個)。實測 `--provider grok` 在沒 key 時會乾淨退出並指出要設哪個變數。

**H-1 的品質提醒**:Grok 是前沿模型,不是本機小模型,所以先前「模型太弱會污染判斷」的顧慮大致不適用。但**繁體中文的文學性敘事 Claude 通常比較穩**,而 H-1 要判斷的正是敘事有沒有打中你——如果用 Grok 跑完覺得普通,值得再用 Claude 跑一次對照,再下結論。

**下一步**:H-1 playtest(人類),兩家擇一。

**待人決定**:H-1 playtest;舊 commit 的 history 重寫指令仍待執行。

---

## 2026-08-02 — 第一次真的打 API,又抓到一個錯誤路徑

Agent: Claude Opus 5(互動 session)

人類設好 key 後叫我試跑。用**另一個 scratch DB**(不動 `everliving.db`,免得污染他自己的 H-1)實際打了一次真實 API,結果:額度還沒入帳,回 400「credit balance is too low」——而程式直接吐一整串 traceback。

又是同一類問題:**只有真的跑才會現形的錯誤路徑**。而且這一條的命中率極高,任何人第一次跑、還沒儲值就是這個畫面。

- 新增 `LLMUnavailable`:涵蓋額度不足、rate limit、伺服器錯誤、連不上。這些**改講法沒有用**,所以 CLI 直接印訊息並退出,不做重試迴圈(單人週末工具,重試迴圈是過度設計)。
- 從 `exc.body["error"]["message"]` 取伺服器原文——它通常已經寫清楚該怎麼辦(「go to Plans & Billing」),比我自己重寫一段有用。
- **例外攔截順序有陷阱**:`AuthenticationError` 是 `APIStatusError` 的子類別,必須先攔。有測試專門守這點。

測試 68 passed(新增 5 個 SDK 例外對應 + 1 個 CLI 端對端)。實際重跑確認:現在額度不足會印出乾淨的兩行提示,不是 traceback。

**目前已知的三種失敗都收斂了**:沒憑證 / 憑證被拒 → `LLMAuthError`;額度、限流、斷線 → `LLMUnavailable`;模型婉拒 → `LLMRefusal`(唯一可以繼續玩的一種)。

**下一步**:等額度入帳,H-1 playtest(人類)。

**待人決定**:儲值入帳後跑 H-1;舊 commit 的 history 重寫指令仍待執行。

---

## 2026-08-02 — 真的跑一次,抓到兩個只有跑才會出現的 bug

Agent: Claude Opus 5(互動 session)

人類去 console 儲值前,先把回來要用的東西備好。本機裝了 `anthropic`(0.120.2),然後**實際在沒有 key 的情況下跑一次 CLI**——結果抓到兩個測試抓不到、只有真的執行才會現形的 bug:

**1. 沒有 API key 時,CLI 會照常進入對話迴圈,友善錯誤訊息完全沒觸發。**
原本的 `try/except` 包在 `AnthropicLLMClient()` 建構上,但 SDK 的憑證解析是**延遲**的——沒有 key 也能順利建構,要等到第一次真的呼叫才炸。使用者體驗會是:打完第一句話,吃到一整串 raw traceback。

而且 SDK 丟的是**兩種不同的例外**:
- 完全找不到憑證 → 從 header 驗證丟出的**純 `TypeError`**(根本沒送出請求)
- 有 key 但被伺服器拒絕(401)→ `anthropic.AuthenticationError`

→ 新增 `LLMAuthError`,兩種都對應過去。`TypeError` 那條有用訊息內容做篩選,避免把我們自己程式裡真正的 `TypeError` 吃掉(有測試守著這點)。CLI 兩個呼叫點都接住,印出「設定 ANTHROPIC_API_KEY 或用 `ant auth login`」然後乾淨退出。

**2. 修第一個 bug 的過程中,自己製造了第二個。**
`_exit_no_credentials()` 裡順手 `conn.close()`,結果 `finally` 區塊接著要寫 `last_seen` → `sqlite3.ProgrammingError: Cannot operate on a closed database`。連線清理本來就歸 `finally` 管,那行 close 是多餘且有害的,已移除並在 docstring 註明原因。

測試 58 passed(新增 5 個:CLI 兩條無憑證路徑、兩種 SDK 例外的對應、以及「無關的 TypeError 仍要往上拋」)。

**這一輪的教訓**:前一輪的 53 個測試全過,但這兩個 bug 一個都沒抓到——因為它們都在「跟真實 SDK 的介面」上,而測試裡的 SDK 是我自己寫的假的。**mock 只能驗證我以為的契約,不能驗證真實的契約。**

**下一步**:H-1 playtest(人類)。`anthropic` 已裝好,儲值完設好 key 就能直接跑。

**待人決定**:H-1 playtest;舊 commit 的 history 重寫指令仍待執行。

---

## 2026-08-02 — 修掉 LLM 回應處理的真實 bug(in-scope 稽核)

Agent: Claude Opus 5(互動 session)

專案卡在 H-1,所以這輪只做自己定義的 in-scope 類別(修 bug / 測試 / 摩擦 / 文件),沒有加新功能。對照 Anthropic API 的實際契約稽核 `llm.py`,抓到一個**會當掉的真 bug**:

- **`response.content[0].text` 是錯的**。回應的 content 是「區塊清單」,不保證第 0 塊是文字。Claude 5 系列**預設就會思考**,第 0 塊是 thinking 區塊、根本沒有 `.text` → `AttributeError`。而 README 明講可以用 `EVERLIVING_MODEL` 換模型,等於我自己開了一條會炸的路。
  → 改成 `extract_text()`:只挑 `type == "text"` 的區塊串起來,thinking / tool 區塊直接跳過。
- **`max_tokens=512` 對會思考的模型太緊**——那個上限是「思考 + 回覆」共用的,會在句子中間被截斷。提高到 2048(回覆本身只有 2-4 句,多的是給思考的餘裕)。
- **沒有處理 `stop_reason == "refusal"`**。模型婉拒時是正常的 HTTP 200,content 可能是空的——照舊寫法會靜靜地拿到空字串或當掉。
  → 新增 `LLMRefusal` 例外;CLI 兩處都接住:對話中拒絕只印一行提示並繼續(session 不會中斷),離線敘事被拒絕則跳過敘事、照常進入對話迴圈。
- 模型 ID 從寫死日期的 `claude-haiku-4-5-20251001` 改成別名 `claude-haiku-4-5`。

也順手驗證了一個**不是問題的問題**:擔心 Windows 主控台編碼會讓中文輸出爆掉,實測 cp950(Big5)完整涵蓋 CLI 用到的所有字元,所以**沒有改**——不修不存在的問題。

測試 53 passed(新增 9 個:文字擷取跳過 thinking/tool 區塊、多區塊串接、拒絕例外型別、CLI 兩條拒絕路徑各一個端對端測試)。

**下一步**:仍然是 H-1 playtest(人類)。

**待人決定**:H-1 playtest;舊 commit 的 history 重寫指令仍待執行。

---

## 2026-08-02 — T0-11:離線期間真的會產生後果(H-2 已處理)

Agent: Claude Opus 5(互動 session)

人類選擇「先把離線敘事做厚再跑 playtest」,理由是假陰性會殺掉一個好點子。已完成。

**核心改動**:離線模擬從「一次無狀態呼叫產生散文」變成「一次呼叫產生結構化後果」。

- 新 schema:`agent_state`(agent 目前有什麼/是什麼狀態)、`open_threads`(懸而未決、需要玩家回應的事)
- `simulate_offline_period()` 回傳 `OfflineResult`(narrative / events / state_changes / open_thread / resolved_thread_ids),並把後果全部寫進 DB
- **迴圈閉合**:下次對話時 `respond()` 會把目前狀態與未解決的懸念帶進 prompt,system prompt 也會指示 agent 自然地提起它在等玩家的事。下次離線模擬也會拿到這些,所以連續性會累積
- CLI 會分區塊顯示:敘事 / 有些事情變了 / **[ 有件事在等你 ]**
- **穩健性**:JSON 解析失敗時退化成純敘事——玩家要讀的東西永遠不會弄丟。幻覺出來的 thread id 不會碰到 DB
- 測試 44 passed。舊的純散文測試仍然通過,正好驗證了退化路徑

**為什麼這是關鍵**:原本玩家讀完敘事之後什麼都沒發生,明天打開會是另一段同樣沒後果的散文。現在離線期間會改變世界、並留下一件在等玩家的事——這才對得起「**故事仍然會發生**」這個差異化主張。日記不是故事。

**下一步**:H-1 playtest(人類)。`TASKS.md` 有四步驟的跑法,重點是第 4 步——看它有沒有接住你上次的回應。

**待人決定**:
- **H-1 playtest** — 現在測的是有後果的版本了
- 排程 agent 仍建議等 H-1 有結論再建
- 舊 commit 的 history 重寫指令仍待人手動執行

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
