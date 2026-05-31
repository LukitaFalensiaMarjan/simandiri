/**
 * SIMANDIRI — Dashboard JavaScript
 * ==================================
 * Chart.js, auto-refresh, camera simulation, UI interactions
 */

// ============================================================
//  CHART DEFAULTS (Aerospace HUD style)
// ============================================================

Chart.defaults.color           = 'rgba(139, 158, 192, 0.9)';
Chart.defaults.borderColor     = 'rgba(255,255,255,0.05)';
Chart.defaults.font.family     = "'JetBrains Mono', monospace";
Chart.defaults.font.size       = 11;

// ============================================================
//  DASHBOARD CHARTS
// ============================================================

let absensiChart     = null;
let pelanggaranChart = null;

function initDashboardCharts(absensiData, pelanggaranData) {
    const chartOptions = (color, label) => ({
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: '#0D1726',
                titleColor: '#F0F4FC',
                bodyColor: 'rgba(139, 158, 192, 0.9)',
                borderColor: 'rgba(59, 130, 246, 0.2)',
                borderWidth: 1,
                cornerRadius: 8,
                padding: 10,
                displayColors: false,
                titleFont: { weight: '600', size: 12 },
                bodyFont: { size: 11 }
            }
        },
        scales: {
            x: {
                grid: { display: false },
                border: { display: false },
                ticks: { font: { size: 10 }, color: '#4A5E7A' }
            },
            y: {
                beginAtZero: true,
                grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
                border: { display: false },
                ticks: {
                    stepSize: 1,
                    font: { size: 10 },
                    color: '#4A5E7A',
                    padding: 8
                }
            }
        }
    });

    // Absensi Chart
    const absensiCtx = document.getElementById('absensiChart');
    if (absensiCtx) {
        const ctx  = absensiCtx.getContext('2d');
        const grad = ctx.createLinearGradient(0, 0, 0, 200);
        grad.addColorStop(0, 'rgba(59, 130, 246, 0.25)');
        grad.addColorStop(1, 'rgba(59, 130, 246, 0.00)');

        const labels = absensiData.map(d => fmtChartDate(d.tanggal));
        const values = absensiData.map(d => d.total);

        absensiChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Absensi',
                    data: values,
                    borderColor: '#3B82F6',
                    backgroundColor: grad,
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#3B82F6',
                    pointBorderColor: '#0D1726',
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointHoverBorderColor: '#93C5FD',
                }]
            },
            options: chartOptions('#3B82F6', 'Absensi')
        });
    }

    // Pelanggaran Chart
    const pelanggaranCtx = document.getElementById('pelanggaranChart');
    if (pelanggaranCtx) {
        const ctx  = pelanggaranCtx.getContext('2d');
        const grad = ctx.createLinearGradient(0, 0, 0, 200);
        grad.addColorStop(0, 'rgba(239, 68, 68, 0.25)');
        grad.addColorStop(1, 'rgba(239, 68, 68, 0.00)');

        const labels = pelanggaranData.map(d => fmtChartDate(d.tanggal));
        const values = pelanggaranData.map(d => d.total);

        pelanggaranChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Pelanggaran',
                    data: values,
                    borderColor: '#EF4444',
                    backgroundColor: grad,
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#EF4444',
                    pointBorderColor: '#0D1726',
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointHoverBorderColor: '#FCA5A5',
                }]
            },
            options: chartOptions('#EF4444', 'Pelanggaran')
        });
    }
}

function fmtChartDate(dateStr) {
    if (!dateStr) return '';
    const months = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agt','Sep','Okt','Nov','Des'];
    const parts   = dateStr.split('-');
    if (parts.length === 3) {
        return `${parseInt(parts[2])} ${months[parseInt(parts[1]) - 1]}`;
    }
    return dateStr;
}

// ============================================================
//  AUTO-REFRESH (30 seconds)
// ============================================================

function startDashboardAutoRefresh() {
    setInterval(async () => {
        try {
            const resp = await fetch('/api/dashboard');
            if (!resp.ok) return;
            const data = await resp.json();

            animateValue('statPegawai', data.total_pegawai);
            animateValue('statAbsensi', data.absensi_hari_ini);
            animateValue('statCompliance', data.compliance_rate + '%');
            animateValue('statPelanggaran', data.pelanggaran_hari_ini);

            if (absensiChart && data.absensi_chart) {
                absensiChart.data.labels                = data.absensi_chart.map(d => fmtChartDate(d.tanggal));
                absensiChart.data.datasets[0].data      = data.absensi_chart.map(d => d.total);
                absensiChart.update('none');
            }

            if (pelanggaranChart && data.pelanggaran_chart) {
                pelanggaranChart.data.labels            = data.pelanggaran_chart.map(d => fmtChartDate(d.tanggal));
                pelanggaranChart.data.datasets[0].data  = data.pelanggaran_chart.map(d => d.total);
                pelanggaranChart.update('none');
            }

            const ind = document.getElementById('refreshIndicator');
            if (ind) {
                ind.classList.add('refreshing');
                setTimeout(() => ind.classList.remove('refreshing'), 1200);
            }
        } catch (e) {
            console.warn('[SIMANDIRI] Auto-refresh gagal:', e);
        }
    }, 30000);
}

function animateValue(id, newVal) {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.textContent === String(newVal)) return;

    el.style.transition = 'transform 0.15s ease, opacity 0.15s ease';
    el.style.transform  = 'translateY(-4px)';
    el.style.opacity    = '0.4';

    setTimeout(() => {
        el.textContent    = newVal;
        el.style.transform = 'translateY(0)';
        el.style.opacity   = '1';
    }, 160);
}

// ============================================================
//  STAT CARD BAR ANIMATION
// ============================================================

function initStatBars() {
    document.querySelectorAll('.stat-bar-fill').forEach(bar => {
        const width = bar.getAttribute('data-width') || '0';
        setTimeout(() => {
            bar.style.width = width + '%';
        }, 200);
    });
}

// ============================================================
//  LIVE CLOCK
// ============================================================

function updateClock() {
    const el = document.getElementById('headerClock');
    if (!el) return;

    const now    = new Date();
    const days   = ['Minggu','Senin','Selasa','Rabu','Kamis','Jumat','Sabtu'];
    const months = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agt','Sep','Okt','Nov','Des'];

    const day   = days[now.getDay()];
    const date  = String(now.getDate()).padStart(2, '0');
    const month = months[now.getMonth()];
    const year  = now.getFullYear();
    const hh    = String(now.getHours()).padStart(2, '0');
    const mm    = String(now.getMinutes()).padStart(2, '0');
    const ss    = String(now.getSeconds()).padStart(2, '0');

    const dateEl = el.querySelector('.clock-date');
    const timeEl = el.querySelector('.clock-time');

    if (dateEl) dateEl.textContent = `${day}, ${date} ${month} ${year}`;
    if (timeEl) timeEl.textContent = `${hh}:${mm}:${ss}`;
}

// ============================================================
//  CAMERA SIMULATION
// ============================================================

const camScenes = [
    {
        id: 'cam-gerbang-utama',
        name: 'GATE A — ENTRANCE',
        persons: [
            { x: 30, y: 20, w: 22, h: 55, label: 'APD OK', ok: true },
            { x: 58, y: 25, w: 20, h: 50, label: 'APD OK', ok: true },
        ]
    },
    {
        id: 'cam-gerbang-b',
        name: 'GATE B — EXIT',
        persons: [
            { x: 45, y: 15, w: 18, h: 52, label: 'NO HELMET', ok: false },
        ]
    },
    {
        id: 'cam-area-1',
        name: 'PRODUCTION FLOOR 1',
        persons: [
            { x: 20, y: 18, w: 20, h: 54, label: 'APD OK', ok: true },
            { x: 70, y: 22, w: 18, h: 50, label: 'APD OK', ok: true },
        ]
    },
    {
        id: 'cam-area-2',
        name: 'PRODUCTION FLOOR 2',
        persons: [
            { x: 35, y: 20, w: 20, h: 52, label: 'NO VEST', ok: false },
        ]
    },
];

function drawCamScene(canvasEl, persons, palette) {
    const ctx  = canvasEl.getContext('2d');
    const W    = canvasEl.width  = canvasEl.offsetWidth  || 320;
    const H    = canvasEl.height = canvasEl.offsetHeight || 180;

    // Background — dark industrial floor
    const bgGrad = ctx.createLinearGradient(0, 0, 0, H);
    bgGrad.addColorStop(0, palette.bg1);
    bgGrad.addColorStop(1, palette.bg2);
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, W, H);

    // Floor grid perspective
    ctx.strokeStyle = 'rgba(255,255,255,0.04)';
    ctx.lineWidth   = 0.5;
    for (let i = 0; i < 8; i++) {
        const y = H * 0.5 + (H * 0.5 / 7) * i;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(W, y);
        ctx.stroke();
    }
    for (let i = 0; i < 12; i++) {
        const x = (W / 11) * i;
        ctx.beginPath();
        ctx.moveTo(W / 2 + (x - W / 2) * (H * 0.5 / H), H * 0.5);
        ctx.lineTo(x, H);
        ctx.stroke();
    }

    // Ambient gradient overlay
    const ambGrad = ctx.createRadialGradient(W * 0.5, H * 0.4, 0, W * 0.5, H * 0.4, W * 0.6);
    ambGrad.addColorStop(0, 'rgba(59,130,246,0.06)');
    ambGrad.addColorStop(1, 'transparent');
    ctx.fillStyle = ambGrad;
    ctx.fillRect(0, 0, W, H);

    // Draw persons as silhouettes with detection boxes
    persons.forEach(p => {
        const px = (p.x / 100) * W;
        const py = (p.y / 100) * H;
        const pw = (p.w / 100) * W;
        const ph = (p.h / 100) * H;

        // Silhouette
        ctx.fillStyle = 'rgba(30, 50, 80, 0.7)';
        ctx.beginPath();
        // Head
        const headR = pw * 0.25;
        ctx.arc(px + pw / 2, py + headR, headR, 0, Math.PI * 2);
        ctx.fill();
        // Body
        ctx.fillRect(px + pw * 0.1, py + headR * 2, pw * 0.8, ph * 0.6);
        // Legs
        ctx.fillRect(px + pw * 0.1, py + headR * 2 + ph * 0.6, pw * 0.35, ph * 0.35);
        ctx.fillRect(px + pw * 0.55, py + headR * 2 + ph * 0.6, pw * 0.35, ph * 0.35);

        // Detection box
        const boxColor = p.ok ? '#10B981' : '#EF4444';
        ctx.strokeStyle = boxColor;
        ctx.lineWidth   = 1.5;
        ctx.setLineDash([]);

        // Corner marks only
        const cLen = 8;
        ctx.beginPath();
        // TL
        ctx.moveTo(px, py + cLen); ctx.lineTo(px, py); ctx.lineTo(px + cLen, py);
        // TR
        ctx.moveTo(px + pw - cLen, py); ctx.lineTo(px + pw, py); ctx.lineTo(px + pw, py + cLen);
        // BR
        ctx.moveTo(px + pw, py + ph - cLen); ctx.lineTo(px + pw, py + ph); ctx.lineTo(px + pw - cLen, py + ph);
        // BL
        ctx.moveTo(px + cLen, py + ph); ctx.lineTo(px, py + ph); ctx.lineTo(px, py + ph - cLen);
        ctx.stroke();

        // Label
        ctx.fillStyle    = boxColor;
        ctx.font         = 'bold 8px "JetBrains Mono", monospace';
        ctx.textAlign    = 'left';
        ctx.textBaseline = 'bottom';
        ctx.fillText(p.label, px, py - 2);
    });

    // Scanlines
    for (let y = 0; y < H; y += 3) {
        ctx.fillStyle = 'rgba(0,0,0,0.04)';
        ctx.fillRect(0, y, W, 1);
    }
}

const camPalettes = [
    { bg1: '#020810', bg2: '#050F1C' },
    { bg1: '#030A10', bg2: '#060E18' },
    { bg1: '#020C0C', bg2: '#04121A' },
    { bg1: '#080412', bg2: '#0C0818' },
];

function initCameras() {
    camScenes.forEach((scene, idx) => {
        const canvas = document.getElementById(scene.id);
        if (!canvas) return;
        drawCamScene(canvas, scene.persons, camPalettes[idx] || camPalettes[0]);
    });
}

// Animate detection boxes (subtle pulsing)
function animateCameras() {
    let tick = 0;
    setInterval(() => {
        tick++;
        camScenes.forEach((scene, idx) => {
            const canvas = document.getElementById(scene.id);
            if (!canvas) return;
            // Add slight flicker on every 5th tick
            if (tick % 5 === 0) {
                // Randomly nudge one person
                const persons = JSON.parse(JSON.stringify(scene.persons));
                persons.forEach(p => {
                    p.x += (Math.random() - 0.5) * 0.5;
                    p.y += (Math.random() - 0.5) * 0.3;
                });
                drawCamScene(canvas, persons, camPalettes[idx] || camPalettes[0]);
            }
        });
    }, 500);
}

// ============================================================
//  CAMERA TIMESTAMP
// ============================================================

function updateCamTimestamps() {
    document.querySelectorAll('.cam-timestamp').forEach(el => {
        const now = new Date();
        const hh  = String(now.getHours()).padStart(2, '0');
        const mm  = String(now.getMinutes()).padStart(2, '0');
        const ss  = String(now.getSeconds()).padStart(2, '0');
        el.textContent = `REC ${hh}:${mm}:${ss}`;
    });
}

// ============================================================
//  SIDEBAR TOGGLE
// ============================================================

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const body    = document.body;

    if (window.innerWidth <= 768) {
        sidebar.classList.toggle('mobile-open');
    } else {
        sidebar.classList.toggle('collapsed');
        body.classList.toggle('sidebar-collapsed');
    }
}

// ============================================================
//  THEME TOGGLE (Light/Dark Mode)
// ============================================================

function initTheme() {
    const savedTheme = localStorage.getItem('simandiri_theme') || 'dark';
    if (savedTheme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    }
    updateThemeIcon();
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = current === 'dark' ? 'light' : 'dark';
    
    if (newTheme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    } else {
        document.documentElement.removeAttribute('data-theme');
    }
    
    localStorage.setItem('simandiri_theme', newTheme);
    updateThemeIcon();
}

function updateThemeIcon() {
    const btn = document.getElementById('themeToggleBtn');
    if (!btn) return;
    
    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    const iconSun = btn.querySelector('.icon-sun');
    const iconMoon = btn.querySelector('.icon-moon');
    
    if (iconSun && iconMoon) {
        if (isLight) {
            iconSun.style.display = 'none';
            iconMoon.style.display = 'inline-block';
        } else {
            iconSun.style.display = 'inline-block';
            iconMoon.style.display = 'none';
        }
    }
}

// Mobile overlay backdrop
function setupMobileOverlay() {
    if (window.innerWidth > 768) return;

    let overlay = document.getElementById('sidebarOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'sidebarOverlay';
        overlay.style.cssText = `
            position: fixed; inset: 0; z-index: 199;
            background: rgba(0,0,0,0.6); backdrop-filter: blur(4px);
            display: none;
        `;
        overlay.onclick = () => {
            document.getElementById('sidebar')?.classList.remove('mobile-open');
            overlay.style.display = 'none';
        };
        document.body.appendChild(overlay);
    }

    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;

    const observer = new MutationObserver(() => {
        overlay.style.display = sidebar.classList.contains('mobile-open') ? 'block' : 'none';
    });
    observer.observe(sidebar, { attributes: true, attributeFilter: ['class'] });
}

// ============================================================
//  ENTRANCE ANIMATIONS
// ============================================================

function runEntranceAnimations() {
    const cards = document.querySelectorAll(
        '.stat-card, .glass-card, .pegawai-card, .anim-enter'
    );

    cards.forEach((card, i) => {
        card.style.opacity   = '0';
        card.style.transform = 'translateY(16px)';

        requestAnimationFrame(() => {
            setTimeout(() => {
                card.style.transition = 'opacity 0.45s ease, transform 0.45s ease';
                card.style.opacity    = '1';
                card.style.transform  = 'translateY(0)';
            }, 80 + i * 50);
        });
    });
}

// ============================================================
//  ROOM PRESENCE — Live Panel
// ============================================================

let presenceRefreshInterval = null;

function initRoomPresence() {
    const container = document.getElementById('presenceList');
    if (!container) return;
    fetchAndRenderPresence();
    presenceRefreshInterval = setInterval(fetchAndRenderPresence, 5000);
}

async function fetchAndRenderPresence() {
    try {
        const resp = await fetch('/api/room/presence');
        if (!resp.ok) return;
        const data = await resp.json();

        // Update counter
        const counter = document.getElementById('presenceCount');
        if (counter) {
            animateValue('presenceCount', data.count);
        }

        // Render cards
        const container = document.getElementById('presenceList');
        if (!container) return;

        if (data.count === 0) {
            container.innerHTML = `
                <div class="empty-state-compact">
                    <i data-lucide="user-x"></i>
                    <p>Ruangan kosong</p>
                    <span>Belum ada pegawai di dalam ruangan</span>
                </div>
            `;
        } else {
            container.innerHTML = data.presence.map(p => {
                const initials = p.nama.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
                const apdClass = p.status_apd === 'lengkap' ? 'apd-ok' : 'apd-fail';
                const apdLabel = p.status_apd === 'lengkap' ? 'APD OK' : 'APD ✕';
                return `
                    <div class="presence-card">
                        <div class="presence-avatar">${initials}</div>
                        <div class="presence-info">
                            <div class="presence-name">${p.nama}</div>
                            <div class="presence-time">
                                <i data-lucide="clock"></i>
                                Masuk ${p.waktu_masuk}
                            </div>
                        </div>
                        <span class="presence-apd-badge ${apdClass}">${apdLabel}</span>
                    </div>
                `;
            }).join('');
        }

        // Re-init lucide icons for newly added elements
        if (window.lucide) lucide.createIcons();
    } catch (e) {
        console.warn('[SIMANDIRI] Presence fetch error:', e);
    }
}

// ============================================================
//  ACCESS TIMELINE — History Panel
// ============================================================

let timelineRefreshInterval = null;

function initAccessTimeline() {
    const container = document.getElementById('accessTimeline');
    if (!container) return;
    fetchAndRenderTimeline();
    timelineRefreshInterval = setInterval(fetchAndRenderTimeline, 10000);
}

async function fetchAndRenderTimeline() {
    try {
        const resp = await fetch('/api/room/history');
        if (!resp.ok) return;
        const data = await resp.json();

        const container = document.getElementById('accessTimeline');
        if (!container) return;

        if (data.count === 0) {
            container.innerHTML = `
                <div class="empty-state-compact">
                    <i data-lucide="clock"></i>
                    <p>Belum ada aktivitas</p>
                    <span>Riwayat akses akan muncul di sini</span>
                </div>
            `;
        } else {
            container.innerHTML = data.history.map(h => {
                let nodeClass, iconName, badgeClass;
                if (h.aksi === 'IN') {
                    nodeClass = 'node-in';
                    iconName = 'log-in';
                    badgeClass = 'badge-in';
                } else if (h.aksi === 'OUT') {
                    nodeClass = 'node-out';
                    iconName = 'log-out';
                    badgeClass = 'badge-out';
                } else {
                    nodeClass = 'node-denied';
                    iconName = 'x-circle';
                    badgeClass = 'badge-denied';
                }

                const reasonHtml = h.alasan_tolak
                    ? `<div class="timeline-reason">${h.alasan_tolak}</div>`
                    : '';

                return `
                    <div class="timeline-entry">
                        <div class="timeline-node ${nodeClass}">
                            <i data-lucide="${iconName}"></i>
                        </div>
                        <div class="timeline-content">
                            <div class="timeline-header">
                                <span class="timeline-name">${h.nama_pegawai || 'Unknown'}</span>
                                <span class="timeline-action-badge ${badgeClass}">${h.aksi}</span>
                            </div>
                            <div class="timeline-meta">
                                <i data-lucide="clock"></i>
                                ${h.waktu}
                                ${h.nama_ruangan ? ' · ' + h.nama_ruangan : ''}
                            </div>
                            ${reasonHtml}
                        </div>
                    </div>
                `;
            }).join('');
        }

        if (window.lucide) lucide.createIcons();
    } catch (e) {
        console.warn('[SIMANDIRI] Timeline fetch error:', e);
    }
}

// ============================================================
//  RFID MODAL — Registration
// ============================================================

let rfidModalPegawaiId = null;

function openRfidModal(pegawaiId, pegawaiNama, currentRfid) {
    rfidModalPegawaiId = pegawaiId;
    const backdrop = document.getElementById('rfidModalBackdrop');
    if (!backdrop) return;

    const nameEl = backdrop.querySelector('.rfid-modal-employee-name');
    if (nameEl) nameEl.textContent = pegawaiNama;

    const input = backdrop.querySelector('#rfidUidInput');
    if (input) input.value = currentRfid || '';

    const removeBtn = backdrop.querySelector('.btn-rfid-remove');
    if (removeBtn) removeBtn.style.display = currentRfid ? 'inline-block' : 'none';

    const feedback = backdrop.querySelector('.rfid-feedback');
    if (feedback) { feedback.className = 'rfid-feedback'; feedback.textContent = ''; }

    backdrop.classList.add('active');
    if (input) setTimeout(() => input.focus(), 300);
}

function closeRfidModal() {
    const backdrop = document.getElementById('rfidModalBackdrop');
    if (backdrop) backdrop.classList.remove('active');
    rfidModalPegawaiId = null;
}

async function saveRfid() {
    if (!rfidModalPegawaiId) return;
    const backdrop = document.getElementById('rfidModalBackdrop');
    const input = backdrop.querySelector('#rfidUidInput');
    const feedback = backdrop.querySelector('.rfid-feedback');
    const rfidUid = input.value.trim().toUpperCase();

    if (!rfidUid) {
        feedback.className = 'rfid-feedback error';
        feedback.textContent = 'RFID UID tidak boleh kosong';
        return;
    }

    try {
        const resp = await fetch(`/api/pegawai/${rfidModalPegawaiId}/rfid`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rfid_uid: rfidUid })
        });
        const result = await resp.json();

        if (resp.ok) {
            feedback.className = 'rfid-feedback success';
            feedback.textContent = result.message;
            setTimeout(() => { closeRfidModal(); location.reload(); }, 800);
        } else {
            feedback.className = 'rfid-feedback error';
            feedback.textContent = result.message;
        }
    } catch (e) {
        feedback.className = 'rfid-feedback error';
        feedback.textContent = 'Gagal menghubungi server';
    }
}

async function removeRfid() {
    if (!rfidModalPegawaiId) return;
    const backdrop = document.getElementById('rfidModalBackdrop');
    const feedback = backdrop.querySelector('.rfid-feedback');

    try {
        const resp = await fetch(`/api/pegawai/${rfidModalPegawaiId}/rfid`, {
            method: 'DELETE'
        });
        const result = await resp.json();

        if (resp.ok) {
            feedback.className = 'rfid-feedback success';
            feedback.textContent = result.message;
            setTimeout(() => { closeRfidModal(); location.reload(); }, 800);
        } else {
            feedback.className = 'rfid-feedback error';
            feedback.textContent = result.message;
        }
    } catch (e) {
        feedback.className = 'rfid-feedback error';
        feedback.textContent = 'Gagal menghubungi server';
    }
}

// ============================================================
//  INIT
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    // Theme
    initTheme();

    // Clock
    updateClock();
    setInterval(updateClock, 1000);

    // Cameras
    initCameras();
    animateCameras();
    updateCamTimestamps();
    setInterval(updateCamTimestamps, 1000);

    // Stat bars
    initStatBars();

    // Room Presence & Timeline (dashboard)
    initRoomPresence();
    initAccessTimeline();

    // Entrance
    runEntranceAnimations();

    // Mobile
    if (window.innerWidth <= 768) {
        const sidebar = document.getElementById('sidebar');
        if (sidebar) sidebar.classList.remove('mobile-open');
        setupMobileOverlay();
    }

    // Lucide icons
    if (window.lucide) lucide.createIcons();

    // RFID modal — close on backdrop click
    const rfidBackdrop = document.getElementById('rfidModalBackdrop');
    if (rfidBackdrop) {
        rfidBackdrop.addEventListener('click', (e) => {
            if (e.target === rfidBackdrop) closeRfidModal();
        });
    }
});

