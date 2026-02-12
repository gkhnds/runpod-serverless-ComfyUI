FROM runpod/pytorch:2.2.1-py3.10-cuda12.1.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /

RUN git clone https://github.com/comfyanonymous/ComfyUI.git

WORKDIR /ComfyUI

# torch* satırlarını atla, gerisini kur
RUN grep -vE "^torch" requirements.txt > requirements_notorch.txt && \
    pip install --no-cache-dir -r requirements_notorch.txt && \
    rm requirements_notorch.txt

# Handler bağımlılıkları (requests zaten requirements.txt'de var ama zarar vermez)
RUN pip install --no-cache-dir runpod boto3

COPY handler.py .
COPY workflow.json .
COPY extra_model_paths.yaml .

ENV COMFYUI_PATH_CONFIG=/ComfyUI/extra_model_paths.yaml

CMD ["python", "-u", "handler.py"]