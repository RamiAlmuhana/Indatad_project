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
COPY popularity.py .
COPY kmeans_model.joblib .
COPY scaler.joblib .
COPY sentiment.py .
COPY bow_vectorizer.py .
COPY naive_bayes_model.py .

CMD ["sh", "-c", "python3 main.py && python3 popularity.py && python3 sentiment.py"]
