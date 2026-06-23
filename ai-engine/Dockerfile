FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies only (keeps image lean and rebuilds faster)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV UVICORN_HOST=0.0.0.0
ENV UVICORN_PORT=8000

EXPOSE 8000

CMD ["python", "main.py"]
