FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.12-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 evidencemesh
COPY --from=builder /wheels /wheels
RUN python -m pip install /wheels/*.whl && rm -rf /wheels

USER evidencemesh
WORKDIR /home/evidencemesh
EXPOSE 8000
ENTRYPOINT ["evidencemesh"]
CMD ["serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
