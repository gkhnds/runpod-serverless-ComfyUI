FROM runpod/ai-container-base:latest

# ComfyUI kurulumu
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /ComfyUI
WORKDIR /ComfyUI
RUN pip install -r requirements.txt

# RunPod Handler ve bağımlılıkları
RUN pip install runpod
COPY handler.py /ComfyUI/handler.py
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml

# Modelleri Volume'dan okuması için yol gösteriyoruz
ENV COMFYUI_PATH_CONFIG=/ComfyUI/extra_model_paths.yaml

CMD ["python", "-u", "handler.py"]
