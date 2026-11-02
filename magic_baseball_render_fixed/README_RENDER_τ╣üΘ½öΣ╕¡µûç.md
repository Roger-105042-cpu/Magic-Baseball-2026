# 魔法棒球學院：Render + PostgreSQL 部署教學（Windows）

## 本版內容與限制
本專案由先前 PostgreSQL 原型改造：Render Blueprint (`render.yaml`)、自動建立資料表、首次管理員建立、健康檢查 `/healthz`、原始 LOGO、Excel 匯出。**尚未通過正式安全驗收，不應立即開放真實家長帳號。**

原型仍缺登入限流、完整 CSRF 防護、家長密碼啟用／重設、所有原始日期統計、完整學員編輯、定期備份還原驗證。前端使用 CDN React/Babel/Tailwind，正式環境應改成編譯部署並加入 CSP。資料庫方案與價格以 Render 建立頁面為準。

## 1. Windows 準備
1. 註冊 GitHub 與 Render 帳號。
2. 下載本 ZIP 解壓縮。**不要將含家長密碼的原始 CSV 上傳 GitHub。**
3. 建立 GitHub **Private** repository，例如 `magic-baseball`。
4. 用 GitHub 網頁的 Add file → Upload files 上傳解壓後資料夾**內部的所有專案檔案**，尤其 `render.yaml`、`server.py`、`requirements.txt`、`static/`。請確保 `render.yaml` 在儲存庫根目錄。

## 2. Render 一鍵建立服務與資料庫
1. 登入 https://dashboard.render.com/ → New → Blueprint。
2. 連接 GitHub 私有儲存庫，選擇此 repo。
3. Render 讀取根目錄 `render.yaml`，預覽一個 Python Web Service 和一個 PostgreSQL 資料庫。
4. 對 `BOOTSTRAP_ADMIN_PASSWORD` 設定唯一強密碼（至少 10 碼，大小寫、數字、特殊符號），**不要寫進 GitHub**。
5. 檢查 Render 顯示的方案及每月費用，確認後套用 Blueprint。`render.yaml` 預設採用付費服務與資料庫，以避免免費資料庫到期造成資料遺失；如方案名稱不再適用，請依 Render 介面更新。
6. 等待部署成功，取得 `https://magic-baseball-web.onrender.com` 或 Render 實際分配網址。
7. 開啟 `/healthz` 應顯示 `{"status":"ok"}`。登入帳號 `superadmin`，密碼為第 4 步設定值。
8. **成功首次建立管理員後，請從 Render Web Service 的 Environment 刪除 `BOOTSTRAP_ADMIN_PASSWORD` 並重新部署。**已建立的帳號不受影響。

## 3. 匯入 CSV（選擇性）
原始 CSV 含明文密碼，**不要**放進 GitHub 或公開網站。建議先使用匿名測試資料驗證。正式資料請經受控的管理作業匯入（例如從本機經 Render Postgres 外部連線暫時匯入），使用 `python manage.py import-csv --file ...`。匯入程序不沿用 CSV 明文密碼，家長帳號預設停用；本版尚未提供安全的家長帳號啟用／密碼重設流程。

## 4. 驗證
- `/healthz` 正常、管理員登入與登出正常。
- 新增一位測試學員，點名一次後剩餘堂數 -1，取消點名後 +1。
- 重複點名同一日期應拒絕。
- 測試裝備、續約、Excel 匯出與權限限制。
- 開兩台裝置登入，確認共同 PostgreSQL 資料一致。

## 5. 正式營運前必做
- 實作登入限流、CSRF token、家長安全啟用／密碼重設、密碼嘗試紀錄與封鎖。
- 移除前端 CDN 即時 Babel 編譯，改用固定版本編譯後資源。
- 完成資料庫 migration（例如 Alembic）、備份排程及還原演練。
- 檢查家長只能看到自己孩子資料，並完善同一手機多名子女的關聯。
- 核對原始 HTML 各功能，補齊日期範圍／月季年統計與其他未移植細節。
- 避免匯出檔案包含密碼或過多個資；匯出檔案應妥善保存。

## 6. 常見問題
- `DATABASE_URL`：Blueprint 由 Render 資料庫自動注入，不需自行貼上。
- `No open ports detected`：確認 `startCommand` 含 `--host 0.0.0.0 --port $PORT`。
- `healthz` 失敗：檢查 Render Logs，確認資料庫已建立且同區域。
- GitHub 上傳 ZIP 本身不會自動展開，必須上傳解壓後的檔案。
- Render 上線不代表安全驗收通過，先用測試資料。
