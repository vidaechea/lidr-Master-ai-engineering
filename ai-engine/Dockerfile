FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Install dependencies from pyproject.toml (no dev extras)
COPY pyproject.toml .
RUN uv pip install --system --no-cache -e .

COPY . .

ENV UVICORN_HOST=0.0.0.0
ENV UVICORN_PORT=8000

EXPOSE 8000

CMD ["python", "main.py"]
