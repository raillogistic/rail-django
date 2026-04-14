###########
# BUILDER #
###########

# Python 3.12 — ~10-15% faster startup and runtime vs 3.11
# (specialized adaptive interpreter, comprehension inlining, immortal objects)
FROM python:3.12-slim AS builder

# set work directory
WORKDIR /app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_PROGRESS_BAR=off

# install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential git libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# install dependencies
COPY requirements/ requirements/
RUN pip install --upgrade pip
RUN mkdir -p /app/wheels
RUN if [ -d requirements/wheels ] && [ "$(ls -A requirements/wheels)" ]; then \
        cp -r requirements/wheels/. /app/wheels; \
    else \
        success=; \
        for attempt in 1 2 3 4 5; do \
            if pip wheel --wheel-dir /app/wheels -r requirements/prod.txt; then \
                success=1; \
                break; \
            fi; \
            echo "pip wheel failed (attempt ${attempt}); retrying in 5s..." >&2; \
            sleep 5; \
        done; \
        if [ -z "$success" ]; then \
            echo "pip wheel failed after 5 attempts." >&2; \
            exit 1; \
        fi; \
    fi


#########
# FINAL #
#########

# Python 3.12 — match builder stage
FROM python:3.12-slim

# set runtime environment variables
ENV PYTHONDONTWRITEBYTECODE=0 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONOPTIMIZE=1

# create directory for the app user
RUN mkdir -p /home/app

# create the app user
RUN addgroup --system app && adduser --system --group app

# create the appropriate directories
ENV HOME=/home/app
ENV APP_HOME=/home/app/web
RUN mkdir -p $APP_HOME/staticfiles $APP_HOME/mediafiles $APP_HOME/logs $APP_HOME/cache
WORKDIR $APP_HOME

# install runtime dependencies (no build tools in final image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libpq5 \
    libaio1t64 \
    netcat-openbsd \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libffi8 \
    curl \
    && \
    if [ ! -e /usr/lib/x86_64-linux-gnu/libaio.so.1 ] && [ -e /usr/lib/x86_64-linux-gnu/libaio.so.1t64 ]; then \
      ln -s /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1; \
    fi \
    && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir --no-index /wheels/*

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/rail-django.txt

# copy entrypoint.sh
COPY deploy/docker/entrypoint.sh $APP_HOME/entrypoint.sh
RUN sed -i 's/\r$//' $APP_HOME/entrypoint.sh
RUN chmod +x $APP_HOME/entrypoint.sh

# copy project
COPY . $APP_HOME

# Precompile Python bytecode — eliminates first-import compilation penalty.
# This shaves ~200-500ms off cold-start per module and reduces runtime CPU spikes.
RUN python -m compileall -q -j 0 \
    $APP_HOME/root \
    $APP_HOME/apps \
    $(python -c "import site; print(site.getsitepackages()[0])") \
    2>/dev/null || true

# Clean up unnecessary files copied from context
RUN rm -rf $APP_HOME/.env.* \
    $APP_HOME/.git \
    $APP_HOME/db.sqlite3* \
    2>/dev/null || true

# chown all the files to the app user
RUN chown -R app:app $APP_HOME

# change to the app user
USER app

# expose app port
EXPOSE 8000

# run entrypoint.sh
ENTRYPOINT ["/home/app/web/entrypoint.sh"]
