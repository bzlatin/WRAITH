#!/usr/bin/env node
'use strict';

const { CodeIndex } = require('./lib/index.cjs');
const { ContextError } = require('./lib/repository.cjs');
const VERSION = '0.1.0';
const HELP = `wraith-context ${VERSION} — experimental local TypeScript/JavaScript syntax context

Usage: node cli.cjs <index|context|symbols|references|mcp|doctor> [query] [options]
  --root PATH       Local Git checkout (default: current directory)
  --cache PATH      Private cache parent (default: system temporary directory)
  --max-bytes N     Snippet UTF-8 byte budget, 512–64000 (default: 12000)
  --limit N         Result count, 1–50 (default: 8)

No accounts, uploads, model calls or repository script execution. MCP uses stdio.
References are lexical candidates; this is not a complete type or impact analyzer.
`;

function argumentsFor(argv) {
  const command = argv.shift();
  if (!command || ['--help', '-h', 'help'].includes(command)) return { help: true };
  if (command === '--version') return { version: true };
  if (!['index', 'context', 'symbols', 'references', 'mcp', 'doctor'].includes(command)) throw new ContextError('invalid_arguments', 'Unknown command. Use --help.');
  const result = { command, query: [], root: process.cwd() };
  const flags = { '--root': 'root', '--cache': 'cache', '--max-bytes': 'max_bytes', '--limit': 'limit' };
  for (let i = 0; i < argv.length; i++) {
    if (flags[argv[i]]) {
      const key = flags[argv[i]], value = argv[++i];
      if (!value || value.startsWith('--')) throw new ContextError('invalid_arguments', 'Option requires a value.');
      if (Object.hasOwn(result, key) && key !== 'root') throw new ContextError('invalid_arguments', 'Duplicate option.');
      result[key] = ['limit', 'max_bytes'].includes(key) ? Number(value) : value;
    } else if (argv[i].startsWith('-')) throw new ContextError('invalid_arguments', 'Unknown option. Use --help.');
    else result.query.push(argv[i]);
  }
  result.query = result.query.join(' ');
  return result;
}

async function serve(index) {
  const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
  const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
  const { ListToolsRequestSchema, CallToolRequestSchema } = require('@modelcontextprotocol/sdk/types.js');
  const schema = name => ({ type: 'object', properties: { [name]: { type: 'string', minLength: 1, maxLength: 500 },
    limit: { type: 'integer', minimum: 1, maximum: 50 }, max_bytes: { type: 'integer', minimum: 512, maximum: 64000 } },
    required: [name], additionalProperties: false });
  const tools = [
    { name: 'code_context', description: 'Rank local syntax snippets and candidate tests for a task. Citations are hash-checked. Syntax/lexical analysis, not a complete call graph.', inputSchema: schema('query') },
    { name: 'code_symbols', description: 'Find named syntax definitions in the selected checkout.', inputSchema: schema('query') },
    { name: 'code_references', description: 'Find lexical identifier occurrences. Results include declarations and shadowed names; they are not proven semantic references.', inputSchema: schema('name') }
  ];
  const server = new Server({ name: 'wraith-code-context-experiment', version: VERSION }, { capabilities: { tools: {} } });
  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));
  server.setRequestHandler(CallToolRequestSchema, async request => {
    try {
      const name = request.params.name, args = request.params.arguments || {};
      const tool = tools.find(t => t.name === name);
      if (!tool || Object.keys(args).some(k => !Object.hasOwn(tool.inputSchema.properties, k))) throw new ContextError('invalid_arguments', 'Unknown tool or argument.');
      const result = name === 'code_context' ? index.context(args.query, args)
        : name === 'code_symbols' ? index.symbols(args.query, args) : index.references(args.name, args);
      return { content: [{ type: 'text', text: JSON.stringify(result) }], structuredContent: result };
    } catch (error) {
      return { isError: true, content: [{ type: 'text', text: JSON.stringify(problem(error)) }] };
    }
  });
  await server.connect(new StdioServerTransport());
}
function problem(error) {
  return { schema_version: 1, status: 'incomplete', error: error instanceof ContextError ? error.code : 'execution_error',
    message: error instanceof ContextError ? error.message : 'Local operation failed. Check checkout/cache access and retry; no complete result was produced.' };
}
async function main(argv) {
  const args = argumentsFor([...argv]);
  if (args.help) { process.stdout.write(HELP); return; }
  if (args.version) { process.stdout.write(VERSION + '\n'); return; }
  const index = new CodeIndex(args.root, { cache: args.cache });
  if (args.command === 'mcp') return serve(index);
  const result = ['index', 'doctor'].includes(args.command) ? index.refresh() : index[args.command](args.query, args);
  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
}
main(process.argv.slice(2)).catch(error => { process.stderr.write(JSON.stringify(problem(error)) + '\n'); process.exitCode = 2; });
