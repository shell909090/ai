FROM python:3.11-slim

WORKDIR /app

RUN pip install uv --no-cache-dir

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra dev

COPY little_agent/ little_agent/
COPY tests/ tests/

CMD ["uv", "run", "pytest", "tests/", "-v", "--timeout=60"]
