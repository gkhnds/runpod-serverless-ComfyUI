# 1. Base Image: İçinde Python, CUDA ve PyTorch zaten var.
FROM runpod/pytorch:2.2.1-py3.10-cuda12.1.1-devel-ubuntu22.04

# 2. Sistem güncellemeleri ve Git kurulumu (Tek satırda yaparak katman tasarrufu sağlıyoruz)
RUN apt-get update && apt-get install -y git && apt-get clean && rm -rf /var/lib/apt/lists/*

# 3. ComfyUI'yi klonla
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /ComfyUI

# 4. Çalışma dizinini ayarla
WORKDIR /ComfyUI

# 5. Kritik Müdahale: requirements.txt içindeki "torch" satırlarını siliyoruz.
# Çünkü base imajda zaten var. Tekrar indirip sistemi kilitlemesin.
RUN sed -i '/torch/d' requirements.txt

# 6. Kalan hafif bağımlılıkları ve RunPod araçlarını kur
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir runpod boto3 requests

# 7. Kendi dosyalarımızı kopyala
COPY handler.py /ComfyUI/handler.py
COPY workflow.json /ComfyUI/workflow.json
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml

# 8. Modelleri volume'dan okuması için yol ayarı
ENV COMFYUI_PATH_CONFIG=/ComfyUI/extra_model_paths.yaml

# 9. Başlat
CMD ["python", "-u", "handler.py"]
