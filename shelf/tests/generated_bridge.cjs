'use strict';
// NDJSON transport for generated parity checks. All verdicts come from the
// actual browser engine; this file only batches calls and resolves card indexes.
// A line is an operation, an array of operations, {cards, operations}, or the
// one-time {catalog: [...]} load (acknowledged as {loaded: N}). Operations use
// {operation, args}; validate/compose also accept {operation, refs, purpose?}.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const readline = require('node:readline');
const {once} = require('node:events');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const match = html.match(/<script id="shelf-engine">([\s\S]*?)<\/script>/);
if (!match) throw new Error('shelf-engine script missing from index.html');
vm.runInThisContext(match[1], {filename: 'index.html#shelf-engine'});
const S = globalThis.Shelf;
const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
let catalog;

function protocolError(message) {
  const error = new Error(message);
  error.name = 'BridgeProtocolError';
  throw error;
}

function failure(error) {
  return {ok: false, error: {
    name: error && typeof error.name === 'string' ? error.name : 'Error',
    message: error && typeof error.message === 'string' ? error.message : String(error)
  }};
}

function keysOnly(value, allowed) {
  const unknown = Object.keys(value).filter(key => !allowed.includes(key));
  if (unknown.length) protocolError('Unknown field(s): ' + unknown.join(', '));
}

function resolveArgs(request, cards) {
  const arities = {validate: 1, compose: 3, which: 4};
  if (!Object.hasOwn(arities, request.operation)) protocolError('Unknown operation: ' + String(request.operation));
  if (Object.hasOwn(request, 'args')) {
    keysOnly(request, ['operation', 'args']);
    if (!Array.isArray(request.args) || request.args.length !== arities[request.operation]) {
      protocolError(request.operation + ' requires args with length ' + arities[request.operation]);
    }
    return request.args;
  }
  if (request.operation === 'which') protocolError('which requires args');
  keysOnly(request, request.operation === 'compose' ? ['operation', 'refs', 'purpose'] : ['operation', 'refs']);
  if (!Array.isArray(cards)) protocolError('refs require a catalog or line-local cards');
  const count = request.operation === 'validate' ? 1 : 2;
  if (!Array.isArray(request.refs) || request.refs.length !== count) {
    protocolError(request.operation + ' requires refs with length ' + count);
  }
  const args = request.refs.map(index => {
    if (!Number.isSafeInteger(index) || index < 0 || index >= cards.length) {
      protocolError('Card reference must be an in-range integer: ' + String(index));
    }
    return cards[index];
  });
  if (request.operation === 'compose') {
    if (!Object.hasOwn(request, 'purpose')) protocolError('compose refs require purpose');
    args.push(request.purpose);
  }
  return args;
}

function execute(request, cards) {
  try {
    if (!isObject(request)) protocolError('Operation must be an object');
    const args = resolveArgs(request, cards);
    let value;
    switch (request.operation) {
      case 'validate': value = S.validateCard(...args); break;
      case 'compose': value = S.compose(...args); break;
      case 'which': value = S.which(...args); break;
    }
    // Refuse values JSON would silently drop/coerce instead of hiding them.
    JSON.stringify(value, (key, item) => {
      if (item === undefined || (typeof item === 'number' && !Number.isFinite(item))) {
        const error = new Error('Native result contains a value JSON cannot preserve');
        error.name = 'BridgeSerializationError';
        throw error;
      }
      return item;
    });
    return {ok: true, value};
  } catch (error) {
    return failure(error);
  }
}

function dispatch(request) {
  if (Array.isArray(request)) return request.map(operation => execute(operation, catalog));
  if (isObject(request) && Object.hasOwn(request, 'catalog')) {
    keysOnly(request, ['catalog']);
    if (catalog !== undefined) protocolError('Catalog is already loaded');
    if (!Array.isArray(request.catalog)) protocolError('catalog must be an array');
    catalog = request.catalog;
    return {loaded: catalog.length};
  }
  if (isObject(request) && (Object.hasOwn(request, 'cards') || Object.hasOwn(request, 'operations'))) {
    keysOnly(request, ['cards', 'operations']);
    if (!Array.isArray(request.cards) || !Array.isArray(request.operations)) {
      protocolError('cards and operations must be arrays');
    }
    return request.operations.map(operation => execute(operation, request.cards));
  }
  return execute(request, catalog);
}

async function main() {
  process.stdin.setEncoding('utf8');
  const lines = readline.createInterface({input: process.stdin, crlfDelay: Infinity});
  for await (const line of lines) {
    let response;
    try { response = dispatch(JSON.parse(line)); }
    catch (error) { response = failure(error); }
    if (!process.stdout.write(JSON.stringify(response) + '\n', 'utf8')) await once(process.stdout, 'drain');
  }
}

main().catch(error => {
  process.stderr.write(JSON.stringify(failure(error)) + '\n');
  process.exitCode = 1;
});
