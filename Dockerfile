FROM python:3.11-slim AS base

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[dev]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.interfaces.api:app", "--host", "0.0.0.0", "--port", "8000"]
