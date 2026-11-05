#!/usr/bin/env bash
set -euo pipefail
output=/srv/hmi8-lab/bin
mkdir -p "$output"
protocol=/usr/share/libweston-13/protocols/weston-output-capture.xml
wayland-scanner client-header "$protocol" "$output/capture-client.h"
wayland-scanner private-code "$protocol" "$output/capture-protocol.c"
cc -O2 -Wall -Werror=implicit-function-declaration -I"$output" \
    /mnt/hmi8-lab/stream_guest.c "$output/capture-protocol.c" \
    -o "$output/hmi-stream.new" $(pkg-config --cflags --libs wayland-client) -ljpeg
mv "$output/hmi-stream.new" "$output/hmi-stream"
