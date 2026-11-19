"""Read actual agent events, independently of the runner's diagnostic stdout.

Files are append-only JSONL. A cursor only advances over complete lines, so a
writer can flush a partial UTF-8 message without losing it. No transcript is
inferred from program logs and no original evidence is modified.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

MAX_LINE = 2 * 1024 * 1024
PAGE_BYTES = 256 * 1024


def validate_source(value):
    if value is None:
        return
    if not isinstance(value, dict) or value.get('format') not in ('codex-jsonl', 'linkmind-events'):
        raise ValueError('conversation needs format codex-jsonl or linkmind-events')
    path = value.get('path')
    if not isinstance(path, str) or not path or '\0' in path or Path(path).is_absolute() or '..' in Path(path).parts:
        raise ValueError('Conversation path must be relative to this run output')


def normalize(event, format, offset):
    """Return a patch for one real message/tool, or provider lifecycle metadata."""
    if not isinstance(event, dict):
        raise ValueError('Event must be an object')
    kind = event.get('type', '')
    if format == 'linkmind-events':
        if kind == 'session':
            return {'type': 'session', 'thread_id': str(event.get('thread_id', ''))}
        if kind not in ('message', 'tool', 'status', 'error') or not isinstance(event.get('id'), str):
            raise ValueError('Expected session or an event with type and stable id')
        # Public adapter protocol. Writers emit full snapshots with the same id
        # as their API streams arrive; this is provider-independent, not log parsing.
        fields = ('id', 'role', 'text', 'name', 'arguments', 'output', 'status', 'exit_code')
        return {'type': 'item', 'item': {'kind': kind, **{k: event[k] for k in fields if k in event}}}
    if kind == 'thread.started':
        return {'type': 'session', 'thread_id': str(event.get('thread_id', ''))}
    if kind in ('item.started', 'item.updated', 'item.completed'):
        item = event.get('item')
        if not isinstance(item, dict) or not isinstance(item.get('id'), str):
            raise ValueError('Item requires a stable id')
        subtype = item.get('type')
        value = {'id': item['id'], 'status': item.get('status') or ('completed' if kind == 'item.completed' else 'in_progress')}
        if subtype in ('agent_message', 'user_message', 'reasoning'):
            value.update(kind='message', role='user' if subtype == 'user_message' else 'assistant', text=item.get('text', ''), summary=subtype == 'reasoning')
        elif subtype == 'command_execution':
            value.update(kind='tool', name='执行命令', arguments=item.get('command', ''), output=item.get('aggregated_output', ''), exit_code=item.get('exit_code'))
        elif subtype in ('mcp_tool_call', 'dynamic_tool_call'):
            value.update(kind='tool', name=' / '.join(str(item[k]) for k in ('server', 'tool') if k in item) or subtype,
                         arguments=item.get('arguments'), output=item.get('result', item.get('error')))
        elif subtype == 'error':
            value.update(kind='error', text=item.get('message', ''))
        else:
            value.update(kind='tool', name=subtype or 'Provider item', output=item)
        return {'type': 'item', 'item': value}
    if kind in ('turn.started', 'turn.completed', 'turn.failed', 'error'):
        return {'type': 'lifecycle', 'event': kind, 'id': 'event-' + str(offset), 'detail': event.get('error', event.get('message')), 'usage': event.get('usage')}
    return {'type': 'unsupported', 'event': str(kind), 'id': 'event-' + str(offset)}


def read_conversation(output, declaration=None, offset=0, source=None):
    validate_source(declaration)
    if type(offset) is not int or offset < 0 or (source is not None and not isinstance(source, str)):
        raise ValueError('Use a nonnegative conversation offset and string source')
    root = Path(output).resolve()
    candidates = [declaration] if declaration else [
        {'format': 'codex-jsonl', 'path': 'agent-events.jsonl'},
        {'format': 'codex-jsonl', 'path': 'hexashell/agent-events.jsonl'},
    ]
    chosen = None
    for candidate in candidates:
        path = (root / candidate['path']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Conversation path escapes run output')
        if path.is_file():
            chosen = candidate
            break
    if chosen is None:
        return {'available': False, 'events': [], 'next_offset': 0, 'source': None, 'more': False, 'reset': bool(source)}
    # O_NONBLOCK avoids hanging if a writer substitutes a pipe for a regular file.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Conversation source must be a regular file')
        # Check the opened fd as well as the declared path against symlink races.
        actual = Path(f'/proc/self/fd/{stream.fileno()}').resolve()
        if not actual.is_relative_to(root):
            raise ValueError('Conversation source escapes run output')
        identity = hashlib.sha256(f"{chosen['path']}:{info.st_dev}:{info.st_ino}".encode()).hexdigest()[:24]
        reset = source != identity or offset > info.st_size
        if reset:
            offset = 0
        stream.seek(offset)
        events, warnings = [], []
        consumed = 0
        for _ in range(100):
            start = stream.tell()
            line = stream.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE:
                # Stop explicitly rather than discarding part of a real tool result.
                warnings.append('单条事件超过 2 MB，请在源文件查看；后续读取暂停。')
                break
            if not line.endswith(b'\n'):
                break
            offset = stream.tell()
            consumed += len(line)
            try:
                events.append(normalize(json.loads(line), chosen['format'], start))
            except (ValueError, TypeError, KeyError, UnicodeError) as error:
                warnings.append(f'字节 {start} 的事件无法解析：{error}')
            if consumed >= PAGE_BYTES:
                break
        return {'available': True, **chosen, 'source': identity, 'reset': reset,
                'events': events, 'warnings': warnings, 'next_offset': offset,
                'more': offset < info.st_size and bool(events), 'bytes': info.st_size}
