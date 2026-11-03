# The seeder uses only the standard library of Python, so there is nothing to install.
FROM python:3.14-alpine@sha256:eb2c62658b8d51bff0acc408504b76521d02030de56a8a3c1e830083e89b89d2

LABEL org.opencontainers.image.source=https://github.com/aethera-deeptech/demo-seeder

# pip is removed because the service installs nothing at run time, and the libraries that pip bundles (urllib3, msgpack) carry advisories of their own
# tzdata follows the Alpine release of the base image, so a pinned package version would break the build at the next base update
# hadolint ignore=DL3018
RUN apk add --no-cache tzdata && python -m pip uninstall -y pip setuptools wheel && adduser -D -u 10001 seeder && mkdir /data && chown seeder /data

WORKDIR /app
COPY seeder ./seeder
COPY plugins ./plugins

USER 10001
VOLUME /data
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# the loop touches /data/heartbeat after every cycle, and the check fails when it is older than ten minutes
HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=3 \
  CMD ["python", "-c", "import os,sys,time; sys.exit(0 if time.time()-os.path.getmtime('/data/heartbeat') < 600 else 1)"]

ENTRYPOINT ["python", "-m", "seeder"]
CMD ["run", "--config", "/config/demo.toml"]
