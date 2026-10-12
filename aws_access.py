"""AWS access pinned to a single isolated profile; never use ambient credentials."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def session(config):
    import boto3
    from botocore.config import Config
    result = subprocess.run(
        [sys.executable, str(ROOT / "aws-lab.py"), "configure", "export-credentials", "--format", "process"],
        capture_output=True, text=True, check=False, timeout=60)
    if result.returncode:
        raise RuntimeError("Isolated CLI authentication failed. Run aws-lab.py login.")
    credentials = json.loads(result.stdout)
    sdk = boto3.Session(aws_access_key_id=credentials["AccessKeyId"],
                        aws_secret_access_key=credentials["SecretAccessKey"],
                        aws_session_token=credentials["SessionToken"],
                        region_name=config["region"])
    options = Config(retries={"total_max_attempts": 1}, connect_timeout=10, read_timeout=90)
    caller = sdk.client("sts", config=options).get_caller_identity()
    if caller["Account"] != config["expected_account_id"]:
        raise RuntimeError("Wrong AWS account. No experiment calls allowed.")
    if caller["Arn"].endswith(":root"):
        raise RuntimeError("Root credentials are not permitted for the experiment.")
    return sdk, options

def plan_state(sdk, options):
    state = sdk.client("freetier", config=options).get_account_plan_state()
    credits = state.get("accountPlanRemainingCredits", {})
    public = {"account_matches": True,
              "plan": state.get("accountPlanType"),
              "status": state.get("accountPlanStatus"),
              "remaining_credits": credits,
              "expires_at": str(state.get("accountPlanExpirationDate"))}
    if public["plan"] != "FREE" or public["status"] != "ACTIVE":
        raise RuntimeError("The test requires an active Free plan. No model calls allowed.")
    return public

