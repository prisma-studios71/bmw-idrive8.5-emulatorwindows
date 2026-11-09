/*
 * Userspace touchscreen for kernels or emulators without evdev/uinput.
 *
 * Preloaded into Hmi8 only. When Hmi8 opens $LAB_EVDEV_DEVICE, the shim
 * returns a Unix stream socket connected to runtime/touch_guest.py instead of
 * a kernel event node, and answers the EVIOC* ioctls for that descriptor
 * itself. Events arrive on the socket as ordinary struct input_event records.
 *
 * Used where the real path cannot work:
 *  - WSL2 on ARM64: the Microsoft kernel is built without CONFIG_INPUT_EVDEV.
 *  - x86-64 hosts running the ARM64 container through qemu-user: qemu does
 *    not translate evdev/uinput ioctls.
 * Every other descriptor and ioctl is passed through unchanged.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#define MAX_TRACKED 4096
#define TOUCH_SLOTS 10

static _Atomic unsigned char tracked[MAX_TRACKED];
static const char *device_path;
static const char *socket_path;
static int width = 1920, height = 720;
static pthread_once_t once = PTHREAD_ONCE_INIT;

static int (*real_open)(const char *, int, ...);
static int (*real_open64)(const char *, int, ...);
static int (*real_openat)(int, const char *, int, ...);
static int (*real_openat64)(int, const char *, int, ...);
static int (*real_open_2)(const char *, int);
static int (*real_open64_2)(const char *, int);
static int (*real_openat_2)(int, const char *, int);
static int (*real_close)(int);
static int (*real_ioctl)(int, unsigned long, ...);

static void initialize(void) {
    real_open = dlsym(RTLD_NEXT, "open");
    real_open64 = dlsym(RTLD_NEXT, "open64");
    real_openat = dlsym(RTLD_NEXT, "openat");
    real_openat64 = dlsym(RTLD_NEXT, "openat64");
    real_open_2 = dlsym(RTLD_NEXT, "__open_2");
    real_open64_2 = dlsym(RTLD_NEXT, "__open64_2");
    real_openat_2 = dlsym(RTLD_NEXT, "__openat_2");
    real_close = dlsym(RTLD_NEXT, "close");
    real_ioctl = dlsym(RTLD_NEXT, "ioctl");
    device_path = getenv("LAB_EVDEV_DEVICE");
    socket_path = getenv("LAB_EVDEV_SOCKET");
    const char *size = getenv("LAB_EVDEV_SIZE");
    if (size && sscanf(size, "%dx%d", &width, &height) != 2) width = 1920, height = 720;
    if (width < 2) width = 2;
    if (height < 2) height = 2;
}

static void ready(void) { pthread_once(&once, initialize); }

static int is_device(const char *path) {
    ready();
    return device_path && socket_path && path && strcmp(path, device_path) == 0;
}

static int is_tracked(int fd) { return fd >= 0 && fd < MAX_TRACKED && atomic_load(&tracked[fd]); }

static int open_touch(int flags) {
    int type = SOCK_STREAM | ((flags & O_CLOEXEC) ? SOCK_CLOEXEC : 0);
    int fd = socket(AF_UNIX, type, 0);
    if (fd < 0) return -1;
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(socket_path) >= sizeof(address.sun_path)) {
        real_close(fd);
        errno = ENAMETOOLONG;
        return -1;
    }
    strcpy(address.sun_path, socket_path);
    for (int attempt = 0;; ++attempt) {
        if (connect(fd, (struct sockaddr *)&address, sizeof(address)) == 0) break;
        if (attempt >= 50 || (errno != ENOENT && errno != ECONNREFUSED)) {
            int saved = errno;
            real_close(fd);
            errno = saved == ENOENT ? ENODEV : saved;
            return -1;
        }
        usleep(100000);
    }
    if (flags & O_NONBLOCK) fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK);
    if (fd < MAX_TRACKED) atomic_store(&tracked[fd], 1);
    fprintf(stderr, "evdev-touch-shim: %s -> %s (fd %d, %dx%d)\n", device_path, socket_path, fd, width, height);
    return fd;
}

static mode_t mode_argument(int flags, va_list arguments) {
    return (flags & (O_CREAT | O_TMPFILE)) ? va_arg(arguments, mode_t) : 0;
}

int open(const char *path, int flags, ...) {
    if (is_device(path)) return open_touch(flags);
    va_list arguments;
    va_start(arguments, flags);
    mode_t mode = mode_argument(flags, arguments);
    va_end(arguments);
    return real_open(path, flags, mode);
}

int open64(const char *path, int flags, ...) {
    if (is_device(path)) return open_touch(flags);
    va_list arguments;
    va_start(arguments, flags);
    mode_t mode = mode_argument(flags, arguments);
    va_end(arguments);
    return (real_open64 ? real_open64 : real_open)(path, flags, mode);
}

int openat(int directory, const char *path, int flags, ...) {
    if (is_device(path)) return open_touch(flags);
    va_list arguments;
    va_start(arguments, flags);
    mode_t mode = mode_argument(flags, arguments);
    va_end(arguments);
    return real_openat(directory, path, flags, mode);
}

int openat64(int directory, const char *path, int flags, ...) {
    if (is_device(path)) return open_touch(flags);
    va_list arguments;
    va_start(arguments, flags);
    mode_t mode = mode_argument(flags, arguments);
    va_end(arguments);
    return (real_openat64 ? real_openat64 : real_openat)(directory, path, flags, mode);
}

int __open_2(const char *path, int flags) {
    if (is_device(path)) return open_touch(flags);
    return real_open_2 ? real_open_2(path, flags) : real_open(path, flags);
}

int __open64_2(const char *path, int flags) {
    if (is_device(path)) return open_touch(flags);
    return real_open64_2 ? real_open64_2(path, flags) : real_open(path, flags);
}

int __openat_2(int directory, const char *path, int flags) {
    if (is_device(path)) return open_touch(flags);
    return real_openat_2 ? real_openat_2(directory, path, flags) : real_openat(directory, path, flags);
}

int close(int fd) {
    ready();
    if (fd >= 0 && fd < MAX_TRACKED) atomic_store(&tracked[fd], 0);
    return real_close(fd);
}

static void set_bit(unsigned char *bits, unsigned int bit) { bits[bit / 8] |= 1u << (bit % 8); }

static int copy_out(void *argument, unsigned int length, const void *source, unsigned int available) {
    unsigned int count = length < available ? length : available;
    memcpy(argument, source, count);
    if (length > count) memset((char *)argument + count, 0, length - count);
    return (int)count;
}

static size_t bitmap_bytes(unsigned int count) {
    return ((count + 8 * sizeof(long) - 1) / (8 * sizeof(long))) * sizeof(long);
}

static int fail(int error) {
    errno = error;
    return -1;
}

static int absinfo(unsigned int code, struct input_absinfo *info) {
    memset(info, 0, sizeof(*info));
    switch (code) {
    case ABS_X: case ABS_MT_POSITION_X: info->maximum = width - 1; return 0;
    case ABS_Y: case ABS_MT_POSITION_Y: info->maximum = height - 1; return 0;
    case ABS_MT_SLOT: info->maximum = TOUCH_SLOTS - 1; return 0;
    case ABS_MT_TRACKING_ID: info->maximum = 65535; info->value = -1; return 0;
    case ABS_MT_TOUCH_MAJOR: case ABS_MT_PRESSURE: info->maximum = 255; return 0;
    default: return -1;
    }
}

static void send_clock(int fd, int clock) {
    unsigned char message[5] = {'C'};
    memcpy(message + 1, &clock, sizeof(clock));
    ssize_t ignored = send(fd, message, sizeof(message), MSG_NOSIGNAL | MSG_DONTWAIT);
    (void)ignored;
}

static int touch_ioctl(int fd, unsigned long request, void *argument) {
    unsigned int type = _IOC_TYPE(request), number = _IOC_NR(request), size = _IOC_SIZE(request);
    unsigned int direction = _IOC_DIR(request);
    if (type != 'E') return real_ioctl(fd, request, argument);
    if (direction & _IOC_READ && !argument) return fail(EFAULT);
    if (number >= 0x20 && number < 0x40 && direction == _IOC_READ) {  /* EVIOCGBIT */
        unsigned char bits[bitmap_bytes(KEY_CNT)];
        memset(bits, 0, sizeof(bits));
        unsigned int event = number - 0x20;
        size_t available = bitmap_bytes(EV_CNT);
        if (event == 0) {
            set_bit(bits, EV_SYN), set_bit(bits, EV_KEY), set_bit(bits, EV_ABS);
        } else if (event == EV_KEY) {
            set_bit(bits, BTN_TOUCH), set_bit(bits, BTN_TOOL_FINGER);
            available = bitmap_bytes(KEY_CNT);
        } else if (event == EV_ABS) {
            static const unsigned int axes[] = {ABS_X, ABS_Y, ABS_MT_SLOT, ABS_MT_TRACKING_ID,
                                                ABS_MT_POSITION_X, ABS_MT_POSITION_Y,
                                                ABS_MT_TOUCH_MAJOR, ABS_MT_PRESSURE};
            for (size_t index = 0; index < sizeof(axes) / sizeof(*axes); ++index) set_bit(bits, axes[index]);
            available = bitmap_bytes(ABS_CNT);
        } else if (event == EV_SYN) {
            set_bit(bits, SYN_REPORT);
            available = bitmap_bytes(SYN_CNT);
        } else if (event == EV_REL) available = bitmap_bytes(REL_CNT);
        else if (event == EV_MSC) available = bitmap_bytes(MSC_CNT);
        else if (event == EV_SW) available = bitmap_bytes(SW_CNT);
        else if (event == EV_LED) available = bitmap_bytes(LED_CNT);
        else if (event == EV_SND) available = bitmap_bytes(SND_CNT);
        else if (event == EV_FF) available = bitmap_bytes(FF_CNT);
        return copy_out(argument, size, bits, (unsigned int)available);
    }
    if (number >= 0x40 && number < 0x80 && direction == _IOC_READ) {  /* EVIOCGABS */
        struct input_absinfo info;
        if (absinfo(number - 0x40, &info)) return fail(EINVAL);
        copy_out(argument, size, &info, sizeof(info));
        return 0;
    }
    if (number >= 0xc0 && number < 0x100 && direction == _IOC_WRITE) return 0;  /* EVIOCSABS */
    switch (number) {
    case 0x01: { int version = EV_VERSION; copy_out(argument, size, &version, sizeof(version)); return 0; }
    case 0x02: {
        struct input_id id = {.bustype = BUS_VIRTUAL, .vendor = 0x1d6b, .product = 0x0104, .version = 1};
        copy_out(argument, size, &id, sizeof(id));
        return 0;
    }
    case 0x03: case 0x04: case 0x05: return fail(EINVAL);  /* repeat and keycode maps */
    case 0x06: {
        static const char name[] = "Hmi8 laboratory touchscreen";
        return copy_out(argument, size, name, sizeof(name));
    }
    case 0x07: case 0x08: return fail(ENOENT);  /* phys, uniq */
    case 0x09: {  /* EVIOCGPROP */
        unsigned char properties[bitmap_bytes(INPUT_PROP_CNT)];
        memset(properties, 0, sizeof(properties));
        set_bit(properties, INPUT_PROP_DIRECT);
        return copy_out(argument, size, properties, sizeof(properties));
    }
    case 0x0a: {  /* EVIOCGMTSLOTS: __u32 code followed by one __s32 per slot */
        if (size < 4) return fail(EINVAL);
        __u32 code;
        memcpy(&code, argument, sizeof(code));
        __s32 *values = (__s32 *)((char *)argument + 4);
        unsigned int count = (size - 4) / 4;
        for (unsigned int slot = 0; slot < count; ++slot)
            values[slot] = (code == ABS_MT_TRACKING_ID) ? -1 : 0;
        return 0;
    }
    case 0x18: case 0x19: case 0x1a: case 0x1b:  /* key, led, sound, switch state: all released */
        memset(argument, 0, size);
        return (int)size;
    case 0x84: { int effects = 0; copy_out(argument, size, &effects, sizeof(effects)); return 0; }
    case 0x90: case 0x91: case 0x92: case 0x93: return 0;  /* grab, revoke, masks */
    case 0xa0: {  /* EVIOCSCLOCKID: the bridge stamps events with this clock */
        int clock;
        memcpy(&clock, argument, sizeof(clock));
        if (clock != CLOCK_REALTIME && clock != CLOCK_MONOTONIC && clock != CLOCK_BOOTTIME) return fail(EINVAL);
        send_clock(fd, clock);
        return 0;
    }
    default: return fail(EINVAL);
    }
}

int ioctl(int fd, unsigned long request, ...) {
    ready();
    va_list arguments;
    va_start(arguments, request);
    void *argument = va_arg(arguments, void *);
    va_end(arguments);
    if (is_tracked(fd)) return touch_ioctl(fd, request, argument);
    return real_ioctl(fd, request, argument);
}
