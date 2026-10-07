"""Wraith function adapter, Python 3.10+. Standard library only.

Export a function(input, context), sync or async. Return its final JSON output.
Wrap every live model attempt in `with context.model_call():`, including retries.
"""
import asyncio
import contextlib
import importlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys


class Context:
    def __init__(self, request):
        self.scenario_id = request['scenarioId']
        self.metadata = request.get('metadata', {})
        self.tools = []
        self.retrievals = []
        self.tokens = None
        self.model_calls = 0

    def tool(self, name, arguments=None, result=None, success=True):
        self.tools.append(dict(name=name, arguments=arguments, result=result, success=success))

    def retrieval(self, source, document_id=None, **metadata):
        self.retrievals.append(dict(source=source, documentId=document_id, metadata=metadata))

    def usage(self, input_tokens, output_tokens):
        if any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in (input_tokens, output_tokens)):
            raise ValueError('Usage requires nonnegative integer token counts')
        self.tokens = self.tokens or dict(inputTokens=0, outputTokens=0)
        self.tokens['inputTokens'] += input_tokens
        self.tokens['outputTokens'] += output_tokens

    @contextlib.contextmanager
    def model_call(self):
        filename = os.environ.get('WRAITH_REQUEST_BUDGET')
        if not filename:
            raise RuntimeError('Model calls require a live baseline/check with --allow-live and --max-requests')
        reserve_request(filename)
        self.model_calls += 1
        yield


def reserve_request(filename):
    path = Path(filename)
    if not path.is_absolute():
        raise ValueError('Request budget path must be absolute')
    lock = Path(str(path) + '.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        budget = json.loads(path.read_text())
        limit, used = budget['limit'], budget['used']
        if any(isinstance(n, bool) or not isinstance(n, int) for n in (limit, used)) or not 1 <= limit <= 10000 or not 0 <= used < limit:
            raise RuntimeError('Request budget exhausted or invalid')
        budget['used'] += 1  # Failed calls consume budget too.
        path.write_text(json.dumps(budget))
    finally:
        os.close(fd)
        lock.unlink()


def load_function(entrypoint):
    target, separator, name = entrypoint.rpartition(':')
    if not separator or not target or not name:
        raise ValueError('Entrypoint must be module:function or path.py:function')
    if target.endswith('.py') or '/' in target or '\\' in target:
        path = Path(target).resolve()
        sys.path.insert(0, str(path.parent))
        spec = importlib.util.spec_from_file_location('_wraith_user_agent', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    else:
        sys.path.insert(0, str(Path.cwd()))
        module = importlib.import_module(target)
    function = getattr(module, name)
    if not callable(function):
        raise ValueError('Entrypoint export must be callable')
    return function


async def run(entrypoint):
    raw = sys.stdin.buffer.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Request exceeds 1 MiB')
    request = json.loads(raw)
    if request.get('protocolVersion') != 1 or not isinstance(request.get('scenarioId'), str) or 'input' not in request:
        raise ValueError('Expected Wraith protocol v1 request')
    context = Context(request)
    with contextlib.redirect_stdout(sys.stderr):
        function = load_function(entrypoint)
        output = function(request['input'], context)
        if inspect.isawaitable(output):
            output = await output
    response = dict(protocolVersion=1, scenarioId=context.scenario_id, output=output,
                    toolCalls=context.tools, retrievals=context.retrievals,
                    metadata=dict(wraith=dict(modelCalls=context.model_calls, budgeted=True)))
    if context.tokens is not None:
        response['usage'] = context.tokens
    encoded = json.dumps(response, allow_nan=False)
    if len(encoded.encode()) > 1024 * 1024:
        raise ValueError('Response exceeds 1 MiB')
    sys.stdout.write(encoded + '\n')


if __name__ == '__main__':
    try:
        asyncio.run(run(sys.argv[1]))
    except Exception as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
