FROM python:alpine
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app

COPY main.py .

CMD ["sh", "-c", "python3 main.py"]