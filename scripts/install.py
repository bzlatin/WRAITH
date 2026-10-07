#!/usr/bin/env python3
"""Install a verified native Wraith release. Python 3.10+, no third-party packages."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile

MAX_BYTES = 256 * 1024 * 1024


def native_target():
    machine = platform.machine().lower()
    system = platform.system()
    if system == 'Darwin' and machine in ('arm64', 'aarch64'):
        return 'aarch64-apple-darwin'
    if system == 'Darwin' and machine in ('x86_64', 'amd64'):
        return 'x86_64-apple-darwin'
    if system == 'Linux' and machine in ('x86_64', 'amd64'):
        return 'x86_64-unknown-linux-gnu'
    if system == 'Windows' and machine in ('x86_64', 'amd64'):
        return 'x86_64-pc-windows-msvc'
    raise ValueError(f'No packaged binary for {system}/{machine}; use a supported archive or build from source')


def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Wraith-installer'})
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError('Download exceeded 256 MiB')
    return content


def install(archive, checksum, version, target, directory):
    if not re.fullmatch(r'[0-9a-fA-F]{64}', checksum) or hashlib.sha256(archive).hexdigest() != checksum.lower():
        raise ValueError('Archive SHA-256 verification failed; nothing installed')
    prefix = f'wraith-{version}-{target}'
    executable = 'wraith.exe' if 'windows' in target else 'wraith'
    if 'windows' in target:
        with zipfile.ZipFile(io.BytesIO(archive)) as container:
            metadata = json.loads(container.read(prefix + '/RELEASE.json'))
            binary = container.read(prefix + '/' + executable)
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as container:
            member = container.getmember(prefix + '/' + executable)
            info = container.getmember(prefix + '/RELEASE.json')
            if not member.isfile() or not info.isfile():
                raise ValueError('Expected regular binary and metadata members')
            if member.size > MAX_BYTES or info.size > 65536:
                raise ValueError('Archive members exceed supported size')
            metadata = json.load(container.extractfile(info))
            binary = container.extractfile(member).read()
    if metadata.get('version') != version or metadata.get('target') != target or metadata.get('binarySha256') != hashlib.sha256(binary).hexdigest():
        raise ValueError('Binary metadata verification failed; nothing installed')
    directory = Path(directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / executable
    fd, temporary = tempfile.mkstemp(prefix='.wraith-install-', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(binary)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary, 0o755)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True, help='Published version, e.g. 0.5.0')
    parser.add_argument('--directory', type=Path, default=Path.home() / '.local/bin')
    parser.add_argument('--repository', default='bzlatin/WRAITH')
    parser.add_argument('--target', default=None)
    parser.add_argument('--archive', type=Path, help='Use a local native archive instead of downloading')
    parser.add_argument('--checksum', type=Path, help='Local SHA-256 sidecar, required with --archive')
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', args.version):
        parser.error('--version must be a release version')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository):
        parser.error('--repository must be owner/name')
    try:
        target = args.target or native_target()
        if not re.fullmatch(r'[A-Za-z0-9_-]+', target):
            raise ValueError('Invalid target')
        if args.archive:
            if not args.checksum:
                raise ValueError('--archive requires --checksum')
            archive = args.archive.read_bytes()
            checksum = args.checksum.read_text().split()[0]
        else:
            filename = f'wraith-{args.version}-{target}' + ('.zip' if 'windows' in target else '.tar.gz')
            base = f'https://github.com/{args.repository}/releases/download/v{args.version}/'
            archive = download(base + filename)
            checksum = download(base + filename + '.sha256').decode().split()[0]
        installed = install(archive, checksum, args.version, target, args.directory)
        print(f'Installed {installed}\nAdd {installed.parent} to PATH, then run wraith --version and wraith init. Shell profiles were not edited.')
    except (OSError, ValueError, KeyError, IndexError, tarfile.TarError, zipfile.BadZipFile, urllib.error.URLError) as error:
        parser.exit(2, f'Install failed: {error}\nCheck that v{args.version} has published assets for your platform, or use --archive and --checksum.\n')
