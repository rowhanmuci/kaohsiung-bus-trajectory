# 專案資料庫（PostgreSQL 17 on Docker）

| 擴充 | 版本 | 用途 |
|---|---|---|
| PostGIS | 3.6.4 | 空間型別和空間索引（R-tree／GiST）：鏡頭、GPS 點、路段 |
| pgvector | 0.8.7 | crop 的 embedding 和 HNSW 相似度搜尋 |
| pgRouting | 4.0.1 | 路網最短路徑（HMM map matching、補上稀疏點之間的路徑） |
| MobilityDB | 1.3.0 | 移動物件型別 `tgeompoint`：存軌跡、依時間內插位置、算最接近時刻 |

- 啟動和停止：在專案根目錄執行 `docker compose up -d --build`（啟動）、`docker compose stop`（停止）。設定檔是根目錄的 `compose.yaml`。
- 連線：`localhost:5432`，只有本機連得到。帳號、密碼和資料庫名稱都在根目錄 `.env` 的 `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`。
- 資料存放：Docker volume `std_std_pgdata`。執行 `docker compose down` 不會刪掉它，加上 `-v` 才會刪。
- 第一次啟動時，`init/20_extensions.sql` 會自動建立上面四個擴充。
- 為什麼不用 `postgis/postgis` 映像：它的底層是 Debian bullseye，PostgreSQL 官方套件庫已經不再支援，裝不了其他擴充。所以改用 `postgres:17-bookworm`，再自己裝擴充。
