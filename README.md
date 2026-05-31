# 🚀 GuardVision IoT - Sistem Gerbang Cerdas

Sistem pengecekan kelengkapan APD (Helm) otomatis menggunakan AI dengan Face Recognition dan YOLOv8.

## 🎯 Fitur

- ✅ **Face Recognition** - Identifikasi pegawai dengan bounding box
- ✅ **YOLOv8 Detection** - Deteksi helm
- ✅ **Text-to-Speech** - Feedback suara Bahasa Indonesia
- ✅ **Stable Tracking** - History-based detection untuk mengurangi flickering
- ✅ **Real-time Monitoring** - Via webcam

---

## 📦 Instalasi

```bash
pip install -r requirements.txt
```

**Catatan Windows:** Jika `dlib` gagal install, download wheel dari [sini](https://github.com/z-mahmud22/Dlib_Windows_Python3.x)

---

## 🚀 Cara Menggunakan

### Jalankan Sistem

```bash
python main_simandiri.py
```

**Sistem akan:**
1. Mendeteksi wajah pegawai dari database
2. Menyapa pegawai
3. Mengecek apakah helm terdeteksi
4. Memberikan akses jika helm terdeteksi

Tekan `q` untuk keluar.

---

## 📁 Struktur Project

```
guardvision-iot/
├── main_simandiri.py          # ⭐ Aplikasi utama
├── train_yolo.py              # Training model (opsional)
├── test_webcam.py             # Test deteksi helm
├── requirements.txt           # Dependencies
├── README.md                  # File ini
│
├── dataset_apd/               # Dataset APD (YOLO format)
│   ├── data.yaml
│   ├── train/
│   ├── valid/
│   └── test/
│
├── dataset_wajah/             # Dataset wajah pegawai
│   ├── basit/
│   ├── chakim/
│   ├── ilham/
│   └── luki/
│
└── runs/detect/               # Model training
    └── simandiri_apd_model_final/
        └── weights/best.pt
```

---

## ⚙️ Konfigurasi

### APD yang Dicek

Sistem saat ini hanya mengecek: **HELM**

Jika helm terdeteksi → APD lengkap → Akses diberikan

### Parameter Deteksi

```python
conf=0.25              # Confidence threshold
iou=0.4                # IoU threshold
```

### Parameter Tracking

```python
HISTORY_THRESHOLD = 2  # Helm harus terdeteksi 2 frame berturut-turut
HISTORY_INCREMENT = 3  # Naik cepat saat terdeteksi
HISTORY_DECAY = 1      # Turun lambat saat tidak terdeteksi
```

---

## 🧪 Testing

### Test Deteksi Helm

```bash
python test_webcam.py
```

Test apakah helm terdeteksi dengan baik di webcam.

---

## 🎓 Training Model (Opsional)

Jika ingin training ulang model:

```bash
python train_yolo.py
```

- Durasi: 60-90 menit
- Model: YOLOv8s
- Output: `runs/detect/simandiri_apd_model_final/weights/best.pt`

Setelah training, update path model di `main_simandiri.py` line 13.

---

## 🔧 Troubleshooting

### Helm Tidak Terdeteksi?

**Solusi:**
1. Pastikan helm yang dipakai mirip dengan dataset training
2. Perbaiki lighting ruangan (harus cukup terang)
3. Turunkan confidence: `conf=0.20` di `main_simandiri.py`
4. Test dengan: `python test_webcam.py`

### Wajah Tidak Terdeteksi?

**Solusi:**
1. Pastikan folder `dataset_wajah/` terisi dengan benar
2. Setiap orang minimal 3-5 foto
3. Foto harus format JPG (bukan HEIC)

### Kotak Deteksi Flickering?

**Solusi:**
Edit `main_simandiri.py`:
```python
HISTORY_THRESHOLD = 3  # Naikkan untuk lebih stabil
```

---

## 📊 Spesifikasi Sistem

### Minimum Requirements
- Python 3.8+
- Webcam 480p
- RAM 4GB
- CPU 2 core

### Dependencies
- OpenCV
- Ultralytics YOLOv8
- face_recognition
- gTTS
- pygame

---

## 🎯 Workflow Sistem

1. **Deteksi Wajah** → Identifikasi pegawai dari database
2. **Sapaan** → Sistem menyapa pegawai
3. **Cek Helm** → Deteksi apakah helm terdeteksi
4. **Keputusan:**
   - ✅ Helm terdeteksi → "Terimakasih, silahkan masuk"
   - ❌ Helm tidak terdeteksi → "Silakan pakai helm terlebih dahulu"

---

## 📝 Catatan Penting

- **Dataset Wajah**: 4 pegawai (basit, chakim, ilham, luki)
- **Foto per Orang**: 5 foto untuk efisiensi loading
- **APD yang Dicek**: Hanya helm (sistem disederhanakan)
- **Model**: YOLOv8 custom trained dengan dataset APD

---

## 🎯 Status Project

- ✅ Face Recognition: **Berfungsi dengan bounding box**
- ✅ Deteksi Helm: **Berfungsi**
- ✅ Text-to-Speech: **Berfungsi (Bahasa Indonesia)**
- ✅ Stable Tracking: **Implemented**
- ✅ Sistem Sederhana: **Hanya cek helm**

---

## 📞 Support

Jika ada masalah:
1. Test dengan `python test_webcam.py`
2. Cek lighting ruangan
3. Pastikan helm yang dipakai mirip dengan dataset
4. Adjust confidence threshold jika perlu

---

**GuardVision IoT** 🛡️  
*Sistem Gerbang Cerdas dengan AI untuk Keselamatan Kerja*

**Sistem Sederhana - Hanya Cek Helm**
