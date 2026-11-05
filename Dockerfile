FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-evdev strace binutils e2fsprogs libegl1-mesa-dev \
    libgles2-mesa-dev libgl1-mesa-dri mesa-utils weston build-essential \
    pkg-config libweston-13-dev libwayland-dev libjpeg-dev util-linux \
    iproute2 udev kmod ca-certificates procps mesa-vulkan-drivers libvulkan-dev \
    && rm -rf /var/lib/apt/lists/*
COPY runtime/ /mnt/hmi8-lab/
COPY container/ /opt/hmi8-container/
COPY web/ /opt/hmi8-container/web/
COPY config/*.json /opt/hmi8-container/presets/
COPY LICENSE NOTICE /usr/share/doc/bmw-idrive85/
ENV HMI_CODING_CONFIG=/srv/hmi8-lab/config/coding.json \
    HMI_EMBEDDED_COMPOSITOR=1 HMI_TIMEOUT=0 HMI_PREVIEW_SCALE=2 HMI_STREAM_FPS=60 \
    LD_LIBRARY_PATH=/opt/venus VK_DRIVER_FILES=/opt/venus/venus.json
EXPOSE 5001 5002
HEALTHCHECK --interval=15s --timeout=5s --start-period=180s \
    CMD python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:5001/healthz", timeout=3)'
ENTRYPOINT ["bash", "/opt/hmi8-container/entrypoint.sh"]
