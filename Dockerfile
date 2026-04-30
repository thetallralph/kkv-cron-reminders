FROM python:3.12-slim

WORKDIR /app

# pas de deps externes — stdlib only
COPY cron_reminders.py /app/cron_reminders.py

RUN mkdir -p /data
VOLUME ["/data"]

ENV PYTHONUNBUFFERED=1
ENV STATE_PATH=/data/cron_state.json

CMD ["python3", "/app/cron_reminders.py"]
