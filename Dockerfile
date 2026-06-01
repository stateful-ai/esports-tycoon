FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ESPORTS_TYCOON_CONTENT_BACKEND=templated

WORKDIR /app

COPY pyproject.toml constraints.txt README.md ./
COPY esports_tycoon ./esports_tycoon
COPY saves ./saves

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir --constraint constraints.txt ".[web]"

EXPOSE 8765

CMD ["python", "-m", "esports_tycoon.web", "--host", "0.0.0.0", "--port", "8765", "--runs-dir", "/tmp/esports-tycoon-runs"]
