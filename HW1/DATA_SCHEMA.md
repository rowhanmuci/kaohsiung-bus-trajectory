# 資料來源與欄位格式

以下欄位都是從實際抓到的回應整理出來的（2026-10-02 ～ 10-04）。範例值都是真實資料。

---

## 一、HW1 主要使用的資料

### 1. 高雄市區公車即時 GPS（TDX A1 定時回報資料）

- **API**：`GET https://tdx.transportdata.tw/api/basic/v2/Bus/RealTimeByFrequency/City/Kaohsiung?$format=JSON`
- **需要**：TDX 會員金鑰（OAuth2 client credentials）。一般會員每把金鑰每分鐘最多 5 次。
- **回傳**：JSON 陣列，每個元素是一台車「最新的一筆」位置。週日傍晚約有 450～480 台。
- **原始檔**：`data/raw/bus_gps_kaohsiung/<YYYYMMDD>/<HHMMSS>.json.gz`，每分鐘一份，內容原封不動。

| 欄位 | 型態 | 範例 | 說明 |
|---|---|---|---|
| `PlateNumb` | str | `002-V3` | **車牌號碼，用來識別每一台車**。同一路線同時有好幾台車時，靠這個欄位區分 |
| `OperatorID` / `OperatorNo` | str | `10250` / `0804` | 客運業者代碼 |
| `RouteUID` / `RouteID` | str | `KHH9201` / `9201` | 路線代碼。UID 前面會加上縣市代碼 |
| `RouteName.Zh_tw` / `.En` | str | `橘20B` / `Orange20B` | 路線名稱 |
| `SubRouteUID` / `SubRouteID` / `SubRouteName` | str | `KHH9201` | 附屬路線，例如同一路線的區間車 |
| `Direction` | int | `1` | 行駛方向：0 = 去程、1 = 返程 |
| `BusPosition.PositionLon` | float | `120.392319` | **經度**（WGS84） |
| `BusPosition.PositionLat` | float | `22.622023` | **緯度**（WGS84） |
| `BusPosition.GeoHash` | str | `wsj8ew5nb` | 位置的 GeoHash（9 碼，精度約 5 m） |
| `Speed` | int | `0` | 車速（km/h） |
| `Azimuth` | int | `235` | 行進方位角（度，0 = 正北） |
| `DutyStatus` | int | `1` | 勤務狀態：0 = 正常（尚未正式發車）、1 = 營運中、2 = 結束 |
| `BusStatus` | int | `0` | 行車狀況：0 = 正常、99 = 非營運（回場、加油、包車等）。**有些紀錄沒有這個欄位** |
| `GPSTime` | str（ISO 8601，+08:00） | `2026-10-04T17:56:20+08:00` | **車機記錄位置的時間**。分析時用這個當時間戳 |
| `SrcUpdateTime` | str | `2026-10-04T17:56:40+08:00` | 來源系統（高雄市公車動態系統）更新的時間 |
| `UpdateTime` | str | `2026-10-04T17:56:50+08:00` | TDX 平台更新的時間（最晚） |

**實測觀察**（週日 17:12–17:57，共 45 次抓取，20,959 筆回報）：

| 現象 | 數量 | 原因或處理方式 |
|---|---|---|
| 回報頻率 | 約每 60 秒一次 | `GPSTime` 前後兩次相差的中位數是 60 秒 |
| 延遲 | `UpdateTime − GPSTime` 中位數 29 秒，p95 51 秒 | — |
| 跨次抓取的重複回報 | 366 筆 | 同一台車在兩次抓取之間沒有新的回報，所以內容一樣。用 (`PlateNumb`, `GPSTime`) 去除重複 |
| 同一次抓取裡同一台車出現兩次 | 135 次 | 內容完全相同，原因不明，去除重複即可 |
| 過時的位置 | 例如 15:58 的位置在 17:12 還出現 | **TDX 會保留每台車最近 2 小時內的最後一筆位置**，停駛的車也會留在清單裡 |
| 中途換路線的車 | 42 台 | 同一台車跑完一條路線後改跑另一條，軌跡要在換路線的地方切開 |
| 座標落在高雄以外 | 25 筆 | 座標錯誤 |
| 不合理的跳點（換算速度超過 100 km/h） | 32 筆 | GPS 飄移 |
| `Speed` 最大值 111 km/h | — | 市區公車不太可能，要檢查 |

### 2. 高雄市 CCTV 清單（TDX）

- **API**：`GET /v2/Road/Traffic/CCTV/City/Kaohsiung`，共 263 支。
- **原始檔**：`data/static/tdx_cctv_kaohsiung.json`

| 欄位 | 型態 | 範例 | 說明 |
|---|---|---|---|
| `UpdateTime` / `UpdateInterval` | str / int | `2026-10-02T20:43:24+08:00` / `21600` | TDX 的更新時間和更新週期（秒） |
| `SrcUpdateTime` / `SrcUpdateInterval` | str / int | `…T00:00:00+08:00` / `86400` | 來源每天更新一次 |
| `AuthorityCode` | str | `KHH` | 管理機關（高雄市） |
| `CCTVs[].CCTVID` | str | `64000C000004` | 鏡頭代碼 |
| `CCTVs[].VideoStreamURL` | str | `https://cctvN.<主機>/<代碼>/`（範例省略） | **影像串流網址**（見第 3 點） |
| `CCTVs[].PositionLon` / `PositionLat` | float | `120.29296` / `22.63687` | 鏡頭位置（WGS84） |
| `CCTVs[].SurveillanceDescription` | str | `中華三路、建國三路` | 監視的路口 |
| `CCTVs[].RoadName` / `RoadID` / `RoadClass` | str / str / int | `中華二路` / `619314E` / `6` | 所在道路和道路等級代碼 |
| `CCTVs[].RoadDirection` | str | `N` | 方向 |
| `CCTVs[].LinkID` | str | `6193140000040E` | 路段代碼（交通部路段編碼），可以和 VD 對應 |
| `CCTVs[].LocationType` / `SurveillanceType` | int | `1` / `-1` | 位置類型 / 監視類型代碼 |
| `CCTVs[].RoadSection.Start/End`、`LocationMile`、`LayoutMapURL` | str | （高雄市區多半是空的） | 路段起訖、里程、配置圖 |

### 3. CCTV 影像串流（高雄市交控中心）

- **網址**：上面的 `VideoStreamURL`，直接連到 `cctvN.kctmc.nat.gov.tw`，**不經過 TDX，不用金鑰**。
- **格式**：HTTPS 上的 MJPEG（`Content-Type: multipart/x-mixed-replace; boundary=---mjpeg---`），每一張都是完整的 JPEG。
- **畫面率**：約 9～14 fps。**解析度因鏡頭而異**，從 320×240 到 1280×720 都有。
- **頻寬**：每支約 330～670 KB/s。
- **時間戳**：串流**沒有**時間資訊。畫面上印的時間有時是錯的（看過印成 2018 年的），**一律用收到畫面的時間**。
- **讀取方式**：`cv2.VideoCapture(url, cv2.CAP_FFMPEG)`，或用 HTTP 串流自己切出 JPEG（見 `scripts/grab_cctv_samples.py`）。

### 4. 公車路線形狀（TDX）

- **API**：`GET /v2/Bus/Shape/City/Kaohsiung`，共 628 筆（路線 × 方向）。
- **原始檔**：`data/static/tdx_bus_shape_kaohsiung.json`

| 欄位 | 型態 | 範例 | 說明 |
|---|---|---|---|
| `RouteUID` / `RouteID` / `RouteName` | str | `KHH100` / `100` / `100百貨幹線` | 路線 |
| `SubRouteUID` / `SubRouteID` / `SubRouteName` | str | `KHH100` | 附屬路線 |
| `Direction` | int | `0` | 0 = 去程、1 = 返程 |
| `Geometry` | str（WKT） | `LINESTRING(120.33852 22.60605, …)` | 路線的線形 |
| `EncodedPolyline` | str | `yf~hCwrn}U~@dX…` | 同一條線形的 Google Encoded Polyline 編碼 |
| `UpdateTime` / `VersionID` | str / int | `2026-10-01T05:35:59+08:00` / `0` | 版本資訊 |

### 5. 高雄市 VD 靜態資料（TDX）

- **API**：`GET /v2/Road/Traffic/VD/City/Kaohsiung`，共 156 支，原始檔在 `data/static/tdx_vd_kaohsiung.json`。
- **欄位**：`VDID`、`PositionLon/Lat`、`RoadName`、`RoadSection.Start/End`、`BiDirectional`、`DetectionLinks[].{LinkID, Bearing, RoadDirection, LaneNum, ActualLaneNum}`、`VDType`、`DetectionType`、`LocationType`、`RoadClass`

### 6. 高雄市 VD 即時資料（TDX，從 2026-10-16 10:30 開始收集）

- **API**：`GET /v2/Road/Traffic/Live/VD/City/Kaohsiung`。每 60 秒更新，資料大約延遲 3 分鐘。
- **原始檔**：`data/raw/vd_kaohsiung/<YYYYMMDD>/<HHMMSS>.json.gz`，每分鐘一份。
- **最上層欄位**：`UpdateTime`、`UpdateInterval`（60）、`SrcUpdateTime`、`AuthorityCode`（KHH）、`VDLives[]`

| 欄位（`VDLives[]` 底下） | 說明 |
|---|---|
| `VDID` | 對應第 5 點的 VD |
| `LinkFlows[].LinkID` | 偵測的路段 |
| `LinkFlows[].Lanes[].{LaneID, LaneType, Speed, Occupancy}` | 每個車道的平均車速（km/h）和佔有率（%） |
| `LinkFlows[].Lanes[].Vehicles[].{VehicleType, Volume, Speed}` | 分車種的車流量：S 小車、L 大車、T 聯結車、**M 機車** |
| `LinkFlows[].Lanes[].ErrorType` | 例如 `diag0` |
| `Status` | 0 = 正常。實測 156 支裡有 58 支是 1、17 支是 3 |
| `DataCollectTime` | 量測時間 |

⚠️ 實測有大約一半的車道車速是 0 或負數。原因可能是那一分鐘沒有車經過，也可能是設備異常，要再分辨。

### 7. CCTV 原始畫面（`crawl_cctv_frames.py`，只用在 2026-10-16 09:00–11:00）

- `data/raw/cctv_kaohsiung/<YYYYMMDD>/<cctv_id>/<HHMMSS_mmm>.jpg`，原始 JPEG，沒有重新壓縮。
- `index.csv`：`fetched_at`（毫秒）、`file`、`bytes`。
- 10:30 以後的版本會**跳過和前一張完全相同的畫面**。原因是伺服器常常重送同一張，有些鏡頭實際每秒只有 1.2～3.4 張不同的畫面；103 號還曾經凍結約 65 秒。

### 8. CCTV 邊收邊切的輸出（`crawl_cctv_online.py`，從 2026-10-16 11:00 開始）

每支鏡頭各自一個資料夾：`data/processed/cctv_online/<YYYYMMDD>/<cctv_id>/`

| 檔案 | 欄位 | 說明 |
|---|---|---|
| `counts.csv` | `fetched_at`、`n_car`、`n_motorcycle`、`n_bus`、`n_truck` | 每一張處理過的畫面中，各車種有幾台（信心分數 ≥ 0.3），每秒約 3～5 列 |
| `bus_detections.csv` | `fetched_at`、`track_uid`、`conf`、`x1`、`y1`、`x2`、`y2`、`frame_w`、`frame_h` | **每一個公車偵測框**（ByteTrack 追蹤之後的結果） |
| `bus_tracks.csv` | `cctv_id`、`track_uid`、`first_seen`、`last_seen`、`n_frames`、`max_conf`、`entry_cx/cy`、`exit_cx/cy`、`best_time`、`best_x1..y2`、`crop_file`、`frame_w/h` | **一台公車在這支鏡頭的一筆紀錄**。超過 10 秒沒再出現就結束這筆紀錄；最高信心分數要達 0.35 才會寫入 |
| `crops/<track_uid>.jpg` | — | 這台公車最大的那一張畫面（長、寬都至少 40 px） |

- `track_uid` = 程式啟動時間（HHMMSS）-追蹤器編號。ByteTrack 有時會把跟丟的車找回來、沿用原本的編號，這時會再加上 `-k` 後綴，所以同一支鏡頭、同一天內不會重複。
- crop 檔名是 `<最佳畫面的時間 HHMMSS_mmm>_<track_uid>.jpg`，開頭就是拍攝時間。2026-10-16 的檔案已經事後改成這個格式。
- `crops_orphaned/`：11:00:10 那次執行在 11:05 被中斷，這些 crop 對應的紀錄還沒寫進 `bus_tracks.csv` 就遺失了，所以沒有時間和位置。只知道拍攝時間在 11:00:10～11:05:05 之間。
- ⚠️ **`bus_tracks.csv` 裡有不少其實不是公車**（YOLO 的 COCO 類別常把箱型貨車、廂型車、小巴判成 bus）。依 2026-10-16 抽樣，`max_conf` 0.35–0.5 只有約 15% 是公車，0.85 以上約 80–85% 是公車。使用前必須再過濾。
- **鏡頭的經緯度不寫在這些檔案裡**，用 `cctv_id` 對照 `config/cameras_main.csv` 或 TDX 的 CCTV 清單取得。
- 另外保留少量原始畫面，用來事後檢查偵測漏了多少：
  - `data/raw/cctv_kaohsiung/<YYYYMMDD>/<cctv_id>/keyframes/`：每 10 分鐘一張完整畫面。
  - `.../sample/`：每小時前 2 分鐘的全部畫面，附 `index.csv`。
- 收集紀錄：`data/raw/cctv_kaohsiung/logs/online_<YYYYMMDD>.log`，每分鐘一列，包含處理速度、佇列長度、丟棄張數、重複張數、公車紀錄數。

---

## 二、自己算出來的衍生檔案（不是 API 原本的欄位）

### `candidate_areas.csv`、`cctv_samples/grab_log.csv`（由 `select_areas.py`、`grab_cctv_samples.py` 產生）

| 欄位 | 說明 |
|---|---|
| `area` | 候選區域編號（area1～area4） |
| `area_center` | 該區域中心鏡頭的路口名稱 |
| `cctv_id` / `desc` / `road` / `lon` / `lat` / `stream_url` | 照抄 TDX CCTV 清單的 `CCTVID` / `SurveillanceDescription` / `RoadName` / `PositionLon` / `PositionLat` / `VideoStreamURL` |
| **`n_routes`** | **依路線圖推算**：有幾條公車路線的線形（第 4 點的 `Geometry`）經過這支鏡頭 30 m 以內。用路線名稱計算，去程和返程算同一條。路口橫向道路上的路線也會算進去。contact sheet 上的 `routes=N` 就是這個值 |
| `status` / `width` / `height` / `fetched_at`（只在 grab_log） | 抓畫面的結果、畫面解析度、抓取時間 |

### `bus_camera_passes.csv`、`bus_camera_pairs.csv`（由 `plot_bus_tracks.py` 產生）

| 欄位 | 說明 |
|---|---|
| `buses` | **依實際 GPS 軌跡統計**：抓取期間有幾台不同的公車（依 `PlateNumb`）的軌跡經過鏡頭 50 m 以內 |
| `routes` | 上面那些公車分屬幾條路線 |
| `from` / `to`（只在 pairs） | 一台公車依序經過的兩支鏡頭 |
| `median_secs` / `dist_m`（只在 pairs） | 這兩支鏡頭之間的旅行時間中位數（秒）、直線距離（m） |

⚠️ **兩個檔案的「路線數」意思不一樣**。以站西路、建國三路（`64000C000341`）為例：
- `n_routes = 37`：路線圖上有 37 條路線經過，這是理論上的數字。
- `routes = 23`：那 45 分鐘內，實際有 43 台車經過，分屬 23 條路線，這是觀測到的數字。

有些路線班次很少，或週日不開，所以實際觀測到的會比較少。

### 處理後的公車 GPS（`data/processed/gps/`，HW1 Part 2–3）

時間都是台灣當地時間（UTC+8），沒有時區標記。`x` / `y` 是 TWD97 / TM2 座標（EPSG:3826，公尺）。

| 檔案 | 產生的程式 | 一列代表 | 筆數 |
|---|---|---|---|
| `gps_polls.csv` | `gps_flatten.py` | 一次輪詢：`poll_time`、`n_reports`（這次回傳幾台車） | 2,549 |
| `gps_reports_raw.parquet` | `gps_flatten.py` | 原始回應的一筆回報，**沒有任何清理** | 1,138,165 |
| `gps_fixes_eda.parquet` | `gps_eda.py` | 一個定位點（研究時段內），加上 EDA 用的欄位 | 1,114,707 |
| `gps_clean.parquet` | `gps_clean.py` | 清理後的一個定位點，已切成趟次 | 1,111,254 |
| `gps_trips.csv` | `gps_clean.py` | 一趟（同一台車、同一路線和方向、中間沒有斷超過 300 秒） | 20,147 |
| `gps_repaired.parquet` | `gps_repair.py` | 修復後的一個點（對到道路的點，或補出來的點） | 見 `report/repair_summary.csv` |

`gps_reports_raw.parquet` 的欄位對應第 1 點的 API 欄位：

| 欄位 | API 欄位 | 欄位 | API 欄位 |
|---|---|---|---|
| `poll_time` | （我們送出請求的時間） | `lon` / `lat` | `BusPosition.PositionLon` / `PositionLat` |
| `plate` | `PlateNumb` | `geohash` | `BusPosition.GeoHash` |
| `operator_id` | `OperatorID` | `speed` / `azimuth` | `Speed`（km/h，瞬時）/ `Azimuth`（度） |
| `route_uid` / `route_name` | `RouteUID` / `RouteName.Zh_tw` | `duty_status` / `bus_status` | `DutyStatus` / `BusStatus` |
| `subroute_uid` / `subroute_name` | `SubRouteUID` / `SubRouteName.Zh_tw` | `gps_time` | `GPSTime` |
| `direction` | `Direction`（0 去程、1 返程） | `src_update_time` / `update_time` | `SrcUpdateTime` / `UpdateTime` |

`gps_fixes_eda.parquet` 多出來的欄位：

| 欄位 | 說明 |
|---|---|
| `window` | 收集日（`10/16 Fri` 等） |
| `dt_s` / `step_m` | 和同一台車上一個點的時間差（秒）、直線距離（m） |
| `implied_kmh` | `step_m / dt_s` 推算的車速 |
| `prev_speed` | 上一個點回報的 `speed` |
| `express` | 路線名稱是否為國道快線（`E` 開頭、快線、快捷、國道），這些路線超過 90 km/h 是正常的 |
| `in_study_area` | 是否在研究範圍方框（120.25–120.43 E，22.53–22.80 N）內 |
| `road_dist_m` | 到最近 OSM 道路的距離（m）；方框外為空值 |
| `drift_spike` | 單點飄移：這個點離路 > 30 m，但前後兩點都離路 < 10 m，而且車在移動 |

`gps_clean.parquet`：保留 `gps_reports_raw` 的主要欄位，再加上 `trip_id`、`express`、`x`、`y`、`dt_s`（趟次內和上一點的秒數），以及 `clock_skew`（`gps_time` 比 `poll_time` 晚超過 5 秒，只標記、不刪除）。清理步驟和每步剩下的筆數在 `report/clean_summary.csv`。

`gps_trips.csv`：`trip_id`、`plate`、`route_name`、`direction`、`express`、`start`、`end`、`n_fixes`、`max_gap_s`（趟次內最長的斷訊秒數）、`minutes`。

`gps_repaired.parquet`：

| 欄位 | 說明 |
|---|---|
| `trip_id` / `plate` / `route_name` / `direction` | 同 `gps_clean` |
| `time` | 點的時間（原有的點 = 原本的 `gps_time`；補出來的點每 60 秒一個） |
| `lon` / `lat` | 修復後的位置 |
| `raw_lon` / `raw_lat` | 原始 GPS 位置（補出來的點為空值） |
| `kind` | `matched`（HMM 對到 `drive` 路網的道路，位置改成道路上的投影點）、`offnet`（50 m 內沒有 `drive` 道路，但有 `bus` 路網的道路，例如總站、轉運站裡的 service road，保留原始位置）、`unmatched`（50 m 內完全沒有道路，例如在研究範圍外、停在車庫裡，或大幅飄移，保留原始位置）、`imputed`（兩個點相隔超過 90 秒時，沿最短行車路徑補的點） |
| `snap_m` | 原始位置到對應道路位置的距離（m），只有 `matched` 有值 |
| `edge_u` / `edge_v` | 對到的 OSM 路段起訖節點 id（`kaohsiung_drive_edges.parquet` 的 `u` / `v`），只有 `matched` 有值 |

---

## 三、其他測過的來源（備查）

| 來源 | 存取方式 | 主要欄位 |
|---|---|---|
| **國道客運即時 GPS**（TDX `/v2/Bus/RealTimeByFrequency/InterCity`） | TDX 金鑰 | 和第 1 點相同，多了 `MessageType`、`SrcRecTime`、`SrcTransTime` |
| **台北市公車 GPS**（`tcgbusfs.blob.core.windows.net/blobbus/GetBusData.gz`） | 不用金鑰，gzip JSON | `BusID`（車牌）、`RouteID`、`GoBack`（去返程）、`Longitude`、`Latitude`、`Speed`、`Azimuth`、`DutyStatus`、`BusStatus`、`DataTime`（`2026-10-02 19:59:07`）。⚠️ **數值全部是字串**，命名也跟 TDX 不同 |
| **台北 YouBike 2.0**（`…/youbike/v2/youbike_immediate.json`） | 不用金鑰 | `sno`（站代碼）、`sna`（站名）、`latitude`、`longitude`、`Quantity`（車柱數）、`available_rent_bikes`、`available_return_bikes`、`act`（是否營運）、`mday`（更新時間） |
| **國道 VD 即時**（高公局 `VDLive.xml`，每分鐘） | 不用金鑰，XML | `VDID`、`LinkFlows.LinkFlow.Lanes.Lane.{LaneID, LaneType, Speed, Occupancy, Vehicles.Vehicle.{VehicleType S/L/T, Volume, Speed}}`、`Status`、`DataCollectTime` |
| **國道 CCTV**（高公局 `CCTV.xml`） | 不用金鑰，XML | `CCTVID`、`VideoStreamURL`（MJPEG，352×240）、`PositionLon/Lat`、`RoadName`、`RoadDirection`、`LocationMile` |
| **國道 eTag 旅行時間**（高公局 `ETagPairLive.xml`，每 5 分鐘） | 不用金鑰，XML | `ETagPairID`（`01F0017N-01F0005N`）、`Flows.Flow.{VehicleType, TravelTime（秒）, SpaceMeanSpeed, VehicleCount}`、`StartTime`、`EndTime` |
| **國道 ETC 旅次 M06A**（高公局 TDCS，每小時一個 CSV） | 不用金鑰，CSV、沒有標題列 | `VehicleType`（31 小客車、32 小貨車、41 大客車、42 大貨車、5 聯結車）、`DetectionTime_O`、`GantryID_O`、`DetectionTime_D`、`GantryID_D`、`TripLength`（km）、`TripEnd`（Y/N）、`TripInformation`（`時間+門架; 時間+門架; …`） |
| **省道 VD**（公路局 `vd/one/VDLiveList.xml`，每分鐘） | 不用金鑰，XML，抓取間隔要 60 秒以上 | 格式和國道 VD 相同。實測有 -99、速度 0、佔有率超過 100% 等異常值 |
| **省道 eTag／路段路況**（公路局） | 不用金鑰，XML | eTag：格式同國道。路段：`SectionID`、`TravelTime`、`TravelSpeed`、`CongestionLevel`、`DataSources.{HasVD, HasETAG, HasGVP…}`、`DataCollectTime` |
| **省道 CCTV**（公路局 `opendataCCTVs.xml`） | 不用金鑰，XML | 欄位同國道 CCTV，多了 `VideoImageURL`（單張截圖，320×240） |
| **OpenSky 航班**（`/api/states/all?lamin…`） | 匿名每天 400 次 | `states[]` 是依位置排列的陣列：`icao24`、`callsign`、`origin_country`、`time_position`、`last_contact`、`longitude`、`latitude`、`baro_altitude`（m）、`on_ground`、`velocity`（m/s）、`true_track`（度）、`vertical_rate`、`sensors`、`geo_altitude`、`squawk`、`spi`、`position_source` |
