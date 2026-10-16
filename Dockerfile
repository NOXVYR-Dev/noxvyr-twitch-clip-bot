FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 DB_PATH=/data/bot.sqlite3
WORKDIR /app
COPY bot.py /app/bot.py
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 bot \
    && mkdir -p /data \
    && chown bot:bot /data
CMD ["sh", "-c", "chown -R bot:bot /data && exec su -s /bin/sh bot -c 'python /app/bot.py'"]
