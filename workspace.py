"""Choose isolated run directories without touching recorded evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid


def fresh_id():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]


def select_run(root, lab_root, command, run_id=None, new_run=False):
    root, lab_root = Path(root).resolve(), Path(lab_root).resolve()
    pointer = lab_root / 'private/active-experiment-run.json'
    runs = root / 'measurements/runs'
    if runs.is_symlink():
        raise ValueError('The fresh-run directory cannot be a symlink')
    if run_id and new_run:
        raise ValueError('Choose --run-id or --new-run, not both')
    if new_run and command not in {'check', 'prepare'}:
        raise ValueError('Start a new run with check or prepare')
    if not run_id and not new_run and pointer.exists():
        run_id = json.loads(pointer.read_text())['run_id']
    if not run_id:
        if command not in {'check', 'prepare'}:
            raise ValueError('No active run; start with check or prepare, or specify --run-id')
        run_id = fresh_id()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', run_id):
        raise ValueError('Run IDs must be simple names, not paths')
    output = runs / run_id
    if output.is_symlink() or output.resolve().parent != runs.resolve():
        raise ValueError('Run directory must stay inside measurements/runs')
    if not output.exists():
        if command not in {'check', 'prepare'}:
            raise ValueError('Unknown run; start it with check or prepare')
        output.mkdir(parents=True, exist_ok=False)
    ensure_command_allowed(output, command)
    pointer.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    pointer.write_text(json.dumps({'run_id': run_id}) + '\n')
    pointer.chmod(0o600)
    return output


def ensure_command_allowed(output, command):
    output = Path(output)
    if command == 'prepare' and any((output / name).exists() for name in
                                    ('manifest.json', 'development.json')):
        raise ValueError('This run is already prepared or frozen; resume it or use --new-run')


def state_path(lab, output):
    folder = lab.private / 'experiment-runs' / Path(output).name
    folder.mkdir(parents=True, mode=0o700, exist_ok=True)
    return folder / 'kb-state.json'
