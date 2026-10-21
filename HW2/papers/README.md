# HW2 候選論文（完整清單）

> 主要論文已經移到上一層 `HW2/`，總覽見 [../README.md](../README.md)。這裡保留完整的候選清單和其他方向的論文。

HW2 規定：2024 年以後發表、ACM/IEEE Transactions 或頂尖會議、和時空資料有關，而且方法要能用在 HW1 的資料集上。

## 推薦：軌跡修復（主線）＋ 軌跡預測（附帶）

HW1 資料集：高雄市區公車 GPS（約每 60 秒一點）＋ 路口 CCTV 畫面 ＋ OSM 路網。

引用數是 Semantic Scholar 在 2026-10-15 的數字。

| 推薦 | 論文 | 出處 | 機構 | 引用 | 程式碼 | 和我們資料的契合度 |
|---|---|---|---|---|---|---|
| ★1 | **UniTraj**: Learning a Universal Trajectory Foundation Model from Billion-Scale Worldwide Traces | **NeurIPS 2025** | 港科大（廣州）梁宇軒、南科大 James Yu（DiffTraj、ControlTraj 的團隊） | 27（influential 7） | ✅ [Yasoz/UniTraj](https://github.com/Yasoz/UniTraj)，有預訓練模型，Apache-2.0 | 直接吃原始 GPS 點，**不需要路網**，可以處理不同取樣頻率。下游任務同時包含**修復和預測** |
| ★2 | **BIGCity**: A Universal Spatiotemporal Model for Unified Trajectory and Traffic State Data Analysis | **ICDE 2025** | 北航王靜遠（BIGSCity 實驗室，LibCity 的作者群） | 32 | ✅ [bigscity/BIGCity](https://github.com/bigscity/BIGCity)，91★，有預訓練權重和微調腳本 | 一個模型包辦**軌跡修復、下一段預測、旅行時間估計**等 8 種任務。需要先把 GPS 對應到路網（map matching），也可以加入路況資料 |
| 備案 | **MM-STGED**: Micro-Macro ST Graph Encoder-Decoder for Map-Constrained Trajectory Recovery | IEEE TKDE 2024 | 北京交通大學萬懷宇 | 24（influential 5） | ✅ 17★ | 標準的「路網約束軌跡修復」做法，最適合當 baseline |
| 延伸 | VisionTraj | IEEE T-ITS 2025 | 中科院自動化所、商湯 | 8 | ✅ | 從鏡頭紀錄還原軌跡。原論文用的是模擬資料，**我們有 CCTV＋GPS 真實答案**，可以補上這個缺口 |

只能當 baseline 或背景引用（2024 年以前，但引用數高）：MTrajRec（KDD 2021，鄭宇，127 次）、RNTrajRec（ICDE 2023，84 次）、START（ICDE 2023，北航，156 次）、DiffTraj（NeurIPS 2023，136 次）。

## 先前整理的其他候選（跨鏡頭／向量搜尋方向）

| 分類 | 論文 | 出處 | 符合規定？ | 本地檔案 |
|---|---|---|---|---|
| 01 鏡頭紀錄 → 軌跡 | VisionTraj: A Noise-Robust Trajectory Recovery Framework based on Large-scale Camera Network | IEEE T-ITS 2025 | ✅ | 已移到 `../4_extension_VisionTraj_T-ITS2025.pdf` |
| 01 | TrajRecovery: An Efficient Vehicle Trajectory Recovery Framework based on Urban-Scale Traffic Camera Records | KDD 2024 | ✅ | ❌ ACM 會擋程式下載，請用瀏覽器下載：https://dl.acm.org/doi/10.1145/3637528.3671558 |
| 01 | MM-STGED: Micro-Macro ST Graph Encoder-Decoder for Map-Constrained Trajectory Recovery | IEEE TKDE 2024 | ✅ | 已移到 `../3_baseline_MM-STGED_TKDE2024.pdf` |
| 01 | PLMTrajRec: Scalable and Generalizable Trajectory Recovery with Pre-trained LMs | NeurIPS 2025 | ✅ | `01_camera_records_to_trajectory/2025_NeurIPS_PLMTrajRec_sparse_trajectory_recovery.pdf` |
| 02 跨鏡頭查詢處理 | TRACER: Efficient Object Re-Identification in Networked Cameras through Adaptive Query Processing | arXiv 2025 | ⚠️ 正式出處待確認 | `02_crosscamera_query_processing/2025_arXiv_TRACER_ReID_query_processing.pdf` |
| 02 | Argus: Enabling Cross-Camera Collaboration for Video Analytics on Distributed Smart Cameras | IEEE TMC 2025 | ✅ | `02_crosscamera_query_processing/2025_TMC_Argus_crosscamera_collaboration.pdf` |
| 03 帶條件的向量搜尋 | Approximate Nearest Neighbor Search with Window Filters | ICML 2024 | ✅（時空成分要自己在 proposal 裡講清楚） | `03_filtered_vector_search/2024_ICML_ANN_with_Window_Filters.pdf` |
| 03 | iRangeGraph: Improvising Range-dedicated Graphs for Range-filtering NN Search | SIGMOD 2025 | ✅（同上） | `03_filtered_vector_search/2025_SIGMOD_iRangeGraph.pdf` |
| 03 | Dynamic Range-Filtering Approximate Nearest Neighbor Search | VLDB 2025 | ✅（同上） | `03_filtered_vector_search/2025_VLDB_Dynamic_RangeFiltering_ANN.pdf` |
| 03 | WoW: A Window-to-Window Incremental Index for Range-Filtering ANN Search | SIGMOD 2026 | ✅（同上） | `03_filtered_vector_search/2026_SIGMOD_WoW_incremental_window_index.pdf` |
| 03 | SeRF: Segment Graph for Range-Filtering ANN Search | SIGMOD 2024 | ✅（同上） | ❌ 請用瀏覽器下載：https://dl.acm.org/doi/10.1145/3639324 |
| 03 | Timestamp Approximate Nearest Neighbor Search over High-Dimensional Vector Data | ICDE 2025 | ✅（同上） | ❌ 沒有 arXiv 版本，要透過學校連 IEEE Xplore 下載（DOI 10.1109/ICDE65448.2025.00228） |
| 01 | Efficient Methods for Accurate Sparse Trajectory Recovery and Map Matching | ICDE 2025（香港理工） | ✅（引用 6 次） | `01_camera_records_to_trajectory/2025_ICDE_sparse_trajectory_recovery_and_map_matching_PolyU.pdf` |
| 04 軌跡基礎模型 | UniTraj | NeurIPS 2025 | ✅ | 已移到 `../1_main_UniTraj_NeurIPS2025.pdf` |
| 04 | BIGCity | ICDE 2025 | ✅ | 已移到 `../2_candidate_BIGCity_ICDE2025.pdf` |
| 00 背景（2024 年前） | Spatio-Temporal Vehicle Trajectory Recovery on Road Network Based on Traffic Camera Video Data | KDD 2022 | ❌ 太舊，只當背景參考 | `00_background_pre2024/2022_KDD_CamTrajRec_trajectory_recovery_from_camera_video.pdf` |
| 00 | ReXCam: Resource-Efficient, Cross-Camera Video Analytics at Scale | arXiv 2018 | ❌ 太舊，只當背景參考 | `00_background_pre2024/2018_arXiv_ReXCam_crosscamera_ST_locality.pdf` |

## 怎麼組合比較穩

教授要求 proposal 必須清楚說明時空成分。第 03 類是通用的向量索引論文，單獨提出去可能被認為「時空成分不夠」。比較穩的做法是：

- 主要的候選論文從 01 類或 02 類選，這兩類明確在處理鏡頭網路、時空資料。
- 03 類當作我們自己的查詢優化技術，例如「依照路況決定的時間窗」配上「帶範圍條件的向量搜尋」。
