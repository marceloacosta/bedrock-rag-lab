"""Run a new comparison in an isolated directory; recorded evidence is read-only."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab-root', type=Path, default=ROOT)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--run-id')
    group.add_argument('--new-run', action='store_true')
    parser.add_argument('command', choices=['pin','validate','prepare','pilot','run','check','cleanup'])
    args = parser.parse_args()
    lab_root = args.lab_root.resolve()
    if args.command == 'pin':
        config = json.loads((lab_root/'config.local.json').read_text())
        if config.get('profile') != 'decodingai-lab':
            raise RuntimeError('An isolated decodingai-lab profile is required')
        spec = importlib.util.spec_from_file_location('isolated_lab_access', lab_root/'aws_access.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        sdk, options = module.session(config)
        caller = sdk.client('sts', config=options).get_caller_identity()
        if caller['Account'] != config['expected_account_id'] or caller['Arn'].endswith(':root'):
            raise RuntimeError('Wrong account or root principal')
        path = lab_root/'private/login-details.json'
        identity = {'expected_account_id':caller['Account'],'expected_principal_arn':caller['Arn']}
        if path.exists():
            saved = json.loads(path.read_text())
            if any(saved.get(k)!=v for k,v in identity.items()):
                raise RuntimeError('Existing principal pin differs; no automatic replacement')
        else:
            path.write_text(json.dumps(identity,indent=2)+'\n');path.chmod(0o600)
        print('Verified dedicated account and saved its non-root principal privately.')
        return
    import experiment
    experiment.LAB_ROOT = lab_root
    sys.argv = [sys.argv[0],args.command]
    if args.run_id:
        sys.argv += ['--run-id', args.run_id]
    if args.new_run:
        sys.argv += ['--new-run']
    experiment.main()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error':type(exc).__name__,'message':'Operation stopped; verify local configuration without exposing credentials.'}))
        raise SystemExit(1)
