# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY . .

ENV UVICORN_HOST=0.0.0.0
ENV UVICORN_PORT=8000

EXPOSE 8000

CMD ["python", "main.py"]
