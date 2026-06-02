# paper-monitor

自動偵測最佳化領域新論文（arXiv + 正式期刊），用 Claude API 做快速判讀，每天推送到 Telegram。

---

## 快速開始

### 步驟 1 — 建立 Telegram Bot（約 2 分鐘）

1. 在 Telegram 搜尋 `@BotFather`，開始對話。
2. 傳送 `/newbot`，依提示輸入 bot 名稱與 username。
3. BotFather 會給你一串 **Bot Token**（格式如 `123456789:ABCdef...`），複製保存。
4. 開啟你剛建立的 Bot，點「Start」或傳一則訊息。
5. 取得你的 **Chat ID**：
   - 在瀏覽器開啟 `https://api.telegram.org/bot<你的TOKEN>/getUpdates`
   - 找到 `"chat":{"id":xxxxxxxxx}` 裡面的數字，即為 Chat ID。

---

### 步驟 2 — Fork / Clone 此 repo 到你的 GitHub

```bash
git clone https://github.com/<你的帳號>/paper-monitor.git
cd paper-monitor
```

---

### 步驟 3 — 設定 GitHub Secrets

在 repo 頁面：**Settings → Secrets and variables → Actions → New repository secret**

新增以下三個 Secret：

| Secret 名稱 | 填入內容 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Console 取得的 API Key |
| `TELEGRAM_BOT_TOKEN` | 步驟 1 取得的 Bot Token |
| `TELEGRAM_CHAT_ID` | 步驟 1 取得的 Chat ID |

> ⚠️ 不要把這些值直接寫進 `config.yaml` 或任何程式碼，永遠只放在 Secrets。

---

### 步驟 4 — 調整 config.yaml

編輯 `config.yaml`：
- **確認 ISSN**：請上各期刊官網確認正確 ISSN，填入 `journals.crossref` 清單。
- **新增期刊**：照格式在 `journals.crossref` 下方加一筆。
- **調整 arXiv 分類**：預設追蹤 `math.OC`，可新增其他分類。
- **調整 LLM prompt**：在 `llm.prompt` 欄位自訂判讀格式與重點。

---

### 步驟 5 — 啟用 GitHub Actions

1. 進入 repo 的 **Actions** 頁面。
2. 如果看到「Workflows disabled」提示，點擊啟用。
3. 找到 **Paper Monitor** workflow，點 **Run workflow** 手動測試一次。
4. 確認 Telegram 有收到訊息後，排程就會每天自動執行。

> 預設排程：每天 UTC 00:00（台灣時間 08:00）。  
> 修改時間：編輯 `.github/workflows/monitor.yml` 裡的 `cron` 欄位。

---

## 專案結構

```
paper-monitor/
├── config.yaml                   # 所有可調設定（期刊清單、LLM prompt 等）
├── main.py                       # 主程式，串起整個 pipeline
├── sources.py                    # 抓論文（arXiv / Crossref / RSS）
├── summarize.py                  # LLM 判讀（Claude API）
├── notify.py                     # Telegram 推送
├── state.py                      # state.json 去重管理
├── state.json                    # 自動產生，記錄已處理的論文 ID
├── requirements.txt
└── .github/workflows/monitor.yml  # GitHub Actions 排程
```

---

## 本機執行（測試用）

```bash
pip install -r requirements.txt

# 設定環境變數（Linux/Mac）
export ANTHROPIC_API_KEY="sk-ant-..."
export TELEGRAM_BOT_TOKEN="123456789:ABCdef..."
export TELEGRAM_CHAT_ID="987654321"

python main.py
```

Windows（PowerShell）：
```powershell
$env:ANTHROPIC_API_KEY="sk-ant-..."
$env:TELEGRAM_BOT_TOKEN="123456789:ABCdef..."
$env:TELEGRAM_CHAT_ID="987654321"
python main.py
```

---

## 常見問題

**Q：state.json 要不要 commit 進 repo？**  
A：要。GitHub Actions workflow 會在每次執行後自動 commit 更新的 state.json，這樣下次執行才能正確去重。如果你自己也在本機跑，記得先 pull 最新的 state.json。

**Q：第一次執行會推送大量舊論文嗎？**  
A：會。arXiv 會抓最新 50 篇，Crossref 看往前 3 天。如果不想第一次就被洗版，可以先把 `config.yaml` 裡的 `max_results` 調小，或手動執行一次（不推送）讓 state.json 建立基線：暫時把 `TELEGRAM_BOT_TOKEN` 設成無效值跑一次即可。

**Q：Crossref abstract 是空的怎麼辦？**  
A：部分期刊不授權 Crossref 顯示 abstract，LLM 會標注「摘要過短或不可用」。這類論文的標題和連結仍會推送，你可以點連結去看原文。

**Q：想改成推送到 Email / Slack 怎麼做？**  
A：參考架構說明文件的「擴充」章節。
