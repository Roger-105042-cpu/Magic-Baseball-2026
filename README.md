# 魔法棒球學院：PostgreSQL 多人版（初期可執行原型）

依據上傳 HTML / CSV / LOGO 重建。保留點名、扣堂、請假、教練評語、學員、裝備、續約、管理員、家長查詢與 Excel 匯出。**這是初期原型，尚未通過正式上線安全稽核。**

## 本機啟動（Docker Desktop）
1. 將 `.env.example` 複製成 `.env`，更換為隨機長密碼（避免特殊 URL 保留字，或正確 URL 編碼）。
2. 執行 `docker compose up -d --build`。
3. 建立管理員：`docker compose exec web python manage.py init`，互動輸入強密碼。
4. 匯入 CSV：先將檔案放入專案目錄（如 `students.csv`），執行 `docker compose exec web python manage.py import-csv --file /app/students.csv`。
5. 開啟 http://localhost:8000 登入。網站前端需連外載入 React、Tailwind 與 Babel CDN。

## 正式網際網路部署
目前 compose 僅綁定 `127.0.0.1:8000`，**不能直接對外使用**。需由 HTTPS 反向代理（如 Caddy / Nginx）接入，設定 DNS、有效 TLS、定期 PostgreSQL 備份、機密管理、監控與限制登入嘗試。`COOKIE_SECURE=1` 必須保持。建議將 CDN 前端改為預編譯、版本鎖定資源，設定 CSP、CSRF 防護與帳號重設流程，再開放家長使用。

## 匯入注意
CSV 只有學員及裝備快照，沒有完整歷史點名／續約資料。匯入**不沿用 CSV 的明文密碼**，匯入家長帳號預設停用；管理者需要後續建置安全的密碼重設與啟用流程。若同一手機對應多位學員，本版匯入只會建立第一位的家長帳號，需擴充家庭關聯資料表。不要把原始含密碼 CSV 放入公開 Git 或網站靜態目錄。

## 原型已知限制
- 管理員可新增學員，但未提供學員編輯／刪除（避免誤刪），需補上軟刪除與審計。
- 出席統計為目前載入資料的全期間彙總；原網站的月／季／年與日期區間篩選尚未完整移植。
- 尚無 CSV 網頁匯入、批次編輯、家長密碼重設／啟用、登入限流與 CSRF 防護。
- 使用者帳號登入與點名交易由 PostgreSQL 處理，避免 localStorage 不同步。
- 需經正式環境整合測試、安全測試及備份還原演練後才適合上線。
