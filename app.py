# -*- coding: utf-8 -*-
"""
WindMatch - 小型风机智能选型助手
Flask Web 主程序
"""

from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for
import os
import uuid
import json
import tempfile

# ── 加载中国城市经纬度数据库 ──────────────────────────────────────────────
_city_db = {}
_city_keys = []
_db_path = os.path.join(os.path.dirname(__file__), "china_cities.json")
try:
    with open(_db_path, "r", encoding="utf-8") as _f:
        _raw = json.load(_f)
        _city_db = {k: v for k, v in _raw.items() if not k.startswith("_")}
        _city_keys = sorted(_city_db.keys(), key=len, reverse=True)
except Exception:
    pass
from datetime import datetime

from wind_api import get_wind_speed
from matching import calculate_recommended_power, match_turbines, calculate_storage
from report import build_report

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "windmatch-secret-key-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB

# 临时文件存放目录
REPORT_DIR = tempfile.mkdtemp(prefix="windmatch_")


def save_report(filename: str, content: bytes) -> str:
    """保存报告到临时目录"""
    filepath = os.path.join(REPORT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)
    return filepath


@app.route("/")
def index():
    """主页"""
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    核心分析API：
    1. 获取用户输入
    2. 抓取风资源数据
    3. 计算推荐功率
    4. 匹配风机型号
    5. 生成PDF报告
    6. 返回结果和下载链接
    """
    try:
        # ── 1. 解析输入 ───────────────────────────────────────
        latitude  = float(request.form.get("latitude", 0))
        longitude = float(request.form.get("longitude", 0))
        monthly_kwh = float(request.form.get("monthly_kwh", 0))
        usage_type = request.form.get("usage_type", "home")
        grid_type  = request.form.get("grid_type", "off-grid")
        storage_needed = request.form.get("storage_needed", "false") == "true"

        budget_str = request.form.get("budget", "").strip()
        budget = float(budget_str) if budget_str else None

        location_name = request.form.get("location_name", f"{latitude},{longitude}")

        if not latitude or not longitude:
            return jsonify({"error": "请提供有效的地理位置坐标"}), 400
        if monthly_kwh <= 0:
            return jsonify({"error": "请填写有效的月均用电量"}), 400

        # ── 2. 风资源数据 ──────────────────────────────────────
        wind_data = get_wind_speed(latitude, longitude)

        # ── 3. 功率计算 ────────────────────────────────────────
        cf = wind_data.get("capacity_factor_estimate", 0.25)
        annual_hours = int(cf * 8760)
        power_calc = calculate_recommended_power(monthly_kwh, annual_hours=annual_hours)

        # ── 4. 匹配选型 ────────────────────────────────────────
        matches = match_turbines(
            recommended_kw=power_calc["recommended_kw"],
            min_power=power_calc["min_power_kw"],
            max_power=power_calc["max_power_kw"],
            budget_low=budget,
            budget_high=budget * 1.5 if budget else None,
            grid_type=grid_type,
            storage_needed=storage_needed,
            wind_data=wind_data,
            top_n=5,
        )

        # ── 4.5 储能配置建议 ─────────────────────────────────
        storage_advice = None
        if storage_needed and matches:
            top_match = matches[0]
            storage_advice = calculate_storage(
                monthly_kwh=monthly_kwh,
                turbine_power_kw=top_match["power_kw"],
                annual_output_kwh=top_match["annual_output_kwh"],
                grid_type=grid_type,
            )

        # ── 5. 生成PDF ────────────────────────────────────────
        user_input = {
            "latitude": latitude,
            "longitude": longitude,
            "location": location_name,
            "monthly_kwh": monthly_kwh,
            "usage_type": usage_type,
            "grid_type": grid_type,
            "storage_needed": storage_needed,
            "budget": budget,
        }

        report_filename = f"选型方案_{uuid.uuid4().hex[:8]}.pdf"
        report_filepath = os.path.join(REPORT_DIR, report_filename)

        build_report(
            output_path=report_filepath,
            user_input=user_input,
            wind_data=wind_data,
            power_calc=power_calc,
            matches=matches,
            storage_advice=storage_advice,
        )

        # ── 6. 返回结果 ────────────────────────────────────────
        result = {
            "success": True,
            "report_url": f"/download/{report_filename}",
            "wind_data": wind_data,
            "power_calc": power_calc,
            "matches": [
                {
                    "rank": i + 1,
                    "brand": m["brand"],
                    "model": m["model"],
                    "power_kw": m["power_kw"],
                    "price_range": f"¥{m['price_low']:,} ~ ¥{m['price_high']:,}",
                    "annual_output_kwh": m["annual_output_kwh"],
                    "score_pct": m["score_pct"],
                    "blade_type": m.get("blade_type"),
                    "start_wind_speed": m.get("start_wind_speed"),
                    "payback_years": m.get("payback_years"),
                    "irr": m.get("irr"),
                    "reasons": m.get("reasons", []),
                    "warnings": m.get("warnings", []),
                }
                for i, m in enumerate(matches)
            ],
        }
        if storage_advice:
            result["storage_advice"] = storage_advice

        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": f"输入数据格式错误：{str(e)}"}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"分析失败：{str(e)}"}), 500


@app.route("/download/<filename>")
def download(filename):
    """下载PDF报告"""
    # 安全检查：只允许下载我们生成的文件
    safe_name = os.path.basename(filename)
    filepath = os.path.join(REPORT_DIR, safe_name)
    if not os.path.exists(filepath):
        return "文件不存在或已过期", 404
    return send_file(
        filepath,
        as_attachment=True,
        download_name=safe_name,
        mimetype="application/pdf",
    )


# ── 地理编码工具函数 ─────────────────────────────────────────────────────

def _geocode_local(address):
    """本地中国城市数据库匹配（零延迟，零依赖）"""
    addr_clean = address.strip()
    # 1. 精确匹配
    if addr_clean in _city_db:
        lat, lon = _city_db[addr_clean]
        return lat, lon, addr_clean
    # 2. 模糊匹配：地址包含城市名，或城市名包含地址
    for key in _city_keys:
        if key in addr_clean or addr_clean in key:
            lat, lon = _city_db[key]
            return lat, lon, key
    # 3. 去掉"市""省""区""县"等后缀再匹配
    suffixes = ["市", "省", "自治区", "特别行政区", "区", "县", "州", "盟", "地区"]
    for s in suffixes:
        if addr_clean.endswith(s):
            trimmed = addr_clean[:-len(s)].strip()
            if trimmed in _city_db:
                lat, lon = _city_db[trimmed]
                return lat, lon, trimmed
            for key in _city_keys:
                if key in trimmed or trimmed in key:
                    lat, lon = _city_db[key]
                    return lat, lon, key
            break
    return None


def _geocode_nominatim(address):
    """Nominatim (OpenStreetMap) — 海外备用"""
    import requests as req
    resp = req.get("https://nominatim.openstreetmap.org/search", params={
        "q": address, "format": "json", "limit": 1, "accept-language": "zh-CN",
    }, timeout=8, headers={"User-Agent": "WindMatch/1.0"})
    resp.raise_for_status()
    data = resp.json()
    if data:
        return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", "")
    return None


def geocode_address(address):
    """
    多源级联地理编码：
    1. 本地中国城市数据库（零延迟）
    2. Nominatim（海外环境备用）
    """
    # 优先本地数据库
    result = _geocode_local(address)
    if result:
        return {"latitude": result[0], "longitude": result[1], "display_name": result[2], "source": "本地数据库"}

    # 备用：Nominatim（海外服务器可能可用）
    try:
        result = _geocode_nominatim(address)
        if result:
            return {"latitude": result[0], "longitude": result[1], "display_name": result[2], "source": "Nominatim"}
    except Exception:
        pass

    return None, ["本地数据库未匹配", "Nominatim不可达"]


@app.route("/api/geocode", methods=["GET"])
def geocode():
    """
    地理编码API：地址 → 经纬度
    多源级联，确保国内和海外都能用
    """
    address = request.args.get("address", "").strip()
    if not address:
        return jsonify({"error": "请提供地址"}), 400

    ret = geocode_address(address)
    if isinstance(ret, dict):
        return jsonify(ret)
    else:
        errors = ret[1] if ret and len(ret) > 1 else []
        err_detail = "；".join(errors) if errors else "所有地理编码服务均不可用"
        return jsonify({"error": f"未找到该地址。{err_detail}。请尝试更精确的描述或直接输入经纬度。"}), 404


@app.route("/health")
def health():
    """健康检查接口"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


if __name__ == "__main__":
    # Railway 或其他平台用 PORT 环境变量，本地默认 5000
    import os
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print(" WindMatch 智能选型系统启动中...")
    print(f" 访问地址：http://127.0.0.1:{port}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)
