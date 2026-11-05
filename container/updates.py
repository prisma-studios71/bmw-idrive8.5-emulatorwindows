import argparse
import datetime
import json
import pathlib
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_CONFIG = {'repository': 'rishik250809/bmw-idrive8.5-emulator', 'version': None}


def repository_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', value):
        raise ValueError('Update repository must be a GitHub owner/repository name')
    return value


def github_remote(value):
    if value.startswith('git@github.com:'):
        path = value.split(':', 1)[1]
    else:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ('https', 'ssh') or parsed.hostname != 'github.com':
            return None
        path = parsed.path.lstrip('/')
    return repository_name(path.rstrip('/').removesuffix('.git'))


def source_version(root, config):
    def git(*arguments):
        try:
            result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True, text=True, timeout=10)
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    result = {'repository': repository_name(config['repository']), 'version': config.get('version'),
              'source': 'folder', 'branch': None, 'remote_branch': None, 'commit': None,
              'tag': None, 'dirty': None, 'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    top = git('rev-parse', '--show-toplevel')
    if not top or pathlib.Path(top).resolve() != root.resolve():
        return result
    result.update(source='git', branch=git('symbolic-ref', '--quiet', '--short', 'HEAD'),
                  commit=git('rev-parse', '--verify', 'HEAD'), tag=git('describe', '--tags', '--exact-match', 'HEAD'))
    status = git('status', '--porcelain')
    result['dirty'] = status != '' if status is not None else None
    result['version'] = git('describe', '--tags', '--always', 'HEAD') or result['version']
    upstream = git('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}')
    remote = upstream.split('/', 1)[0] if upstream and '/' in upstream else 'origin'
    result['remote_branch'] = upstream.split('/', 1)[1] if upstream and '/' in upstream else result['branch']
    url = git('remote', 'get-url', remote)
    if url:
        result['repository'] = github_remote(url)
    return result


def api_json(repository, path):
    request = urllib.request.Request('https://api.github.com/repos/' + repository + path,
                                     headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'bmw-idrive85-update-check'})
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            payload = response.read(1048577)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        if error.code in (403, 429):
            raise ValueError('GitHub denied the request or its public API rate limit was reached. Try again later.') from error
        raise ValueError('GitHub update check failed (HTTP ' + str(error.code) + ').') from error
    if len(payload) > 1048576:
        raise ValueError('GitHub response exceeded the update-check size limit')
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError('Unexpected GitHub response')
    return result


class UpdateChecker:
    def __init__(self, directory=HERE):
        warning = ''
        try:
            config = json.loads((directory / 'update-config.json').read_text())
            repository_name(config['repository'])
        except (OSError, ValueError, TypeError, KeyError):
            config = dict(DEFAULT_CONFIG)
            warning = 'Update configuration is unavailable; using the default project website. '
        path = directory / 'build-version.json'
        try:
            self.installed = json.loads(path.read_text()) if path.exists() else source_version(directory.parent, config)
            if not isinstance(self.installed, dict):
                raise ValueError('Invalid version metadata')
            repository = self.installed.get('repository')
            self.home = 'https://github.com/' + repository_name(repository) if repository else None
        except (OSError, ValueError, TypeError):
            self.installed = {'repository': config['repository'], 'version': None, 'source': 'unknown',
                              'branch': None, 'remote_branch': None, 'commit': None, 'tag': None, 'dirty': None}
            self.home = 'https://github.com/' + config['repository']
            warning += 'Installed version metadata is unreadable; sync the source and restart to repair it. '
        self.lock = threading.Lock()
        self.last_check = None
        self.report = {'status': 'unchecked', 'message': warning + 'Not checked. GitHub is contacted only when you press Check for updates.',
                       'checked_at': None, 'latest_release': None, 'update_url': self.home}

    def snapshot(self):
        return {'installed': dict(self.installed), 'repository_url': self.home,
                'releases_url': self.home + '/releases' if self.home else None, **self.report}

    def check(self):
        if not self.lock.acquire(blocking=False):
            return {**self.snapshot(), 'status': 'checking', 'message': 'An update check is already running.'}
        try:
            if self.last_check is not None and time.monotonic() - self.last_check < 300:
                return self.snapshot()
            report = {'status': 'unknown', 'message': 'Installed revision is unknown; compare with the project website manually.',
                      'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      'latest_release': None, 'update_url': self.home}
            try:
                self.remote_status(report)
            except (OSError, ValueError, KeyError, TypeError) as error:
                report.update(status='error', message='Could not check for updates: ' + str(error))
            self.report = report
            self.last_check = time.monotonic()
            return self.snapshot()
        finally:
            self.lock.release()

    def remote_status(self, report):
        if not self.home:
            report.update(status='unsupported', message='The tracked Git remote is not on GitHub. Check that remote manually.')
            return
        repository = repository_name(self.installed['repository'])
        release = api_json(repository, '/releases/latest')
        if release and isinstance(release.get('tag_name'), str):
            tag = release['tag_name']
            report['latest_release'] = {'tag': tag, 'url': self.home + '/releases/tag/' + urllib.parse.quote(tag, safe='')}
        commit = self.installed.get('commit')
        branch = self.installed.get('remote_branch')
        if branch and commit:
            target = branch
            report['update_url'] = self.home + '/tree/' + urllib.parse.quote(branch, safe='')
        elif commit and report['latest_release']:
            target = 'refs/tags/' + report['latest_release']['tag']
            report['update_url'] = report['latest_release']['url']
        elif self.installed.get('version') and report['latest_release']:
            report['update_url'] = report['latest_release']['url']
            report['message'] = 'Latest release: ' + report['latest_release']['tag'] + '. This folder has no Git revision; compare releases manually.'
            return
        else:
            return
        latest = api_json(repository, '/commits/' + urllib.parse.quote(target, safe=''))
        if not latest:
            report.update(status='unknown', message='Repository or tracked branch/tag is unavailable. It may be private, unpublished, or deleted.')
            return
        remote_commit = latest['sha']
        if not all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{40,64}', value) for value in (commit, remote_commit)):
            raise ValueError('Unexpected commit identifier')
        report['remote_commit'] = remote_commit
        if commit == remote_commit:
            report.update(status='current', message='The installed commit matches ' + target + ' on GitHub.')
            return
        comparison = api_json(repository, '/compare/' + commit + '...' + remote_commit + '?per_page=1')
        if not comparison:
            report.update(status='unknown', message='The installed commit cannot be compared with GitHub. It may be an unpublished local commit.')
            return
        status = comparison.get('status')
        if status == 'ahead':
            report.update(status='available', message='An update is available on ' + target + '.',
                          ahead_by=comparison.get('ahead_by'), update_url=self.home + '/compare/' + commit + '...' + remote_commit)
        elif status == 'behind':
            report.update(status='ahead', message='Your installed commit is ahead of GitHub. No fast-forward update is available.')
        elif status == 'diverged':
            report.update(status='diverged', message='Your installed commit and GitHub have diverged. Review changes manually; do not reset your checkout.')
        elif status == 'identical':
            report.update(status='current', message='The installed commit matches GitHub.')
        else:
            raise ValueError('Unexpected GitHub comparison status')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Record the source revision deployed into the HMI VM')
    parser.add_argument('--write', type=pathlib.Path, required=True)
    options = parser.parse_args()
    configuration = json.loads((HERE / 'update-config.json').read_text())
    document = source_version(HERE.parent, configuration)
    options.write.write_text(json.dumps(document, indent=2) + '\n')
