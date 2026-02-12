# 1. Base Image (Zaten içinde PyTorch ve CUDA var)
FROM runpod/pytorch:2.2.1-py3.10-cuda12.1.1-devel-ubuntu22.04

# 2. Sistem güncellemeleri
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y git && apt-get clean && rm -rf /var/lib/apt/lists/*

# 3. ComfyUI'yi İndir
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /ComfyUI

# 4. Çalışma Dizinini Ayarla
WORKDIR /ComfyUI

# 5. KRİTİK ADIM: Ağır kütüphaneleri requirements.txt içinden siliyoruz.
# Çünkü bunlar zaten base image içinde var. Tekrar indirip build'i dondurmasın.
RUN sed -i '/torch/d' requirements.txt
RUN sed -i '/torchvision/d' requirements.txt
RUN sed -i '/torchaudio/d' requirements.txt
RUN sed -i '/numpy/d' requirements.txt

# 6. Geri kalan hafif bağımlılıkları ve BOTO3'ü kur
# --no-cache-dir sayesinde disk şişmez, hızlı kurulur.
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir runpod boto3 requests

# 7. Senin dosyalarını kopyala
COPY handler.py /ComfyUI/handler.py
COPY workflow.json /ComfyUI/workflow.json
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml

# 8. Modelleri volume'dan okuması için yol ayarı
ENV COMFYUI_PATH_CONFIG=/ComfyUI/extra_model_paths.yaml

# 9. Başlat
CMD ["python", "-u", "handler.py"]
