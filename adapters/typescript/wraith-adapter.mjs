/** Wraith function adapter. Node 22.18+. No npm dependencies. */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

export function reserveRequest(filename) {
  if (!path.isAbsolute(filename)) throw new Error('Request budget path must be absolute');
  const lock = `${filename}.lock`;
  const fd = fs.openSync(lock, 'wx', 0o600);
  try {
    const budget = JSON.parse(fs.readFileSync(filename, 'utf8'));
    if (!Number.isSafeInteger(budget.limit) || budget.limit < 1 || budget.limit > 10000 ||
        !Number.isSafeInteger(budget.used) || budget.used < 0 || budget.used >= budget.limit) {
      throw new Error('Request budget exhausted or invalid');
    }
    budget.used += 1;
    fs.writeFileSync(filename, JSON.stringify(budget));
  } finally { fs.closeSync(fd); fs.unlinkSync(lock); }
}

export class Context {
  constructor(request) {
    this.scenarioId = request.scenarioId;
    this.metadata = request.metadata ?? {};
    this.tools = [];
    this.retrievals = [];
    this.tokens = undefined;
    this.modelCalls = 0;
  }
  tool(name, argumentsValue = null, result = null, success = true) {
    this.tools.push({ name, arguments: argumentsValue, result, success });
  }
  retrieval(source, documentId = null, metadata = {}) {
    this.retrievals.push({ source, documentId, metadata });
  }
  usage(inputTokens, outputTokens) {
    if (![inputTokens, outputTokens].every(n => Number.isSafeInteger(n) && n >= 0)) throw new Error('Usage requires nonnegative integer token counts');
    this.tokens ??= { inputTokens: 0, outputTokens: 0 };
    this.tokens.inputTokens += inputTokens;
    this.tokens.outputTokens += outputTokens;
  }
  async modelCall(call) {
    const filename = process.env.WRAITH_REQUEST_BUDGET;
    if (!filename) throw new Error('Model calls require a live baseline/check with --allow-live and --max-requests');
    reserveRequest(filename);
    this.modelCalls += 1;
    return await call();
  }
}

export async function run(entrypoint) {
  const separator = entrypoint.lastIndexOf(':');
  if (separator <= 0) throw new Error('Entrypoint must be path.js:export or path.ts:export');
  let raw = '';
  for await (const chunk of process.stdin) {
    raw += chunk;
    if (Buffer.byteLength(raw) > 1024 * 1024) throw new Error('Request exceeds 1 MiB');
  }
  const request = JSON.parse(raw);
  if (request.protocolVersion !== 1 || typeof request.scenarioId !== 'string' || !Object.hasOwn(request, 'input')) throw new Error('Expected Wraith protocol v1 request');
  const context = new Context(request);
  console.log = (...args) => console.error(...args);
  const module = await import(pathToFileURL(path.resolve(entrypoint.slice(0, separator))).href);
  const agent = module[entrypoint.slice(separator + 1)];
  if (typeof agent !== 'function') throw new Error('Entrypoint export must be callable');
  const output = await agent(request.input, context);
  if (output === undefined || output === null) throw new Error('Agent must return non-null JSON output');
  const response = { protocolVersion: 1, scenarioId: context.scenarioId, output,
    toolCalls: context.tools, retrievals: context.retrievals,
    metadata: { wraith: { modelCalls: context.modelCalls, budgeted: true } } };
  if (context.tokens) response.usage = context.tokens;
  const encoded = JSON.stringify(response);
  if (Buffer.byteLength(encoded) > 1024 * 1024) throw new Error('Response exceeds 1 MiB');
  process.stdout.write(encoded + '\n');
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  run(process.argv[2]).catch(error => { console.error(`${error.name}: ${error.message}`); process.exitCode = 1; });
}
