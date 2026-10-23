FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Pacific/Auckland
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x docker/entrypoint.sh && python manage.py collectstatic --noinput
EXPOSE 8000
ENTRYPOINT ["sh", "docker/entrypoint.sh"]
