ARG EXTERNAL_REG
ARG INTERNAL_REG
ARG PYTHON_VERSION
FROM ${INTERNAL_REG}/debian:bullseye as certs



FROM ${EXTERNAL_REG}/python:${PYTHON_VERSION}-slim-bullseye as base

ARG APP_VERSION
ARG PYTHON_VERSION
ARG MAINTAINER
LABEL envidat.ch.app-version="${APP_VERSION}" \
      envidat.ch.python-img-tag="${PYTHON_VERSION}" \
      envidat.ch.maintainer="${MAINTAINER}"

# CA-Certs
COPY --from=certs \
    /etc/ssl/certs/ca-certificates.crt \
    /etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

RUN set -ex \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install \
       -y --no-install-recommends locales \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# Set locale
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8



FROM base as build
RUN set -ex \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install \
        -y --no-install-recommends \
            build-essential \
            gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/python
COPY Pipfile /opt/python/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir pipenv==11.9.0 \
    && PIPENV_VENV_IN_PROJECT=1 pipenv install \
    && rm /opt/python/Pipfile /opt/python/Pipfile.lock



FROM base as runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

RUN set -ex \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install \
        -y --no-install-recommends \
            curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build \
    /opt/python/ \
    /opt/python/
ENV PATH="/opt/python/.venv/bin:$PATH"
WORKDIR /opt/app
COPY main.py .

# Upgrade pip & pre-compile deps to .pyc, add appuser, permissions
RUN /opt/python/.venv/bin/python -m pip install --no-cache-dir --upgrade pip \
    && python -c "import compileall; compileall.compile_path(maxlevels=10, quiet=1)" \
    && useradd -r -u 900 -m -c "unprivileged account" -d /home/appuser -s /bin/false appuser \
    && chown -R appuser:appuser /opt

ENTRYPOINT ["python"]
USER appuser



FROM runtime as debug
RUN pip install --no-cache-dir debugpy
ENTRYPOINT ["python", "-m", "debugpy", "--wait-for-client", "--listen", "0.0.0.0:5678"]
CMD ["/opt/app/main.py"]



FROM runtime as prod
CMD ["/opt/app/main.py"]
