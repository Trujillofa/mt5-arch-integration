/*
 * LD_PRELOAD shim: deny XInput2 to Wine so each MT5 book only acts on input
 * addressed to its own X11 window.
 *
 * Why: every book runs in its own Wine prefix, i.e. its own wineserver, so
 * each one believes its terminal is the foreground window. Wine 11 Staging's
 * winex11 listens for XInput2 *raw* button events on the root window
 * (X11DRV_RawButtonEvent). Raw events are broadcast to every client that
 * selects them, whatever window is under the pointer, so one right-click was
 * turned into a click on *every* book's chart: tested 2026-09-24, a
 * right-click on a plain Tk window made Vantage and FTMO (hidden workspace)
 * both open their chart menu in the same millisecond.
 *
 * winex11 loads libXi at runtime (dlopen SONAME_LIBXI). Refusing that one
 * dlopen makes it log "XInput2 not available" and fall back to core X11
 * events, which the X server delivers to exactly one window. Nothing an MT5
 * book needs is lost: XInput2 only backs ClipCursor and WM_INPUT raw mouse.
 *
 * Only libXi is refused; every other dlopen passes straight through.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <string.h>

void *dlopen(const char *file, int mode)
{
    static void *(*real_dlopen)(const char *, int);
    if (!real_dlopen)
        real_dlopen = (void *(*)(const char *, int))dlsym(RTLD_NEXT, "dlopen");
    if (file && strstr(file, "libXi.so"))
        return NULL;
    return real_dlopen(file, mode);
}
