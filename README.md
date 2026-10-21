# 高雄市公車軌跡：時空資料庫課程專案

國立中山大學 115-1「時空資料庫」（邱勝敏老師）的個人專案。整學期都使用同一份自己收集的資料：高雄市公車即時 GPS。

| 階段 | 內容 | 狀態 |
|---|---|---|
| HW1 | 從 TDX 收集公車 GPS，做 EDA、清理、修復（HMM map matching），並評估修復結果 | 完成 |
| HW2 | 論文提案：挑選 2024 年後、能用在這份資料上的時空論文 | 進行中 |
| 期末專題 | 在這份資料上實作 HW2 選定的方法，和 baseline 比較 | 未開始 |

## 資料夾結構

```
├── HW1/            公車 GPS 資料管線：收集、EDA、清理、修復、評估、報告投影片（說明見 HW1/README.md）
│   ├── scripts/    所有程式
│   ├── report/     結果摘要（csv、json）和產生投影片的 build_pptx.py
│   ├── README.md   資料夾說明、收集時段、分析流程（依序執行就能重現結果）
│   └── DATA_SCHEMA.md  所有資料的欄位格式
├── HW2/            參考論文清單和筆記（README.md）
├── db/             PostgreSQL 17＋PostGIS、pgvector、pgRouting、MobilityDB 的 Docker 映像
├── compose.yaml    資料庫的 Docker Compose 設定
└── .env            金鑰和資料庫帳密（不進版控，需自己建立）
```

## 環境

Python 3.10（miniconda 的 `ml` 環境）。主要套件：

| 用途 | 套件（版本） |
|---|---|
| 資料處理 | pandas 2.3、numpy 2.2、pyarrow 21、scipy 1.15 |
| 空間資料與路網 | geopandas 1.1、shapely 2.1、osmnx 2.0、networkx 3.4 |
| 圖表與投影片 | matplotlib 3.10、python-pptx 1.0、lxml 6.0、pillow 11 |
| 收集 | requests 2.32、python-dotenv 1.1 |

在根目錄建立 `.env`，填入以下變數：

| 變數 | 用途 |
|---|---|
| `TDX_CLIENT_ID`、`TDX_CLIENT_SECRET` | TDX API 金鑰（到 TDX 運輸資料流通服務註冊取得） |
| `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` | 資料庫帳密，只傳給 Docker 容器 |

資料庫：在根目錄執行 `docker compose up -d --build`，只有本機（`localhost:5432`）連得到。細節見 [db/README.md](db/README.md)。

## 沒有放進版控的檔案

規則寫在 [.gitignore](.gitignore)：

- **資料**（`HW1/data/`）：原始快照、處理後的 parquet、OSM 路網。檔案太大，用 `HW1/scripts/` 的程式重新收集或產生。
- **CCTV 相關**：畫面、鏡頭清單、收集程式和模型權重。
- **產出物**：圖表、公式圖、投影片（`.pptx`）、執行紀錄。照 [HW1/README.md](HW1/README.md) 的分析流程就能重新產生。
- **PDF**：課程講義和論文。

## 資料來源與授權

- 公車即時 GPS、公車路線線形：資料介接「交通部 TDX 平臺」。
- 道路網：© OpenStreetMap contributors，ODbL 授權。
