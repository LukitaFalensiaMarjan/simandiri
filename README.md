# SIMANDIRI - Sistem Keamanan Mandiri & Terintegrasi

SIMANDIRI adalah purwarupa sistem keamanan industri cerdas berbasis *Internet of Things* (IoT) dan *Artificial Intelligence* (AI). Sistem ini dirancang untuk memastikan kedisiplinan dan keselamatan kerja pegawai melalui verifikasi identitas ganda (RFID + Pengenalan Wajah) serta inspeksi Alat Pelindung Diri (APD) secara otomatis menggunakan teknologi *Computer Vision*.

## Fitur Utama

- **Verifikasi Ganda**: Kombinasi pembacaan kartu RFID (Mifare) dan pemindaian biometrik (Face Recognition) untuk mencegah kecurangan absensi.
- **Inspeksi K3 Otomatis**: Mendeteksi kelengkapan APD (khususnya helm) secara *real-time* menggunakan model *Deep Learning* YOLOv8.
- **Sistem Gerbang Terintegrasi**: Mengontrol akses pintu fisik (solenoid lock) melalui ESP32 yang terhubung ke server via protokol MQTT.
- **Pemantauan CCTV Indoor**: Pemantauan area kerja secara terus-menerus untuk mendeteksi pegawai yang melepaskan APD saat bekerja, dilengkapi dengan teguran audio otomatis.
- **Web Dashboard**: Antarmuka berbasis web (Flask) untuk mengelola data pegawai, memantau riwayat absensi, melihat log pelanggaran, dan memantau *live streaming* kamera.
- **Feedback Interaktif**: Layar sentuh HMI (Nextion TFT) dan umpan balik suara (*Text-to-Speech*) dalam bahasa Indonesia untuk memandu pengguna.

---

## Arsitektur Sistem

Sistem ini terdiri dari beberapa komponen utama:

1. **IoT Edge Node (`arduino/esp32_gerbang/esp32_gerbang.ino`)**
   - Perangkat keras: ESP32, RFID-RC522, Nextion TFT, Solenoid Door Lock (via Relay), Buzzer.
   - Fungsi: Membaca UID RFID, mengirimkan data tap ke server via MQTT, mengontrol penguncian fisik, dan memperbarui antarmuka layar Nextion.

2. **Server Pemroses Utama (`main_simandiri.py`)**
   - Fungsi: Mendengarkan permintaan akses dari MQTT, memvalidasi identitas dengan basis data, mengaktifkan kamera gerbang untuk pengenalan wajah dan pengecekan APD dengan YOLOv8, serta mengirim balik perintah buka/tutup pintu.

3. **CCTV Pemantau Ruangan (`cctv_monitor.py`)**
   - Fungsi: Kamera pengawas pasif yang terus memindai area kerja. Jika ada pegawai terdaftar yang tidak mengenakan APD, sistem akan memberikan teguran suara otomatis dan mencatat pelanggaran ke basis data.

4. **Web Dashboard (`web/app.py`)**
   - Fungsi: Panel administrasi untuk memantau status operasional secara keseluruhan, manajemen pegawai, rekap absensi harian, dan menampilkan aliran video dari kamera gerbang maupun CCTV.

5. **Database & Konfigurasi (`database.py` & `config.py`)**
   - Fungsi: Pengelolaan penyimpanan data absensi, log pelanggaran, data identitas di MySQL, serta pengaturan variabel sistem (kredensial, IP kamera, dll).

---

## Prasyarat Lingkungan (Requirements)

- **Hardware**: Komputer/Laptop Server (minimum 4GB RAM, CPU 2-core), Webcam eksternal/internal, ESP32 beserta komponen pendukung.
- **Software**: 
  - Python 3.8+
  - MySQL Server (XAMPP / MariaDB)
  - Modul Python (dapat diinstal melalui `requirements.txt`)

### Instalasi Dependencies

```bash
pip install -r requirements.txt
```

*(Catatan untuk pengguna Windows: Jika library `dlib` untuk `face_recognition` gagal diinstal, silakan unduh wheel pre-compiled yang sesuai dengan versi Python Anda).*

---

## Cara Penggunaan

### 1. Persiapan Database
1. Pastikan layanan MySQL Anda berjalan.
2. Skrip Python akan secara otomatis membuat basis data `simandiri_db` dan melakukan migrasi tabel yang diperlukan saat dijalankan pertama kali.

### 2. Mengisi Dataset Wajah
1. Masukkan foto wajah pegawai ke dalam folder `dataset_wajah/[nama_pegawai]/`.
2. Format gambar yang disarankan adalah JPG/JPEG dengan wajah terlihat jelas. Sistem akan mengekstrak pola wajah dari foto-foto ini.

### 3. Menjalankan Server Web (Dashboard)
Jalankan aplikasi Flask untuk membuka antarmuka pemantauan:
```bash
python web/app.py
```
Akses dashboard melalui peramban di `http://localhost:5000`.

### 4. Menjalankan Node Gerbang Pintar (Gate)
Jalankan skrip utama pengendali gerbang:
```bash
python main_simandiri.py
```
Kamera akan aktif. Saat pegawai melakukan *tap* RFID, skrip akan memindai wajah dan helm, kemudian memberikan instruksi akses ke ESP32.

### 5. Menjalankan CCTV Indoor
Buka jendela terminal baru dan jalankan:
```bash
python cctv_monitor.py
```
CCTV akan aktif dan secara pasif memantau pelanggaran APD di area kerja.

### 6. Node ESP32 (Hardware)
1. Unggah kode `arduino/esp32_gerbang/esp32_gerbang.ino` ke papan ESP32 menggunakan Arduino IDE.
2. Pastikan kredensial Wi-Fi dan pengaturan MQTT Broker (secara bawaan menggunakan `broker.emqx.io`) sesuai dengan `config.py` pada server Python.

---

## Pengaturan (Configuration)
Seluruh variabel operasional dapat disesuaikan di `config.py`, meliputi:
- Konfigurasi koneksi MySQL
- Pemilihan indeks kamera (Webcam)
- Toleransi *Face Recognition* dan model YOLOv8
- Broker MQTT (Host, Port, dan Topik)
- Pengaturan waktu absensi (Shift)

---

## Troubleshooting

- **Sensor RFID (RC522) Freeze / Berhenti Membaca**: Sering kali terjadi akibat induksi elektromagnetik (EMI) dari pergerakan solenoid. Solusi telah diterapkan pada kode ESP32 dengan melakukan *re-initialization* (`rfid.PCD_Init()`) secara otomatis. Jika masalah berlanjut, pisahkan sumber daya (VCC) relay solenoid dari suplai utama ESP32.
- **Wajah Tidak Terdeteksi**: Pastikan resolusi kamera memadai dan pencahayaan ruangan optimal. Sesuaikan nilai `FACE_TOLERANCE` di `config.py` jika sistem terlalu sensitif.
- **Gagal Terhubung ke MQTT**: Jika menemui *Error rc=-2*, kemungkinan ISP atau jaringan hotspot Anda memblokir lalu lintas port MQTT (1883). Gunakan jaringan alternatif.

---

**Dikembangkan untuk keperluan purwarupa inovasi keselamatan kerja cerdas (SIMANDIRI).**
