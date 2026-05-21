# -*- coding: utf-8 -*-
"""
PDF报告生成模块
使用reportlab生成专业选型方案报告
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
import sys
import urllib.request
import tempfile
from datetime import datetime


# ── 字体注册（兼容 Windows 和 Linux/Railway）─────────────────────────────
def _ensure_chinese_font():
    """
    确保中文字体可用：
    1. Windows: 使用系统自带的微软雅黑
    2. Linux/Railway: 自动下载 Google Noto Sans SC（免费开源）到临时目录
    返回 (普通字体名, 粗体字体名)
    """
    # ── Windows 本地字体 ──
    _win_fonts = [
        (r"C:\Windows\Fonts\msyh.ttc",    "msyh",    "msyh"),
        (r"C:\Windows\Fonts\msyhbd.ttc",  "msyhbd",  "msyhbd"),
        (r"C:\Windows\Fonts\simhei.ttf",  "simhei",  "simhei"),
    ]
    registered = []
    for fp, name, _ in _win_fonts:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont(name, fp))
                registered.append(name)
            except Exception:
                pass

    if "msyh" in registered and "msyhbd" in registered:
        return "msyh", "msyhbd"
    if registered:
        return registered[0], registered[0]

    # ── Linux/Railway: 下载 Google Noto Sans SC ──
    font_dir = os.path.join(tempfile.gettempdir(), "windmatch_fonts")
    os.makedirs(font_dir, exist_ok=True)

    noto_regular = os.path.join(font_dir, "NotoSansSC-Regular.ttf")
    noto_bold   = os.path.join(font_dir, "NotoSansSC-Bold.ttf")

    # 使用 Google Fonts 的可变字体（单文件包含所有粗细）
    noto_url = (
        "https://github.com/google/fonts/raw/main/"
        "ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf"
    )

    downloaded = False
    for path in [noto_regular]:
        if not os.path.exists(path):
            try:
                print(f"[WindMatch] 正在下载中文字体...")
                req = urllib.request.Request(noto_url, headers={
                    "User-Agent": "Mozilla/5.0"
                })
                with urllib.request.urlopen(req, timeout=60) as resp:
                    with open(path, "wb") as f:
                        f.write(resp.read())
                downloaded = True
                print(f"[WindMatch] 中文字体下载完成")
            except Exception as e:
                print(f"[WindMatch] 字体下载失败: {e}")

    # 注册字体
    if os.path.exists(noto_regular):
        try:
            pdfmetrics.registerFont(TTFont("noto_sc", noto_regular))
            registered.append("noto_sc")
        except Exception as e:
            print(f"[WindMatch] 字体注册失败: {e}")

    if "noto_sc" in registered:
        return "noto_sc", "noto_sc"

    # 最终兜底
    print("[WindMatch] 警告: 未找到中文字体，PDF中文可能显示为方块")
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = _ensure_chinese_font()

W, H = A4
MARGIN = 2.0 * cm

# ── 颜色 ──────────────────────────────────────────────────────────────────
C_DARK   = colors.HexColor("#1A3A5C")
C_ACCENT = colors.HexColor("#E8A020")
C_LIGHT  = colors.HexColor("#EDF3F8")
C_LINE   = colors.HexColor("#2E7DBF")
C_GRAY   = colors.HexColor("#6C757D")
C_GREEN  = colors.HexColor("#27AE60")
C_RED    = colors.HexColor("#C0392B")
C_ORANGE = colors.HexColor("#E67E22")


def S(name, **kw):
    return ParagraphStyle(name, **kw)


# ── 样式定义 ───────────────────────────────────────────────────────────────
sTitle = S("sTitle",
    fontName=FONT_BOLD, fontSize=22, leading=30,
    textColor=C_DARK, alignment=1, spaceAfter=6)

sSubtitle = S("sSubtitle",
    fontName=FONT, fontSize=12, leading=17,
    textColor=C_ACCENT, alignment=1, spaceAfter=4)

sChapter = S("sChapter",
    fontName=FONT_BOLD, fontSize=13, leading=18,
    textColor=colors.white, spaceAfter=0)

sH2 = S("sH2",
    fontName=FONT_BOLD, fontSize=11, leading=16,
    textColor=C_DARK, spaceBefore=8, spaceAfter=3)

sH3 = S("sH3",
    fontName=FONT_BOLD, fontSize=10, leading=14,
    textColor=C_LINE, spaceBefore=6, spaceAfter=2)

sBody = S("sBody",
    fontName=FONT, fontSize=9, leading=14,
    textColor=colors.HexColor("#2C2C2C"), spaceAfter=3)

sBodyBold = S("sBodyBold",
    fontName=FONT_BOLD, fontSize=9, leading=14,
    textColor=C_DARK, spaceAfter=3)

sCaption = S("sCaption",
    fontName=FONT, fontSize=7.5, leading=10,
    textColor=C_GRAY, alignment=1, spaceAfter=5)

sCoverMeta = S("sCoverMeta",
    fontName=FONT, fontSize=10, leading=16,
    textColor=colors.HexColor("#4A4A4A"), alignment=1)

sSmall = S("sSmall",
    fontName=FONT, fontSize=8, leading=11,
    textColor=C_GRAY, spaceAfter=2)

sGreen = S("sGreen",
    fontName=FONT_BOLD, fontSize=9, leading=14,
    textColor=C_GREEN, spaceAfter=3)

sRed = S("sRed",
    fontName=FONT_BOLD, fontSize=9, leading=14,
    textColor=C_RED, spaceAfter=3)


# ── 工具函数 ──────────────────────────────────────────────────────────────
def HR(color=C_LINE, thickness=0.8):
    return HRFlowable(width="100%", thickness=thickness,
                      color=color, spaceAfter=5, spaceBefore=2)


def spacer(h=0.3):
    return Spacer(1, h * cm)


def chapter_banner(title):
    tbl = Table([[Paragraph(title, sChapter)]],
                colWidths=[W - 2 * MARGIN])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_DARK),
        ("LEFTPADDING",  (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING",   (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0), (-1,-1), 6),
    ]))
    return tbl


def kv_table(rows, col_w=None):
    if col_w is None:
        col_w = [(W - 2 * MARGIN) * f for f in [0.34, 0.66]]
    ts_k = S("tk", fontName=FONT_BOLD, fontSize=8.5, textColor=C_DARK)
    ts_v = S("tv", fontName=FONT, fontSize=8.5, textColor=colors.HexColor("#333"))
    data = [[Paragraph(k, ts_k), Paragraph(v, ts_v)] for k, v in rows]
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), C_LIGHT),
        ("GRID",       (0,0), (-1,-1), 0.4, colors.HexColor("#CCDDEE")),
        ("LEFTPADDING",  (0,0), (-1,-1), 7),
        ("RIGHTPADDING", (0,0), (-1,-1), 7),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    return t


def multi_col_table(headers, rows, col_widths=None, header_color=C_DARK):
    ts_h = S("th", fontName=FONT_BOLD, fontSize=8.5, textColor=colors.white, alignment=1)
    ts_d = S("td", fontName=FONT, fontSize=8.2, textColor=colors.HexColor("#2C2C2C"))
    ts_dc = S("tdc", fontName=FONT, fontSize=8.2, textColor=colors.HexColor("#2C2C2C"), alignment=1)
    data = [[Paragraph(h, ts_h) for h in headers]]
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            if i == 0:
                cells.append(Paragraph(str(cell), ts_d))
            else:
                cells.append(Paragraph(str(cell), ts_dc))
        data.append(cells)
    if col_widths is None:
        n = len(headers)
        col_widths = [(W - 2 * MARGIN) / n] * n
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), header_color),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, C_LIGHT]),
        ("GRID",         (0,0), (-1,-1), 0.4, colors.HexColor("#CCDDEE")),
        ("LEFTPADDING",  (0,0), (-1,-1), 5),
        ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ]))
    return t


def score_bar_table(matches: list):
    """带评分条形图的表格"""
    ts_h = S("th", fontName=FONT_BOLD, fontSize=8.5, textColor=colors.white, alignment=1)
    ts_d = S("td", fontName=FONT, fontSize=8.2, textColor=colors.HexColor("#2C2C2C"))
    ts_pct = S("tpct", fontName=FONT_BOLD, fontSize=9, textColor=C_ACCENT, alignment=1)

    headers = ["推荐排序", "品牌型号", "额定功率", "价格区间", "年发电量", "投资回收期", "综合评分"]
    widths = [(W-2*MARGIN)*f for f in [0.10, 0.20, 0.10, 0.18, 0.12, 0.12, 0.18]]

    data = [[Paragraph(h, ts_h) for h in headers]]

    for rank, m in enumerate(matches[:5], 1):
        payback = f"{m['payback_years']}年" if m.get('payback_years') else "—"
        irr_str = f"{m.get('irr', 0):.0f}%" if m.get('irr') else "—"
        price_str = f"¥{m['price_low']:,} ~ {m['price_high']:,}"
        score_str = f"{m['score_pct']:.0f}分"

        score_pct = m['score_pct']
        bar_width = int(score_pct / 100 * 60)
        bar_color = C_GREEN if score_pct >= 75 else (C_ACCENT if score_pct >= 60 else C_ORANGE)

        row = [
            Paragraph(f"#{rank}", ts_pct),
            Paragraph(f"{m['brand']}<br/>{m['model']}", ts_d),
            Paragraph(f"{m['power_kw']} kW", ts_d),
            Paragraph(price_str, ts_d),
            Paragraph(f"{m['annual_output_kwh']:,} kWh", ts_d),
            Paragraph(f"{payback}<br/>IRR {irr_str}", ts_d),
            Paragraph(score_str, ts_pct),
        ]
        data.append(row)

    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), C_DARK),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, C_LIGHT]),
        ("GRID",         (0,0), (-1,-1), 0.4, colors.HexColor("#CCDDEE")),
        ("LEFTPADDING",  (0,0), (-1,-1), 5),
        ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("BACKGROUND",   (0,1), (-1,1), colors.HexColor("#E8F5E9")),
        ("BACKGROUND",   (0,2), (-1,2), colors.HexColor("#FFF8E1")),
    ]))
    return t


def wind_gauge_chart(wind_data: dict):
    """风资源仪表图（文本版）"""
    mean = wind_data.get("mean_wind_speed", 0)
    grade = wind_data.get("wind_class", {}).get("grade", 0)
    grade_desc = wind_data.get("wind_class", {}).get("description", "")

    grade_colors = ["#E0E0E0", "#FFCDD2", "#FFCCBC", "#FFE0B2", "#FFF9C4", "#C8E6C9", "#A5D6A7", "#81C784"]
    grade_labels = ["", "1级", "2级", "3级", "4级", "5级", "6级", "7级"]
    bar_color = grade_colors[min(grade, 7)] if grade > 0 else "#E0E0E0"

    rows = [
        [f"年均风速：{mean} m/s", f"风资源等级：{grade_labels[min(grade,7)]} — {grade_desc}"]
    ]
    return rows


def build_report(
    output_path: str,
    user_input: dict,
    wind_data: dict,
    power_calc: dict,
    matches: list,
    storage_advice: dict = None,
) -> str:
    """
    生成完整的PDF选型报告。
    """
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title="小型风机智能选型方案报告",
        author="WindMatch 智能选型系统",
    )

    story = []

    # ══════════════════════════════════════════════════════════════════════
    # 封面
    # ══════════════════════════════════════════════════════════════════════
    story.append(spacer(2.5))
    story.append(Paragraph("WindMatch 智能选型报告", sSubtitle))
    story.append(spacer(0.4))
    story.append(HR(C_ACCENT, 2))
    story.append(spacer(0.4))
    story.append(Paragraph("小型永磁风力发电机", sTitle))
    story.append(Paragraph("选型方案报告", sTitle))
    story.append(spacer(0.6))

    today_str = datetime.now().strftime("%Y年%m月%d日")
    location = user_input.get("location", user_input.get("latitude", "未知地点"))

    story.append(Paragraph(today_str, sCoverMeta))
    story.append(spacer(0.4))
    story.append(Paragraph(f"项目地点：{location}", sCoverMeta))
    story.append(Paragraph(f"推荐装机：{power_calc.get('recommended_kw', '—')} kW", sCoverMeta))
    story.append(Paragraph(f"月均用电：{power_calc.get('monthly_kwh', '—')} kWh", sCoverMeta))

    story.append(spacer(4.0))

    if matches:
        top = matches[0]
        conclusion_data = [
            ["最佳推荐型号", top["brand"] + " " + top["model"]],
            ["推荐功率", f"{top['power_kw']} kW"],
            ["预估年发电量", f"{top['annual_output_kwh']:,} kWh"],
            ["建议预算", f"¥{top['price_low']:,} ~ ¥{top['price_high']:,}"],
            ["预计回收期", f"{top['payback_years']}年" if top.get("payback_years") else "—"],
        ]
        ts_l = S("tcl", fontName=FONT_BOLD, fontSize=9.5, textColor=C_DARK)
        ts_v = S("tcv", fontName=FONT, fontSize=9.5, textColor=C_ACCENT)
        conclusion_rows = [[Paragraph(k, ts_l), Paragraph(v, ts_v)] for k, v in conclusion_data]
        t = Table(conclusion_rows, colWidths=[(W-2*MARGIN)*0.40, (W-2*MARGIN)*0.60])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), C_LIGHT),
            ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#AACCEE")),
            ("LEFTPADDING",  (0,0), (-1,-1), 10),
            ("RIGHTPADDING", (0,0), (-1,-1), 10),
            ("TOPPADDING",   (0,0), (-1,-1), 7),
            ("BOTTOMPADDING",(0,0), (-1,-1), 7),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(t)

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 第一部分：用户需求摘要
    # ══════════════════════════════════════════════════════════════════════
    story.append(chapter_banner("第一部分  需求摘要"))
    story.append(spacer(0.25))

    usage_labels = {
        "home": "家用（住宅/农村）",
        "commercial": "商业（酒店/景区）",
        "industrial": "工业（工厂/园区）",
        "telecom": "电信塔",
        "agriculture": "农业（灌溉/养殖）",
    }
    grid_labels = {"off-grid": "离网系统", "grid": "并网系统"}
    storage_labels = {True: "需要储能配套", False: "无需储能"}

    usage_val = usage_labels.get(user_input.get("usage_type", ""), user_input.get("usage_type", "—"))
    grid_val = grid_labels.get(user_input.get("grid_type", "off-grid"), "离网系统")
    storage_val = storage_labels.get(user_input.get("storage_needed", False), "—")
    budget_val = user_input.get("budget", None)
    budget_str = f"¥{budget_val:,}" if budget_val else "不限"

    story.append(kv_table([
        ("项目地点", location),
        ("经纬度", f"{user_input.get('latitude', '—')}, {user_input.get('longitude', '—')}"),
        ("主要用途", usage_val),
        ("系统类型", grid_val),
        ("储能需求", storage_val),
        ("月均用电量", f"{user_input.get('monthly_kwh', '—')} kWh"),
        ("预算范围", budget_str),
    ]))
    story.append(spacer(0.3))

    # ══════════════════════════════════════════════════════════════════════
    # 第二部分：风资源分析
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(chapter_banner("第二部分  风资源分析"))
    story.append(spacer(0.25))

    if wind_data.get("error"):
        story.append(Paragraph(
            f"数据说明：{wind_data.get('source', '')} — {wind_data.get('error', '')}",
            sCaption))
        story.append(spacer(0.2))

    story.append(kv_table([
        ("数据来源", wind_data.get("source", "—")),
        ("数据时段", wind_data.get("data_period", "—")),
        ("年均风速", f"{wind_data.get('mean_wind_speed', '—')} m/s"),
        ("最大风速", f"{wind_data.get('max_wind_speed', '—')} m/s"),
        ("风功率密度", f"{wind_data.get('wind_power_density', '—')} W/m2"),
        ("威布尔k参数", str(wind_data.get("weibull_k", "—"))),
        ("威布尔a参数", f"{wind_data.get('weibull_a', '—')} m/s"),
        ("风资源等级", f"第{wind_data.get('wind_class', {}).get('grade', '—')}级 — {wind_data.get('wind_class', {}).get('description', '')}"),
        ("估算容量因子", f"{wind_data.get('capacity_factor_estimate', 0) * 100:.1f}%"),
        ("每kW年发电量", f"{wind_data.get('annual_output_kwh_per_kw', '—'):,} kWh/kW"),
    ]))
    story.append(spacer(0.2))

    grade = wind_data.get("wind_class", {}).get("grade", 0)
    grade_explain = {
        1: "风资源较差，需要选择超低启动风速（<=2.0m/s）的风机，建议搭配光伏形成风光互补系统。",
        2: "风资源较差，冬季可能发电不足，建议选择低切入风机并配置储能。",
        3: "风资源一般，具备一定经济性，建议选择切入风速<=3.0m/s的机型。",
        4: "风资源较好，经济性良好，是小型风机的理想场址。",
        5: "风资源充沛，投资回报较好，可优先考虑风机方案。",
        6: "风资源非常充沛，投资回报优，注意风机抗风设计，避免切出损失。",
        7: "风资源极佳，需要选择高强度抗台风机型，切出风速建议>=40m/s。",
    }
    explain = grade_explain.get(grade, "风资源数据不足以评估。")
    story.append(Paragraph("风资源评估说明", sH3))
    story.append(Paragraph(explain, sBody))
    story.append(spacer(0.3))

    # ══════════════════════════════════════════════════════════════════════
    # 第三部分：装机容量建议
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(chapter_banner("第三部分  装机容量建议"))
    story.append(spacer(0.25))
    story.append(Paragraph(
        f"根据月均用电量 {power_calc.get('monthly_kwh', '—')} kWh 及当地风资源条件，"
        "系统计算出以下装机建议：", sBody))
    story.append(spacer(0.2))
    story.append(kv_table([
        ("月均用电量", f"{power_calc.get('monthly_kwh', '—')} kWh"),
        ("年用电量", f"{power_calc.get('annual_kwh', '—')} kWh"),
        ("理论所需装机容量", f"{power_calc.get('theoretical_kw', '—')} kW"),
        ("建议装机容量（含损耗系数）", f"{power_calc.get('recommended_kw', '—')} kW"),
        ("推荐功率段", f"{power_calc.get('min_power_kw', '—')} ~ {power_calc.get('max_power_kw', '—')} kW"),
        ("建议台数", f"{power_calc.get('suggested_count', '—')} 台"),
        ("目标容量利用率", f"{power_calc.get('capacity_utilization', 0) * 100:.0f}%"),
    ]))
    story.append(spacer(0.2))
    story.append(Paragraph(
        "注：损耗系数1.2已考虑传输损耗、停机维护、叶片污染等因素。"
        "如需更精确评估，建议进行为期1年的现场风速实测。",
        sCaption))
    story.append(spacer(0.3))

    # ══════════════════════════════════════════════════════════════════════
    # 第四部分：推荐型号对比
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(chapter_banner("第四部分  推荐型号对比"))
    story.append(spacer(0.25))

    if matches:
        story.append(Paragraph(
            f"基于您的需求和当地风资源，共筛选出 {min(5, len(matches))} 个最优匹配型号，综合评分排序如下：",
            sBody))
        story.append(spacer(0.2))
        story.append(score_bar_table(matches))
        story.append(spacer(0.15))
        story.append(Paragraph("说明：绿色行为最优推荐，黄色行为备选方案。综合评分基于功率匹配度40%、启动风速适配20%、预算匹配20%、并网类型10%、认证完整性10%加权计算。", sCaption))
        story.append(spacer(0.3))

        for rank, m in enumerate(matches[:3], 1):
            story.append(KeepTogether([
                chapter_banner(f"推荐 #{rank}：{m['brand']} {m['model']}"),
                spacer(0.15),
                kv_table([
                    ("额定功率", f"{m['power_kw']} kW"),
                    ("叶片类型", "垂直轴（VAWT）" if m.get("blade_type") == "vertical" else "水平轴（HAWT）"),
                    ("最低启动风速", f"{m.get('start_wind_speed', '—')} m/s"),
                    ("额定风速", f"{m.get('rated_wind_speed', '—')} m/s"),
                    ("切出风速", f"{m.get('cutout_wind_speed', '—')} m/s"),
                    ("扫风面积", f"{m.get('swept_area', '—')} m2"),
                    ("系统类型", {"off-grid": "纯离网", "grid": "并网", "both": "离并网两用"}.get(m.get("grid_type", ""), "—")),
                    ("价格区间", f"¥{m['price_low']:,} ~ ¥{m['price_high']:,}"),
                    ("质保年限", f"{m.get('warranty_years', '—')} 年"),
                    ("认证证书", "、".join(m.get("certifications", [])) or "—"),
                    ("预估年发电量", f"{m['annual_output_kwh']:,} kWh"),
                    ("容量因子", f"{m.get('capacity_factor', 0) * 100:.1f}%"),
                    ("度电成本（LCOE）", f"{m.get('lcoe', '—')} 元/kWh" if m.get("lcoe") else "—"),
                    ("投资回收期", f"{m['payback_years']} 年" if m.get("payback_years") else "—"),
                    ("预计IRR", f"{m.get('irr', 0):.1f}%" if m.get("irr") else "—"),
                    ("特点标签", " / ".join(m.get("tags", [])) or "—"),
                ]),
            ]))

            if m.get("reasons"):
                story.append(spacer(0.1))
                reasons_text = "，".join(m["reasons"])
                story.append(Paragraph(f"推荐理由：{reasons_text}", sGreen))

            if m.get("warnings"):
                warnings_text = "；".join(m["warnings"])
                story.append(Paragraph(f"注意事项：{warnings_text}", sRed))

            story.append(spacer(0.25))
    else:
        story.append(Paragraph("未找到符合条件的型号，请调整预算或联系专业工程师进一步评估。", sBody))
        story.append(spacer(0.3))

    # ══════════════════════════════════════════════════════════════════════
    # 第四.五部分：储能配置建议（仅当用户需要储能时）
    # ══════════════════════════════════════════════════════════════════════
    if storage_advice:
        story.append(PageBreak())
        story.append(chapter_banner("第四部分（续）  储能配置建议"))
        story.append(spacer(0.25))

        grid_type = user_input.get("grid_type", "off-grid")
        autonomy_label = "离网备用" if grid_type == "off-grid" else "并网平滑"

        story.append(Paragraph(
            f"您选择了需要储能配套，系统类型为{grid_labels.get(grid_type, '—')}。"
            f"以下是基于推荐首选风机（{matches[0]['brand']} {matches[0]['model']}）的储能配置建议：",
            sBody))
        story.append(spacer(0.2))

        # 储能核心参数
        story.append(Paragraph("电池储能配置", sH2))
        story.append(kv_table([
            ("日均用电量", f"{storage_advice['daily_consumption_kwh']} kWh"),
            ("日均发电量", f"{storage_advice['daily_generation_kwh']} kWh"),
            ("设计备用时间", f"{storage_advice['autonomy_days']}天（{autonomy_label}）"),
            ("推荐电池容量", f"{storage_advice['battery_capacity_kwh']} kWh"),
            ("电池类型", storage_advice['battery_type']),
            ("循环寿命", f"{storage_advice['cycle_life']} 次"),
            ("系统直流电压", f"{storage_advice['dc_voltage']} V"),
        ]))
        story.append(spacer(0.2))

        # 电池组配置
        story.append(Paragraph("电池组配置方案", sH2))
        story.append(kv_table([
            ("标准电池模块", f"{storage_advice['battery_module_size_kwh']} kWh / 组"),
            ("建议模块数量", f"{storage_advice['num_battery_modules']} 组"),
            ("实际配置容量", f"{storage_advice['actual_battery_capacity_kwh']} kWh"),
            ("储能逆变器", f"{storage_advice['inverter_kw']} kW"),
        ]))
        story.append(spacer(0.2))

        # 成本估算
        story.append(Paragraph("储能成本估算", sH2))
        story.append(kv_table([
            ("电池组成本", f"¥{storage_advice['battery_cost']:,} 元"),
            ("储能逆变器", f"¥{storage_advice['inverter_cost']:,} 元"),
            ("BMS 电池管理", f"¥{storage_advice['bms_cost']:,} 元"),
            ("储能总计", f"¥{storage_advice['total_storage_cost']:,} 元"),
            ("电池单价参考", f"约 ¥{storage_advice['battery_price_per_kwh']}/kWh（2025年市场均价）"),
        ]))
        story.append(spacer(0.2))

        # 储能说明
        story.append(Paragraph("储能说明", sH3))
        story.append(Paragraph(
            "1. 上述电池容量按磷酸铁锂（LiFePO4）计算，放电深度80%，含10%安全余量。",
            sBody))
        story.append(Paragraph(
            "2. 离网系统建议配置2天备用容量，确保连续无风时段仍可正常供电；并网系统0.5天主要用于夜间用电平滑。",
            sBody))
        story.append(Paragraph(
            "3. 电池循环寿命约6000次，按每天完整充放电1次计算，可使用约16年，与风机使用寿命基本匹配。",
            sBody))
        story.append(Paragraph(
            "4. 实际配置建议咨询专业储能系统集成商，根据负载曲线进行精确设计。",
            sBody))
        story.append(spacer(0.3))

    # ══════════════════════════════════════════════════════════════════════
    # 第五部分：投资回报分析
    # ══════════════════════════════════════════════════════════════════════
    if matches:
        story.append(PageBreak())
        story.append(chapter_banner("第五部分  投资回报分析"))
        story.append(spacer(0.25))

        top = matches[0]
        annual_output = top.get("annual_output_kwh", 0)
        price_mid = (top["price_low"] + top["price_high"]) / 2

        elec_price = 0.8 if user_input.get("grid_type") == "off-grid" else 0.6
        annual_saving = annual_output * elec_price

        roi_data = [
            ["项目", "数值"],
            ["推荐型号", f"{top['brand']} {top['model']} ({top['power_kw']}kW)"],
            ["建议投资额（设备+安装20%）", f"约 ¥{int(price_mid * 1.2):,} 元"],
            ["年均发电量", f"{annual_output:,} kWh"],
            ["参考电价", f"¥{elec_price}/kWh"],
            ["年节省电费/发电收益", f"约 ¥{int(annual_saving):,} 元"],
            ["投资回收期", f"约 {top.get('payback_years', '—')} 年" if top.get("payback_years") else "需进一步评估"],
            ["15年累计收益（估算）", f"约 ¥{int(annual_saving * 15 - price_mid * 1.2):,} 元"],
            ["对比柴油发电（离网）", "电价节省约40%~60%"],
        ]

        ts_l = S("til", fontName=FONT_BOLD, fontSize=9, textColor=C_DARK)
        ts_v2 = S("tiv", fontName=FONT, fontSize=9, textColor=colors.HexColor("#333"))
        roi_rows = [[Paragraph(rr[0], ts_l), Paragraph(rr[1], ts_v2)] for rr in roi_data]

        t = Table(roi_rows, colWidths=[(W-2*MARGIN)*0.42, (W-2*MARGIN)*0.58])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), C_DARK),
            ("BACKGROUND", (0,1), (0,-1), C_LIGHT),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, C_LIGHT]),
            ("GRID",       (0,0), (-1,-1), 0.4, colors.HexColor("#CCDDEE")),
            ("LEFTPADDING",  (0,0), (-1,-1), 8),
            ("RIGHTPADDING", (0,0), (-1,-1), 8),
            ("TOPPADDING",   (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",(0,0), (-1,-1), 5),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(t)
        story.append(spacer(0.2))
        story.append(Paragraph(
            "注：上述回报分析为基于年均风速和标准机型的估算，实际回报受具体安装位置、"
            "运维水平、电价政策等因素影响，建议在项目实施前进行详细可行性研究。",
            sCaption))
        story.append(spacer(0.3))

    # ══════════════════════════════════════════════════════════════════════
    # 第六部分：下一步行动建议
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(chapter_banner("第六部分  下一步行动建议"))
    story.append(spacer(0.25))
    story.append(kv_table([
        ("Step 1：确认需求",
         "核实月均用电量数据（建议参考最近6个月电费单），确认安装场地是否在规划限制区域。"),
        ("Step 2：实地考察",
         "委托当地服务商进行为期1个月的实地风速测量，或参考附近气象站数据。"),
        ("Step 3：联系厂家",
         "根据推荐型号联系对应厂家，核实现货情况、认证证书、交货周期和付款条件。"),
        ("Step 4：小额试单",
         "首次采购建议先购买1~2台进行测试，验证实际发电量是否与理论估算吻合。"),
        ("Step 5：整体采购",
         "测试满意后批量采购，建议签订设备采购合同和运维协议，明确质保条款。"),
    ]))
    story.append(spacer(0.4))

    # ══════════════════════════════════════════════════════════════════════
    # 免责声明
    # ══════════════════════════════════════════════════════════════════════
    story.append(HR(C_ACCENT, 1))
    story.append(spacer(0.1))
    ts_disc = S("disc", fontName=FONT, fontSize=8, leading=12,
                 textColor=C_GRAY, alignment=1)
    disclaimer_lines = [
        "免责声明",
        "本报告由 WindMatch 智能选型系统自动生成，数据仅供参考，不构成商业合作背书或投资建议。",
        f"报告生成时间：{today_str}。风资源数据来源于 Open-Meteo（{wind_data.get('source', 'API')}），",
        "价格数据来源于市场公开渠道，均不代表任何厂家立场。",
        "投资决策前请自行进行详细可行性研究和尽职调查。",
    ]
    for line in disclaimer_lines:
        story.append(Paragraph(line, ts_disc))

    doc.build(story)
    return output_path
