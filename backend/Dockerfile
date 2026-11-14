FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --system continuity && useradd --system --gid continuity --create-home continuity

COPY --chown=continuity:continuity . .
RUN mkdir -p /app/storage && chown -R continuity:continuity /app/storage

USER continuity

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
