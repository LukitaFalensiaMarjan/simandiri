"""
SIMANDIRI - Database Manager
==============================
Module untuk mengelola koneksi dan operasi MySQL.
Digunakan oleh: main_simandiri.py, cctv_monitor.py, web/app.py
"""

import mysql.connector
from mysql.connector import Error
import json
from datetime import datetime, timedelta
from config import MYSQL_CONFIG


class DatabaseManager:
    def __init__(self):
        self.config = MYSQL_CONFIG.copy()
        self.db_name = self.config.pop('database')
        self._create_database()
        self.config['database'] = self.db_name
        self._create_tables()
        self._migrate_tables()
        print(f"[OK] Database '{self.db_name}' siap digunakan.")

    def _get_connection(self, with_db=True):
        """Buat koneksi baru ke MySQL."""
        config = self.config.copy()
        if not with_db:
            config.pop('database', None)
        return mysql.connector.connect(**config)

    def _create_database(self):
        """Buat database jika belum ada."""
        try:
            conn = self._get_connection(with_db=False)
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{self.db_name}` "
                           f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.commit()
            cursor.close()
            conn.close()
        except Error as e:
            print(f"❌ Gagal membuat database: {e}")
            raise

    def _create_tables(self):
        """Buat tabel-tabel yang dibutuhkan."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Tabel pegawai
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pegawai (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nama VARCHAR(100) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB
        """)

        # Tabel absensi (dari sistem gerbang) — 1 record per pegawai per hari
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS absensi (
                id INT AUTO_INCREMENT PRIMARY KEY,
                pegawai_id INT,
                nama_pegawai VARCHAR(100) NOT NULL,
                tanggal DATE NOT NULL,
                waktu_masuk TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                waktu_keluar TIMESTAMP NULL DEFAULT NULL,
                status_kehadiran VARCHAR(20) DEFAULT 'Tepat Waktu',
                waktu_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                status_apd VARCHAR(20) NOT NULL,
                apd_terdeteksi TEXT,
                apd_kurang TEXT,
                FOREIGN KEY (pegawai_id) REFERENCES pegawai(id) ON DELETE SET NULL,
                UNIQUE KEY uq_pegawai_tanggal (pegawai_id, tanggal)
            ) ENGINE=InnoDB
        """)

        # Tabel riwayat gerbang — setiap percobaan masuk dicatat
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS riwayat_gerbang (
                id INT AUTO_INCREMENT PRIMARY KEY,
                absensi_id INT,
                pegawai_id INT,
                nama_pegawai VARCHAR(100) NOT NULL,
                waktu TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status_apd VARCHAR(20) NOT NULL,
                apd_terdeteksi TEXT,
                apd_kurang TEXT,
                FOREIGN KEY (absensi_id) REFERENCES absensi(id) ON DELETE SET NULL,
                FOREIGN KEY (pegawai_id) REFERENCES pegawai(id) ON DELETE SET NULL
            ) ENGINE=InnoDB
        """)

        # Tabel pelanggaran CCTV (dari sistem CCTV indoor)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pelanggaran_cctv (
                id INT AUTO_INCREMENT PRIMARY KEY,
                pegawai_id INT,
                nama_pegawai VARCHAR(100) NOT NULL,
                waktu_pelanggaran TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                apd_dilepas TEXT NOT NULL,
                kamera VARCHAR(50) DEFAULT 'CCTV-Indoor-1',
                FOREIGN KEY (pegawai_id) REFERENCES pegawai(id) ON DELETE SET NULL
            ) ENGINE=InnoDB
        """)

        # Tabel ruangan (untuk akses RFID)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ruangan (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nama VARCHAR(100) UNIQUE NOT NULL,
                kode VARCHAR(20) UNIQUE NOT NULL,
                reader_id VARCHAR(50) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB
        """)

        # Tabel akses ruangan (log RFID tap IN/OUT/DENIED)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS akses_ruangan (
                id INT AUTO_INCREMENT PRIMARY KEY,
                pegawai_id INT,
                ruangan_id INT,
                rfid_uid VARCHAR(20) NOT NULL,
                aksi ENUM('IN', 'OUT', 'DENIED') NOT NULL,
                status_apd VARCHAR(20) DEFAULT NULL,
                alasan_tolak VARCHAR(100) DEFAULT NULL,
                waktu TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pegawai_id) REFERENCES pegawai(id) ON DELETE SET NULL,
                FOREIGN KEY (ruangan_id) REFERENCES ruangan(id) ON DELETE SET NULL,
                INDEX idx_pegawai_waktu (pegawai_id, waktu),
                INDEX idx_ruangan_waktu (ruangan_id, waktu)
            ) ENGINE=InnoDB
        """)

        # Seed ruangan default
        cursor.execute("""
            INSERT IGNORE INTO ruangan (nama, kode, reader_id)
            VALUES ('Ruang Produksi A', 'PROD-A', 'READER-01')
        """)

        conn.commit()
        cursor.close()
        conn.close()

    def _migrate_tables(self):
        """Migrasi struktur tabel jika ada pembaruan (misal: tambah kolom)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Cek apakah kolom 'tanggal' sudah ada di tabel 'absensi'
        cursor.execute("SHOW COLUMNS FROM absensi LIKE 'tanggal'")
        if not cursor.fetchone():
            print("   [INFO] Migrasi: Menambahkan kolom baru ke tabel 'absensi'...")
            try:
                cursor.execute("ALTER TABLE absensi ADD COLUMN tanggal DATE")
                cursor.execute("UPDATE absensi SET tanggal = DATE(waktu_masuk)")
                cursor.execute("ALTER TABLE absensi ADD COLUMN waktu_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
                conn.commit()
                # Hindari error NOT NULL jika ada data lama, set NOT NULL setelah update
                cursor.execute("ALTER TABLE absensi MODIFY COLUMN tanggal DATE NOT NULL")
                conn.commit()
            except Error as e:
                print(f"   ❌ Gagal melakukan alter table: {e}")
                
            try:
                cursor.execute("ALTER TABLE absensi ADD UNIQUE KEY uq_pegawai_tanggal (pegawai_id, tanggal)")
                conn.commit()
            except Error as e:
                print(f"   ⚠️ Peringatan saat menambah unique key (mungkin ada data duplikat): {e}")
                
            print("   [OK] Migrasi database selesai.")

        # Migrasi: Tambah kolom rfid_uid ke tabel pegawai
        cursor.execute("SHOW COLUMNS FROM pegawai LIKE 'rfid_uid'")
        if not cursor.fetchone():
            print("   [INFO] Migrasi: Menambahkan kolom 'rfid_uid' ke tabel 'pegawai'...")
            try:
                cursor.execute("ALTER TABLE pegawai ADD COLUMN rfid_uid VARCHAR(20) UNIQUE DEFAULT NULL")
                conn.commit()
                print("   [OK] Kolom 'rfid_uid' berhasil ditambahkan.")
            except Error as e:
                print(f"   ❌ Gagal menambah kolom rfid_uid: {e}")

        # Migrasi: Tambah kolom waktu_keluar dan status_kehadiran ke tabel absensi
        cursor.execute("SHOW COLUMNS FROM absensi LIKE 'waktu_keluar'")
        if not cursor.fetchone():
            print("   [INFO] Migrasi: Menambahkan kolom 'waktu_keluar' dan 'status_kehadiran' ke tabel 'absensi'...")
            try:
                cursor.execute("ALTER TABLE absensi ADD COLUMN waktu_keluar TIMESTAMP NULL DEFAULT NULL AFTER waktu_masuk")
                cursor.execute("ALTER TABLE absensi ADD COLUMN status_kehadiran VARCHAR(20) DEFAULT 'Tepat Waktu' AFTER waktu_keluar")
                conn.commit()
                print("   [OK] Kolom absensi industri berhasil ditambahkan.")
            except Error as e:
                print(f"   ❌ Gagal menambah kolom absensi industri: {e}")

        cursor.close()
        conn.close()

    # ============================================================
    #  OPERASI INSERT
    # ============================================================

    def get_or_create_pegawai(self, nama):
        """Dapatkan ID pegawai, atau buat baru jika belum ada."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM pegawai WHERE nama = %s", (nama,))
        result = cursor.fetchone()

        if result:
            pegawai_id = result[0]
        else:
            cursor.execute("INSERT INTO pegawai (nama) VALUES (%s)", (nama,))
            conn.commit()
            pegawai_id = cursor.lastrowid
            print(f"   [INFO] Pegawai baru ditambahkan: {nama}")

        cursor.close()
        conn.close()
        return pegawai_id

    def catat_absensi(self, nama, status_apd, apd_terdeteksi, apd_kurang):
        """
        Catat absensi pegawai dari sistem gerbang.
        Aturan: 1 pegawai hanya 1 absensi per hari.
        - Jika belum ada absensi hari ini -> INSERT baru
        - Jika sudah ada -> JANGAN update absensi
        Selalu catat ke riwayat_gerbang sebagai history.
        Returns: absensi_id
        """
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        pegawai_id = self.get_or_create_pegawai(nama)
        today = datetime.now().strftime('%Y-%m-%d')
        apd_terdeteksi_json = json.dumps(apd_terdeteksi)
        apd_kurang_json = json.dumps(apd_kurang)

        # Cek apakah sudah absen hari ini
        cursor.execute(
            "SELECT id, status_apd FROM absensi WHERE pegawai_id = %s AND tanggal = %s",
            (pegawai_id, today)
        )
        existing = cursor.fetchone()

        # Cek status keterlambatan
        from config import SHIFT_START_TIME
        current_time = datetime.now()
        shift_time = datetime.strptime(f"{today} {SHIFT_START_TIME}", "%Y-%m-%d %H:%M:%S")
        status_kehadiran = 'Terlambat' if current_time > shift_time else 'Tepat Waktu'

        if existing:
            absensi_id = existing['id']
            print(f"   ℹ️ Absensi sudah ada hari ini: {nama} (Tidak diupdate)")
        else:
            # Belum absen hari ini -> INSERT baru
            cursor.execute("""
                INSERT INTO absensi (pegawai_id, nama_pegawai, tanggal, status_apd,
                                     apd_terdeteksi, apd_kurang, status_kehadiran)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (pegawai_id, nama, today, status_apd,
                  apd_terdeteksi_json, apd_kurang_json, status_kehadiran))
            conn.commit()
            absensi_id = cursor.lastrowid
            print(f"   [INFO] Absensi diupdate: {nama} - APD {status_apd} - {status_kehadiran}")

        # Selalu catat ke riwayat gerbang (history setiap percobaan)
        cursor.execute("""
            INSERT INTO riwayat_gerbang (absensi_id, pegawai_id, nama_pegawai,
                                         status_apd, apd_terdeteksi, apd_kurang)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (absensi_id, pegawai_id, nama, status_apd,
              apd_terdeteksi_json, apd_kurang_json))
        conn.commit()

        cursor.close()
        conn.close()
        return absensi_id

    def update_waktu_keluar(self, pegawai_id):
        """Update waktu keluar (clock-out) di tabel absensi untuk hari ini."""
        conn = self._get_connection()
        cursor = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute("""
            UPDATE absensi 
            SET waktu_keluar = CURRENT_TIMESTAMP 
            WHERE pegawai_id = %s AND tanggal = %s
        """, (pegawai_id, today))
        
        conn.commit()
        cursor.close()
        conn.close()

    def catat_pelanggaran(self, nama, apd_dilepas, kamera="CCTV-Indoor-1"):
        """Catat pelanggaran dari sistem CCTV indoor."""
        conn = self._get_connection()
        cursor = conn.cursor()

        pegawai_id = self.get_or_create_pegawai(nama)

        cursor.execute("""
            INSERT INTO pelanggaran_cctv (pegawai_id, nama_pegawai, apd_dilepas, kamera)
            VALUES (%s, %s, %s, %s)
        """, (
            pegawai_id,
            nama,
            json.dumps(apd_dilepas),
            kamera
        ))

        conn.commit()
        cursor.close()
        conn.close()
        print(f"   [WARN] Pelanggaran dicatat: {nama} - melepas {apd_dilepas}")

    # ============================================================
    #  OPERASI QUERY (untuk Web Dashboard)
    # ============================================================

    def get_absensi(self, tanggal=None, status=None, limit=20, offset=0):
        """Ambil data absensi dengan filter opsional."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        query = "SELECT * FROM absensi WHERE 1=1"
        params = []

        if tanggal:
            query += " AND tanggal = %s"
            params.append(tanggal)

        if status:
            query += " AND status_apd = %s"
            params.append(status)

        query += " ORDER BY waktu_masuk DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        results = cursor.fetchall()

        cursor.close()
        conn.close()
        return results

    def get_absensi_count(self, tanggal=None, status=None):
        """Hitung total data absensi dengan filter opsional."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT COUNT(*) FROM absensi WHERE 1=1"
        params = []

        if tanggal:
            query += " AND tanggal = %s"
            params.append(tanggal)

        if status:
            query += " AND status_apd = %s"
            params.append(status)

        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count

    def get_advanced_absensi(self, tanggal=None):
        """Ambil data kehadiran seluruh pegawai terdaftar (roster) beserta statusnya."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        if not tanggal:
            tanggal = datetime.now().strftime('%Y-%m-%d')

        # Ambil semua pegawai dengan LEFT JOIN absensi pada hari ini
        query = """
            SELECT 
                p.id as pegawai_id,
                p.nama,
                a.id as absensi_id,
                a.waktu_masuk,
                a.waktu_keluar,
                a.status_kehadiran,
                a.status_apd,
                a.apd_terdeteksi,
                a.apd_kurang
            FROM pegawai p
            LEFT JOIN absensi a ON p.id = a.pegawai_id AND a.tanggal = %s
            ORDER BY p.nama
        """
        cursor.execute(query, (tanggal,))
        results = cursor.fetchall()
        
        # Hitung statistik
        stats = {
            'total_pegawai': len(results),
            'hadir': 0,
            'terlambat': 0,
            'belum_hadir': 0
        }
        
        for row in results:
            if not row['absensi_id']:
                row['status'] = 'Belum Hadir'
                stats['belum_hadir'] += 1
            else:
                if row['status_kehadiran'] == 'Terlambat':
                    row['status'] = 'Terlambat'
                    stats['terlambat'] += 1
                else:
                    row['status'] = 'Hadir'
                    stats['hadir'] += 1
                    
            # Hitung durasi kerja jika ada waktu_masuk & waktu_keluar
            if row['waktu_masuk'] and row['waktu_keluar']:
                diff = row['waktu_keluar'] - row['waktu_masuk']
                hours, remainder = divmod(diff.total_seconds(), 3600)
                minutes, _ = divmod(remainder, 60)
                row['durasi'] = f"{int(hours)}j {int(minutes)}m"
            else:
                row['durasi'] = "-"

        cursor.close()
        conn.close()
        return results, stats

    def get_pelanggaran(self, tanggal=None, nama=None, limit=20, offset=0):
        """Ambil data pelanggaran gabungan dari CCTV dan Gerbang dengan filter opsional."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT * FROM (
                SELECT 
                    id, 
                    nama_pegawai, 
                    waktu_pelanggaran, 
                    apd_dilepas, 
                    kamera
                FROM pelanggaran_cctv
                
                UNION ALL
                
                SELECT 
                    id, 
                    nama_pegawai, 
                    waktu as waktu_pelanggaran, 
                    apd_kurang as apd_dilepas, 
                    'Gerbang Utama' as kamera
                FROM riwayat_gerbang
                WHERE status_apd = 'tidak_lengkap'
            ) AS combined
            WHERE 1=1
        """
        params = []

        if tanggal:
            query += " AND DATE(waktu_pelanggaran) = %s"
            params.append(tanggal)

        if nama:
            query += " AND nama_pegawai = %s"
            params.append(nama)

        query += " ORDER BY waktu_pelanggaran DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        results = cursor.fetchall()

        cursor.close()
        conn.close()
        return results

    def get_pelanggaran_count(self, tanggal=None, nama=None):
        """Hitung total data pelanggaran gabungan (CCTV + Gerbang) dengan filter opsional."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
            SELECT COUNT(*) FROM (
                SELECT nama_pegawai, waktu_pelanggaran FROM pelanggaran_cctv
                UNION ALL
                SELECT nama_pegawai, waktu as waktu_pelanggaran FROM riwayat_gerbang WHERE status_apd = 'tidak_lengkap'
            ) AS combined
            WHERE 1=1
        """
        params = []

        if tanggal:
            query += " AND DATE(waktu_pelanggaran) = %s"
            params.append(tanggal)

        if nama:
            query += " AND nama_pegawai = %s"
            params.append(nama)

        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count

    # ============================================================
    #  RIWAYAT GERBANG (History & Pelanggaran Gerbang)
    # ============================================================

    def get_riwayat_gerbang(self, tanggal=None, nama=None, status=None, limit=20, offset=0):
        """Ambil riwayat semua percobaan masuk di gerbang."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        query = "SELECT * FROM riwayat_gerbang WHERE 1=1"
        params = []

        if tanggal:
            query += " AND DATE(waktu) = %s"
            params.append(tanggal)

        if nama:
            query += " AND nama_pegawai = %s"
            params.append(nama)

        if status:
            query += " AND status_apd = %s"
            params.append(status)

        query += " ORDER BY waktu DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        results = cursor.fetchall()

        cursor.close()
        conn.close()
        return results

    def get_riwayat_gerbang_count(self, tanggal=None, nama=None, status=None):
        """Hitung total riwayat gerbang dengan filter."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT COUNT(*) FROM riwayat_gerbang WHERE 1=1"
        params = []

        if tanggal:
            query += " AND DATE(waktu) = %s"
            params.append(tanggal)

        if nama:
            query += " AND nama_pegawai = %s"
            params.append(nama)

        if status:
            query += " AND status_apd = %s"
            params.append(status)

        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count

    def get_pelanggaran_gerbang(self, tanggal=None, limit=20, offset=0):
        """Ambil data pelanggaran APD di gerbang (riwayat dengan APD tidak lengkap)."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        query = "SELECT * FROM riwayat_gerbang WHERE status_apd = 'tidak_lengkap'"
        params = []

        if tanggal:
            query += " AND DATE(waktu) = %s"
            params.append(tanggal)

        query += " ORDER BY waktu DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        results = cursor.fetchall()

        cursor.close()
        conn.close()
        return results

    def get_pelanggaran_gerbang_count(self, tanggal=None):
        """Hitung total pelanggaran APD di gerbang."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT COUNT(*) FROM riwayat_gerbang WHERE status_apd = 'tidak_lengkap'"
        params = []

        if tanggal:
            query += " AND DATE(waktu) = %s"
            params.append(tanggal)

        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count

    # ============================================================
    #  DASHBOARD STATS
    # ============================================================

    def get_dashboard_stats(self):
        """Ambil statistik untuk halaman dashboard."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        today = datetime.now().strftime('%Y-%m-%d')

        # Total pegawai
        cursor.execute("SELECT COUNT(*) as total FROM pegawai")
        total_pegawai = cursor.fetchone()['total']

        # Absensi hari ini
        cursor.execute(
            "SELECT COUNT(*) as total FROM absensi WHERE tanggal = %s",
            (today,)
        )
        absensi_hari_ini = cursor.fetchone()['total']

        # APD Compliance rate hari ini
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status_apd = 'lengkap' THEN 1 ELSE 0 END) as lengkap
            FROM absensi WHERE tanggal = %s
        """, (today,))
        compliance = cursor.fetchone()
        if compliance['total'] and compliance['total'] > 0:
            lengkap = compliance['lengkap'] if compliance['lengkap'] else 0
            compliance_rate = round((lengkap / compliance['total']) * 100, 1)
        else:
            compliance_rate = 100.0

        # Pelanggaran hari ini (CCTV + Gerbang)
        cursor.execute(
            "SELECT COUNT(*) as total FROM pelanggaran_cctv WHERE DATE(waktu_pelanggaran) = %s",
            (today,)
        )
        pelanggaran_cctv = cursor.fetchone()['total']

        cursor.execute(
            "SELECT COUNT(*) as total FROM riwayat_gerbang WHERE DATE(waktu) = %s AND status_apd = 'tidak_lengkap'",
            (today,)
        )
        pelanggaran_gerbang = cursor.fetchone()['total']

        pelanggaran_hari_ini = pelanggaran_cctv + pelanggaran_gerbang

        # Absensi 7 hari terakhir (untuk chart)
        cursor.execute("""
            SELECT tanggal, COUNT(*) as total
            FROM absensi
            WHERE tanggal >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY tanggal
            ORDER BY tanggal
        """)
        absensi_chart = cursor.fetchall()

        # Pelanggaran 7 hari terakhir (untuk chart) — gabungan CCTV + gerbang
        cursor.execute("""
            SELECT tanggal, SUM(total) as total FROM (
                (SELECT DATE(waktu_pelanggaran) as tanggal, COUNT(*) as total
                 FROM pelanggaran_cctv
                 WHERE waktu_pelanggaran >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                 GROUP BY DATE(waktu_pelanggaran))
                UNION ALL
                (SELECT DATE(waktu) as tanggal, COUNT(*) as total
                 FROM riwayat_gerbang
                 WHERE waktu >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                   AND status_apd = 'tidak_lengkap'
                 GROUP BY DATE(waktu))
            ) combined
            GROUP BY tanggal
            ORDER BY tanggal
        """)
        pelanggaran_chart = cursor.fetchall()

        # Recent activity (10 terbaru)
        cursor.execute("""
            (SELECT 'absensi' as tipe, nama_pegawai, waktu_masuk as waktu,
                    status_apd as detail
             FROM absensi ORDER BY waktu_masuk DESC LIMIT 5)
            UNION ALL
            (SELECT 'pelanggaran' as tipe, nama_pegawai, waktu_pelanggaran as waktu,
                    apd_dilepas as detail
             FROM pelanggaran_cctv ORDER BY waktu_pelanggaran DESC LIMIT 5)
            ORDER BY waktu DESC LIMIT 10
        """)
        recent_activity = cursor.fetchall()

        cursor.close()
        conn.close()

        return {
            'total_pegawai': total_pegawai,
            'absensi_hari_ini': absensi_hari_ini,
            'compliance_rate': compliance_rate,
            'pelanggaran_hari_ini': pelanggaran_hari_ini,
            'absensi_chart': absensi_chart,
            'pelanggaran_chart': pelanggaran_chart,
            'recent_activity': recent_activity
        }

    def get_all_pegawai(self):
        """Ambil semua data pegawai dengan statistik."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.*,
                (SELECT COUNT(*) FROM absensi WHERE pegawai_id = p.id) as total_absensi,
                (SELECT COUNT(*) FROM pelanggaran_cctv WHERE pegawai_id = p.id) as total_pelanggaran,
                (SELECT COUNT(*) FROM riwayat_gerbang WHERE pegawai_id = p.id
                    AND status_apd = 'tidak_lengkap') as total_pelanggaran_gerbang
            FROM pegawai p ORDER BY p.nama
        """)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results

    def get_nama_pegawai_list(self):
        """Ambil daftar nama pegawai untuk dropdown filter."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT nama FROM pegawai ORDER BY nama")
        results = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return results

    # ============================================================
    #  RFID & AKSES RUANGAN
    # ============================================================

    def get_pegawai_by_rfid(self, rfid_uid):
        """Cari pegawai berdasarkan RFID UID."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM pegawai WHERE rfid_uid = %s", (rfid_uid,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result

    def set_pegawai_rfid(self, pegawai_id, rfid_uid):
        """Assign RFID UID ke pegawai. Returns True jika berhasil."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE pegawai SET rfid_uid = %s WHERE id = %s",
                (rfid_uid, pegawai_id)
            )
            conn.commit()
            success = cursor.rowcount > 0
        except Error as e:
            print(f"   ❌ Gagal set RFID: {e}")
            success = False
        cursor.close()
        conn.close()
        return success

    def get_ruangan_by_reader(self, reader_id):
        """Cari ruangan berdasarkan reader_id."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM ruangan WHERE reader_id = %s", (reader_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result

    def get_ruangan_by_id(self, ruangan_id):
        """Ambil data ruangan berdasarkan ID."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM ruangan WHERE id = %s", (ruangan_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result

    def get_default_ruangan(self):
        """Ambil ruangan default (pertama)."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM ruangan ORDER BY id LIMIT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result

    def catat_akses_ruangan(self, pegawai_id, ruangan_id, rfid_uid, aksi,
                            status_apd=None, alasan_tolak=None):
        """Catat event akses ruangan (IN/OUT/DENIED)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO akses_ruangan
                (pegawai_id, ruangan_id, rfid_uid, aksi, status_apd, alasan_tolak)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (pegawai_id, ruangan_id, rfid_uid, aksi, status_apd, alasan_tolak))
        conn.commit()
        insert_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return insert_id

    def get_last_akses(self, pegawai_id, ruangan_id):
        """Ambil akses terakhir (IN/OUT) pegawai di ruangan tertentu."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM akses_ruangan
            WHERE pegawai_id = %s AND ruangan_id = %s AND aksi IN ('IN', 'OUT')
            ORDER BY waktu DESC LIMIT 1
        """, (pegawai_id, ruangan_id))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result

    def get_presence(self, ruangan_id=None):
        """
        Ambil daftar pegawai yang saat ini berada di dalam ruangan.
        Logic: pegawai terakhir IN dan belum OUT.
        """
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT
                p.id as pegawai_id,
                p.nama,
                p.rfid_uid,
                a.waktu as waktu_masuk,
                a.status_apd,
                r.nama as nama_ruangan,
                r.kode as kode_ruangan
            FROM akses_ruangan a
            INNER JOIN pegawai p ON a.pegawai_id = p.id
            INNER JOIN ruangan r ON a.ruangan_id = r.id
            WHERE a.aksi = 'IN'
              AND a.id = (
                  SELECT a2.id FROM akses_ruangan a2
                  WHERE a2.pegawai_id = a.pegawai_id
                    AND a2.ruangan_id = a.ruangan_id
                    AND a2.aksi IN ('IN', 'OUT')
                  ORDER BY a2.waktu DESC LIMIT 1
              )
        """
        params = []
        if ruangan_id:
            query += " AND a.ruangan_id = %s"
            params.append(ruangan_id)

        query += " ORDER BY a.waktu DESC"
        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results

    def get_akses_history(self, ruangan_id=None, tanggal=None, limit=50, offset=0):
        """Ambil riwayat akses ruangan (untuk timeline)."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT
                a.*,
                p.nama as nama_pegawai,
                r.nama as nama_ruangan,
                r.kode as kode_ruangan
            FROM akses_ruangan a
            LEFT JOIN pegawai p ON a.pegawai_id = p.id
            LEFT JOIN ruangan r ON a.ruangan_id = r.id
            WHERE 1=1
        """
        params = []

        if ruangan_id:
            query += " AND a.ruangan_id = %s"
            params.append(ruangan_id)

        if tanggal:
            query += " AND DATE(a.waktu) = %s"
            params.append(tanggal)
        else:
            query += " AND DATE(a.waktu) = CURDATE()"

        query += " ORDER BY a.waktu DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results

    def get_akses_history_count(self, ruangan_id=None, tanggal=None):
        """Hitung total riwayat akses ruangan."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT COUNT(*) FROM akses_ruangan WHERE 1=1"
        params = []

        if ruangan_id:
            query += " AND ruangan_id = %s"
            params.append(ruangan_id)

        if tanggal:
            query += " AND DATE(waktu) = %s"
            params.append(tanggal)
        else:
            query += " AND DATE(waktu) = CURDATE()"

        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count

    def get_room_stats(self):
        """Ambil statistik ruangan untuk dashboard."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        # Jumlah orang di dalam ruangan saat ini
        presence = self.get_presence()
        total_dalam_ruangan = len(presence)

        # Total akses hari ini
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT COUNT(*) as total FROM akses_ruangan WHERE DATE(waktu) = %s AND aksi IN ('IN', 'OUT')",
            (today,)
        )
        total_akses_hari_ini = cursor.fetchone()['total']

        # Total ditolak hari ini
        cursor.execute(
            "SELECT COUNT(*) as total FROM akses_ruangan WHERE DATE(waktu) = %s AND aksi = 'DENIED'",
            (today,)
        )
        total_ditolak_hari_ini = cursor.fetchone()['total']

        cursor.close()
        conn.close()

        return {
            'total_dalam_ruangan': total_dalam_ruangan,
            'total_akses_hari_ini': total_akses_hari_ini,
            'total_ditolak_hari_ini': total_ditolak_hari_ini,
            'presence': presence
        }
