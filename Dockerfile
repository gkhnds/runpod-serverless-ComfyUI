# 1. Base Image (PyTorch ve CUDA zaten var)
FROM runpod/pytorch:2.2.1-py3.10-cuda12.1.1-devel-ubuntu22.04

# Sistem ayarları
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Çalışma dizini
WORKDIR /

# ComfyUI'yi indir
RUN git clone https://github.com/comfyanonymous/ComfyUI.git

# ComfyUI içine gir
WORKDIR /ComfyUI

# --- KRİTİK DÜZELTME BAŞLANGICI ---
# 1. Ağır topları (torch, torchvision, torchaudio) listeden çıkarıyoruz.
#    Böylece 3GB indirmekle uğraşmaz, base image'dakini kullanır.
RUN sed -i '/^torch$/d' requirements.txt
RUN sed -i '/torchvision/d' requirements.txt
RUN sed -i '/torchaudio/d' requirements.txt

# 2. AMA "torchsde" listede kalsın! (Önceki hatamız buydu)
#    Eğer requirements.txt içinde silindiyse bile elle kurmayı garantiye alalım.
RUN pip install torchsde

# 3. Geri kalan hafif bağımlılıkları kur (transformers, numpy vb.)
RUN pip install --no-cache-dir -r requirements.txt

# 4. RunPod ve R2 için gerekli ekstralar
RUN pip install --no-cache-dir runpod boto3 requests
# --- KRİTİK DÜZELTME BİTİŞİ ---

# Dosyalarımızı kopyala
COPY handler.py .
COPY workflow.json .
COPY extra_model_paths.yaml .

# Modellerin yerini göster
ENV COMFYUI_PATH_CONFIG=/ComfyUI/extra_model_paths.yaml

# Başlat (Hata olursa görebilmek için sleep infinity modunda bırakabilirsin, 
# ama sistemin çalışacağından eminsen handler'ı açabilirsin. 
# Şimdilik crash riskine karşı 'sleep' modunda tutup, active olunca handler'ı elle tetikleyelim)
CMD ["python", "-u", "handler.py"]