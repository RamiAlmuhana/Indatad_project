FROM python:alpine

WORKDIR /app

COPY main.py .

CMD ["sh", "-c", "python3 main.py"]