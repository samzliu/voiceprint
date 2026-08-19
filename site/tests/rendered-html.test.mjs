import assert from "node:assert/strict";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the Voiceprint demo", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<title>Voiceprint — write in a trained human voice<\/title>/i);
  assert.match(html, /Give it the facts/);
  assert.match(html, /What should it write/);
  assert.match(html, /pip install voiceprint/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/i);
});

test("server-renders the private beta shell", async () => {
  const response = await render("/beta");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Opening your workspace/i);
  assert.match(html, /Voiceprint Beta — train your writing model/i);
});

test("server-renders the API reference", async () => {
  const response = await render("/api-docs");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /API \/ VERSION 1/i);
  assert.match(html, /Corpus preflight/i);
  assert.match(html, /Idempotency-Key/i);
});

test("server-renders the protected operations shell", async () => {
  const response = await render("/admin");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /PRIVATE BETA \/ OPERATIONS/i);
  assert.match(html, /Loading beta operations/i);
});
