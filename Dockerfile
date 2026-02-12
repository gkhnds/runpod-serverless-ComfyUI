# Base Image: PyTorch ve CUDA hazır geliyor.
FROM runpod/pytorch:2.2.1-py3.10-cuda12.1.1-devel-ubuntu22.04

# Sistem ayarları
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Çalışma dizinine geç
WORKDIR /

# ComfyUI'yi indir
RUN git clone https://github.com/comfyanonymous/ComfyUI.git

# ComfyUI içine gir
WORKDIR /ComfyUI

# SADECE bizim için gerekli olanları kuruyoruz. 
# Base image'daki PyTorch'a güveniyoruz, tekrar indirmiyoruz.
RUN pip install --no-cache-dir runpod boto3 requests

# Bizim dosyalarımızı içeri kopyala
COPY handler.py .
COPY workflow.json .
COPY extra_model_paths.yaml .

# Modellerin nerede olduğunu sisteme bildir
ENV COMFYUI_PATH_CONFIG=/ComfyUI/extra_model_paths.yaml

# Başlat
CMD ["python", "-u", "handler.py"]