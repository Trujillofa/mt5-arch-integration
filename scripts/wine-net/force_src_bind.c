#define _GNU_SOURCE
#include <dlfcn.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>

/* Force outbound IPv4 sockets to bind to LAN_IP before connect (avoids Docker bridge src). */
static int (*real_connect)(int, const struct sockaddr *, socklen_t) = NULL;
static int (*real_bind)(int, const struct sockaddr *, socklen_t) = NULL;

static in_addr_t preferred_src(void) {
  const char *ip = getenv("MT5_FORCE_SRC_IP");
  if (!ip || !*ip)
    ip = "192.168.0.144";
  return inet_addr(ip);
}

static int is_dockerish(in_addr_t a) {
  unsigned char *b = (unsigned char *)&a;
  /* 172.16/12, 10/8, 100.64/10 (CGNAT/tailscale-ish).
     Do not treat 127/8 as dockerish: bind() rewrite of loopback remaps
     official MT5 MCP (127.0.0.1:22346) onto the LAN NIC, so Cursor's
     localhost client gets Connection refused. Outbound connect() still
     forces LAN source below. */
  if (b[0] == 10) return 1;
  if (b[0] == 172 && b[1] >= 16 && b[1] <= 31) return 1;
  if (b[0] == 100 && b[1] >= 64 && b[1] <= 127) return 1;
  return 0;
}

int bind(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
  if (!real_bind)
    real_bind = (int (*)(int, const struct sockaddr *, socklen_t))dlsym(RTLD_NEXT, "bind");
  if (addr && addr->sa_family == AF_INET && addrlen >= sizeof(struct sockaddr_in)) {
    const struct sockaddr_in *in = (const struct sockaddr_in *)addr;
    if (in->sin_addr.s_addr != INADDR_ANY && is_dockerish(in->sin_addr.s_addr)) {
      struct sockaddr_in fixed = *in;
      fixed.sin_addr.s_addr = preferred_src();
      return real_bind(sockfd, (struct sockaddr *)&fixed, sizeof(fixed));
    }
  }
  return real_bind(sockfd, addr, addrlen);
}

int connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
  if (!real_connect)
    real_connect = (int (*)(int, const struct sockaddr *, socklen_t))dlsym(RTLD_NEXT, "connect");
  if (addr && addr->sa_family == AF_INET) {
    struct sockaddr_in local;
    memset(&local, 0, sizeof(local));
    local.sin_family = AF_INET;
    local.sin_addr.s_addr = preferred_src();
    local.sin_port = 0;
    /* best-effort; ignore if already bound */
    if (!real_bind)
      real_bind = (int (*)(int, const struct sockaddr *, socklen_t))dlsym(RTLD_NEXT, "bind");
    real_bind(sockfd, (struct sockaddr *)&local, sizeof(local));
  }
  /* drop IPv6 connects when MT5_FORCE_SRC_IP set — prefer IPv4 path */
  if (addr && addr->sa_family == AF_INET6 && getenv("MT5_FORCE_SRC_IP")) {
    errno = EHOSTUNREACH;
    return -1;
  }
  return real_connect(sockfd, addr, addrlen);
}
