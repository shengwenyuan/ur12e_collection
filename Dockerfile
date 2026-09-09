# syntax=docker/dockerfile:1
ARG ROS_IMAGE=ros@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4
FROM ${ROS_IMAGE} AS dependencies
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      libusb-1.0-0 python3-venv \
      ros-jazzy-foxglove-msgs ros-jazzy-ros2bag \
      ros-jazzy-rosbag2-storage-mcap ros-jazzy-rosbag2-transport \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv --system-site-packages /opt/venv
COPY requirements/runtime.txt /opt/requirements/runtime.txt
RUN pip install --no-cache-dir --require-hashes -r /opt/requirements/runtime.txt

FROM dependencies AS builder
WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
RUN pip wheel --no-deps --wheel-dir /wheels .

FROM dependencies AS runtime
ARG SOURCE_REVISION=unknown
ARG ROS_IMAGE
LABEL org.opencontainers.image.base.name="${ROS_IMAGE}" \
      org.opencontainers.image.title="ur12e-collection" \
      org.opencontainers.image.revision="${SOURCE_REVISION}"
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-deps /wheels/*.whl && rm -rf /wheels \
    && groupadd --gid 10001 collector \
    && useradd --uid 10001 --gid 10001 --create-home collector \
    && mkdir /config /data \
    && chown collector:collector /config /data \
    && dpkg-query -W > /opt/os-packages.txt \
    && pip freeze > /opt/python-packages.txt
COPY config/station.example.json /opt/examples/station.json
COPY scripts/entrypoint.sh /entrypoint.sh
USER collector
WORKDIR /data
ENTRYPOINT ["/entrypoint.sh"]
CMD ["--help"]

FROM runtime AS development
USER root
COPY requirements/development.txt /opt/requirements/development.txt
RUN pip install --no-cache-dir --require-hashes -r /opt/requirements/development.txt
COPY tests /opt/tests
COPY pyproject.toml /opt/pyproject.toml
USER collector
