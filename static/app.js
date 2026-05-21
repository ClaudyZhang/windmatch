/**
 * WindMatch 前端交互逻辑
 */

$(function () {

    // ── 地理定位按钮 ──────────────────────────────────────────────────────
    $('#geocode-btn').on('click', function () {
        const address = $('#location-input').val().trim();
        if (!address) {
            alert('请先输入地址');
            return;
        }

        const $btn = $(this);
        $btn.prop('disabled', true).text('定位中...');

        // 先检查是否是经纬度
        const coordMatch = address.match(/^(-?\d+\.?\d*)\s*[,，]\s*(-?\d+\.?\d*)$/);
        if (coordMatch) {
            const lat = parseFloat(coordMatch[1]);
            const lon = parseFloat(coordMatch[2]);
            if (lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
                setCoords(lat, lon, `${lat}, ${lon}`);
                $btn.prop('disabled', false).text('定位');
                return;
            }
        }

        $.get('/api/geocode', { address: address })
            .done(function (res) {
                if (res.latitude && res.longitude) {
                    setCoords(res.latitude, res.longitude, res.display_name || address);
                    $('#location-input').val(res.display_name || address);
                } else {
                    showGeoError('未找到该地址，请尝试更精确的描述');
                }
            })
            .fail(function (err) {
                const msg = err.responseJSON?.error || '定位失败，请检查网络或直接输入经纬度';
                showGeoError(msg);
            })
            .always(function () {
                $btn.prop('disabled', false).text('定位');
            });
    });

    // 回车触发定位
    $('#location-input').on('keypress', function (e) {
        if (e.which === 13) {
            $('#geocode-btn').click();
        }
    });

    // ── 分析按钮 ──────────────────────────────────────────────────────────
    $('#analyze-btn').on('click', function () {
        // 收集数据
        const latitude = parseFloat($('#latitude').val());
        const longitude = parseFloat($('#longitude').val());
        const monthly_kwh = parseFloat($('#monthly_kwh').val());
        const usage_type = $('#usage_type').val();
        const grid_type = $('#grid_type').val();
        const storage_needed = $('#storage_needed').val() === 'true';
        const budget_str = $('#budget').val().trim();
        const budget = budget_str ? parseFloat(budget_str) : null;
        const location_name = $('#location-input').val().trim() || `${latitude}, ${longitude}`;

        // 验证
        if (!latitude || !longitude) {
            alert('请先定位，填写经纬度');
            return;
        }
        if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
            alert('经纬度超出有效范围');
            return;
        }
        if (!monthly_kwh || monthly_kwh <= 0) {
            alert('请填写有效的月均用电量');
            return;
        }

        const $btn = $(this);
        const $form = $('.form-section');
        const $loading = $('#loading-state');
        const $result = $('#result-section');
        const $error = $('#error-state');

        $form.hide();
        $error.hide();
        $result.hide();
        $loading.show();
        $btn.prop('disabled', true).html('<span class="spinner-small"></span> 分析中...');

        // 加载动画文字
        const loadingMsgs = [
            '正在抓取风资源数据...',
            '正在分析风功率密度...',
            '正在计算威布尔参数...',
            '正在匹配最优风机型号...',
            '正在生成PDF报告...',
        ];
        let msgIdx = 0;
        const msgTimer = setInterval(function () {
            msgIdx = (msgIdx + 1) % loadingMsgs.length;
            $('#loading-msg').text(loadingMsgs[msgIdx]);
        }, 1200);

        $.ajax({
            url: '/api/analyze',
            method: 'POST',
            data: {
                latitude: latitude,
                longitude: longitude,
                location_name: location_name,
                monthly_kwh: monthly_kwh,
                usage_type: usage_type,
                grid_type: grid_type,
                storage_needed: storage_needed,
                budget: budget || '',
            },
            timeout: 60000,  // 60秒超时
        })
            .done(function (res) {
                clearInterval(msgTimer);
                $loading.hide();
                $btn.prop('disabled', false).html('🚀 开始智能分析');

                if (res.success) {
                    renderResults(res);
                    $result.show();
                    window._lastReportUrl = res.report_url;
                } else {
                    showError(res.error || '分析失败');
                }
            })
            .fail(function (err) {
                clearInterval(msgTimer);
                $loading.hide();
                $btn.prop('disabled', false).html('🚀 开始智能分析');
                $form.show();
                const msg = err.responseJSON?.error || '网络错误，请重试';
                showError(msg);
            });
    });

    // ── 下载PDF ────────────────────────────────────────────────────────────
    $(document).on('click', '#download-pdf-btn', function (e) {
        if (window._lastReportUrl) {
            // 在新标签页打开下载
            window.open(window._lastReportUrl, '_blank');
        } else {
            e.preventDefault();
            alert('报告尚未生成，请先运行分析');
        }
    });

    // ── 推荐型号展开/收起 ──────────────────────────────────────────────────
    $(document).on('click', '.match-header', function () {
        const $body = $(this).next('.match-body');
        const $arrow = $(this).find('.match-arrow');
        $body.toggleClass('open');
        $arrow.toggleClass('open');
    });

});

// ── 辅助函数 ──────────────────────────────────────────────────────────────

function setCoords(lat, lon, display) {
    $('#latitude').val(lat.toFixed(4));
    $('#longitude').val(lon.toFixed(4));
    $('#coords-text').text(`纬度 ${lat.toFixed(4)}, 经度 ${lon.toFixed(4)}`);
    $('#coords-status')
        .removeClass('status-pending status-error')
        .addClass('status-ok')
        .text('定位成功');
}

function showGeoError(msg) {
    $('#coords-status')
        .removeClass('status-pending status-ok')
        .addClass('status-error')
        .text('定位失败');
    // 尝试设置错误状态
    $('#coords-text').text(msg.substring(0, 40));
}

function showError(msg) {
    const $error = $('#error-state');
    $('#error-msg').text(msg);
    $error.show();
}

function renderResults(res) {
    renderWind(res.wind_data);
    renderPower(res.power_calc);
    renderMatches(res.matches);

    // 下载链接
    if (res.report_url) {
        $('#download-pdf-btn').attr('href', res.report_url);
    }

    // 滚动到顶部
    $('html, body').scrollTop(0);
}

function renderWind(data) {
    const badge = $('#wind-grade-badge');
    const stats = $('#wind-stats');
    const note = $('#wind-note');

    const grade = data.wind_class?.grade || 0;
    const desc = data.wind_class?.description || '';

    const gradeColors = ['#ccc', '#FFCDD2', '#FFCCBC', '#FFE0B2', '#FFF9C4', '#C8E6C9', '#A5D6A7', '#81C784'];
    const bgColor = gradeColors[Math.min(grade, 7)];
    badge
        .text(`风资源等级：第 ${grade} 级 — ${desc}`)
        .css('background', bgColor);

    stats.html(`
        <div class="wind-stat">
            <div class="value">${data.mean_wind_speed || '—'} <small>m/s</small></div>
            <div class="label">年均风速</div>
        </div>
        <div class="wind-stat">
            <div class="value">${data.wind_power_density || '—'} <small>W/m²</small></div>
            <div class="label">风功率密度</div>
        </div>
        <div class="wind-stat">
            <div class="value">${(data.capacity_factor_estimate * 100).toFixed(0) || '—'} <small>%</small></div>
            <div class="label">估算容量因子</div>
        </div>
        <div class="wind-stat">
            <div class="value">${data.annual_output_kwh_per_kw || '—'}</div>
            <div class="label">每kW年发电量(kWh)</div>
        </div>
        <div class="wind-stat">
            <div class="value">${data.weibull_k || '—'}</div>
            <div class="label">威布尔k参数</div>
        </div>
        <div class="wind-stat">
            <div class="value">${data.weibull_a || '—'}</div>
            <div class="label">威布尔a参数</div>
        </div>
    `);

    if (data.error) {
        note.html(`⚠️ ${data.source || '数据说明'}：${data.error}，以上数据仅供参考。`);
    } else {
        note.html(`✅ 数据来源：${data.source || 'Open-Meteo'}（${data.data_period || '历史数据'}），${data.coverage || 0}%数据覆盖率`);
    }
}

function renderPower(power) {
    const hl = $('#power-highlight');
    const dt = $('#power-details');

    hl.html(`
        <div class="number">${power.recommended_kw} <span class="unit">kW</span></div>
        <div class="subtitle">建议装机容量 · 推荐功率段 ${power.min_power_kw} ~ ${power.max_power_kw} kW</div>
    `);

    dt.html(`
        <div class="power-detail"><span class="key">月均用电</span><span class="val">${power.monthly_kwh} kWh</span></div>
        <div class="power-detail"><span class="key">年用电量</span><span class="val">${power.annual_kwh} kWh</span></div>
        <div class="power-detail"><span class="key">理论所需功率</span><span class="val">${power.theoretical_kw} kW</span></div>
        <div class="power-detail"><span class="key">建议台数</span><span class="val">${power.suggested_count} 台</span></div>
        <div class="power-detail"><span class="key">目标容量利用率</span><span class="val">${(power.capacity_utilization * 100).toFixed(0)}%</span></div>
        <div class="power-detail"><span class="key">年均有效小时</span><span class="val">约 ${Math.round(power.capacity_utilization * 8760)} 小时</span></div>
    `);
}

function renderMatches(matches) {
    const list = $('#matches-list');

    if (!matches || matches.length === 0) {
        list.html('<p style="text-align:center;color:#6C757D;padding:2rem;">未找到符合条件的型号，请调整条件后重试。</p>');
        return;
    }

    let html = '';
    matches.forEach(function (m, i) {
        const rank = i + 1;
        const topClass = rank === 1 ? 'top1' : rank === 2 ? 'top2' : '';
        const scoreClass = m.score_pct >= 75 ? 'score-high' : m.score_pct >= 60 ? 'score-mid' : '';

        const reasons = m.reasons?.length ? `<div class="match-reasons">✅ ${m.reasons.join('，')}</div>` : '';
        const warnings = m.warnings?.length ? `<div class="match-warnings">⚠️ ${m.warnings.join('；')}</div>` : '';

        html += `
        <div class="match-item ${topClass}">
            <div class="match-header">
                <span class="match-rank rank-${rank <= 3 ? rank : 'other'}">${rank}</span>
                <div class="match-name">
                    <div class="brand">${m.brand}</div>
                    <div class="model">${m.model} · ${m.blade_type === 'vertical' ? '垂直轴VAWT' : '水平轴HAWT'} · ${m.start_wind_speed} m/s启动</div>
                </div>
                <div class="match-meta">
                    <div class="match-power">${m.power_kw}<span> kW</span></div>
                    <div class="match-score ${scoreClass}">${m.score_pct}分</div>
                    <span class="match-arrow">▼</span>
                </div>
            </div>
            <div class="match-body">
                <div class="match-grid">
                    <div class="match-cell"><span class="k">价格区间</span><span class="v">${m.price_range}</span></div>
                    <div class="match-cell"><span class="k">年发电量</span><span class="v">${m.annual_output_kwh?.toLocaleString()} kWh</span></div>
                    <div class="match-cell"><span class="k">额定风速</span><span class="v">${m.start_wind_speed} m/s（启动）</span></div>
                    <div class="match-cell"><span class="k">回收期</span><span class="v">${m.payback_years ? m.payback_years + ' 年' : '—'}</span></div>
                    <div class="match-cell"><span class="k">预计IRR</span><span class="v">${m.irr ? m.irr + '%' : '—'}</span></div>
                    <div class="match-cell"><span class="k">综合评分</span><span class="v">${m.score_pct} / 100</span></div>
                </div>
                ${reasons}
                ${warnings}
            </div>
        </div>`;
    });

    list.html(html);
}
