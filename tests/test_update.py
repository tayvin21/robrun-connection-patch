import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GOOD_URL = 'https://github.com/tayvin21/robrun-connection-patch/releases/download/v9.9.9/ROB-RUN-Connection-Patch.zip'


def make_zip(path, version='9.9.9', extra=None):
    files = {'app/VERSION': version, 'app/a.txt': 'hello', 'START.cmd': '@echo off'}
    lines = ''.join(hashlib.sha256(v.encode()).hexdigest() + '  ' + k + '\n' for k, v in sorted(files.items()))
    files['app/SHA256SUMS.txt'] = lines
    with zipfile.ZipFile(path, 'w') as z:
        for name, text in files.items():
            z.writestr('ROB-RUN-Connection-Patch/' + name, text)
        for name, text in (extra or {}).items():
            z.writestr(name, text)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def release(tag='v9.9.9', digest='', url=GOOD_URL, size=1000, draft=False, asset='ROB-RUN-Connection-Patch.zip'):
    return {'tag_name': tag, 'draft': draft, 'html_url': 'https://github.com/x/releases/' + tag, 'body': 'Notes line one.',
            'assets': [{'name': asset, 'size': size, 'digest': ('sha256:' + digest) if digest else None, 'browser_download_url': url}]}


@unittest.skipUnless(os.name == 'nt' and shutil.which('powershell'), 'needs Windows PowerShell')
class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.app = base / 'inst' / 'ROB-RUN-Connection-Patch' / 'app'
        self.app.mkdir(parents=True)
        shutil.copy(ROOT / 'Update.ps1', self.app / 'Update.ps1')
        (self.app / 'VERSION').write_text('0.3.0')
        (self.app / 'settings.json').write_text('{"unicode":false,"check_updates":true}')
        self.zip = base / 'pkg.zip'
        self.digest = make_zip(self.zip)
        self.feed = base / 'feed.json'
        self.parent = base / 'inst'

    def tearDown(self):
        self.tmp.cleanup()

    def run_update(self, mode, releases, zip_path=None, stdin='', feed=True):
        self.feed.write_text(json.dumps(releases))
        cmd = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(self.app / 'Update.ps1'), '-Mode', mode]
        if feed:
            cmd += ['-FeedFile', str(self.feed)]
        if zip_path:
            cmd += ['-LocalZip', str(zip_path)]
        done = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=120)
        return done.returncode, done.stdout + done.stderr

    def installed(self):
        return sorted(p.name for p in self.parent.iterdir() if p.name.startswith('ROB-RUN-Connection-Patch-v'))

    def test_check_reports_newer_release(self):
        code, out = self.run_update('Check', [release(digest=self.digest)])
        self.assertIn('Update available: v9.9.9', out)
        self.assertIn('this is v0.3.0', out)

    def test_check_ignores_drafts_foreign_tags_and_assetless_releases(self):
        releases = [release('v10.0.0', digest=self.digest, draft=True), release('nightly', digest=self.digest),
                    release('v11.0.0', digest=self.digest, asset='other.zip'), release('v0.3.0', digest=self.digest)]
        code, out = self.run_update('Check', releases)
        self.assertIn('Up to date (v0.3.0)', out)

    def test_check_is_silent_when_the_user_turned_checks_off(self):
        (self.app / 'settings.json').write_text('{"check_updates":false}')
        code, out = self.run_update('Check', [release(digest=self.digest)], feed=False)
        self.assertEqual(out.strip(), '')

    def test_install_verifies_unpacks_next_to_the_old_copy_and_keeps_settings(self):
        code, out = self.run_update('Install', [release(digest=self.digest)], self.zip, stdin='Y\n')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.installed(), ['ROB-RUN-Connection-Patch-v9.9.9'])
        new = self.parent / 'ROB-RUN-Connection-Patch-v9.9.9' / 'app'
        self.assertEqual((new / 'VERSION').read_text(), '9.9.9')
        self.assertIn('"check_updates":true', (new / 'settings.json').read_text())
        self.assertEqual((self.app / 'VERSION').read_text(), '0.3.0')

    def test_install_can_be_declined(self):
        code, out = self.run_update('Install', [release(digest=self.digest)], self.zip, stdin='N\n')
        self.assertIn('Cancelled', out)
        self.assertEqual(self.installed(), [])

    def test_wrong_digest_is_refused_before_unpacking(self):
        code, out = self.run_update('Install', [release(digest='0' * 64)], self.zip, stdin='Y\n')
        self.assertNotEqual(code, 0)
        self.assertIn('does not match the published SHA-256', out)
        self.assertEqual(self.installed(), [])

    def test_release_without_a_digest_is_refused(self):
        code, out = self.run_update('Install', [release(digest='')], self.zip, stdin='Y\n')
        self.assertNotEqual(code, 0)
        self.assertIn('publishes no SHA-256', out)
        self.assertEqual(self.installed(), [])

    def test_digest_in_release_notes_is_accepted_as_a_fallback(self):
        item = release(digest='')
        item['body'] = f'Notes.\nSHA-256 of ROB-RUN-Connection-Patch.zip: {self.digest}\n'
        code, out = self.run_update('Install', [item], self.zip, stdin='Y\n')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.installed(), ['ROB-RUN-Connection-Patch-v9.9.9'])

    def test_archive_that_escapes_its_folder_is_refused(self):
        bad = Path(self.tmp.name) / 'bad.zip'
        digest = make_zip(bad, extra={'../evil.txt': 'x'})
        code, out = self.run_update('Install', [release(digest=digest)], bad, stdin='Y\n')
        self.assertNotEqual(code, 0)
        self.assertIn('Unexpected archive contents', out)
        self.assertEqual(self.installed(), [])
        self.assertFalse((self.parent.parent / 'evil.txt').exists())

    def test_package_version_must_match_its_release_tag(self):
        wrong = Path(self.tmp.name) / 'wrong.zip'
        digest = make_zip(wrong, version='9.9.8')
        code, out = self.run_update('Install', [release(digest=digest)], wrong, stdin='Y\n')
        self.assertNotEqual(code, 0)
        self.assertIn('does not match its release tag', out)
        self.assertEqual(self.installed(), [])

    def test_download_address_outside_the_project_is_refused(self):
        code, out = self.run_update('Install', [release(digest=self.digest, url='https://evil.example/pkg.zip')], stdin='Y\n')
        self.assertNotEqual(code, 0)
        self.assertIn('Refusing a download address', out)

    def test_existing_target_folder_is_never_overwritten(self):
        (self.parent / 'ROB-RUN-Connection-Patch-v9.9.9').mkdir()
        code, out = self.run_update('Install', [release(digest=self.digest)], self.zip, stdin='Y\n')
        self.assertNotEqual(code, 0)
        self.assertIn('already exists', out)


class VersionTests(unittest.TestCase):
    def test_version_file_is_semver_and_matches_the_program(self):
        text = (ROOT / 'VERSION').read_text(encoding='ascii').strip()
        self.assertRegex(text, r'^[0-9]{1,3}[.][0-9]{1,3}[.][0-9]{1,4}$')
        import sys
        sys.path.insert(0, str(ROOT))
        import patch
        self.assertEqual(patch.VERSION, text)

    def test_changelog_has_an_entry_for_this_version(self):
        text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
        version = (ROOT / 'VERSION').read_text(encoding='ascii').strip()
        self.assertIn(f'## v{version}', text)


if __name__ == '__main__':
    unittest.main()
