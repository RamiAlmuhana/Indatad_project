FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    build-essential \
    python3-dev \
    wget \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

RUN pip install torch --extra-index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

CMD ["sh", "-c", "python3 main.py"]
