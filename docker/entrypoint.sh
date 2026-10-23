#!/bin/sh
set -e
mkdir -p /app/data/uploads /app/data/outputs
python manage.py migrate --noinput
if [ "$1" = "scheduler" ]; then
  exec python manage.py run_scheduler
else
  exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 180
fi
