"""CLI for the Knowledge Base experiment, using only an explicitly pinned account."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent


class Lab:
    def __init__(self, lab_root=ROOT):
        self.root = Path(lab_root).resolve()
        self.private = self.root / 'private'
        self.private.mkdir(mode=0o700, exist_ok=True)
        self.config = json.loads((self.root / 'config.local.json').read_text())
        if self.config.get('region') != 'us-east-2' or self.config.get('model_id') != 'zai.glm-5':
            raise ValueError('This experiment requires GLM 5 in us-east-2')
        spec = importlib.util.spec_from_file_location('pinned_account_access', self.root / 'aws_access.py')
        access = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(access)
        self.sdk, self.options = access.session(self.config)
        self.clients = {}
        self.verify()
        self.plan = access.plan_state(self.sdk, self.options)

    def verify(self):
        caller = self.sdk.client('sts', config=self.options).get_caller_identity()
        if caller.get('Account') != self.config['expected_account_id'] or caller.get('Arn', '').endswith(':root'):
            raise RuntimeError('Account mismatch or root credentials; no operation executed')

    def call(self, service, method, **parameters):
        self.verify()
        if service not in self.clients:
            self.clients[service] = self.sdk.client(service, config=self.options)
        began = time.perf_counter()
        result = getattr(self.clients[service], method)(**parameters)
        self.last_api_seconds = time.perf_counter() - began
        return result

