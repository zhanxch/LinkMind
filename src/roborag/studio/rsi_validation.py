"""Command-based RSI validators and their machine-readable receipts."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

CHECK_ID = re.compile(r'[a-z][a-z0-9_-]{0,39}\Z')


@dataclass(frozen=True)
class Validator:
    id: str
    label: str
    argv: tuple[str, ...]
    required: bool = True
    timeout: int = 60


def validators_from(path):
    """Read an explicitly supplied manifest. Reading the Board never calls this."""
    if path is None:
        return ()
    with Path(path).open('rb') as source:
        data = json.loads(source.read(64 * 1024))
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('Validator manifest requires version 1')
    entries = data.get('validators')
    if not isinstance(entries, list) or len(entries) > 16:
        raise ValueError('Expected up to 16 validator entries')
    validators, ids = [], {'native-smoke','validator-preparation'}
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError('Invalid validator entry')
        ident, argv = item.get('id'), item.get('argv')
        label = item.get('label', ident)
        required, timeout = item.get('required', True), item.get('timeout_seconds', 60)
        if not isinstance(ident, str) or not CHECK_ID.fullmatch(ident) or ident in ids:
            raise ValueError('Duplicate, reserved or invalid validator ID')
        if (not isinstance(label, str) or not label.strip() or len(label) > 100 or
            not isinstance(argv, list) or not 1 <= len(argv) <= 64 or
            any(not isinstance(a, str) or '\0' in a or len(a) > 4096 for a in argv) or not argv[0].strip()):
            raise ValueError(f'Invalid command for validator {ident}')
        if type(required) is not bool or type(timeout) is not int or not 1 <= timeout <= 3600:
            raise ValueError(f'Invalid policy or timeout for validator {ident}')
        ids.add(ident)
        validators.append(Validator(ident, label, tuple(argv), required, timeout))
    return tuple(validators)


def run_validators(validators, candidate, output, notify, *, version='', variables=None):
    """Run checks in candidate cwd. notify is called before and after every command."""
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    replacements = {'{candidate}': str(Path(candidate).resolve()), **(variables or {})}
    for check in validators:
        notify(check, 'pending', '', None, None)
    blocked = []
    for check in validators:
        log_path = output / (check.id + '.log')
        receipt = output / (check.id + '.json')
        argv = []
        for arg in check.argv:
            for token, value in replacements.items():
                arg = arg.replace(token, str(value))
            argv.append(arg)
        notify(check, 'running', '', None, None)
        started = time.monotonic()
        code = None
        with log_path.open('wb') as log:
            try:
                child = subprocess.Popen(argv, cwd=candidate, stdin=subprocess.DEVNULL,
                                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = child.wait(timeout=check.timeout)
                except BaseException:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.wait()
                    raise
                status, reason = ('passed', '') if code == 0 else ('failed', f'退出码 {code}')
            except subprocess.TimeoutExpired:
                status, reason = 'error', f'超过 {check.timeout} 秒'
            except OSError as exc:
                status, reason = 'error', exc.strerror or type(exc).__name__
        if check.required and status != 'passed':
            blocked.append(check.id)
        value = dict(id=check.id, label=check.label, required=check.required, candidate_version=version,
                     argv=argv, timeout_seconds=check.timeout, elapsed_seconds=round(time.monotonic()-started,3),
                     status=status, reason=reason, exit_code=code, log=log_path.name)
        temporary = receipt.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
        temporary.replace(receipt)
        notify(check, status, reason, receipt, log_path)
    return blocked
