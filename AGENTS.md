# AGENTS.md — 給任何開發這個專案的 AI agent(不限廠商)

這個專案預期會有**多個不同來源的 AI agent**(Claude Code、Codex、Qwen、Kimi、Grok 等)輪流或同時對這個 repo 做開發。這份文件是所有 agent 共用的入口,不管你是哪一家模型都先讀這份。

## 這是什麼

`everliving`(AI大世界)。完整設計脈絡讀 `AI大世界_設計文件.md`——決策理由都在裡面,不要重複踩已經討論過的問題。

## 現在該做什麼

只做**里程碑 0**,在 `AI大世界_設計文件.md` 第 167–180 行:

- 一個 Agent、一個玩家
- 記憶存 SQLite(不用 vector DB)
- 關掉,隔天打開
- 一次 LLM 呼叫生成「這段時間我做了什麼」
- 讀到那段敘事

**不要**做世界地圖、多角色、前端框架、向量檢索、Unity、金流、帳號系統——這些都是後面里程碑的事,提前做是在浪費額度。里程碑 1 才開始做多 agent(見設計文件第 182–184 行),現在還不是時候。

技術選型:Python + SQLite,能跑就好,不用學新框架。

## 兩種角色

- **規劃(planner)**:讀設計文件 + `PROGRESS.md` + `TASKS.md`,確保 `TASKS.md` 里程碑 0 的 backlog 保持有貨、任務夠具體(小到一次 session 做得完)。backlog 夠用時不用硬做事,不要提前展開下一個里程碑的任務。
- **執行(builder)**:從 `TASKS.md` 挑一個 `todo` 任務做,不要自己重新發明「該做什麼」——那是規劃角色的工作,你重複做只會跟別的 agent 撞工。

## 工作流程(給自動排程 / 自主 session)

1. 先讀 `TASKS.md` 跟 `PROGRESS.md` 最新一則,搞清楚上次是哪個 agent、做到哪、backlog 裡有什麼可撿
2. 認領前把 `TASKS.md` 該任務狀態改 `in-progress` 並填上你是哪個 agent/模型(claimed-by)
3. 做一小塊有意義的進展(寧可小而完整,不要大而半成品)
4. 跑得動、測過的東西才算完成——沒辦法本機驗證的功能不要宣稱做完。能寫自動測試就寫(mock 掉真的 LLM API 呼叫,這裡沒有遊戲要用的 LLM key)
5. 任務做完把 `TASKS.md` 狀態改 `done`,在 `PROGRESS.md` 加一則新記錄(日期、用的是哪個 agent/模型、做了什麼、下一步、任何卡住的地方)
6. 如果卡住需要人決定的問題,寫進 `PROGRESS.md` 的「待人決定」區塊,不要自己猜著往下做

## 多 agent 併發安全(重要)

會有其他 agent(可能是別家模型)同時或交錯在動這個 repo:

- **commit 前一定先 `git pull --rebase`**,避免蓋掉別人剛推上去的東西
- **commit 切小塊**,不要憋一個巨大 commit——衝突範圍越小越好處理
- 遇到真的解不開的 merge conflict:不要用蠻力二選一蓋過去,在 `PROGRESS.md` 記下衝突狀況然後停手,留給人或下一個 session 處理
- `PROGRESS.md` 是唯一的交接窗口,不管你是哪一家 agent——動手前一定要先讀最新記錄
