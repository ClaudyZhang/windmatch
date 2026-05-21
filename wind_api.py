"""
风速数据获取模块
使用 Open-Meteo API 获取任意坐标的历史风速数据
"""

import math
import requests
from datetime import datetime, timedelta

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_REANALYSIS_URL = "https://archive-api.open-meteo.com/v1/era5"

# 平均空气密度 kg/m³（海平面标准大气）
RHO_AIR = 1.225


def get_wind_speed(latitude: float, longitude: float, years_back: int = 1) -> dict:
    """
    获取指定坐标的历史风速数据并计算统计指标。

    参数:
        latitude: 纬度 (-90 ~ 90)
        longitude: 经度 (-180 ~ 180)
        years_back: 回溯多少年（最大5年）

    返回:
        dict 包含:
            mean_wind_speed: 年均风速 m/s
            max_wind_speed: 最大风速 m/s
            wind_power_density: 风功率密度 W/m²
            weibull_k: 威布尔形状参数
            weibull_a: 威布尔尺度参数 m/s
            wind_class: 风资源等级 (1~7)
            data_points: 有效数据点数
            capacity_factor_estimate: 估算容量因子
            annual_output_kwh_per_kw: 每kW年发电量估算 kWh
            coverage: 数据覆盖率 %
    """
    if years_back > 5:
        years_back = 5
    if years_back < 1:
        years_back = 1

    end_date = datetime.now() - timedelta(days=30)
    start_date = end_date - timedelta(days=365 * years_back)

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "hourly": "wind_speed_10m,wind_direction_10m",
        "timezone": "Asia/Shanghai",
        "wind_speed_unit": "ms",
    }

    try:
        response = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        # 如果API调用失败，使用估算数据
        return _fallback_wind_estimate(latitude, longitude, str(e))

    hourly_data = data.get("hourly", {})
    wind_speeds = [float(w) for w in hourly_data.get("wind_speed_10m", []) if w is not None]

    if not wind_speeds or len(wind_speeds) < 100:
        return _fallback_wind_estimate(latitude, longitude, "insufficient_data")

    # 统计计算
    n = len(wind_speeds)
    mean_speed = sum(wind_speeds) / n
    max_speed = max(wind_speeds)

    # 风功率密度 = 0.5 * ρ * v³
    wind_power_density = 0.5 * RHO_AIR * (mean_speed ** 3)

    # 威布尔参数估算（经验公式）
    # k ≈ 1 / sqrt( (std/wind_mean)^2 - 1 + 1e-10 )
    variance = sum((v - mean_speed) ** 2 for v in wind_speeds) / n
    std_dev = math.sqrt(variance)

    if std_dev > 0 and mean_speed > 0:
        cv = std_dev / mean_speed  # 变异系数
        if cv < 1:
            k_approx = 1.0 / (cv + 0.001)
        else:
            k_approx = 1.0 / (cv - 0.3)
        k_approx = max(0.5, min(k_approx, 4.0))
    else:
        k_approx = 2.0

    # 威布尔尺度参数 a
    gamma_1_k = math.gamma(1 + 1 / k_approx)
    a_approx = mean_speed / gamma_1_k if gamma_1_k > 0 else mean_speed

    # 风资源等级（基于年均风速）
    wind_class = _wind_class(mean_speed)

    # 容量因子估算（基于风速分布和风机切入切出特性）
    capacity_factor = _estimate_capacity_factor(mean_speed, k_approx, a_approx)

    # 每kW年发电量 = 容量因子 × 8760h
    annual_output_per_kw = capacity_factor * 8760

    # 数据覆盖率
    total_hours = (end_date - start_date).days * 24
    coverage = min(100, round(len(wind_speeds) / max(total_hours, 1) * 100, 1))

    return {
        "mean_wind_speed": round(mean_speed, 2),
        "max_wind_speed": round(max_speed, 2),
        "min_wind_speed": round(min(wind_speeds), 2),
        "std_dev": round(std_dev, 2),
        "wind_power_density": round(wind_power_density, 1),
        "weibull_k": round(k_approx, 2),
        "weibull_a": round(a_approx, 2),
        "wind_class": wind_class,
        "capacity_factor_estimate": round(capacity_factor, 3),
        "annual_output_kwh_per_kw": round(annual_output_per_kw),
        "data_points": n,
        "coverage": coverage,
        "source": "Open-Meteo Archive",
        "data_period": f"{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}",
        "error": None,
    }


def _estimate_capacity_factor(mean_speed: float, k: float, a: float) -> float:
    """
    估算容量因子。
    基于风速分布概率密度和切入/额定风速范围。
    典型切入风速2.5~3.5m/s，额定风速10~13m/s，切出25m/s
    """
    # 简化容量因子模型
    if mean_speed < 2.5:
        return 0.05
    elif mean_speed < 4.0:
        return 0.12 + (mean_speed - 2.5) * 0.05
    elif mean_speed < 6.0:
        return 0.20 + (mean_speed - 4.0) * 0.04
    elif mean_speed < 8.0:
        return 0.28 + (mean_speed - 6.0) * 0.03
    else:
        return min(0.40, 0.38 + (mean_speed - 8.0) * 0.01)


def _wind_class(mean_speed: float) -> dict:
    """
    风资源等级（1~7级）
    基于IEC 61400-12标准
    """
    if mean_speed < 3.0:
        grade = 1
        desc = "差（年均风速偏低，需选超低启动风机）"
    elif mean_speed < 4.0:
        grade = 2
        desc = "较差（可用，选择低切入风机）"
    elif mean_speed < 5.0:
        grade = 3
        desc = "一般（可用，经济性一般）"
    elif mean_speed < 6.0:
        grade = 4
        desc = "较好（经济性良好）"
    elif mean_speed < 7.0:
        grade = 5
        desc = "良好（风资源充沛）"
    elif mean_speed < 8.0:
        grade = 6
        desc = "优秀（风资源非常充沛）"
    else:
        grade = 7
        desc = "极佳（风资源极其充沛，注意抗风设计）"

    return {"grade": grade, "description": desc, "mean_speed_threshold": f"≥{mean_speed:.1f}m/s"}


def _fallback_wind_estimate(latitude: float, longitude: float, reason: str) -> dict:
    """
    API失败时，使用纬度估算风速（基于全球风资源分布图）
    仅作为粗略估算
    """
    # 基于纬度和海陆位置的粗略估算
    abs_lat = abs(latitude)

    # 大致规律：纬度越高风速越大
    if abs_lat > 55:
        mean_speed = 7.5
    elif abs_lat > 45:
        mean_speed = 6.5
    elif abs_lat > 35:
        mean_speed = 5.5
    elif abs_lat > 25:
        mean_speed = 5.0
    elif abs_lat > 15:
        mean_speed = 4.5
    else:
        mean_speed = 4.0

    # 中国区域特殊调整（东部沿海风资源较好）
    if 110 < longitude < 125 and 20 < latitude < 45:
        mean_speed += 0.5

    max_speed = mean_speed * 2.5
    wind_power_density = 0.5 * RHO_AIR * (mean_speed ** 3)
    k_val, a_val = 2.0, mean_speed / 0.886
    capacity_factor = _estimate_capacity_factor(mean_speed, k_val, a_val)
    wind_class = _wind_class(mean_speed)

    return {
        "mean_wind_speed": round(mean_speed, 2),
        "max_wind_speed": round(max_speed, 2),
        "min_wind_speed": round(mean_speed * 0.3, 2),
        "std_dev": round(mean_speed * 0.4, 2),
        "wind_power_density": round(wind_power_density, 1),
        "weibull_k": round(k_val, 2),
        "weibull_a": round(a_val, 2),
        "wind_class": wind_class,
        "capacity_factor_estimate": round(capacity_factor, 3),
        "annual_output_kwh_per_kw": round(capacity_factor * 8760),
        "data_points": 0,
        "coverage": 0,
        "source": f"估算数据（API失败: {reason[:30]}）",
        "data_period": "估算值",
        "error": f"Open-Meteo API调用失败，使用纬度估算: {reason[:80]}",
    }
