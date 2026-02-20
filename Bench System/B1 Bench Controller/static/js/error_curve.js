/**
 * Error Curve Chart — ISO 4064 Q-point error visualization
 * Uses Chart.js scatter plot with logarithmic X-axis.
 */
function renderErrorCurve(canvasId, qPointData, mpeData) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;

    // Q-point scatter data
    var passPoints = [];
    var failPoints = [];
    qPointData.forEach(function(qp) {
        if (qp.error_pct == null) return;
        var point = { x: qp.flow_rate, y: qp.error_pct, label: 'Q' + qp.q_point };
        if (qp.passed) {
            passPoints.push(point);
        } else {
            failPoints.push(point);
        }
    });

    // MPE envelope lines
    var mpeUpper = [];
    var mpeLower = [];
    mpeData.forEach(function(m) {
        mpeUpper.push({ x: m.flow_rate, y: m.mpe });
        mpeLower.push({ x: m.flow_rate, y: -m.mpe });
    });
    // Sort by flow rate for proper line drawing
    mpeUpper.sort(function(a, b) { return a.x - b.x; });
    mpeLower.sort(function(a, b) { return a.x - b.x; });

    new Chart(canvas, {
        type: 'scatter',
        data: {
            datasets: [
                {
                    label: 'MPE Upper',
                    data: mpeUpper,
                    borderColor: 'rgba(239, 68, 68, 0.6)',
                    backgroundColor: 'rgba(239, 68, 68, 0.05)',
                    borderWidth: 2,
                    borderDash: [6, 3],
                    showLine: true,
                    fill: false,
                    pointRadius: 0,
                    order: 3,
                },
                {
                    label: 'MPE Lower',
                    data: mpeLower,
                    borderColor: 'rgba(239, 68, 68, 0.6)',
                    backgroundColor: 'rgba(239, 68, 68, 0.05)',
                    borderWidth: 2,
                    borderDash: [6, 3],
                    showLine: true,
                    fill: '-1',
                    pointRadius: 0,
                    order: 3,
                },
                {
                    label: 'Pass',
                    data: passPoints,
                    backgroundColor: '#10b981',
                    borderColor: '#059669',
                    borderWidth: 2,
                    pointRadius: 7,
                    pointHoverRadius: 9,
                    order: 1,
                },
                {
                    label: 'Fail',
                    data: failPoints,
                    backgroundColor: '#ef4444',
                    borderColor: '#dc2626',
                    borderWidth: 2,
                    pointRadius: 7,
                    pointHoverRadius: 9,
                    pointStyle: 'crossRot',
                    order: 1,
                },
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        font: { family: "'Inter', sans-serif", size: 12 },
                        usePointStyle: true,
                        padding: 16,
                        filter: function(item) {
                            // Hide MPE Lower from legend (redundant with Upper)
                            return item.text !== 'MPE Lower';
                        }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            var p = ctx.raw;
                            if (p.label) {
                                return p.label + ': ' + p.y.toFixed(2) + '% @ ' + p.x + ' L/h';
                            }
                            return ctx.dataset.label + ': ' + p.y.toFixed(1) + '%';
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'logarithmic',
                    title: {
                        display: true,
                        text: 'Flow Rate (L/h)',
                        font: { family: "'Inter', sans-serif", size: 13, weight: '600' },
                        color: '#64748b',
                    },
                    grid: { color: 'rgba(0,0,0,0.04)' },
                    ticks: {
                        font: { family: "'JetBrains Mono', monospace", size: 11 },
                        color: '#94a3b8',
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Error (%)',
                        font: { family: "'Inter', sans-serif", size: 13, weight: '600' },
                        color: '#64748b',
                    },
                    grid: { color: 'rgba(0,0,0,0.04)' },
                    ticks: {
                        font: { family: "'JetBrains Mono', monospace", size: 11 },
                        color: '#94a3b8',
                        callback: function(val) { return val + '%'; }
                    }
                }
            }
        }
    });
}
