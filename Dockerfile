FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV DATA_SOURCE=csv
ENV RAW_DATA_DIR=/app/data/raw
ENV PROCESSED_DATA_DIR=/app/data/processed
ENV APP_AUTO_RUN_PIPELINE_ON_START=1
ENV VALIDATION_MODE=warn

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY . /app

EXPOSE 8501

CMD ["sh", "-c", "python -m python.webapp.run_server --host 0.0.0.0 --port ${PORT:-8501}"]
