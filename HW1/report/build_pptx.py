"""Build the HW1 report deck (report/HW1_report.pptx) on the Google Slides template, theme fonts and sizes untouched.

Inputs, next to this script:
  template.pptx   the Google Slides theme (only its layouts are used; its sample slides are dropped)
  figures/        from scripts/gps_eda.py and scripts/repair_figures.py
The formulas are rendered first with matplotlib mathtext into formulas/.
Upload the output to Google Slides and download the PDF from there.

Run: python build_pptx.py [out.pptx]
"""
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.oxml.ns import qn
from pptx.util import Inches

HERE = Path(__file__).resolve().parent
TEMPLATE, FIG, FORM = HERE / "template.pptx", HERE / "figures", HERE / "formulas"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "HW1_report.pptx"  # another path if the deck is open in PowerPoint
TEAL, ROW_ALT, WHITE = RGBColor(0x4D, 0xB6, 0xAC), RGBColor(0xF3, 0xF3, 0xF3), RGBColor(0xFF, 0xFF, 0xFF)
L, W, TOP, BOTTOM = 0.34, 9.32, 1.38, 5.05  # content box (inches)
# the template's own slide-number placeholder (layout idx 12) with an auto-updating slidenum field
SLDNUM = ('<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
          'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
          '<p:nvSpPr><p:cNvPr id="{id}" name="Slide Number {id}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
          '<p:nvPr><p:ph type="sldNum" idx="12"/></p:nvPr></p:nvSpPr><p:spPr/>'
          '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:pPr algn="r"/>'
          '<a:fld id="{{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}}" type="slidenum"><a:rPr lang="zh-TW"/><a:t>{n}</a:t></a:fld>'
          '<a:endParaRPr lang="zh-TW"/></a:p></p:txBody></p:sp>')

FORMULAS = {
    "f_emis": r"$p(z_t \mid c)\ \propto\ \exp\left(-\frac{1}{2}\left(\frac{\|z_t - c\|}{\sigma_z}\right)^{2}\right)$",
    "f_trans": r"$p(c_{t+1} \mid c_t)\ \propto\ \exp\left(-\frac{\left|\ \|z_t - z_{t+1}\| - \delta(c_t,\, c_{t+1})\ \right|}{\beta}\right)$",
    "f_viterbi": r"$V_{t+1}(c^{\prime}) = \log p(z_{t+1} \mid c^{\prime}) + \max_{c \in C_t}\left[\,V_t(c) + \log p(c^{\prime} \mid c)\,\right]$",
    "f_interp": r"$\hat{p}(t) = \mathcal{P}_i\left(L_i \cdot \frac{t - t_i}{t_{i+1} - t_i}\right),\quad t_i < t < t_{i+1}$",
    "f_spike": r"$\frac{\|p_i - p_{i-1}\|}{t_i - t_{i-1}} > V_{\max}\quad \mathrm{and}\quad \frac{\|p_{i+1} - p_i\|}{t_{i+1} - t_i} > V_{\max}$",
    "f_kalman": r"$\mathbf{x}_k = [x,\ y,\ v_x,\ v_y]^{T},\qquad \mathbf{x}_{k+1} = F_k\,\mathbf{x}_k + \mathbf{w}_k,\qquad \mathbf{w}_k \sim \mathcal{N}(\mathbf{0},\ \sigma_a^{2}\, G_k G_k^{T})$",
    "f_rts": r"$\hat{\mathbf{x}}_{k|n} = \hat{\mathbf{x}}_{k|k} + C_k\left(\hat{\mathbf{x}}_{k+1|n} - \hat{\mathbf{x}}_{k+1|k}\right),\qquad C_k = P_{k|k}\, F_k^{T}\, P_{k+1|k}^{-1}$",
    "f_metrics": r"$e_i = \|\hat{p}_i - p_i\|,\qquad \mathrm{MAE} = \frac{1}{N}\sum_i e_i,\qquad \mathrm{RMSE} = \sqrt{\frac{1}{N}\sum_i e_i^{2}}$",
    "f_decomp": r"$e_i^{\parallel} = |(\hat{p}_i - p_i)\cdot u_i|,\qquad e_i^{\perp} = |(\hat{p}_i - p_i)\times u_i|,\qquad u_i = \frac{p_{i+1} - p_{i-1}}{\|p_{i+1} - p_{i-1}\|}$",
}


def render_formulas():
    """Each formula as a transparent PNG (STIX math font, dark ink) in formulas/."""
    FORM.mkdir(exist_ok=True)
    plt.rcParams.update({"mathtext.fontset": "stix", "font.family": "STIXGeneral"})
    for name, tex in FORMULAS.items():
        fig = plt.figure(figsize=(0.01, 0.01))
        fig.text(0, 0, tex, fontsize=30, color="#1C2333")
        fig.savefig(FORM / f"{name}.png", dpi=150, transparent=True, bbox_inches="tight", pad_inches=0.06)
        plt.close(fig)


render_formulas()
prs = Presentation(TEMPLATE)
for sid in list(prs.slides._sldIdLst):  # drop the template's sample slides, keep its layouts
    prs.part.drop_rel(sid.rId)
    prs.slides._sldIdLst.remove(sid)
LAY = {l.name: l for l in prs.slide_layouts}


def ph(slide, idx):
    return next(p for p in slide.placeholders if p.placeholder_format.idx == idx)


def rich(paragraph, text):
    """Write text into a paragraph; _{...} becomes a subscript run and ^{...} a superscript run."""
    pos = 0
    for m in re.finditer(r"([_^])\{([^}]*)\}", text):
        if m.start() > pos:
            paragraph.add_run().text = text[pos:m.start()]
        r = paragraph.add_run()
        r.text = m.group(2)
        r.font._rPr.set("baseline", "-25000" if m.group(1) == "_" else "30000")
        pos = m.end()
    if pos < len(text):
        paragraph.add_run().text = text[pos:]


def fill(tf, lines):
    """Lines are strings (level 0) or (level, text) tuples."""
    for n, line in enumerate(lines):
        level, text = line if isinstance(line, tuple) else (0, line)
        p = tf.paragraphs[0] if n == 0 else tf.add_paragraph()
        if n == 0:
            p.text = ""
        p.level = level
        rich(p, text)


def place(shape, left, top, width, height):
    shape.left, shape.top, shape.width, shape.height = Inches(left), Inches(top), Inches(width), Inches(height)


def ratio(path):
    w, h = Image.open(path).size
    return w / h


def picture(slide, path, left, top, width=None, height=None):
    r = ratio(path)
    if width is None:
        width = height * r
    if height is None:
        height = width / r
    return slide.shapes.add_picture(str(path), Inches(left), Inches(top), Inches(width), Inches(height))


def table(slide, rows, left, top, width, col_w, row_h=0.36):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(left), Inches(top), Inches(width), Inches(row_h * len(rows)))
    t = shape.table
    for j, cw in enumerate(col_w):
        t.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        t.rows[i].height = Inches(row_h)
        for j, val in enumerate(row):
            cell = t.cell(i, j)
            p = cell.text_frame.paragraphs[0]
            text = str(val)
            bold = text.startswith("**") and text.endswith("**") and len(text) > 4
            rich(p, text[2:-2] if bold else text)
            if bold:
                for r in p.runs:
                    r.font.bold = True
            cell.fill.solid()
            cell.fill.fore_color.rgb = TEAL if i == 0 else (ROW_ALT if i % 2 == 0 else WHITE)
            for r in p.runs:  # theme "dark 1" is a light mint here: use the body text colour
                if i == 0:
                    r.font.color.rgb = WHITE
                    r.font.bold = True
                else:
                    r.font.color.theme_color = MSO_THEME_COLOR.DARK_2
    return shape


def title_slide(title, subtitle_lines):
    s = prs.slides.add_slide(LAY["TITLE"])
    s.shapes.title.text = title
    fill(ph(s, 1).text_frame, subtitle_lines)


def section(title):
    s = prs.slides.add_slide(LAY["SECTION_HEADER"])
    s.shapes.title.text = title


def bullets(title, lines, body_box=None):
    s = prs.slides.add_slide(LAY["TITLE_AND_BODY"])
    s.shapes.title.text = title
    body = ph(s, 1)
    fill(body.text_frame, lines)
    if body_box:
        place(body, *body_box)
    return s


def title_only(title):
    s = prs.slides.add_slide(LAY["TITLE_ONLY"])
    s.shapes.title.text = title
    return s


def fig_text(title, img, lines, img_w=None, img_h=None):
    """Figure on the left, the two-column layout's right text column next to it (theme default text)."""
    s = prs.slides.add_slide(LAY["TITLE_AND_TWO_COLUMNS"])
    s.shapes.title.text = title
    left_col = ph(s, 1)
    left_col._element.getparent().remove(left_col._element)
    r = ratio(img)
    h = min(img_h if img_h else img_w / r, BOTTOM - TOP)
    w = h * r
    y = TOP + (BOTTOM - TOP - h) / 2  # centred in the content box; the text column starts level with it
    picture(s, img, L, y, width=w, height=h)
    col = ph(s, 2)
    x = L + w + 0.25
    place(col, x, y, L + W - x, BOTTOM - y)
    fill(col.text_frame, lines)
    return s


def fig_only(title, img):
    s = title_only(title)
    r = ratio(img)
    w = min(W, (BOTTOM - TOP) * r)
    picture(s, img, L + (W - w) / 2, TOP, width=w)
    return s


def notation(title, rows):
    s = title_only(title)
    table(s, [["符號", "意義"]] + rows, L, TOP, W, [2.3, 7.02], row_h=0.32)


def add_slide_number(slide, n):
    ids = [int(e.get("id")) for e in slide.shapes._spTree.iter(qn("p:cNvPr"))]
    slide.shapes._spTree.append(etree.fromstring(SLDNUM.format(id=max(ids) + 1, n=n)))


F = lambda n: FIG / f"{n}.png"
M = lambda n: FORM / f"{n}.png"

# ---------------------------------------------------------------- cover, outline
title_slide("高雄公車 GPS 資料集", ["資料收集、品質分析與修復", "[姓名]　[學號]　時空資料庫 HW1"])
bullets("大綱", [
    "01　資料概述：來源、收集方法、欄位、時間與空間涵蓋",
    "02　資料品質問題：EDA 找出的五類問題",
    "03　修復方法：清理、HMM 地圖匹配、沿路網補點",
    "04　評估與結果：遮點實驗、官方路線驗證、修復前後比較",
])

# ---------------------------------------------------------------- 01 data overview
section("01　資料概述")
bullets("資料來源與收集方法", [
    "資料來源：TDX 公車動態定時資料（A1），資料介接「交通部 TDX 平臺」",
    "https://tdx.transportdata.tw/api/basic/v2/Bus/RealTimeByFrequency/City/Kaohsiung",
    "Python 爬蟲以 OAuth2 取得 token，每 60 秒輪詢一次全市快照",
    "原始 JSON 不做修改，gzip 壓縮存檔；Windows 工作排程每天定時啟動、停止",
    "另用：TDX 公車路線線形（驗證）、OpenStreetMap 道路網（地圖匹配）",
])
s = title_only("每筆回報的欄位")
table(s, [
    ["欄位", "說明", "範例"],
    ["PlateNumb", "車牌", "002-V3"],
    ["RouteUID / RouteName", "路線代碼 / 名稱", "KHH9208 / 橘20B區間車"],
    ["Direction", "0 去程、1 返程", "1"],
    ["PositionLon / Lat", "經緯度（WGS84）", "120.39319, 22.621786"],
    ["Speed / Azimuth", "瞬時車速 / 方位角", "9 km/h / 334°"],
    ["GPSTime", "車機定位時間", "2026-10-16 10:30:19"],
    ["UpdateTime", "TDX 平台更新時間", "2026-10-16 10:30:50"],
], L, TOP, W, [3.0, 2.8, 3.52])
s = bullets("收集時段與資料量", [
    "合計 2,549 次輪詢（失敗 1 次）、1,138,165 筆回報、780 台公車、301 條路線；原始資料 gzip 後 58 MB",
], body_box=(L, 3.45, W, 1.4))
table(s, [
    ["日期", "收集時段", "輪詢次數", "回報筆數", "涵蓋情境"],
    ["10/16（五）", "10:30–16:00", "330", "167,120", "平日白天"],
    ["10/17（六）", "09:00–16:00", "420", "177,496", "週末白天"],
    ["10/18（日）", "06:00–21:00", "900", "349,529", "週末全天"],
    ["10/19（一）", "06:00–21:00", "899", "444,020", "平日全天（早晚尖峰）"],
], L, TOP, W, [1.6, 1.8, 1.4, 1.6, 2.92])
fig_text("空間涵蓋", F("eda_00_coverage_map"), [
    "去除重複後 1,114,707 個定位點，遍及市區、山區與台南機場線",
    "研究範圍 120.25–120.43°E、22.53–22.80°N（553 km²），含 87.5% 的點",
    "範圍外多半是國道快線；範圍內下載 OSM 道路網做地圖匹配",
], img_h=3.67)
fig_text("時間涵蓋：平日與週末、尖峰與離峰", F("eda_01_active_buses"), [
    "平日每次輪詢約 490 台在線，週末約 400–418 台",
    "週一 08:30、17:30 兩個尖峰，最多 616 台",
    "週末沒有明顯尖峰",
], img_w=6.0)

# ---------------------------------------------------------------- 02 EDA
section("02　資料品質問題（EDA）")
s = title_only("五類資料問題總覽")
table(s, [
    ["問題", "關鍵數字", "修復時的處理"],
    ["A 取樣不規則、斷訊", "96.51% 間隔正常；> 150 s 共 4,903 次，其中行駛中斷訊 1,125 次", "沿路網補點；休息、> 300 s 就切開"],
    ["B 重複、過期", "1.98% 是同一筆紀錄被重送；最舊約 2 小時", "同一 GPSTime 只留一筆"],
    ["C GPS 漂移", "離路 > 20 m 占 9.42%；單點跳離 325 次", "HMM 地圖匹配"],
    ["D 不合理數值", "推算車速 > 100 km/h 217 對；佔位座標 30 筆", "刪除尖峰異常多的車與含尖峰的趟次、無效座標"],
    ["E 平台延遲", "中位數 29 s、P95 41 s", "時間一律用 GPSTime"],
], L, TOP, W, [2.2, 4.6, 2.52], row_h=0.5)
fig_text("問題 A：取樣間隔不規則與傳輸中斷", F("eda_A_sampling_gaps"), [
    "標稱每 60 秒一筆，96.51% 的間隔在 45–90 s",
    "超過 150 s 的間隔 4,903 次，780 台車中有 705 台出現過",
    "其中車還在同一路線上行駛的傳輸斷訊 1,125 次（314 台）；其餘多為總站休息或收班，清理時切開並刪除停留的點",
], img_w=6.0)
fig_text("問題 B：重複回報與過期位置", F("eda_B_duplicates_stale"), [
    "1.98% 的回報是同一筆紀錄（同車、同 GPSTime）被下一次輪詢重送",
    "停紅燈、塞車時的新定位不算重複，全部保留",
    "平台保留車輛最後的位置，最舊約 2 小時",
    "139 筆有時鐘偏差",
], img_w=6.0)
fig_text("問題 C：GPS 雜訊與漂移", F("eda_C_drift"), [
    "離路中位數 4.4 m；> 20 m 占 9.42%、> 50 m 占 2.03%",
    "離路 > 50 m 的點只有 10% 在行駛中，多半停在場站",
    "行駛中單點跳離道路 325 次（153 台車）",
    "路網需含總站、轉運站內的道路，否則會誤判 1,010 次",
], img_w=6.0)
fig_text("問題 D：物理上不合理的數值", F("eda_D_speed_outliers"), [
    "市區路線推算車速 > 100 km/h 僅 217 對；國道快線的高速是真的",
    "Speed 是瞬時值，47.7% 為 0，常與位置不一致",
    "2 台車 Speed 恆為 0；佔位座標 30 筆；高雄範圍外 196 筆",
], img_w=6.0)
fig_text("問題 E：平台延遲", F("eda_E_latency"), [
    "延遲 = UpdateTime − GPSTime",
    "中位數 29 s、P95 41 s，長尾到 120 s",
    "少數為負值：車機時鐘偏差",
    "時間軸一律用 GPSTime",
], img_h=3.67)

# ---------------------------------------------------------------- 03 repair
section("03　修復方法")
bullets("修復流程", [
    "清理：去除重複、無效座標、速度尖峰（尖峰異常多的車整台刪）、總站等候與休息，再切趟次",
    "HMM 地圖匹配：把每個點對到最可能行駛的 OSM 路段",
    "沿路網補點：斷訊超過 90 s，沿最短行車路徑每 60 s 補一點",
    "評估：遮點實驗（MAE、RMSE）與官方路線線形驗證",
    "結果：890,024 個點、18,767 趟，每點標記 matched / imputed / offnet / unmatched",
])
s = bullets("為什麼用 HMM 地圖匹配", [
    "參考論文也都用 HMM：UniTraj、MM-STGED 用它校正資料、產生答案；RNTrajRec、BIGCity 以 Linear+HMM 為 baseline",
    "MM-STGED 指出 HMM 在稀疏軌跡上的限制（車不一定走最短路徑），和我們 k = 8 的結果一致，正是 HW2 的切入點",
], body_box=(L, 3.6, W, 1.45))
table(s, [
    ["類型", "代表方法", "訓練資料", "在本研究"],
    ["HMM 地圖匹配", "Newson & Krumm 2009、FMM 2018；OSRM、Valhalla 等導航引擎", "不需要", "HW1 修復方法"],
    ["學習式軌跡還原", "MTrajRec 2021、RNTrajRec 2023、MM-STGED 2024", "大量高頻軌跡", "HW2／期末候選"],
    ["軌跡基礎模型", "UniTraj 2025、BIGCity 2025", "大規模預訓練", "HW2／期末候選"],
], L, TOP, W, [2.0, 4.1, 1.6, 1.62], row_h=0.52)
notation("符號說明（一）：清理與 HMM", [
    ["p_{i}, t_{i}", "第 i 個 GPS 點的位置（TWD97 公尺座標）與定位時間"],
    ["V_{max}", "速度上限：市區 100 km/h、國道快線 130 km/h"],
    ["z_{t}", "HMM 的觀測（observation）：第 t 個 GPS 點"],
    ["c, C_{t}", "候選點（candidate，GPS 點在 50 m 內路段上的投影）與其集合（≤ 5 個）"],
    ["‖a − b‖", "兩點的直線距離"],
    ["σ_{z}", "GPS 誤差的標準差（5.5 m）"],
    ["π(z_{t})", "GPS 點在最近道路上的投影點"],
    ["δ(c_{t}, c_{t+1})", "兩個候選點在有向路網上的最短行車距離"],
    ["β", "轉移機率的尺度參數（50 m）"],
    ["V_{t}(c)", "Viterbi 分數：到第 t 點、停在候選 c 的最大對數機率"],
])
s = title_only("步驟一：清理與切趟次")
table(s, [
    ["步驟", "規則", "剩下"],
    ["原始回報", "—", "1,138,165 點"],
    ["1 去除重複", "同一筆紀錄（同車、同 GPSTime）只留一筆", "1,115,588 點"],
    ["2 無效座標", "佔位座標（22 點）；高雄市外框 120.1–121.1°E、22.4–23.5°N 以外（90 點）", "1,115,476 點"],
    ["3 時鐘偏差", "GPSTime 晚於輪詢 > 5 s，只標記", "標記 138 點"],
    ["4 切趟次", "斷訊 > 300 s 或換路線、方向就切", "22,222 趟"],
    ["5 速度尖峰", "依每台車 4 天內的尖峰次數：≥ 5 次的車刪除全部資料（9 台）；1–4 次的車只刪含尖峰的那一趟（20 趟）", "1,102,640 點"],
    ["6 總站等候", "頭尾停在 30 m 內只留出發／抵達點；中途停 ≥ 10 分鐘切開", "900,263 點"],
    ["7 過短趟次", "< 5 點，或移動範圍 < 300 m（停著的車）", "890,024 點、18,767 趟"],
], L, TOP, W, [1.9, 4.9, 2.52], row_h=0.37)
s = bullets("清理的判斷（一）：重複與速度尖峰", [
    "去除重複：只刪「同一筆紀錄」被重送（同車、同 GPSTime）",
    (1, "15,736 組重複中，15,734 組的座標、車速、方位角完全相同"),
    (1, "停紅燈、塞車的新定位（GPSTime 不同）不算重複，全部保留"),
    "速度尖峰：進、出兩段都超過上限的點（下式），共 100 點；推算車速中位數 473 / 545 km/h，是 GPS 位置跳動",
    (1, "尖峰集中在少數車：9 台各有 ≥ 5 次（共 73 次，頻率是全體平均的上百倍，原因不明），視為車速異常資料，整台刪除（11,812 點）"),
    (1, "其他 16 台只有 1–3 次：只刪含尖峰的那一趟（20 趟、1,024 點），保留它們其他正常的資料"),
], body_box=(L, TOP, W, 3.0))
picture(s, M("f_spike"), L + 0.2, 4.45, height=0.5)
bullets("清理的判斷（二）：總站等候與休息", [
    "公車在總站等發車、休息時仍持續回報，這些不是行駛軌跡",
    "趟次開頭、結尾停在 30 m 內的點：只留真正出發、抵達的那一點",
    "30 m 來自 GPS 雜訊：σ_{z} = 5.5 m 時，停著的車兩次定位 99% 在 24 m 內；用 50 m 會多刪約 2,100 個慢速移動的點",
    "趟次中途停 10 分鐘以上：視為休息，切成兩趟（2,005 處）",
    "共刪 202,377 點（18.4%），其中 98.6% 回報的 Speed = 0；行駛中停紅燈、塞車的點保留",
    "刪完後少於 5 點、或移動範圍不到 300 m 的趟次（停著的車）整趟刪除",
])
s = bullets("步驟二：HMM 地圖匹配的模型", [
    "隱藏狀態（hidden state）：GPS 點 z_{t} 在 50 m 內路段上的投影點，最多 5 個候選",
    "發射機率（emission probability）：GPS 誤差為高斯分布，離得越遠機率越低",
    "轉移機率（transition probability）：兩點直線距離應接近行車距離 δ（有向圖最短路徑）；超過 144 km/h 或到不了則為 0",
], body_box=(L, TOP, 4.6, BOTTOM - TOP))
picture(s, M("f_emis"), 5.15, 2.05, width=4.2)
picture(s, M("f_trans"), 5.15, 3.3, width=4.45)
s = bullets("步驟二：Viterbi 解碼（decoding）與參數", [
    "由第一點遞推到最後一點再回溯；到不了就斷鏈重來（共 272 次）",
], body_box=(L, 2.15, W, 0.55))
picture(s, M("f_viterbi"), L + 0.1, TOP, width=7.6)
table(s, [
    ["參數", "值", "決定方式"],
    ["σ_{z}（GPS 誤差）", "5.5 m", "1.4826 × 到最近道路距離的中位數"],
    ["β（轉移尺度）", "50 m", "調參集網格搜尋 {25, 50, 100, 200, 400}，MAE 差異很小"],
    ["半徑 / 候選數", "50 m / 5", "固定"],
    ["最高速度", "144 km/h", "固定"],
], L, 2.8, W, [2.4, 1.5, 5.42], row_h=0.42)
notation("符號說明（二）：內插與 Kalman", [
    ["𝒫_{i}, L_{i}", "第 i、i+1 兩個匹配點之間的最短行車路徑與其長度"],
    ["x_{k}", "Kalman 的狀態向量：位置 x, y 與速度 v_{x}, v_{y}"],
    ["F_{k}", "狀態轉移矩陣：位置加上速度 × Δt"],
    ["w_{k}, G_{k}", "過程雜訊與其係數矩陣（白噪音加速度）"],
    ["σ_{a}", "加速度雜訊的標準差（調參選 0.1 m/s²）"],
    ["𝒩(0, Σ)", "平均 0、共變異數 Σ 的常態分布"],
    ["x̂_{k|k}, x̂_{k|n}", "濾波（用到第 k 點）與平滑（用全部 n 點）後的估計"],
    ["P_{k|k}, C_{k}", "估計的共變異數、RTS 平滑增益"],
    ["A^{T}, A^{−1}", "轉置、反矩陣"],
])
s = bullets("步驟三：沿路網內插", [
    "route-based interpolation：兩個匹配點之間，沿最短行車路徑等速前進",
], body_box=(L, 2.15, W, 0.55))
picture(s, M("f_interp"), L + 0.1, TOP, height=0.62)
table(s, [
    ["類別", "規則", "點數"],
    ["matched", "對到道路，改成路上的投影點", "771,601（86.7%）"],
    ["imputed", "斷訊 > 90 s，沿路網每 60 s 補一點", "3,143"],
    ["offnet", "50 m 內只有總站、轉運站內的道路，保留原位", "5,509"],
    ["unmatched", "50 m 內沒有道路（多在研究範圍外），保留原位", "112,914"],
], L, 2.8, W, [1.6, 5.5, 2.22], row_h=0.42)
fig_text("路網的選擇（一）：同一地點，兩種路網", F("network_drive_vs_bus_1"), [
    "左：一般道路網（OSM drive），不含總站、轉運站內的道路，橘點附近沒有路可以對",
    "右：加上 service road 與公車專用道，路段從 116 條增加到 217 條",
    "多出來的大多是巷弄小路",
], img_w=6.6)
fig_text("路網的選擇（二）：仍用一般道路網", F("network_drive_vs_bus_2"), [
    "岡山一帶：路段從 158 條增加到 572 條，總站內的繞行道路仍沒有完整畫出",
    "小路讓最短路徑抄捷徑：清理前的比較中，路徑在官方路線上的比例 97.6% → 96.2%",
    "所以匹配用一般道路網，這些點保留原位、標成 offnet（5,509 點，0.6%）",
], img_w=6.6)
s = bullets("比較用的三種 baseline", [
    "直線內插：x(t)、y(t) 在保留的點之間線性內插",
    "Cubic spline：natural cubic spline 通過保留的點",
    "Kalman + RTS：等速模型，前向濾波後平滑，σ_{a} = 0.1 m/s²",
    "三者都只用時間與座標，不知道道路在哪裡",
], body_box=(L, TOP, W, 1.95))
picture(s, M("f_kalman"), L + 0.1, 3.45, width=8.2)
picture(s, M("f_rts"), L + 0.1, 4.1, width=6.7)

# ---------------------------------------------------------------- 04 evaluation
section("04　評估與結果")
notation("符號說明（三）：評估指標", [
    ["k", "每 k 個點保留 1 個（k = 2、4、8，即每 2、4、8 分鐘一點）"],
    ["p_{i}, p̂_{i}", "第 i 個被遮點的真實位置、還原位置"],
    ["e_{i}, N", "還原誤差（兩點距離）、被遮點的數量"],
    ["MAE, RMSE", "誤差的平均、均方根"],
    ["u_{i}", "用前後兩個真實點估計的行進方向（單位向量）"],
    ["e_{i}^{∥}", "沿行進方向（along-track）的誤差：時間估錯"],
    ["e_{i}^{⊥}", "垂直行進方向（cross-track）的誤差：偏離道路"],
    ["a · b, a × b", "內積、二維外積（取絕對值即投影長度）"],
])
s = bullets("評估一：遮點實驗的設計", [
    "選趟次：整趟在研究範圍內、市區路線、≥ 30 點、無超過 90 s 的斷訊（9,729 趟）",
    "每天抽 70 趟共 280 趟：調參 56 趟、測試 224 趟",
    "每 k 點留 1 點（k = 2、4、8），被遮掉的真實 GPS 點當答案",
    "誤差拆成沿行進方向（along-track）與垂直方向（cross-track）",
], body_box=(L, TOP, W, 2.0))
picture(s, M("f_metrics"), L + 0.1, 3.4, width=6.2)
picture(s, M("f_decomp"), L + 0.1, 4.25, width=6.9)
s = bullets("結果：MAE 與 RMSE（公尺，粗體為最佳）", [
    "HMM 的 MAE 在三種稀疏程度都最低，比最好的 baseline 少 11.0% / 12.4% / 11.7%",
    "k = 2 時 RMSE 與直線內插相當：少數點選錯路、誤差很大，RMSE 對大誤差較敏感",
], body_box=(L, 3.65, W, 1.35))
table(s, [
    ["方法", "MAE k=2", "MAE k=4", "MAE k=8", "RMSE k=2", "RMSE k=4", "RMSE k=8"],
    ["HMM（本研究）", "**108.0**", "**157.2**", "**266.7**", "**146.2**", "**206.6**", "**351.5**"],
    ["直線內插", "121.4", "182.8", "308.5", "**146.2**", "220.1", "379.2"],
    ["Cubic spline", "123.1", "179.7", "304.9", "146.9", "214.7", "373.9"],
    ["Kalman + RTS", "124.6", "179.5", "302.2", "148.4", "214.3", "370.0"],
], L, TOP, W, [2.12, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2], row_h=0.42)
s = bullets("結果：誤差拆解（k = 4，粗體為最佳）", [
    "垂直方向誤差比直線內插少 32–42%；沿行進方向的誤差四種方法幾乎相同，是剩下的主要誤差",
], body_box=(L, 3.75, W, 1.0))
table(s, [
    ["方法", "沿行進方向 e^{∥}", "垂直方向 e^{⊥}", "P90", "15 m 內有道路"],
    ["HMM（本研究）", "**128.2**", "**56.4**", "**318.0**", "**98.9%**"],
    ["直線內插", "130.1", "96.6", "345.9", "48.6%"],
    ["Cubic spline", "131.4", "92.2", "336.9", "41.8%"],
    ["Kalman + RTS", "131.1", "92.3", "334.8", "41.2%"],
], L, TOP, W, [2.32, 1.75, 1.75, 1.75, 1.75], row_h=0.42)
fig_only("各方法的誤差比較", F("repair_error_by_k"))
fig_text("誤差分布（每 4 分鐘留 1 點）", F("repair_cdf_k4"), [
    "HMM 的曲線在每個誤差門檻都在最上方",
    "誤差 < 50 m 的比例：HMM 19.7%、直線內插 9.9%",
    "刪除總站停留前，30 m 以下反而是直線較好：那些多是停著的車，被 HMM 拉到道路中心線",
], img_h=3.67)
fig_only("還原範例：四種方法分開比較", F("repair_example_k4_panels"))
fig_text("評估二：用官方路線線形驗證", F("repair_route_validation"), [
    "官方路線線形 HMM 沒用到，可當獨立答案",
    "原始 GPS 在路線上時，HMM 對到的點 99.93% 在 30 m 內；路徑 97.9% 在路線上（直線相連 86.8%）",
    "越稀疏越容易偏離（k = 8：66%）",
    "4.7% 的趟次整趟不在標示路線上（繞駛、回場）",
], img_w=6.0)
fig_only("官方路線 vs. 修復後的路徑", F("route_vs_repair"))
fig_text("全量修復結果與修復前後比較", F("repair_before_after"), [
    "890,024 個點：771,601 個對到道路（86.7%；研究範圍內 98.9%），補 3,143 點",
    "5,509 / 112,914 個點在路網外（多在研究範圍外），保留原位",
    "對到道路的移動距離：中位數 4.3 m、P95 15.5 m",
    "① 過港隧道附近 49 m 的飄移被拉回隧道路線；隧道附近的補點比例是平均的 2 倍",
    "② 96 路斷訊 240 秒：官方路線繞學府路，直線上沒有隧道；補的 3 點都在路線 3 m 內",
    "公車走的路不在路網時 HMM 不適用（前頁左圖）",
], img_h=3.67)

# ---------------------------------------------------------------- discussion
bullets("限制", [
    "時間誤差是主要誤差：等速內插無法處理停站、紅燈",
    "最短路徑假設：點越稀疏越容易選錯路（k = 8 只有 66% 在路線上）",
    "路網缺路時 HMM 不適用：公車走的路不在 drive 路網（總站、校園；大學橋在 OSM 標成 driveway），只能保留原位，斷訊也補不了",
    "離路 > 50 m 的飄移沒有修（50 m 內沒有候選道路）",
    "答案本身有雜訊：遮點實驗的答案是 GPS（σ_{z} ≈ 5.5 m）",
    "研究範圍外 12.5% 的點沒有做地圖匹配",
])
bullets("結論", [
    "收集：4 天、2,549 次輪詢、1,138,165 筆回報、780 台車，涵蓋平日與週末、尖峰與離峰",
    "清理：刪除重複、速度尖峰、總站停留，留下 890,024 點、18,767 趟",
    "修復：HMM 地圖匹配的 MAE 比最好的 baseline 少 11–12%，垂直方向誤差少 32–42%",
    "驗證：修復後的路徑 97.9% 在官方路線上",
    "剩下的主要誤差在時間；HW2 將用學習式軌跡還原模型處理，並把公車路線當成先驗",
])
bullets("參考資料（一）", [
    "[1] P. Newson and J. Krumm. Hidden Markov map matching through noise and sparseness. ACM SIGSPATIAL GIS, 2009.",
    "[2] C. Yang and G. Gidófalvi. Fast map matching, an algorithm integrating hidden Markov model with precomputation. IJGIS, 2018.",
    "[3] H. E. Rauch, F. Tung, and C. T. Striebel. Maximum likelihood estimates of linear dynamic systems. AIAA Journal, 1965.",
    "[4] G. Boeing. OSMnx: New methods for acquiring, constructing, analyzing, and visualizing complex street networks. CEUS, 2017.",
    "[5] H. Ren et al. MTrajRec: Map-constrained trajectory recovery via seq2seq multi-task learning. KDD, 2021.",
])
bullets("參考資料（二）", [
    "[6] Y. Chen et al. RNTrajRec: Road network enhanced trajectory recovery with spatial-temporal transformer. ICDE, 2023.",
    "[7] T. Wei et al. Micro-macro spatial-temporal graph-based encoder-decoder for map-constrained trajectory recovery. IEEE TKDE, 2024.",
    "[8] Y. Zhu et al. UniTraj: Learning a universal trajectory foundation model from billion-scale worldwide traces. NeurIPS, 2025.",
    "[9] X. Yu et al. BIGCity: A universal spatiotemporal model for unified trajectory and traffic state data analysis. ICDE, 2025.",
    "[10] 交通部 TDX 運輸資料流通服務平臺 https://tdx.transportdata.tw/",
    "[11] OpenStreetMap contributors（ODbL）",
])

for n, slide in enumerate(prs.slides, 1):
    if n > 1:  # no number on the cover
        add_slide_number(slide, n)
prs.save(OUT)
print("slides:", len(prs.slides), "->", OUT)
