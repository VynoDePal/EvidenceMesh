FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/evidencemesh

WORKDIR /build
RUN python -m pip install "uv==0.11.33"
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync \
    --frozen \
    --no-dev \
    --no-editable \
    --python /usr/local/bin/python

FROM python:3.12-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/evidencemesh/bin:$PATH"

RUN useradd --create-home --uid 10001 evidencemesh
COPY --from=builder --chown=evidencemesh:evidencemesh /opt/evidencemesh /opt/evidencemesh

USER evidencemesh
WORKDIR /home/evidencemesh
EXPOSE 8000
ENTRYPOINT ["evidencemesh"]
CMD ["serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
