"""Tests for Da Homi automatic updates (v2.2): scripts/update.py.

Covers version comparison, check (up to date, available, older), apply
(file swap, memory and cache preserved, backup made), sha256 refusal,
unsigned refusal and explicit allowance, refusal of a non Da Homi
directory, and no-op when already up to date. No test touches the
network: manifests and packages are local files.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
UPDATE = os.path.join(SCRIPTS, "update.py")

sys.path.insert(0, SCRIPTS)
import update  # noqa: E402


def run_update(*args):
    return subprocess.run([sys.executable, UPDATE, *args],
                          capture_output=True, text=True, timeout=60)


class TestVersionCompare(unittest.TestCase):
    def test_compare(self):
        self.assertEqual(update.compare_versions("2.2", "2.1"), 1)
        self.assertEqual(update.compare_versions("2.10", "2.2"), 1)
        self.assertEqual(update.compare_versions("2.2", "2.2"), 0)
        self.assertEqual(update.compare_versions("2.1", "2.2"), -1)
        self.assertEqual(update.compare_versions("2", "2.0"), 0)


class TestUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.install = os.path.join(self.tmp.name, "da-homi")
        os.makedirs(os.path.join(self.install, "scripts"))
        os.makedirs(os.path.join(self.install, "da-homi-cache"))
        with open(os.path.join(self.install, "SKILL.md"), "w") as f:
            f.write("old skill\n")
        with open(os.path.join(self.install, "scripts", "da_homi.py"), "w") as f:
            f.write("# old da_homi\n")
        with open(os.path.join(self.install, "VERSION"), "w") as f:
            f.write("2.1\n")
        with open(os.path.join(self.install, "DA_HOMI_MEMORY.md"), "w") as f:
            f.write("MY MEMORY KEEP\n")
        with open(os.path.join(self.install, "da-homi-cache", "run.json"), "w") as f:
            f.write("cache keep\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _package(self, version="2.2"):
        """A package zip; returns (zip path, sha256)."""
        pkg = os.path.join(self.tmp.name, f"pkg-{version}.zip")
        with zipfile.ZipFile(pkg, "w") as zf:
            zf.writestr("SKILL.md", "new skill\n")
            zf.writestr("scripts/da_homi.py", "# new da_homi\n")
            zf.writestr("scripts/update.py", "# updater\n")
            zf.writestr("VERSION", version + "\n")
            zf.writestr("DA_HOMI_MEMORY.md", "TEMPLATE, NEVER OVERWRITE\n")
        with open(pkg, "rb") as f:
            return pkg, hashlib.sha256(f.read()).hexdigest()

    def _manifest(self, version, zip_path, sha="SET"):
        path = os.path.join(self.tmp.name, f"manifest-{version}.json")
        data = {"version": version, "download_url": zip_path,
                "notes": "test release"}
        if sha == "SET":
            with open(zip_path, "rb") as f:
                data["sha256"] = hashlib.sha256(f.read()).hexdigest()
        elif sha:
            data["sha256"] = sha
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def test_check_up_to_date(self):
        pkg, _ = self._package("2.1")
        r = run_update("check", "--manifest", self._manifest("2.1", pkg),
                       "--target", self.install)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("UP TO DATE", r.stdout)

    def test_check_update_available(self):
        pkg, _ = self._package("2.2")
        r = run_update("check", "--manifest", self._manifest("2.2", pkg),
                       "--target", self.install)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("UPDATE AVAILABLE", r.stdout)

    def test_check_older_manifest_is_up_to_date(self):
        pkg, _ = self._package("2.0")
        r = run_update("check", "--manifest", self._manifest("2.0", pkg),
                       "--target", self.install)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("UP TO DATE", r.stdout)

    def test_apply_swaps_files_and_preserves_memory_and_cache(self):
        pkg, _ = self._package("2.2")
        r = run_update("apply", "--manifest", self._manifest("2.2", pkg),
                       "--target", self.install)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.install, "SKILL.md")) as f:
            self.assertEqual(f.read(), "new skill\n")
        with open(os.path.join(self.install, "VERSION")) as f:
            self.assertEqual(f.read().strip(), "2.2")
        with open(os.path.join(self.install, "DA_HOMI_MEMORY.md")) as f:
            self.assertEqual(f.read(), "MY MEMORY KEEP\n")
        with open(os.path.join(self.install, "da-homi-cache", "run.json")) as f:
            self.assertEqual(f.read(), "cache keep\n")
        self.assertIn("BACKUP:", r.stdout)
        backup = r.stdout.split("BACKUP:")[1].strip().splitlines()[0]
        with open(os.path.join(backup, "SKILL.md")) as f:
            self.assertEqual(f.read(), "old skill\n")

    def test_apply_refuses_sha_mismatch_and_changes_nothing(self):
        pkg, _ = self._package("2.2")
        r = run_update("apply", "--manifest",
                       self._manifest("2.2", pkg, sha="0" * 64),
                       "--target", self.install)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        with open(os.path.join(self.install, "SKILL.md")) as f:
            self.assertEqual(f.read(), "old skill\n")

    def test_apply_refuses_unsigned_without_flag_and_allows_with_it(self):
        pkg, _ = self._package("2.2")
        manifest = self._manifest("2.2", pkg, sha=None)
        r = run_update("apply", "--manifest", manifest, "--target", self.install)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        with open(os.path.join(self.install, "SKILL.md")) as f:
            self.assertEqual(f.read(), "old skill\n")
        r = run_update("apply", "--manifest", manifest, "--target", self.install,
                       "--allow-unsigned")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.install, "SKILL.md")) as f:
            self.assertEqual(f.read(), "new skill\n")

    def test_apply_refuses_non_dahomi_directory(self):
        plain = os.path.join(self.tmp.name, "plain")
        os.makedirs(plain)
        with open(os.path.join(plain, "README.md"), "w") as f:
            f.write("not da homi\n")
        pkg, _ = self._package("2.2")
        r = run_update("apply", "--manifest", self._manifest("2.2", pkg),
                       "--target", plain)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        with open(os.path.join(plain, "README.md")) as f:
            self.assertEqual(f.read(), "not da homi\n")

    def test_apply_when_up_to_date_changes_nothing(self):
        pkg, _ = self._package("2.1")
        r = run_update("apply", "--manifest", self._manifest("2.1", pkg),
                       "--target", self.install)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("UP TO DATE", r.stdout)
        self.assertNotIn("BACKUP:", r.stdout)


if __name__ == "__main__":
    unittest.main()
