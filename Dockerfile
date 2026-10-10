FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Africa/Johannesburg
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
# ONE worker on purpose: the app keeps its live data in memory (and writes through to Firestore),
# so a second worker would show a different set of cases. Threads give the concurrency.
CMD exec gunicorn --workers 1 --threads 8 --timeout 60 --bind :${PORT:-8080} app:app
