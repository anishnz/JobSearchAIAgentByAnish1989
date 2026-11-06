# JobSearchAIAgentByAnish1989 Knowledge Base (RAG) service - Docker image (from CyberQuest)
# Started by docker-compose next to the website. Only the website can reach it
# (no port is published to the laptop). The embedding model is downloaded on the first
# start and kept in data/rag/hf, so later starts are fast and work offline.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RAG_DATA_DIR=/data \
    HF_HOME=/data/hf

WORKDIR /srv
COPY requirements.txt .
# CPU-only PyTorch first: a much smaller download than the default GPU build
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY job_search_knowledge_base_NZ.md .
ENV RAG_SEED_FILE=/srv/job_search_knowledge_base_NZ.md
RUN mkdir -p /data

EXPOSE 9000
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9000/health').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
