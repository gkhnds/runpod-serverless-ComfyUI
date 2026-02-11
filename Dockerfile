# Daha stabil ve hazır bir Pytorch/CUDA imajı kullanıyoruz
FROM runpod/pytorch:2.2.1-py3.10-cuda12.1.1-devel-ubuntu22.04

# Sistem paketlerini güncelle ve git kur
RUN apt-get update && apt-get install -y git

# ComfyUI kurulumu
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /ComfyUI
WORKDIR /ComfyUI

# Bağımlılıkları kur
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install runpod boto3

# Kendi dosyalarımızı kopyala
COPY handler.py /ComfyUI/handler.py
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml

# Modelleri volume'dan okuması için yapılandırma dosyası yolu
ENV COMFYUI_PATH_CONFIG=/ComfyUI/extra_model_paths.yaml

# Uygulamayı başlat
CMD ["python", "-u", "handler.py"]
