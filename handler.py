import runpod
import json
import os

def handler(job):
    job_input = job['input']
    workflow_name = job_input.get("workflow", "default.json")
    workflow_path = f"/workspace/workflows/{workflow_name}"

    if not os.path.exists(workflow_path):
        return {"error": f"Workflow dosyası bulunamadı: {workflow_path}"}

    with open(workflow_path, 'r') as f:
        workflow = json.load(f)

    # Burada ComfyUI API'sine gönderim yapılacak (Detayları kurulumda netleştiririz)
    return {"status": "success", "message": "Workflow yuklendi!"}

runpod.serverless.start({"handler": handler})
