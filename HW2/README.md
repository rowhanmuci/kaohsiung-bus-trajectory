# HW2 參考論文

研究主題：用高雄市區公車 GPS（搭配路口 CCTV），做**軌跡修復**（主線）和**軌跡預測**（附帶）。

## 主要論文（直接放在 HW2/ 底下）

引用數是 Semantic Scholar 在 2026-10-15 的數字。

| 檔案 | 論文 | 出處 | 角色 | 引用 | 程式碼 |
|---|---|---|---|---|---|
| `1_main_UniTraj_NeurIPS2025.pdf` | UniTraj: Learning a Universal Trajectory Foundation Model from Billion-Scale Worldwide Traces | NeurIPS 2025 | **主要研究的論文**（修復＋預測，直接吃原始 GPS 點） | 27 | [Yasoz/UniTraj](https://github.com/Yasoz/UniTraj) |
| `2_candidate_BIGCity_ICDE2025.pdf` | BIGCity: A Universal Spatiotemporal Model for Unified Trajectory and Traffic State Data Analysis | ICDE 2025 | **第二篇候選**（以路網為基礎，同時支援修復、下一段預測、旅行時間估計） | 32 | [bigscity/BIGCity](https://github.com/bigscity/BIGCity) |
| `3_baseline_MM-STGED_TKDE2024.pdf` | Micro-Macro Spatial-Temporal Graph-based Encoder-Decoder for Map-Constrained Trajectory Recovery | IEEE TKDE 2024 | 2024 年後的路網約束修復 baseline | 24 | [wtl52656/MM-STGED](https://github.com/wtl52656/MM-STGED) |
| `4_extension_VisionTraj_T-ITS2025.pdf` | VisionTraj: A Noise-Robust Trajectory Recovery Framework based on Large-scale Camera Network | IEEE T-ITS 2025 | CCTV 延伸實驗（從鏡頭紀錄還原軌跡） | 8 | 論文中有附 |

## baselines/：經典論文（2024 年前，只能引用或當 baseline，不能當 HW2 主要論文）

| 檔案 | 論文 | 出處 | 引用 | 用途 |
|---|---|---|---|---|
| `2009_ACM-GIS_HMM_map_matching_Newson_Krumm.pdf` | Hidden Markov Map Matching Through Noise and Sparseness | ACM SIGSPATIAL GIS 2009 | 1,141 | **HW1 Part 3 的 HMM map matching 原始論文**，Lecture 2 也有引用 |
| `2023_ICDE_RNTrajRec_road_network_trajectory_recovery.pdf` | RNTrajRec: Road Network Enhanced Trajectory Recovery with Spatial-Temporal Transformer | ICDE 2023 | 84 | 修復 baseline（BIGCity 有拿它比較） |
| `2023_ICDE_START_trajectory_representation.pdf` | START: Self-supervised Trajectory Representation Learning with Temporal Regularities and Travel Semantics | ICDE 2023 | 156 | 北航團隊，BIGCity 的前身 |
| `2023_NeurIPS_DiffTraj_trajectory_generation.pdf` | DiffTraj: Generating GPS Trajectory with Diffusion Probabilistic Model | NeurIPS 2023 | 136 | UniTraj 團隊的代表作 |

## 需要用瀏覽器手動下載（網站會擋程式下載，或沒有公開版本）

| 論文 | 出處 | 下載 |
|---|---|---|
| MTrajRec: Map-Constrained Trajectory Recovery via Seq2Seq Multi-task Learning（鄭宇團隊，引用 127） | KDD 2021 | https://dl.acm.org/doi/10.1145/3447548.3467238 或 https://par.nsf.gov/biblio/10326792 |
| TrajRecovery: An Efficient Vehicle Trajectory Recovery Framework based on Urban-Scale Traffic Camera Records | KDD 2024 | https://dl.acm.org/doi/10.1145/3637528.3671558 |
| Fast Map Matching (FMM): an algorithm integrating HMM with precomputation（UniTraj 前處理用的方法） | IJGIS 2018 | https://doi.org/10.1080/13658816.2017.1400548 （程式碼：https://github.com/cyang-kth/fmm ） |

## papers/：其他相關論文

跨鏡頭查詢、帶條件的向量搜尋、其他修復方法等，見 [papers/README.md](papers/README.md)。
