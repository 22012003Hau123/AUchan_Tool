FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pin PyTorch 2.4.1 CPU — doclayout_yolo 0.0.4 inference breaks on PyTorch >= 2.6 CPU
RUN pip install --no-cache-dir torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8123
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8123"]
