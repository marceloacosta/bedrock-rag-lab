"""Offline regression tests for preserving recorded evidence and isolating fresh runs."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import experiment as runner
from workspace import select_run, state_path


class RunSafety(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.lab_root = self.root / 'lab'
        self.lab = SimpleNamespace(private=self.lab_root / 'private')

    def test_default_run_is_new_and_resume_uses_same_directory(self):
        recorded = self.root / 'measurements/recorded'
        recorded.mkdir(parents=True)
        sentinel = recorded / 'preflight.json'
        sentinel.write_text('recorded')
        output = select_run(self.root, self.lab_root, 'check')
        self.assertEqual(output.parent, self.root / 'measurements/runs')
        self.assertEqual(select_run(self.root, self.lab_root, 'prepare'), output)
        second = select_run(self.root, self.lab_root, 'check', new_run=True)
        self.assertNotEqual(output, second)
        self.assertNotEqual(state_path(self.lab, output), state_path(self.lab, second))
        self.assertEqual(sentinel.read_text(), 'recorded')

    def test_prepare_rejects_correct_manifest_path_before_any_cloud_work(self):
        output = select_run(self.root, self.lab_root, 'prepare')
        (output / 'manifest.json').write_text('{}')
        with patch.object(runner, 'OUT', output), patch.object(runner, 'preflight') as preflight, patch.object(runner, 'provision') as provision:
            with self.assertRaises(ValueError):
                runner.prepare(self.lab)
            preflight.assert_not_called()
            provision.assert_not_called()
        with self.assertRaises(ValueError):
            select_run(self.root, self.lab_root, 'prepare')

    def test_prepared_development_is_not_overwritten_before_freezing(self):
        output = select_run(self.root, self.lab_root, 'prepare')
        (output / 'development.json').write_text('saved selection')
        with self.assertRaises(ValueError):
            select_run(self.root, self.lab_root, 'prepare')
        self.assertEqual((output / 'development.json').read_text(), 'saved selection')

    def test_run_selection_rejects_traversal_symlinks_and_unknown_resume(self):
        for run_id in ['../revision', '/outside', 'nested/run']:
            with self.assertRaises(ValueError):
                select_run(self.root, self.lab_root, 'check', run_id)
        with self.assertRaises(ValueError):
            select_run(self.root, self.lab_root, 'run', 'missing')
        runs = self.root / 'measurements/runs'
        runs.mkdir(parents=True)
        (runs / 'alias').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            select_run(self.root, self.lab_root, 'prepare', 'alias')

    def test_completed_run_does_not_rewrite_completion_or_call_aws(self):
        output = select_run(self.root, self.lab_root, 'check')
        (output / 'run').mkdir()
        complete = output / 'run/complete.json'
        complete.write_text('{"original":true}')
        with patch.object(runner, 'OUT', output), patch.object(runner, 'preflight') as preflight, contextlib.redirect_stdout(io.StringIO()):
            runner.run(self.lab, 'run')
            preflight.assert_not_called()
        self.assertEqual(complete.read_text(), '{"original":true}')

    def test_cleanup_receipt_is_derived_from_events_and_pending_is_not_success(self):
        output = select_run(self.root, self.lab_root, 'check')
        def pending(*args):
            print(json.dumps({'cleanup_pending': True}))
        def complete(*args):
            print(json.dumps({'removed': 'service_role'}))
            print(json.dumps({'cleanup_complete': True, 'account_matches': True}))
        with patch.object(runner, 'OUT', output), contextlib.redirect_stdout(io.StringIO()):
            with patch.object(runner, 'cleanup', side_effect=pending):
                runner.cleanup_run(self.lab)
            self.assertFalse(json.loads((output / 'cleanup.json').read_text())['cleanup_complete'])
            with patch.object(runner, 'cleanup', side_effect=complete):
                runner.cleanup_run(self.lab)
            receipt = json.loads((output / 'cleanup.json').read_text())
            self.assertTrue(receipt['cleanup_complete'])
            self.assertEqual(len(list((output / 'cleanup-events').glob('*.json'))), 2)
            with patch.object(runner, 'cleanup') as cleanup:
                runner.cleanup_run(self.lab)
                cleanup.assert_not_called()

    def test_empty_or_unknown_citations_are_not_valid_support(self):
        for citations, expected in [([], False), (['missing'], False), (['known'], True)]:
            raw = json.dumps({'answer': 'A policy answer.', 'abstain': False, 'citations': citations})
            _, valid = runner.parse_answer(raw, {'known': {'text': 'Policy'}})
            self.assertEqual(valid, expected)

    def test_fresh_report_cannot_overwrite_recorded_files_or_main_viewer(self):
        files = [p for p in (ROOT / 'measurements/recorded').rglob('*') if p.is_file()]
        files += [ROOT / 'explorer/data.js']
        digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        before = {p: digest(p) for p in files}
        output = self.root / 'report'
        command = [sys.executable, str(ROOT / 'tools/report.py'), '--output-dir', str(output)]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        self.assertTrue((output / 'viewer/index.html').exists())
        self.assertEqual(before, {p: digest(p) for p in files})
        repeated = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertNotEqual(repeated.returncode, 0)
        refused = subprocess.run([sys.executable, str(ROOT / 'tools/report.py'), '--output-dir', str(ROOT / 'measurements/recorded')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(before, {p: digest(p) for p in files})


if __name__ == '__main__':
    unittest.main()
