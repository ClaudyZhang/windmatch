"""
风机选型匹配算法
根据用户需求（用电量、预算、离网/并网）和风资源数据，
从数据库中筛选最优匹配的风机型号。

策略：软评分制 — 所有型号都参与评分，不满足条件的扣分而非跳过。
确保任何输入条件下都有推荐结果返回。
"""

import json
import os
import math


def load_turbine_db() -> dict:
    """加载风机数据库"""
    db_path = os.path.join(os.path.dirname(__file__), "turbine_db.json")
    with open(db_path, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_recommended_power(monthly_kwh: float, annual_hours: int = 2200) -> dict:
    """
    根据月均用电量计算推荐装机容量。

    参数:
        monthly_kwh: 月均用电量 kWh
        annual_hours: 年均有效利用小时数（默认2200h，中等风资源）

    返回:
        dict: 推荐功率范围和说明
    """
    # 年用电量
    annual_kwh = monthly_kwh * 12

    # 理论装机容量 = 年用电量 / 年均利用小时数
    theoretical_kw = annual_kwh / annual_hours

    # 考虑损耗系数1.2（传输损耗、停机维护等）
    recommended_kw = theoretical_kw * 1.2

    # 功率段建议（向上取整到标准功率）
    standard_powers = [0.3, 0.5, 1, 2, 3, 5, 10, 15, 20, 30, 50, 100]
    min_power = min([p for p in standard_powers if p >= recommended_kw * 0.8], default=standard_powers[-1])
    max_power = min([p for p in standard_powers if p >= recommended_kw * 1.5], default=standard_powers[-1])

    # 容量利用率估算（实际发电量 / 理论最大发电量）
    if recommended_kw > 0:
        capacity_util = min(1.0, recommended_kw / max_power)
    else:
        capacity_util = 0.5

    return {
        "monthly_kwh": monthly_kwh,
        "annual_kwh": round(annual_kwh),
        "theoretical_kw": round(theoretical_kw, 2),
        "recommended_kw": round(recommended_kw, 2),
        "min_power_kw": min_power,
        "max_power_kw": max_power,
        "capacity_utilization": round(capacity_util, 2),
        "suggested_count": _suggest_count(recommended_kw, min_power),
    }


def _suggest_count(recommended_kw: float, unit_power: float) -> int:
    """估算需要几台风机"""
    if recommended_kw <= 0:
        return 1
    count = math.ceil(recommended_kw / unit_power)
    return max(1, min(count, 10))


def _score_product(p: dict, recommended_kw: float, min_power: float, max_power: float,
                   budget_low: float, budget_high: float, grid_type: str,
                   mean_wind: float, cf: float) -> dict:
    """
    对单个风机型号进行综合评分（软评分制，不会跳过任何型号）。

    返回:
        dict: 包含评分和详情的字典，如果型号完全不适合返回 None
    """
    score = 0
    reasons = []
    warnings = []

    p_power = p["power_kw"]
    start_wind = p.get("start_wind_speed", 3.0)
    p_grid = p.get("grid_type", "both")
    p_price_low = p.get("price_low", 0)
    p_price_high = p.get("price_high", 9999999)
    certs = p.get("certifications", [])

    # ── 1. 功率匹配度 (40分) ──────────────────────────────
    if min_power <= p_power <= max_power:
        power_match_ratio = recommended_kw / p_power if p_power > 0 else 0
        if 0.8 <= power_match_ratio <= 1.2:
            power_score = 40
            reasons.append("功率匹配度高")
        elif 0.6 <= power_match_ratio <= 1.5:
            power_score = 30
            reasons.append("功率基本匹配")
        else:
            power_score = 15
            warnings.append(f"功率偏{'大' if p_power > recommended_kw * 1.5 else '小'}({p_power}kW)")
    elif p_power < min_power:
        # 功率偏小：按偏离程度降分，最多给15分
        ratio = p_power / min_power
        power_score = max(2, int(15 * ratio))
        warnings.append(f"单机功率偏小({p_power}kW)，可考虑多台并联")
    else:
        # 功率偏大：按偏离程度降分，最多给12分
        ratio = max_power / p_power
        power_score = max(2, int(12 * ratio))
        warnings.append(f"单机功率偏大({p_power}kW)，发电量将有富余")

    # ── 2. 启动风速适配 (20分) ────────────────────────────
    if start_wind <= mean_wind:
        start_score = 20
        reasons.append(f"启动风速{start_wind}m/s ≤ 年均{mean_wind}m/s")
    elif start_wind <= mean_wind * 1.3:
        start_score = 12
        warnings.append("年均风速略低于启动风速，部分时段发电不足")
    elif start_wind <= mean_wind * 1.6:
        # 风速不够理想但不是完全发不了电
        start_score = 5
        warnings.append(f"启动风速{start_wind}m/s较高，需安装在风速较高的位置")
    else:
        # 启动风速远超年均风速，严重不匹配
        start_score = 0
        warnings.append(f"⚠️ 启动风速{start_wind}m/s远超年均{mean_wind}m/s，不推荐")

    # ── 3. 预算匹配 (20分) ─────────────────────────────────
    if budget_low is not None and budget_high is not None:
        if budget_low <= p_price_low and budget_high >= p_price_high:
            budget_score = 20
            reasons.append("在预算范围内")
        elif budget_low <= p_price_high * 1.2:
            budget_score = 12
            reasons.append("略超预算")
        else:
            # 超预算但不是完全不匹配，降分但不跳过
            over_ratio = budget_low / p_price_low if p_price_low > 0 else 0
            budget_score = max(0, int(8 * over_ratio))
            warnings.append(f"超出预算（价格¥{p_price_low:,}~¥{p_price_high:,}）")
    else:
        budget_score = 15  # 不限制预算

    # ── 4. 并网类型匹配 (10分) ────────────────────────────
    if grid_type == "off-grid" and p_grid in ["off-grid", "both"]:
        grid_score = 10
    elif grid_type == "grid" and p_grid in ["grid", "both"]:
        grid_score = 10
    elif grid_type == "off-grid" and p_grid == "grid":
        # 纯并网型号用于离网，严重不匹配
        grid_score = 1
        warnings.append("此型号为纯并网型，不适合离网使用")
    elif grid_type == "grid" and p_grid == "off-grid":
        grid_score = 3
        warnings.append("此型号为纯离网型，不适合并网需求")
    elif p_grid == "both":
        grid_score = 9
    else:
        grid_score = 2

    # ── 5. 认证完整性 (10分) ───────────────────────────────
    cert_score = 0
    if "CE" in certs:
        cert_score += 5
    if "IEC" in str(certs):
        cert_score += 5
    elif cert_score == 0:
        cert_score = 2
        warnings.append("认证信息较少，建议核实")

    # ── 6. 品牌评分 (10分) ─────────────────────────────────
    brand_rating = p.get("brand_rating", 3)
    brand_score = brand_rating * 2

    # ── 总分 ─────────────────────────────────────────────
    total_score = power_score + start_score + budget_score + grid_score + cert_score + brand_score

    # 功率在最佳范围内才有资格拿高分，范围外的整体打折
    in_range = min_power <= p_power <= max_power
    if not in_range:
        total_score = int(total_score * 0.6)

    score_pct = min(100.0, round(total_score, 1))

    # ── 年发电量估算 ─────────────────────────────────────
    annual_output = round(p_power * cf * 8760)
    lcoe = _estimate_lcoe(p_power, p_price_low, annual_output) if annual_output > 0 else None

    # ── 投资回报 ─────────────────────────────────────────
    if lcoe and annual_output > 0:
        avg_price = (p_price_low + p_price_high) / 2
        annual_saving = annual_output * 0.6  # 假设电价0.6元/kWh
        payback_years = round(avg_price / annual_saving, 1) if annual_saving > 0 else None
        irr = round((annual_saving / avg_price) * 100, 1) if avg_price > 0 else 0
    else:
        payback_years = None
        annual_saving = None
        irr = None

    return {
        "id": p["id"],
        "brand": p["brand"],
        "model": p["model"],
        "power_kw": p_power,
        "rated_power_kw": p["rated_power"],
        "start_wind_speed": start_wind,
        "rated_wind_speed": p.get("rated_wind_speed"),
        "cutout_wind_speed": p.get("cutout_wind_speed"),
        "blade_type": p.get("blade_type"),
        "grid_type": p_grid,
        "swept_area": p.get("swept_area"),
        "price_low": p_price_low,
        "price_high": p_price_high,
        "warranty_years": p.get("warranty_years"),
        "certifications": certs,
        "tags": p.get("tags", []),
        "annual_output_kwh": annual_output,
        "capacity_factor": round(cf, 3),
        "lcoe": lcoe,
        "payback_years": payback_years,
        "annual_saving": annual_saving,
        "irr": irr,
        "score_pct": score_pct,
        "score_breakdown": {
            "power": power_score,
            "start_wind": start_score,
            "budget": budget_score,
            "grid": grid_score,
            "cert": cert_score,
            "brand": brand_score,
        },
        "reasons": reasons,
        "warnings": warnings,
    }


def match_turbines(
    recommended_kw: float,
    min_power: float,
    max_power: float,
    budget_low: float = None,
    budget_high: float = None,
    grid_type: str = "off-grid",  # "off-grid" | "grid" | "both"
    storage_needed: bool = False,
    wind_data: dict = None,
    top_n: int = 5,
) -> list:
    """
    核心匹配算法：筛选最优风机型号。

    采用软评分制，所有型号都参与评分，不适合的扣分而非跳过。
    确保任何输入条件下都有推荐结果返回。

    参数:
        recommended_kw: 推荐装机容量 kW
        min_power: 最小功率 kW
        max_power: 最大功率 kW
        budget_low: 最低预算（元）
        budget_high: 最高预算（元）
        grid_type: 离网/并网/both
        storage_needed: 是否需要储能配置
        wind_data: 风资源数据字典
        top_n: 返回前N个结果

    返回:
        list of dict: 排序后的推荐风机列表（保证至少有1个结果）
    """
    db = load_turbine_db()
    products = db["products"]

    # 年均风速（如果有）
    mean_wind = wind_data.get("mean_wind_speed", 5.0) if wind_data else 5.0
    cf = wind_data.get("capacity_factor_estimate", 0.25) if wind_data else 0.25

    scored = []

    for p in products:
        result = _score_product(
            p, recommended_kw, min_power, max_power,
            budget_low, budget_high, grid_type,
            mean_wind, cf
        )
        if result is not None:
            scored.append(result)

    # 按分数降序排序
    scored.sort(key=lambda x: x["score_pct"], reverse=True)

    # 确保至少返回 top_n 个结果（如果有的话）
    # 即使分数很低也返回，让用户看到所有选项
    return scored[:top_n] if scored else []


def _estimate_lcoe(power_kw: float, price_low: float, annual_kwh: int) -> float:
    """估算平准化度电成本（元/kWh）"""
    if annual_kwh <= 0:
        return None
    # 设备成本 + 20%安装 + 15年运维（每年2%设备价）
    total_cost = price_low * 1.2 + price_low * 0.3
    # 年发电量 × 15年
    lifetime_kwh = annual_kwh * 15
    lcoe = total_cost / lifetime_kwh if lifetime_kwh > 0 else None
    return round(lcoe, 3) if lcoe else None


def generate_comparison_table(matches: list) -> str:
    """生成对比表格文本"""
    if not matches:
        return "未找到匹配型号"

    lines = ["型号对比表："]
    lines.append("-" * 80)
    lines.append(f"{'品牌':<10} {'型号':<12} {'功率(kW)':<10} {'价格区间(元)':<18} {'年发电(kWh)':<12} {'评分'}")
    lines.append("-" * 80)

    for m in matches:
        price_str = f"{m['price_low']:,} ~ {m['price_high']:,}"
        lines.append(
            f"{m['brand']:<10} {m['model']:<12} {m['power_kw']:<10} "
            f"{price_str:<18} {m['annual_output_kwh']:<12} {m['score_pct']}分"
        )

    return "\n".join(lines)
