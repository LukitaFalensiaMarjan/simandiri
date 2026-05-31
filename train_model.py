from ultralytics import YOLO
import torch
import os

def main():
    print("=" * 70)
    print("  TRAINING MODEL APD - SIMANDIRI")
    print("=" * 70)

    # Deteksi GPU
    if torch.cuda.is_available():
        device = 0
        gpu_name = torch.cuda.get_device_name(0)
        print(f"\n🚀 GPU Terdeteksi: {gpu_name}")
    else:
        device = 'cpu'
        print("\n⚠️  GPU tidak terdeteksi, menggunakan CPU (lebih lambat)")

    # Pilih mode training
    print("\n📋 PILIH MODE TRAINING:")
    print("   1. Fine-tune dari model yang sudah ada (DIREKOMENDASIKAN)")
    print("      → Lebih cepat, mempertahankan pengetahuan yang sudah dipelajari")
    print("   2. Training dari awal (YOLOv8s pretrained COCO)")
    print("      → Lebih lama, tapi bisa lebih baik jika model lama bermasalah")
    
    pilihan = input("\nPilihan (1/2): ").strip()
    
    if pilihan == "1":
        model_path = "runs/detect/simandiri_apd_model_final/weights/best.pt"
        if not os.path.exists(model_path):
            print(f"\n❌ Model '{model_path}' tidak ditemukan!")
            print("   Menggunakan YOLOv8s pretrained sebagai gantinya...")
            model_path = "yolov8s.pt"
        else:
            print(f"\n✅ Fine-tune dari: {model_path}")
    else:
        model_path = "yolov8s.pt"
        print(f"\n✅ Training dari: {model_path}")

    # Konfigurasi training
    epochs = 200
    batch_size = 16 if device != 'cpu' else 8
    img_size = 640

    print(f"\n⚙️  KONFIGURASI:")
    print(f"   Model     : {model_path}")
    print(f"   Dataset   : dataset_apd/data.yaml")
    print(f"   Epochs    : {epochs}")
    print(f"   Batch     : {batch_size}")
    print(f"   Image Size: {img_size}")
    print(f"   Device    : {device}")
    print(f"   Kelas     : baju, celana, helm, sepatu")
    print(f"\n   ⏱️  Estimasi waktu:")
    if device != 'cpu':
        print(f"      GPU: ~30-60 menit")
    else:
        print(f"      CPU: ~2-4 jam")
    print("=" * 70)

    confirm = input("\nMulai training? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ Training dibatalkan.")
        return

    print("\n📦 Memuat model...")
    model = YOLO(model_path)

    print("\n🚀 Memulai training...")
    print("=" * 70)

    results = model.train(
        data="dataset_apd/data.yaml",
        epochs=epochs,
        imgsz=img_size,
        batch=batch_size,
        patience=40,
        save=True,
        device=device,
        workers=4,
        name="simandiri_apd_v2",
        exist_ok=True,
        pretrained=True,
        optimizer='AdamW',
        verbose=True,
        
        # Learning rate
        lr0=0.001,
        lrf=0.0001,
        cos_lr=True,
        warmup_epochs=5,
        
        # Loss weights - boost classification loss for better APD distinction
        cls=1.0,
        box=7.5,
        
        # Augmentation - lebih agresif untuk dataset kecil
        mosaic=1.0,
        mixup=0.15,
        copy_paste=0.1,
        degrees=10.0,
        translate=0.2,
        scale=0.5,
        shear=5.0,
        flipud=0.0,
        fliplr=0.5,
        hsv_h=0.02,
        hsv_s=0.7,
        hsv_v=0.4,
        erasing=0.3,
    )

    print("\n" + "=" * 70)
    print("✅ TRAINING SELESAI!")
    print("=" * 70)
    print("\n📁 Model baru tersimpan di:")
    print("   runs/detect/simandiri_apd_v2/weights/best.pt")
    print("\n🎯 Untuk menggunakan model baru:")
    print("   1. Update path model di main_simandiri.py (line 16):")
    print('      model_yolo = YOLO("runs/detect/simandiri_apd_v2/weights/best.pt")')
    print("   2. Jalankan: python main_simandiri.py")
    print("=" * 70)

if __name__ == '__main__':
    main()
