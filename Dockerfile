FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Africa/Lagos \
    STATE_PATH=/data/cron_state.json

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py /app/

RUN mkdir -p /data
VOLUME ["/data"]

# Default: tick-loop email+Slack reminders.
# Coolify Scheduled Tasks override this CMD with `python <script>.py` for Telegram crons.
CMD ["python3", "/app/cron_reminders.py"]
