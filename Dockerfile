FROM runpod/pytorch:2.2.1-py3.10-cuda12.1.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /

RUN git clone https://github.com/comfyanonymous/ComfyUI.git

WORKDIR /ComfyUI

# ComfyUI bağımlılıklarını da kur (requirements.txt içinde torch hariç olanlar)
RUN pip install --no-cache-dir runpod boto3 requests

# ComfyUI kendi bağımlılıklarını da ister
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py .
COPY workflow.json .
COPY extra_model_paths.yaml .

ENV COMFYUI_PATH_CONFIG=/ComfyUI/extra_model_paths.yaml

# DÜZELTME: sleep infinity kaldırıldı
CMD ["python", "-u", "handler.py"]