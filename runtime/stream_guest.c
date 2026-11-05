#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#include <wayland-client.h>
#include <jpeglib.h>
#include "capture-client.h"

static struct wl_display *display;
static struct wl_shm *shared_memory;
static struct wl_output *output;
static struct weston_capture_v1 *factory;
static int width, height, complete;
static uint32_t format;

static void registry_global(void *data, struct wl_registry *registry, uint32_t name,
                            const char *interface, uint32_t version) {
    if (!strcmp(interface, "wl_shm"))
        shared_memory = wl_registry_bind(registry, name, &wl_shm_interface, 1);
    if (!strcmp(interface, "wl_output") && !output)
        output = wl_registry_bind(registry, name, &wl_output_interface, 1);
    if (!strcmp(interface, "weston_capture_v1"))
        factory = wl_registry_bind(registry, name, &weston_capture_v1_interface, 1);
}
static void registry_remove(void *data, struct wl_registry *registry, uint32_t name) {}
static const struct wl_registry_listener registry_listener = {registry_global, registry_remove};
static void source_format(void *data, struct weston_capture_source_v1 *source, uint32_t value) { format = value; }
static void source_size(void *data, struct weston_capture_source_v1 *source, int32_t horizontal, int32_t vertical) {
    width = horizontal;
    height = vertical;
}
static void source_complete(void *data, struct weston_capture_source_v1 *source) { complete = 1; }
static void source_retry(void *data, struct weston_capture_source_v1 *source) { complete = -1; }
static void source_failed(void *data, struct weston_capture_source_v1 *source, const char *message) {
    fprintf(stderr, "Capture failed: %s\n", message ? message : "unknown");
    complete = -1;
}
static const struct weston_capture_source_v1_listener source_listener = {
    source_format, source_size, source_complete, source_retry, source_failed
};
static int write_all(int descriptor, const void *buffer, size_t length) {
    const char *bytes = buffer;
    while (length) {
        ssize_t written = write(descriptor, bytes, length);
        if (written < 0 && errno == EINTR) continue;
        if (written <= 0) return -1;
        bytes += written;
        length -= written;
    }
    return 0;
}
static void forward_touch(int descriptor) {
    char bytes[4096];
    ssize_t length;
    while ((length = read(STDIN_FILENO, bytes, sizeof bytes)) > 0)
        if (descriptor >= 0) write_all(descriptor, bytes, length);
}
int main(int argc, char **argv) {
    int target_fps = argc >= 3 ? atoi(argv[2]) : 60;
    int quality = argc >= 4 ? atoi(argv[3]) : 85;
    int scale = argc >= 5 ? atoi(argv[4]) : 1;
    if (target_fps < 1 || target_fps > 60 || quality < 30 || quality > 100 ||
        (scale != 1 && scale != 2 && scale != 4)) {
        fprintf(stderr, "Usage: hmi-stream [touch-socket [fps:1..60 [quality:30..100 [scale:1|2|4]]]]\n");
        return 1;
    }
    int touch = -1;
    if (argc >= 2 && strcmp(argv[1], "-") != 0) {
        struct sockaddr_un address = {.sun_family = AF_UNIX};
        snprintf(address.sun_path, sizeof address.sun_path, "%s", argv[1]);
        touch = socket(AF_UNIX, SOCK_STREAM, 0);
        if (connect(touch, (struct sockaddr *)&address, sizeof address) < 0) {
            perror("touch socket");
            close(touch);
            touch = -1;
        }
    }
    fcntl(STDIN_FILENO, F_SETFL, O_NONBLOCK);
    display = wl_display_connect(NULL);
    if (!display) return 2;
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &registry_listener, NULL);
    if (wl_display_roundtrip(display) < 0 || !factory || !output || !shared_memory) return 3;
    struct weston_capture_source_v1 *source = weston_capture_v1_create(factory, output, WESTON_CAPTURE_V1_SOURCE_FRAMEBUFFER);
    weston_capture_source_v1_add_listener(source, &source_listener, NULL);
    if (wl_display_roundtrip(display) < 0 || width <= 0 || height <= 0 || width > 8192 || height > 8192) return 4;
    if (format != 0x34325258 && format != 0x34325241) {
        fprintf(stderr, "Unsupported capture format: %08x\n", format);
        return 5;
    }
    int memory = memfd_create("hmi8-live-capture", MFD_CLOEXEC);
    size_t size = (size_t)width * height * 4;
    if (memory < 0 || ftruncate(memory, size * 2) < 0) return 6;
    unsigned char *pixels = mmap(NULL, size * 2, PROT_READ | PROT_WRITE, MAP_SHARED, memory, 0);
    if (pixels == MAP_FAILED) return 7;
    int preview_width = width / scale;
    int preview_height = height / scale;
    unsigned char *preview_row = malloc((size_t)preview_width * 4);
    if (!preview_row || !preview_width || !preview_height) return 7;
    struct wl_shm_pool *pool = wl_shm_create_pool(shared_memory, memory, size * 2);
    uint32_t buffer_format = format == 0x34325241 ? WL_SHM_FORMAT_ARGB8888 : WL_SHM_FORMAT_XRGB8888;
    struct wl_buffer *buffers[] = {
        wl_shm_pool_create_buffer(pool, 0, width, height, width * 4, buffer_format),
        wl_shm_pool_create_buffer(pool, size, width, height, width * 4, buffer_format)
    };
    wl_shm_pool_destroy(pool);
    close(memory);
    uint32_t sequence = 0;
    int current_buffer = 0;
    struct timespec requested_at;
    clock_gettime(CLOCK_MONOTONIC, &requested_at);
    weston_capture_source_v1_capture(source, buffers[current_buffer]);
    wl_display_flush(display);
    for (;;) {
        while (!complete) {
            struct pollfd descriptors[] = {{wl_display_get_fd(display), POLLIN, 0}, {STDIN_FILENO, POLLIN, 0}};
            if (poll(descriptors, 2, 1000) < 0 && errno != EINTR) return 8;
            if (descriptors[1].revents & POLLIN) forward_touch(touch);
            if (descriptors[1].revents & POLLHUP) return 0;
            if (descriptors[0].revents & (POLLERR | POLLHUP)) return 9;
            if (descriptors[0].revents & POLLIN && wl_display_dispatch(display) < 0) return 10;
        }
        if (complete < 0) return 11;
        unsigned char *frame_pixels = pixels + size * current_buffer;
        current_buffer = 1 - current_buffer;
        struct timespec ready_at;
        clock_gettime(CLOCK_MONOTONIC, &ready_at);
        int64_t elapsed = (ready_at.tv_sec - requested_at.tv_sec) * 1000000000LL +
                          ready_at.tv_nsec - requested_at.tv_nsec;
        int64_t remaining = 1000000000LL / target_fps - elapsed;
        if (remaining > 0) {
            struct timespec delay = {.tv_nsec = remaining};
            nanosleep(&delay, NULL);
        }
        complete = 0;
        weston_capture_source_v1_capture(source, buffers[current_buffer]);
        wl_display_flush(display);
        clock_gettime(CLOCK_MONOTONIC, &requested_at);
        struct jpeg_compress_struct encoder;
        struct jpeg_error_mgr error;
        encoder.err = jpeg_std_error(&error);
        jpeg_create_compress(&encoder);
        unsigned char *encoded = NULL;
        unsigned long length = 0;
        jpeg_mem_dest(&encoder, &encoded, &length);
        encoder.image_width = preview_width;
        encoder.image_height = preview_height;
        encoder.input_components = 4;
        encoder.in_color_space = JCS_EXT_BGRA;
        jpeg_set_defaults(&encoder);
        jpeg_set_quality(&encoder, quality, TRUE);
        jpeg_start_compress(&encoder, TRUE);
        while (encoder.next_scanline < encoder.image_height) {
            JSAMPROW row = frame_pixels + (size_t)encoder.next_scanline * scale * width * 4;
            if (scale != 1) {
                for (int column = 0; column < preview_width; column++)
                    memcpy(preview_row + column * 4, row + column * scale * 4, 4);
                row = preview_row;
            }
            jpeg_write_scanlines(&encoder, &row, 1);
        }
        jpeg_finish_compress(&encoder);
        uint32_t header[] = {0x38494d48, (uint32_t)length, ++sequence, (uint32_t)width, (uint32_t)height};
        if (write_all(STDOUT_FILENO, header, sizeof header) || write_all(STDOUT_FILENO, encoded, length)) return 0;
        free(encoded);
        jpeg_destroy_compress(&encoder);
        forward_touch(touch);
    }
}
