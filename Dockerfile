FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libudev1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY meshcore_monitor.py .
COPY known_nodes.json .
COPY .env.example .

ENV PYTHONUNBUFFERED=1

CMD ["python3", "meshcore_monitor.py"]