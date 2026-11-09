"""Userspace touchscreen event source for runtime/evdev_touch_shim.c.

Same write()/syn() interface as evdev.UInput, but events go to every Hmi8
descriptor that the preload shim connected to this Unix socket, encoded as
native struct input_event records (64-bit: timeval + type, code, value).
Used where the kernel has no evdev (WSL2 on ARM64) or the ARM64 container
runs under qemu-user, which cannot translate uinput/evdev ioctls.
"""
import os
import pathlib
import select
import socket
import struct
import threading
import time

EVENT = struct.Struct('=qqHHi')
EV_SYN, SYN_REPORT = 0, 0
CLOCKS = {0: time.CLOCK_REALTIME, 1: time.CLOCK_MONOTONIC, 7: time.CLOCK_BOOTTIME}


class SocketTouch:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.path.unlink(missing_ok=True)
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.path))
        os.chmod(self.path, 0o666)
        self.listener.listen(8)
        self.clients = {}
        self.pending = []
        self.lock = threading.Lock()
        self.stopping = False
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()

    def serve(self):
        while not self.stopping:
            with self.lock:
                sockets = [self.listener, *self.clients]
            try:
                readable, _, _ = select.select(sockets, [], [], 1.0)
            except (OSError, ValueError):
                continue
            for ready in readable:
                if ready is self.listener:
                    try:
                        client, _ = self.listener.accept()
                    except OSError:
                        continue
                    with self.lock:
                        self.clients[client] = time.CLOCK_REALTIME
                    print(f'Touch shim client connected ({len(self.clients)} open)', flush=True)
                    continue
                try:
                    message = ready.recv(64)
                except OSError:
                    message = b''
                if not message:
                    self.drop(ready)
                    continue
                # Control messages from the shim: b'C' + int32 clock id (EVIOCSCLOCKID).
                for offset in range(0, len(message) - 4, 5):
                    if message[offset:offset + 1] == b'C':
                        clock = struct.unpack_from('=i', message, offset + 1)[0]
                        with self.lock:
                            if ready in self.clients:
                                self.clients[ready] = CLOCKS.get(clock, time.CLOCK_REALTIME)

    def drop(self, client):
        with self.lock:
            self.clients.pop(client, None)
        try:
            client.close()
        except OSError:
            pass

    def write(self, event_type, code, value):
        self.pending.append((event_type, code, value))

    def syn(self):
        self.write(EV_SYN, SYN_REPORT, 0)
        events, self.pending = self.pending, []
        with self.lock:
            clients = list(self.clients.items())
        for client, clock in clients:
            now = time.clock_gettime_ns(clock)
            seconds, microseconds = now // 1_000_000_000, (now // 1000) % 1_000_000
            payload = b''.join(EVENT.pack(seconds, microseconds, *event) for event in events)
            try:
                client.sendall(payload)
            except OSError:
                self.drop(client)

    def close(self):
        self.stopping = True
        with self.lock:
            clients = list(self.clients)
            self.clients.clear()
        for client in clients:
            try:
                client.close()
            except OSError:
                pass
        self.listener.close()
        self.path.unlink(missing_ok=True)
