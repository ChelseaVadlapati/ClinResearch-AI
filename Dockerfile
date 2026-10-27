FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN --mount=type=secret,id=custom_ca \
    if [ -f /run/secrets/custom_ca ]; then export PIP_CERT=/run/secrets/custom_ca; fi; \
    pip install --require-hashes -r requirements.lock
COPY src ./src
RUN --mount=type=secret,id=custom_ca \
    if [ -f /run/secrets/custom_ca ]; then export PIP_CERT=/run/secrets/custom_ca; fi; \
    pip install --no-deps .
COPY tests/fixtures ./tests/fixtures
COPY configs ./configs
RUN mkdir -p /app/reports
CMD ["uvicorn", "clinresearch.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
