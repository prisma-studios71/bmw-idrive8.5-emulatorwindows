import argparse
import os
import pathlib
import socket


def main():
    parser = argparse.ArgumentParser(description='Pass a local Wayland listener to Hmi8 using socket activation.')
    parser.add_argument('--uid', type=int, default=4010200)
    parser.add_argument('--gid', type=int, default=4010200)
    parser.add_argument('socket_path', type=pathlib.Path)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    options = parser.parse_args()
    if not options.command:
        parser.error('a command is required')
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(options.socket_path))
    try:
        os.chmod(options.socket_path, 0o774)
        os.chown(options.socket_path, options.uid, options.gid)
        listener.listen(16)
        descriptor = listener.detach()
        if descriptor != 3:
            os.dup2(descriptor, 3)
            os.close(descriptor)
        os.set_inheritable(3, True)
        os.environ.update(LISTEN_PID=str(os.getpid()), LISTEN_FDS='1', LISTEN_FDNAMES='hmiec.socket')
        os.execvpe(options.command[0], options.command, os.environ)
    except BaseException:
        options.socket_path.unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    main()
