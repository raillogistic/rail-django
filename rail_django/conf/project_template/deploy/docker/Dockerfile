###########
# BUILDER #
###########

# pull official base image
FROM python:3.8-slim as builder

# set work directory
WORKDIR /app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_PROGRESS_BAR=off

# install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev git && \
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

# pull official base image
FROM python:3.8-slim

# create directory for the app user
RUN mkdir -p /home/app

# create the app user
RUN addgroup --system app && adduser --system --group app

# create the appropriate directories
ENV HOME=/home/app
ENV APP_HOME=/home/app/web
RUN mkdir $APP_HOME
RUN mkdir $APP_HOME/staticfiles
RUN mkdir $APP_HOME/mediafiles
WORKDIR $APP_HOME

# install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 netcat-openbsd && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements/ requirements/
RUN pip install --no-cache --no-index /wheels/*

# copy entrypoint.sh
COPY deploy/docker/entrypoint.sh $APP_HOME/entrypoint.sh
RUN sed -i 's/\r$//g' $APP_HOME/entrypoint.sh
RUN chmod +x $APP_HOME/entrypoint.sh

# copy project
COPY . $APP_HOME

# chown all the files to the app user
RUN chown -R app:app $APP_HOME

# change to the app user
USER app

# run entrypoint.sh
ENTRYPOINT ["/home/app/web/entrypoint.sh"]
