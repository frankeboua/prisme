FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PRISME_MODE=public PRISME_DB=/data/prisme.db
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY database/schema.sql ./database/schema.sql
COPY web ./web
COPY server.py wsgi.py ./
RUN mkdir -p /data && useradd -r prisme && chown -R prisme /data
USER prisme
CMD ["sh", "-c", "exec gunicorn wsgi:application --workers 1 --threads 8 --timeout 120 --bind 0.0.0.0:${PORT:-8000} --access-logfile -"]
