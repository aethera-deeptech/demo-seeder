# The seeder uses only the standard library of Python, so there is nothing to install.
FROM python:3.14-alpine

ARG VERSION=dev
LABEL org.opencontainers.image.version=$VERSION \
      org.opencontainers.image.source=https://github.com/aethera-deeptech/demo-seeder

RUN apk add --no-cache tzdata && adduser -D -u 10001 seeder && mkdir /data && chown seeder /data

WORKDIR /app
COPY seeder ./seeder
COPY plugins ./plugins

USER seeder
VOLUME /data
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# the loop touches /data/heartbeat after every cycle, and the check fails when it is older than ten minutes
HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import os,sys,time; sys.exit(0 if time.time()-os.path.getmtime('/data/heartbeat') < 600 else 1)"

ENTRYPOINT ["python", "-m", "seeder"]
CMD ["run", "--config", "/config/demo.toml"]
