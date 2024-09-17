FROM python:3.10-bookworm

WORKDIR /app

COPY main.py .

CMD ["sh", "-c", "python3 main.py"]