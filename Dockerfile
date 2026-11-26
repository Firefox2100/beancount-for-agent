FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# The version comes from git, which the build context does not carry.
ARG VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION} UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim
RUN useradd --create-home --uid 1000 app && mkdir /data && chown app /data
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    BEANCOUNT_MCP_DATA_DIR=/data \
    BEANCOUNT_MCP_HOST=0.0.0.0 \
    BEANCOUNT_MCP_PORT=8000
USER app
VOLUME /data
EXPOSE 8000
CMD ["beancount-mcp"]
