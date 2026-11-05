#define _GNU_SOURCE
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <dlfcn.h>
#include <stdio.h>

EGLDisplay eglGetDisplay(EGLNativeDisplayType native) {
    static EGLDisplay (*real)(EGLNativeDisplayType);
    static PFNEGLGETPLATFORMDISPLAYEXTPROC platform;
    if (!real) real = (EGLDisplay (*)(EGLNativeDisplayType))dlsym(RTLD_NEXT, "eglGetDisplay");
    if (native == EGL_DEFAULT_DISPLAY) return real(native);
    if (!platform) platform = (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
    if (!platform) return real(native);
    fprintf(stderr, "egl-wayland-shim: eglGetDisplay(%p) -> EGL_PLATFORM_WAYLAND_EXT\n", (void *)native);
    return platform(EGL_PLATFORM_WAYLAND_EXT, (void *)native, NULL);
}
