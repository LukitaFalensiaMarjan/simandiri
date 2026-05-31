"""
 SIMANDIRI - Web Dashboard
================================
Flask web application untuk monitoring keselamatan kerja.
"""

import sys
import os
import json
import time
from datetime import datetime, date

# Import dari parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DatabaseManager
from config import (
    WEB_HOST, WEB_PORT, WEB_DEBUG,
    PPE_STATUS_FILE, PPE_STATUS_MAX_AGE, RFID_REQUIRE_PPE_COMPLETE
)

from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
db = DatabaseManager()


# ============================================================
#  Custom Jinja2 Filters
# ============================================================

@app.template_filter('parse_json')
def parse_json_filter(value):
    """Parse JSON string menjadi list Python."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return [str(value)]


@app.template_filter('format_datetime')
def format_datetime_filter(value):
    """Format datetime menjadi string yang mudah dibaca."""
    if not value:
        return '-'
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.strftime('%d %b %Y, %H:%M')
    return str(value)


@app.template_filter('format_date')
def format_date_filter(value):
    """Format date menjadi string yang mudah dibaca."""
    if not value:
        return '-'
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return value
    if isinstance(value, (date, datetime)):
        return value.strftime('%d %b %Y')
    return str(value)


# ============================================================
#  HALAMAN WEB (HTML Routes)
# ============================================================

@app.route('/')
def dashboard():
    """Halaman utama dashboard."""
    stats = db.get_dashboard_stats()

    # Serialize chart data untuk JavaScript
    absensi_chart = []
    for row in stats.get('absensi_chart', []):
        tanggal = row['tanggal']
        if isinstance(tanggal, (date, datetime)):
            tanggal = tanggal.strftime('%Y-%m-%d')
        absensi_chart.append({'tanggal': str(tanggal), 'total': int(row['total'])})

    pelanggaran_chart = []
    for row in stats.get('pelanggaran_chart', []):
        tanggal = row['tanggal']
        if isinstance(tanggal, (date, datetime)):
            tanggal = tanggal.strftime('%Y-%m-%d')
        pelanggaran_chart.append({'tanggal': str(tanggal), 'total': int(row['total'])})

    recent_activity = []
    for row in stats.get('recent_activity', []):
        waktu = row.get('waktu', '')
        if isinstance(waktu, datetime):
            waktu = waktu.strftime('%Y-%m-%d %H:%M:%S')
        recent_activity.append({
            'tipe': row.get('tipe', ''),
            'nama_pegawai': row.get('nama_pegawai', ''),
            'waktu': str(waktu),
            'detail': row.get('detail', '')
        })

    return render_template('dashboard.html',
                           stats=stats,
                           room_stats=db.get_room_stats(),
                           absensi_chart=json.dumps(absensi_chart),
                           pelanggaran_chart=json.dumps(pelanggaran_chart),
                           recent_activity=recent_activity)


@app.route('/absensi')
def absensi():
    """Halaman data absensi (Roster & Statistik Industri)."""
    tanggal = request.args.get('tanggal', None)
    nama_filter = request.args.get('nama', None)
    status_hadir = request.args.get('status_hadir', None)
    status_apd = request.args.get('status_apd', None)

    # Ambil roster lengkap dan statistik
    roster, stats = db.get_advanced_absensi(tanggal=tanggal)
    
    # Filter secara manual
    if nama_filter:
        roster = [r for r in roster if nama_filter.lower() in r['nama'].lower()]
    if status_hadir:
        roster = [r for r in roster if r['status'].lower() == status_hadir.lower()]
    if status_apd:
        roster = [r for r in roster if r['status_apd'] == status_apd.lower()]
    
    # Ambil data pelanggaran gerbang untuk ditampilkan di bawah
    pelanggaran_gerbang = db.get_pelanggaran_gerbang(tanggal=tanggal, limit=10)

    return render_template('absensi.html',
                           roster=roster,
                           stats=stats,
                           pelanggaran_gerbang=pelanggaran_gerbang,
                           tanggal=tanggal or '',
                           nama=nama_filter or '',
                           status_hadir=status_hadir or '',
                           status_apd=status_apd or '')


@app.route('/pelanggaran')
def pelanggaran():
    """Halaman data pelanggaran CCTV."""
    tanggal = request.args.get('tanggal', None)
    nama = request.args.get('nama', None)
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    # Ambil data
    data = db.get_pelanggaran(tanggal=tanggal, nama=nama, limit=per_page, offset=offset)
    total = db.get_pelanggaran_count(tanggal=tanggal, nama=nama)
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Ambil daftar nama pegawai untuk filter
    nama_list = db.get_nama_pegawai_list()

    return render_template('pelanggaran.html',
                           data=data,
                           tanggal=tanggal or '',
                           nama=nama or '',
                           nama_list=nama_list,
                           page=page,
                           total_pages=total_pages,
                           total=total)


@app.route('/pegawai')
def pegawai():
    """Halaman data pegawai."""
    data = db.get_all_pegawai()
    return render_template('pegawai.html', data=data)


# ============================================================
#  API ENDPOINTS (JSON)
# ============================================================

@app.route('/api/dashboard')
def api_dashboard():
    """API endpoint untuk data dashboard (digunakan untuk auto-refresh)."""
    stats = db.get_dashboard_stats()

    # Serialize untuk JSON
    absensi_chart = []
    for row in stats.get('absensi_chart', []):
        tanggal = row['tanggal']
        if isinstance(tanggal, (date, datetime)):
            tanggal = tanggal.strftime('%Y-%m-%d')
        absensi_chart.append({'tanggal': str(tanggal), 'total': int(row['total'])})

    pelanggaran_chart = []
    for row in stats.get('pelanggaran_chart', []):
        tanggal = row['tanggal']
        if isinstance(tanggal, (date, datetime)):
            tanggal = tanggal.strftime('%Y-%m-%d')
        pelanggaran_chart.append({'tanggal': str(tanggal), 'total': int(row['total'])})

    recent_activity = []
    for row in stats.get('recent_activity', []):
        waktu = row.get('waktu', '')
        if isinstance(waktu, datetime):
            waktu = waktu.strftime('%Y-%m-%d %H:%M:%S')
        recent_activity.append({
            'tipe': row.get('tipe', ''),
            'nama_pegawai': row.get('nama_pegawai', ''),
            'waktu': str(waktu),
            'detail': row.get('detail', '')
        })

    return jsonify({
        'total_pegawai': stats['total_pegawai'],
        'absensi_hari_ini': stats['absensi_hari_ini'],
        'compliance_rate': stats['compliance_rate'],
        'pelanggaran_hari_ini': stats['pelanggaran_hari_ini'],
        'absensi_chart': absensi_chart,
        'pelanggaran_chart': pelanggaran_chart,
        'recent_activity': recent_activity
    })


# ============================================================
#  RFID & AKSES RUANGAN
# ============================================================

def _read_ppe_status():
    """Baca status PPE dari shared JSON file."""
    ppe_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        PPE_STATUS_FILE
    )
    try:
        with open(ppe_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@app.route('/akses-ruangan')
def akses_ruangan():
    """Halaman akses ruangan (dedicated page)."""
    tanggal = request.args.get('tanggal', None)
    aksi = request.args.get('aksi', None)
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    ruangan = db.get_default_ruangan()
    ruangan_id = ruangan['id'] if ruangan else None

    history = db.get_akses_history(
        ruangan_id=ruangan_id, tanggal=tanggal,
        limit=per_page, offset=offset
    )
    total = db.get_akses_history_count(ruangan_id=ruangan_id, tanggal=tanggal)
    total_pages = max(1, (total + per_page - 1) // per_page)

    presence = db.get_presence(ruangan_id)
    room_stats = db.get_room_stats()

    return render_template('akses_ruangan.html',
                           ruangan=ruangan,
                           presence=presence,
                           history=history,
                           room_stats=room_stats,
                           tanggal=tanggal or '',
                           aksi=aksi or '',
                           page=page,
                           total_pages=total_pages,
                           total=total)


@app.route('/api/rfid/tap', methods=['POST'])
def api_rfid_tap():
    """
    API endpoint untuk menerima tap RFID dari hardware.
    Input: {"rfid_uid": "ABCD1234", "reader_id": "READER-01"}
    """
    data = request.get_json()
    if not data or 'rfid_uid' not in data:
        return jsonify({'status': 'error', 'message': 'rfid_uid diperlukan'}), 400

    rfid_uid = data['rfid_uid'].strip().upper()
    reader_id = data.get('reader_id', 'READER-01')

    # 1. Cari pegawai berdasarkan RFID
    pegawai = db.get_pegawai_by_rfid(rfid_uid)
    if not pegawai:
        # RFID tidak terdaftar — cari ruangan dan log DENIED
        ruangan = db.get_ruangan_by_reader(reader_id)
        if ruangan:
            db.catat_akses_ruangan(
                pegawai_id=None,
                ruangan_id=ruangan['id'],
                rfid_uid=rfid_uid,
                aksi='DENIED',
                alasan_tolak='RFID tidak terdaftar'
            )
        return jsonify({
            'status': 'denied',
            'action': None,
            'employee_name': None,
            'room_name': ruangan['nama'] if ruangan else None,
            'message': 'RFID tidak terdaftar dalam sistem',
            'ppe_status': None
        }), 403

    # 2. Cari ruangan berdasarkan reader
    ruangan = db.get_ruangan_by_reader(reader_id)
    if not ruangan:
        # Fallback ke ruangan default
        ruangan = db.get_default_ruangan()
    if not ruangan:
        return jsonify({'status': 'error', 'message': 'Ruangan tidak ditemukan'}), 404

    # 3. Tentukan aksi: IN atau OUT
    last_akses = db.get_last_akses(pegawai['id'], ruangan['id'])
    if last_akses and last_akses['aksi'] == 'IN':
        action = 'OUT'
    else:
        action = 'IN'

    # 4. Validasi
    if action == 'IN':
        # Cek PPE status
        ppe_data = _read_ppe_status()
        employee_ppe = ppe_data.get(pegawai['nama'], None)

        if RFID_REQUIRE_PPE_COMPLETE:
            if not employee_ppe:
                # Tidak ada data PPE
                db.catat_akses_ruangan(
                    pegawai_id=pegawai['id'],
                    ruangan_id=ruangan['id'],
                    rfid_uid=rfid_uid,
                    aksi='DENIED',
                    status_apd='tidak_diketahui',
                    alasan_tolak='Belum dicek APD oleh kamera'
                )
                return jsonify({
                    'status': 'denied',
                    'action': 'IN',
                    'employee_name': pegawai['nama'],
                    'room_name': ruangan['nama'],
                    'message': f'{pegawai["nama"]}, silakan menuju kamera untuk pengecekan APD terlebih dahulu.',
                    'ppe_status': 'tidak_diketahui'
                }), 403

            # Cek apakah data PPE masih fresh
            ppe_age = time.time() - employee_ppe.get('timestamp', 0)
            if ppe_age > PPE_STATUS_MAX_AGE:
                db.catat_akses_ruangan(
                    pegawai_id=pegawai['id'],
                    ruangan_id=ruangan['id'],
                    rfid_uid=rfid_uid,
                    aksi='DENIED',
                    status_apd='kadaluarsa',
                    alasan_tolak='Data APD sudah kadaluarsa, cek ulang'
                )
                return jsonify({
                    'status': 'denied',
                    'action': 'IN',
                    'employee_name': pegawai['nama'],
                    'room_name': ruangan['nama'],
                    'message': f'{pegawai["nama"]}, data pengecekan APD sudah kadaluarsa. Silakan cek ulang.',
                    'ppe_status': 'kadaluarsa'
                }), 403

            # Cek apakah PPE lengkap
            if employee_ppe.get('status') != 'lengkap':
                apd_kurang = employee_ppe.get('apd_kurang', [])
                db.catat_akses_ruangan(
                    pegawai_id=pegawai['id'],
                    ruangan_id=ruangan['id'],
                    rfid_uid=rfid_uid,
                    aksi='DENIED',
                    status_apd='tidak_lengkap',
                    alasan_tolak=f'APD tidak lengkap: kurang {", ".join(apd_kurang)}'
                )
                return jsonify({
                    'status': 'denied',
                    'action': 'IN',
                    'employee_name': pegawai['nama'],
                    'room_name': ruangan['nama'],
                    'message': f'{pegawai["nama"]}, APD tidak lengkap. Kurang: {", ".join(apd_kurang)}.',
                    'ppe_status': 'tidak_lengkap',
                    'apd_kurang': apd_kurang
                }), 403

        ppe_status = employee_ppe.get('status', 'lengkap') if employee_ppe else 'lengkap'

        # PPE OK — Grant access IN
        db.catat_akses_ruangan(
            pegawai_id=pegawai['id'],
            ruangan_id=ruangan['id'],
            rfid_uid=rfid_uid,
            aksi='IN',
            status_apd=ppe_status
        )
        return jsonify({
            'status': 'granted',
            'action': 'IN',
            'employee_name': pegawai['nama'],
            'room_name': ruangan['nama'],
            'message': f'Selamat datang {pegawai["nama"]}! Akses masuk diberikan.',
            'ppe_status': ppe_status
        }), 200

    else:
        # OUT — selalu diizinkan
        db.catat_akses_ruangan(
            pegawai_id=pegawai['id'],
            ruangan_id=ruangan['id'],
            rfid_uid=rfid_uid,
            aksi='OUT'
        )
        # Catat waktu pulang di absensi hari ini (jika ada)
        db.update_waktu_keluar(pegawai['id'])

        return jsonify({
            'status': 'granted',
            'action': 'OUT',
            'employee_name': pegawai['nama'],
            'room_name': ruangan['nama'],
            'message': f'{pegawai["nama"]} keluar dari {ruangan["nama"]}.',
            'ppe_status': None
        }), 200


@app.route('/api/room/presence')
def api_room_presence():
    """API: Siapa saja yang sedang di dalam ruangan."""
    ruangan_id = request.args.get('room_id', None, type=int)
    if not ruangan_id:
        ruangan = db.get_default_ruangan()
        ruangan_id = ruangan['id'] if ruangan else None

    presence = db.get_presence(ruangan_id)

    result = []
    for p in presence:
        waktu = p.get('waktu_masuk', '')
        if isinstance(waktu, datetime):
            waktu = waktu.strftime('%H:%M')
        result.append({
            'pegawai_id': p['pegawai_id'],
            'nama': p['nama'],
            'waktu_masuk': str(waktu),
            'status_apd': p.get('status_apd', ''),
            'nama_ruangan': p.get('nama_ruangan', ''),
        })

    return jsonify({
        'count': len(result),
        'presence': result
    })


@app.route('/api/room/history')
def api_room_history():
    """API: Riwayat akses ruangan hari ini."""
    ruangan_id = request.args.get('room_id', None, type=int)
    tanggal = request.args.get('tanggal', None)

    if not ruangan_id:
        ruangan = db.get_default_ruangan()
        ruangan_id = ruangan['id'] if ruangan else None

    history = db.get_akses_history(ruangan_id=ruangan_id, tanggal=tanggal, limit=50)

    result = []
    for h in history:
        waktu = h.get('waktu', '')
        if isinstance(waktu, datetime):
            waktu = waktu.strftime('%H:%M:%S')
        result.append({
            'id': h['id'],
            'nama_pegawai': h.get('nama_pegawai', 'Unknown'),
            'aksi': h['aksi'],
            'waktu': str(waktu),
            'status_apd': h.get('status_apd', ''),
            'alasan_tolak': h.get('alasan_tolak', ''),
            'nama_ruangan': h.get('nama_ruangan', ''),
        })

    return jsonify({
        'count': len(result),
        'history': result
    })


@app.route('/api/pegawai/<int:pegawai_id>/rfid', methods=['POST'])
def api_set_rfid(pegawai_id):
    """API: Register/update RFID UID untuk pegawai."""
    data = request.get_json()
    if not data or 'rfid_uid' not in data:
        return jsonify({'status': 'error', 'message': 'rfid_uid diperlukan'}), 400

    rfid_uid = data['rfid_uid'].strip().upper()
    if not rfid_uid:
        return jsonify({'status': 'error', 'message': 'rfid_uid tidak boleh kosong'}), 400

    # Cek apakah RFID sudah dipakai pegawai lain
    existing = db.get_pegawai_by_rfid(rfid_uid)
    if existing and existing['id'] != pegawai_id:
        return jsonify({
            'status': 'error',
            'message': f'RFID sudah terdaftar untuk {existing["nama"]}'
        }), 409

    success = db.set_pegawai_rfid(pegawai_id, rfid_uid)
    if success:
        return jsonify({'status': 'ok', 'message': 'RFID berhasil didaftarkan'})
    else:
        return jsonify({'status': 'error', 'message': 'Gagal mendaftarkan RFID'}), 500


@app.route('/api/pegawai/<int:pegawai_id>/rfid', methods=['DELETE'])
def api_remove_rfid(pegawai_id):
    """API: Hapus RFID UID dari pegawai."""
    success = db.set_pegawai_rfid(pegawai_id, None)
    if success:
        return jsonify({'status': 'ok', 'message': 'RFID berhasil dihapus'})
    else:
        return jsonify({'status': 'error', 'message': 'Gagal menghapus RFID'}), 500


# ============================================================
#  RUN SERVER
# ============================================================

if __name__ == '__main__':
    print("=" * 50)
    print("  SIMANDIRI - Web Dashboard")
    print(f"  URL: http://{WEB_HOST}:{WEB_PORT}")
    print("=" * 50)
    app.run(host=WEB_HOST, port=WEB_PORT, debug=WEB_DEBUG)
