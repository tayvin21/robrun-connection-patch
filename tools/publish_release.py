"""Build, verify and publish a release.

    python tools/publish_release.py             dry run: tests, clean build, Defender scan, shows what it would publish
    python tools/publish_release.py --publish   also pins Bootstrap.ps1, pushes main and creates the GitHub release
    add --prerelease to publish as a pre-release; the default is a normal release that GitHub marks "Latest"

Needs git, the GitHub CLI (`gh`, logged in) and Windows Defender. The version comes from the VERSION file; the
release notes come from the matching section of CHANGELOG.md. Nothing is published without --publish.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPO = 'tayvin21/robrun-connection-patch'
ASSET = 'ROB-RUN-Connection-Patch.zip'
DEFENDER = Path(r'C:\Program Files\Windows Defender\MpCmdRun.exe')
DISCLAIMER = 'UNOFFICIAL EXPERIMENTAL PATCH. Could get you banned. No safety or reliability guarantee. Not approved by Kefir or Easy Anti-Cheat.'


def run(*cmd, cwd=ROOT, check=True):
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and done.returncode:
        sys.exit(f'FAILED: {" ".join(map(str, cmd))}\n{done.stdout}{done.stderr}')
    return done.stdout.strip()


def changelog_section(version):
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    match = re.search(rf'^## v{re.escape(version)}\s*\n(.*?)(?=^## |\Z)', text, re.S | re.M)
    if not match or not match.group(1).strip():
        sys.exit(f'CHANGELOG.md has no section "## v{version}".')
    return match.group(1).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--publish', action='store_true', help='actually push and create the release')
    parser.add_argument('--title', default='', help='short title after the version, e.g. "Live console view"')
    parser.add_argument('--prerelease', action='store_true', help='mark the release as a pre-release instead of Latest')
    opt = parser.parse_args()

    version = (ROOT / 'VERSION').read_text(encoding='ascii').strip()
    if not re.fullmatch(r'[0-9]{1,3}[.][0-9]{1,3}[.][0-9]{1,4}', version):
        sys.exit('VERSION is not MAJOR.MINOR.PATCH.')
    tag = 'v' + version
    notes = changelog_section(version)
    print(f'Release {tag}')

    if run('git', 'status', '--porcelain'):
        sys.exit('Working tree is not clean. Commit or stash first: the build is made from HEAD.')
    if run('git', 'rev-parse', '--abbrev-ref', 'HEAD') != 'main':
        sys.exit('Not on main.')
    if subprocess.run(['gh', 'release', 'view', tag, '-R', REPO], cwd=ROOT, capture_output=True).returncode == 0:
        sys.exit(f'{tag} already exists on GitHub. Bump VERSION.')

    print('Running tests ...')
    tests = subprocess.run([sys.executable, '-W', 'ignore', '-m', 'unittest', 'discover', '-s', 'tests'], cwd=ROOT, capture_output=True, text=True)
    if tests.returncode:
        sys.exit('Tests failed:\n' + tests.stdout + tests.stderr)
    print('  ' + tests.stderr.strip().splitlines()[-1])

    work = Path(tempfile.mkdtemp(prefix='robrun-release-'))
    try:
        archive = work / 'src.tar'
        run('git', 'archive', '--format=tar', '-o', str(archive), 'HEAD')
        tree = work / 'tree'
        tree.mkdir()
        shutil.unpack_archive(archive, tree)
        cache = ROOT / 'build' / 'downloads'
        if cache.exists():
            shutil.copytree(cache, tree / 'build' / 'downloads')
        print('Building from HEAD ...')
        run(sys.executable, 'build_release.py', cwd=tree)
        zip_path = tree / 'build' / ASSET
        digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        size = zip_path.stat().st_size
        print(f'  {ASSET}: {size} bytes, SHA-256 {digest}')

        print('Scanning with Microsoft Defender ...')
        scan = run(str(DEFENDER), '-Scan', '-ScanType', '3', '-File', str(zip_path), '-DisableRemediation', check=False)
        if 'found no threats' not in scan:
            sys.exit('Defender did not report a clean scan:\n' + scan)
        print('  found no threats (not a safety guarantee)')

        body = (f'{DISCLAIMER}\n\n{notes}\n\nSHA-256 of {ASSET}: {digest}\n'
                'The ZIP was scanned clean by Microsoft Defender before upload. That is not a safety guarantee. '
                'Older versions stay available for old links.\n')
        notes_file = work / 'notes.md'
        notes_file.write_text(body, encoding='utf-8')

        if not opt.publish:
            print('\nDry run complete. Release notes that would be published:\n')
            print(body)
            print('Run again with --publish to pin Bootstrap.ps1, push main and create the release.')
            return

        bootstrap = ROOT / 'tools' / 'Bootstrap.ps1'
        text = bootstrap.read_text(encoding='utf-8')
        pinned = re.sub(r"\$version = '[^']*'", f"$version = '{version}'", text, count=1)
        pinned = re.sub(r"\$expectedHash = '[^']*'", f"$expectedHash = '{digest}'", pinned, count=1)
        if pinned != text:
            bootstrap.write_text(pinned, encoding='utf-8', newline='')
            run('git', 'add', 'tools/Bootstrap.ps1')
            run('git', 'commit', '-m', f'Pin the source-tree launcher to {tag}')
        run('git', 'push', 'origin', 'main')
        run('gh', 'release', 'create', tag, str(zip_path), '-R', REPO, '--prerelease' if opt.prerelease else '--latest', '--target', 'main',
            '--title', f'{tag} - {opt.title}' if opt.title else tag, '--notes-file', str(notes_file))
        info = json.loads(run('gh', 'release', 'view', tag, '-R', REPO, '--json', 'assets'))
        uploaded = info['assets'][0].get('digest', '')
        if uploaded != 'sha256:' + digest:
            sys.exit(f'UPLOADED DIGEST DOES NOT MATCH ({uploaded}). Inspect the release before anyone installs it.')
        print(f'Published {tag}; uploaded digest verified.')
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
