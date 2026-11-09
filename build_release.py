"""Build the Windows package from pinned dependencies."""
import hashlib
from pathlib import Path
import shutil
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parent
VENDORS = {
    'python': ('https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip', '90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'),
    'wintun': ('https://www.wintun.net/builds/wintun-0.14.1.zip', '07c256185d6ee3652e09fa55c0b673e2624b565e02c4b9091c79ca7d2f24ef51'),
}
FILES = ['START.cmd', 'UNINSTALL.cmd', 'DEMO-CONSOLE.cmd', 'DEMO-WEB.cmd', 'DASHBOARD.cmd', 'Launch.ps1', 'Controls.ps1', 'patch.py', 'transport.py',
         'diagnostics.py', 'dashboard.py', 'console.py', 'demo.py', 'README.md', 'LICENSE', 'THIRD-PARTY.md']
ROOT_FILES = ('START.cmd', 'UNINSTALL.cmd', 'DEMO-CONSOLE.cmd', 'DEMO-WEB.cmd', 'DASHBOARD.cmd')
RUNTIME_FILES = {'python.exe','python314.dll','python3.dll','python314.zip','python314._pth',
                 'vcruntime140.dll','vcruntime140_1.dll','_ctypes.pyd','libffi-8.dll',
                 '_socket.pyd','select.pyd','LICENSE.txt'}


def main():
    downloads = ROOT / 'build' / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    stage = ROOT / 'build' / 'ROB-RUN-Connection-Patch'
    if stage.exists():
        raise SystemExit('Staging directory already exists; use a fresh build directory after reviewing old artifacts.')
    stage.mkdir()
    app = stage / 'app'
    app.mkdir()
    for name in FILES:
        destination = stage / name if name in ROOT_FILES else app / name
        if name == 'README.md': destination = app / 'README.txt'
        shutil.copy2(ROOT / name, destination)
    shutil.copytree(ROOT / 'ui', app / 'ui')
    for name, (url, expected) in VENDORS.items():
        archive = downloads / (name + '.zip')
        if not archive.exists():
            with urlopen(url, timeout=45) as response:
                data = response.read(32 * 1024 * 1024 + 1)
            if len(data) > 32 * 1024 * 1024:
                raise ValueError('Vendor archive exceeds download limit')
            archive.write_bytes(data)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            raise ValueError('Vendor archive hash mismatch: ' + name)
        with zipfile.ZipFile(archive) as z:
            if name == 'python':
                runtime = app / 'runtime'
                runtime.mkdir()
                for entry in z.infolist():
                    if '/' in entry.filename or '\\' in entry.filename or entry.file_size > 30 * 1024 * 1024:
                        raise ValueError('Unexpected embedded runtime entry')
                    if entry.filename in RUNTIME_FILES:
                        (runtime / entry.filename).write_bytes(z.read(entry))
                (runtime / 'python314._pth').write_text('python314.zip\n.\n..\n', encoding='ascii')
            else:
                (app / 'wintun.dll').write_bytes(z.read('wintun/bin/amd64/wintun.dll'))
                (app / 'WINTUN-LICENSE.txt').write_bytes(z.read('wintun/LICENSE.txt'))
    paths = sorted(p for p in stage.rglob('*') if p.is_file())
    (app / 'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(stage).as_posix() + '\n' for p in paths), encoding='ascii')
    output = ROOT / 'build' / 'ROB-RUN-Connection-Patch.zip'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                z.write(path, stage.name + '/' + path.relative_to(stage).as_posix())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (ROOT / 'build' / 'SHA256SUMS.txt').write_text(digest + '  ' + output.name + '\n', encoding='ascii')
    print(output)
    print(digest)


if __name__ == '__main__':
    main()
