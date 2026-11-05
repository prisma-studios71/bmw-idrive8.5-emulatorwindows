import argparse
import http.server
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('start', 'serve', 'status', 'stop'))
    parser.add_argument('root', type=pathlib.Path)
    parser.add_argument('port', type=int)
    parser.add_argument('message', nargs='?', default='Starting the Linux VM…')
    parser.add_argument('--vm', default='bmw-idrive85')
    options = parser.parse_args()
    local = options.root / '.local'
    local.mkdir(exist_ok=True)
    status = local / f'boot-{options.port}.json'
    address = f'http://127.0.0.1:{options.port}'
    if options.action in ('start', 'status'):
        temporary = status.with_suffix('.tmp')
        previous = json.loads(status.read_text()) if status.exists() and options.action == 'status' else {}
        temporary.write_text(json.dumps({'service': 'bmw-hmi8-boot', 'message': options.message,
                                         'started_ns': previous.get('started_ns', time.time_ns())}))
        temporary.replace(status)
    if options.action == 'status':
        return
    if options.action == 'stop':
        try:
            with urllib.request.urlopen(address + '/api/boot', timeout=2) as response:
                if json.load(response).get('service') != 'bmw-hmi8-boot':
                    return
            request = urllib.request.Request(address + '/api/boot/stop', data=b'', method='POST')
            urllib.request.urlopen(request, timeout=2).close()
        except (OSError, ValueError):
            return
        for attempt in range(40):
            try:
                urllib.request.urlopen(address + '/api/boot', timeout=0.2).close()
            except OSError:
                return
            time.sleep(0.05)
        raise SystemExit('Boot splash did not release the viewer port.')
    if options.action == 'start':
        with (local / 'boot-splash.log').open('ab') as log:
            process = subprocess.Popen(
                [sys.executable, str(pathlib.Path(__file__).resolve()), 'serve',
                 str(options.root), str(options.port), '--vm', options.vm], stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        for attempt in range(40):
            if process.poll() is not None:
                raise SystemExit('Cannot start boot splash; see .local/boot-splash.log')
            try:
                urllib.request.urlopen(address + '/api/boot', timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        process.terminate()
        raise SystemExit('Boot splash startup timed out.')

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{options.port}', f'localhost:{options.port}'):
                self.send_error(403)
                return
            if self.path == '/api/boot':
                document = json.loads(status.read_text())
                document['console'] = ''
                serial = pathlib.Path.home() / '.lima' / options.vm / 'serial.log'
                if serial.is_file() and serial.stat().st_mtime_ns >= document['started_ns']:
                    with serial.open('rb') as stream:
                        stream.seek(max(0, serial.stat().st_size - 131072))
                        text = stream.read(131072).decode('utf-8', errors='replace')
                    text = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', text)
                    text = re.sub(r'\x1bP.*?\x1b\\', '', text, flags=re.S)
                    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b.', '', text)
                    text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', text)
                    document['console'] = '\n'.join(text.splitlines()[-100:])
                payload, content_type = json.dumps(document).encode(), 'application/json'
            elif self.path == '/':
                original = (options.root / 'web/index.html').read_text().replace(
                    '<html lang="en">', '<html lang="en" data-boot-console>', 1)
                payload = original.replace('</html>', '<script>' + (
                    options.root / 'web/boot.js').read_text() + '</script></html>', 1).encode()
                content_type = 'text/html; charset=utf-8'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            if (self.path != '/api/boot/stop' or self.headers.get('Origin') or self.headers.get('Sec-Fetch-Site')
                    or self.headers.get('Host') != f'127.0.0.1:{options.port}'):
                self.send_error(403)
                return
            self.send_response(204)
            self.end_headers()
            self.server.stopping = True

    with http.server.HTTPServer(('127.0.0.1', options.port), Handler) as server:
        server.stopping = False
        while not server.stopping:
            server.handle_request()


if __name__ == '__main__':
    main()
