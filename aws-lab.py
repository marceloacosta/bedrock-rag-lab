#!/usr/bin/env python3
"""Run the CLI against this experiment's isolated config, never ~/.aws."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / "private"
CLI = Path(os.environ.get("DECODINGAI_AWS_CLI") or shutil.which("aws") or "missing-aws-cli")
PROFILE = "decodingai-lab"

def isolated_env():
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    (PRIVATE / "login-cache").mkdir(mode=0o700, exist_ok=True)
    config = PRIVATE / "aws-config"
    if not config.exists():
        config.write_text("[profile decodingai-lab]\nregion = us-east-2\noutput = json\n")
        config.chmod(0o600)
    credentials = PRIVATE / "aws-credentials"
    if not credentials.exists():
        credentials.touch(mode=0o600)
    env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_")}
    env.update({"AWS_CONFIG_FILE": str(config),
                "AWS_SHARED_CREDENTIALS_FILE": str(credentials),
                "AWS_LOGIN_CACHE_DIRECTORY": str(PRIVATE / "login-cache"),
                "AWS_PROFILE": PROFILE, "AWS_REGION": "us-east-2",
                "AWS_DEFAULT_REGION": "us-east-2", "AWS_PAGER": "",
                "AWS_EC2_METADATA_DISABLED": "true", "AWS_MAX_ATTEMPTS": "1"})
    return env

if __name__ == "__main__":
    args = sys.argv[1:]
    if any(a == "--profile" or a.startswith("--profile=") for a in args):
        raise SystemExit("This wrapper only permits the decodingai-lab profile.")
    if not CLI.exists():
        raise SystemExit("Install AWS CLI v2.32 or newer, or set DECODINGAI_AWS_CLI.")
    env = isolated_env()
    # Login and credential export establish identity; all service commands must
    # pass an explicit STS check using the same isolated environment first.
    if args and args[0] not in ('login', 'logout', 'configure', '--version', 'help'):
        local = ROOT / 'config.local.json'
        if not local.exists():
            raise SystemExit('Set the explicit expected account ID before service commands.')
        expected = json.loads(local.read_text()).get('expected_account_id')
        identity = subprocess.run([str(CLI), '--profile', PROFILE, 'sts', 'get-caller-identity',
                                   '--output', 'json'], env=env, capture_output=True, text=True, timeout=60)
        if identity.returncode:
            raise SystemExit('Cannot verify isolated account identity. No service command executed.')
        caller = json.loads(identity.stdout)
        if caller.get('Account') != expected or caller.get('Arn', '').endswith(':root'):
            raise SystemExit('Unexpected AWS account or root identity. Service command blocked.')
    os.execve(str(CLI), [str(CLI), "--profile", PROFILE, *args], env)
