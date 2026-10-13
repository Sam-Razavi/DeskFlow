FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
# The code stays owned by root and is only readable by the app user: nothing here needs to write to
# it, so even a compromised process cannot modify the application.
RUN chmod +x start.sh && useradd --system --uid 10001 --no-create-home app
ENV PATH="/app/.venv/bin:$PATH"

# Nothing here needs root, so a compromised process does not get it either.
USER app

EXPOSE 8000
CMD ["./start.sh"]
