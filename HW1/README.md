# HW1：高雄市公車 GPS 資料集（同步收集 VD 與路口 CCTV）

HW1 只使用**公車 GPS**。VD 和 CCTV 跟 GPS 在同一段時間收集，留給期末專題使用。

## 資料夾結構

```
HW1/
├── scripts/
│   ├── tdx.py                 TDX API 客戶端（金鑰從專案根目錄的 .env 讀取，每分鐘最多呼叫 5 次）
│   ├── crawl_tdx_live.py      每分鐘抓一次 TDX 即時資料，原始回應原封保存：--dataset bus_gps（公車 GPS）或 vd（車輛偵測器）
│   ├── crawl_cctv_online.py   正式版 CCTV 收集：邊收邊用 YOLO（多支鏡頭一起批次處理）＋每支鏡頭各自的公車追蹤，存公車 crop、偵測框、各車種數量、少量原始畫面
│   ├── crawl_cctv_frames.py   CCTV 原始畫面錄影（10/16 測試用；原始 JPEG、跳過完全重複的畫面、記錄畫面凍結）
│   ├── extract_crops.py       離線處理：畫面 → YOLO＋ByteTrack → 偵測框、鏡頭內追蹤、每台車最清楚的一張 crop
│   ├── qc_report.py           每日資料品質檢查（GPS、VD、CCTV）
│   ├── build_osm_network.py   下載研究範圍（市區方框，涵蓋 88% 的 GPS 定位點）的 OSM 道路網：drive（map matching 用）、bus（drive＋service＋公車專用道，EDA 和標記用）
│   ├── gps_flatten.py         把公車 GPS 原始快照攤平成一張表（不做任何清理）→ data/processed/gps/gps_reports_raw.parquet
│   ├── gps_eda.py             HW1 Part 2：GPS 探索性分析，資料問題 A–E 的圖和摘要表 → report/
│   ├── gps_clean.py           HW1 Part 3：清理（去重複、刪無效座標、標記時鐘偏差、刪速度尖峰）＋切趟次 → gps_clean.parquet
│   ├── map_matching.py        HMM map matching（Newson & Krumm 2009）＋沿最短行車路徑內插，給下面兩支程式共用
│   ├── repair_eval.py         HW1 Part 3：遮點實驗（每 2／4／8 分鐘留 1 點），比較 HMM、直線、spline、Kalman，調參數 → report/repair_eval_*
│   ├── gps_repair.py          HW1 Part 3：用調好的參數修復全部 20,147 趟（對到道路、斷訊超過 90 秒沿路網補點；路網外的點保留原位並標記）→ gps_repaired.parquet
│   ├── route_shape_check.py   HW1 Part 3：用 TDX 官方路線線形（HMM 沒用到）獨立驗證修復後的點和路徑是否在公車路線上 → report/route_shape_*
│   ├── repair_figures.py      HW1 Part 3 的圖（誤差比較、CDF、還原範例、修復前後）
│   ├── keepawake.py           爬蟲執行期間防止 Windows 進入睡眠
│   ├── maputil.py             共用的地圖底圖（OSM，失敗時自動改用 CARTO Voyager）
│   ├── select_areas.py / evaluate_camera_coverage.py   挑選鏡頭範圍、比較不同鏡頭組合的涵蓋程度
│   ├── grab_cctv_samples.py   每支鏡頭抓一張畫面，產生總覽圖
│   └── plot_bus_tracks.py     把公車 GPS 畫成軌跡，並統計每支鏡頭有幾台公車經過
├── config/cameras_main.csv    正式收集用的 18 支鏡頭（車站 1.5 km 內，排除離線、低解析度、4K 和公車很少的鏡頭）
├── models/yolo11s.pt          YOLO11s 權重（Ultralytics，COCO 預訓練）
├── data/
│   ├── raw/bus_gps_kaohsiung/<YYYYMMDD>/<HHMMSS>.json.gz   公車 GPS 原始快照（每分鐘一份）
│   ├── raw/vd_kaohsiung/<YYYYMMDD>/<HHMMSS>.json.gz        VD 原始快照（每分鐘一份）
│   ├── raw/cctv_kaohsiung/<YYYYMMDD>/<cctv_id>/            CCTV 原始畫面＋index.csv
│   ├── raw/*/logs/                                         每日收集紀錄
│   ├── processed/cctv_online/<YYYYMMDD>/<cctv_id>/         正式版：counts.csv、bus_detections.csv、bus_tracks.csv、crops/
│   ├── processed/cctv_tracks/<YYYYMMDD>/<cctv_id>/         離線版（extract_crops.py）：detections.parquet、tracks.parquet、crops/
│   ├── processed/gps/         gps_reports_raw.parquet（原始回報攤平）、gps_fixes_eda.parquet（每個定位點加上時間差、推算車速、離道路距離）、
│   │                          gps_clean.parquet＋gps_trips.csv（清理後、切好趟次）、gps_repaired.parquet（修復後），欄位見 DATA_SCHEMA.md
│   ├── static/                TDX 靜態資料（CCTV 清單、公車路線形狀、VD 清單）
│   └── static/osm/            OSM 路網 kaohsiung_drive.* 和 kaohsiung_bus.*（.graphml、_edges.parquet、_nodes.parquet、_summary.json）、study_area.geojson（© OpenStreetMap contributors，ODbL 授權）
├── report/figures/            EDA 圖表（eda_*.png）、修復與評估圖表（repair_*.png、network_drive_vs_bus.png、route_vs_repair.png）
├── report/HW1_report.pptx     報告投影片（套用 Google 簡報範本；上傳到 Google 簡報後下載 PDF）
├── report/build_pptx.py       產生報告投影片：先把公式畫成圖（report/formulas/），再套 template.pptx 排版、放進 figures/ 的圖
├── report/template.pptx       Google 簡報範本（只用它的版面配置）
├── report/eda_summary.csv     EDA 各項指標的數字
├── report/clean_summary.csv   清理每一步剩下的筆數
├── report/repair_params.json  調好的參數（σz、β、σa）和調參結果
├── report/repair_eval_summary.csv / repair_eval_errors.parquet / repair_eval_log.txt   遮點實驗結果（每個被遮的點一列）
├── report/repair_summary.csv / repair_log.txt          全部資料修復的統計
├── report/route_shape_*       官方路線線形驗證（摘要 csv、逐點 / 逐段明細）
├── report/v1_drive_network/、v2_bus_network/           兩種路網的實驗結果備份（比較見 EXPERIMENT_LOG.md）
├── EXPERIMENT_LOG.md          實驗紀錄：做過的實驗、結果、修正過的錯誤
├── camera_coverage_designs.csv / camera_coverage_map.html  鏡頭範圍的比較結果
├── bus_tracks_map.html / bus_tracks_focus_map.html         公車軌跡地圖
├── bus_camera_passes.csv / bus_camera_pairs.csv            每支鏡頭、每對鏡頭有幾台公車經過
├── DATA_SCHEMA.md             所有資料來源的欄位格式說明
└── cctv_samples/              範例畫面、YOLO 示範、GPS 和 CCTV 時間對齊的檢查結果
```

## 實際收集的時段（已全部結束，排程已停用）

| 日期 | 公車 GPS、VD | CCTV（邊收邊切） |
|---|---|---|
| 10/16（五） | 10:30–16:00 | 11:00–16:00（09:00–11:00 是測試，存原始畫面） |
| 10/17（六） | 09:00–16:00 | 09:00–16:00 |
| 10/18（日） | 06:00–21:00 | 07:00–20:00 |
| 10/19（一） | 06:00–21:00 | 07:00–20:00 |

HW1 的分析使用上表的公車 GPS：2,549 次輪詢、1,138,165 筆回報、780 台車、301 條路線。10/19 15:09 有一次 TDX 輪詢失敗。

## 正式收集的排程設定（Windows 工作排程，目前已停用）

| 排程 | 程式 | 每天的時段 |
|---|---|---|
| `STD_GPS` | `crawl_tdx_live.py --dataset bus_gps --from 05:00 --until 24:00` | 05:00–24:00，每 60 秒 |
| `STD_VD` | `crawl_tdx_live.py --dataset vd --from 05:00 --until 24:00` | 05:00–24:00，每 60 秒 |
| `STD_CCTV` | `crawl_cctv_online.py --cams ..\config\cameras_main.csv --fps 5 --from 07:00 --until 20:00` | 07:00–20:00（2026-10-16 11:00 起改用這個版本，之前是存原始畫面） |

- 每個排程都會在**每天的開始時間**和**使用者登入時**觸發。如果已經在跑，就不會再開第二份。
- 電腦如果在睡眠中，Windows 會把它叫醒。程式執行期間電腦不會自己睡著，晚上程式結束後就可以正常睡眠。
- 正式收集從 2026-10-16 10:30 開始。在這之前，09:00–10:25 是測試批次。

## HW1 分析流程（依序執行就能重現 report/ 裡的所有數字和圖）

```
cd HW1/scripts
python build_osm_network.py --network drive   # OSM 路網：map matching 用
python build_osm_network.py --network bus     # OSM 路網：EDA 離路距離、標記 offnet 用
python gps_flatten.py         # 原始快照 → gps_reports_raw.parquet
python gps_eda.py             # Part 2：EDA，問題 A–E
python gps_clean.py           # Part 3：清理、切趟次
python repair_eval.py         # Part 3：遮點實驗、調參數（8 核心）
python gps_repair.py          # Part 3：修復全部資料（14 核心）
python route_shape_check.py   # Part 3：用官方路線線形驗證路徑（14 核心）
python repair_figures.py      # Part 3：圖表
cd ../report
python build_pptx.py          # 報告投影片 HW1_report.pptx（簡報在 PowerPoint 開著時，可指定別的輸出路徑）
```

## 手動執行

使用 miniconda 的 `ml` 環境：

```
cd HW1/scripts
C:\Users\User\miniconda3\envs\ml\python.exe crawl_tdx_live.py --dataset bus_gps --minutes 45
C:\Users\User\miniconda3\envs\ml\python.exe qc_report.py --day 20261016
C:\Users\User\miniconda3\envs\ml\python.exe extract_crops.py --day 20261016 --cams ../config/cameras_main.csv
C:\Users\User\miniconda3\envs\ml\python.exe plot_bus_tracks.py
```

地圖要用 http 開才會顯示 OSM 底圖，例如在 `HW1` 資料夾執行 `python -m http.server 8000`，再打開 http://localhost:8000/bus_tracks_map.html 。直接雙擊檔案打開的話，會自動改用 CARTO Voyager 底圖。

## 資料來源

- TDX 運輸資料流通服務（資料介接「交通部 TDX 平臺」）：高雄市公車即時 GPS、VD 即時資料、CCTV 清單、公車路線形狀。
- 高雄市政府交通局 CCTV 的 MJPEG 串流。網域在 2026-10-15 從 `cctvN.kctmc.nat.gov.tw` 改成 `cctvN.itc.tbkc.gov.tw`，所以每次啟動都會先向 TDX 拿最新的網址。
