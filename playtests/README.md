# playtests/ — 跑過的紀錄

一次 playtest 跑完就只剩人的印象,而印象會變。這裡放**當時真的印出來的東西**,
所以之後討論「那次到底長什麼樣」時有原文可看,不是靠回憶。

檔名是 `<日期>-<跑的是什麼>.txt`。

- `2026-08-05-h1-autoplay.txt` — H-1 五步流程用 **AI 代打**跑的排練
  (`python tools/h1_autoplay.py`,provider=groq / `qwen/qwen3.6-27b`)。
  **這不是 H-1 的答案**:H-1 問的是「**你**想不想再打開」,agent 說它覺得有趣不算數。
  它驗的是流程通不通、狀態與懸念有沒有跨 session 接起來、以及四步花多少 token。
