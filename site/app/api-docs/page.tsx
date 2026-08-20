import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Voiceprint API Reference",
  description: "Programmatic access to Voiceprint corpora, models, training, generation, and scoring.",
};

const endpoints = [
  ["GET", "/v1/me", "Current account and credit balance"],
  ["POST", "/v1/corpora", "Create a corpus"],
  ["POST", "/v1/corpora/{id}/text", "Add Markdown or plain text"],
  ["POST", "/v1/corpora/{id}/inspect", "Run readiness preflight"],
  ["POST", "/v1/corpora/{id}/revisions", "Freeze an immutable revision"],
  ["POST", "/v1/training-quotes", "Quote the $20 training purchase"],
  ["POST", "/v1/training-jobs", "Start training from an entitlement"],
  ["GET", "/v1/jobs/{id}", "Poll training or generation"],
  ["GET", "/v1/models", "List custom models"],
  ["POST", "/v1/generations", "Write, continue, revoice, or edit an exact span"],
  ["POST", "/v1/assistant", "Prepare a generation request without spending a credit"],
  ["POST", "/v1/scores", "Score the exact final artifact for style similarity"],
  ["GET", "/v1/credits", "Read generation-credit balance"],
  ["POST", "/v1/api-keys", "Create a scoped personal key"],
];

export default function ApiDocsPage() {
  return <main className="docs-page">
    <nav><Link className="wordmark" href="/">VOICEPRINT<span className="wordmark-dot">●</span></Link><Link href="/beta">OPEN WORKSPACE →</Link></nav>
    <header><p className="eyebrow">API / VERSION 1</p><h1>The same voice tools,<br />without the interface.</h1><p>The browser workspace, guided assistant, and REST API use one capability layer. Authorization, credits, corpus validation, and job states behave the same everywhere.</p></header>
    <div className="docs-layout">
      <aside><a href="#authentication">Authentication</a><a href="#corpora">Corpora</a><a href="#jobs">Jobs</a><a href="#generation">Generation</a><a href="#endpoints">Endpoints</a><a href="#errors">Errors</a></aside>
      <article>
        <section id="authentication"><span>01</span><h2>Authentication</h2><p>Create a personal key in the workspace. Keys are shown once, stored as hashes, revocable, and limited by scope: <code>corpora:read</code>, <code>corpora:write</code>, <code>models:read</code>, <code>models:write</code>, <code>generate</code>, <code>jobs:read</code>, and <code>scores:write</code>. Checkout and key management require a browser session.</p><pre><code>{`Authorization: Bearer vp_live_…`}</code></pre></section>
        <section id="corpora"><span>02</span><h2>Corpus preflight</h2><p>Inspection is deterministic and never starts a GPU. A corpus is blocked below 1,000 usable words and recommends 2,000. Headings, tables, code, quotations, outline fragments, and exact duplicates do not count.</p><pre><code>{`POST /v1/corpora/corpus_123/inspect

{
  "status": "warning",
  "ready": true,
  "usable_words": 1842,
  "minimum_words": 1000,
  "recommended_words": 2000,
  "warnings": ["1842 usable words passed…"]
}`}</code></pre></section>
        <section id="jobs"><span>03</span><h2>Asynchronous jobs</h2><p>Training and cold generation return <code>202 Accepted</code>, a job ID, and a <code>Location</code> header. Poll that location until the job is completed or failed. Use an <code>Idempotency-Key</code> on every credit-consuming or job-creating request.</p></section>
        <section id="generation"><span>04</span><h2>Generation</h2><p>The orchestration model may structure requests and privately plan corrections, but the Voiceprint adapter always writes the final user-visible prose. Intermediate correction drafts are never returned.</p><pre><code>{`POST /v1/generations
Idempotency-Key: 85cbe…

{
  "model_id": "model_123",
  "operation": "write",
  "mode": "raw",
  "length": "medium",
  "notes": [
    "the audience is engineering leaders",
    "memory is a control problem, not storage"
  ],
  "corrections": []
}`}</code></pre><p><b>Raw mode</b> preserves adapter output and may contain errors. <b>Edited mode</b> permits factual and mechanical corrections only, then sends the private correction draft back through Voiceprint. The exact final artifact must be rescored.</p><pre><code>{`// Revoice a complete private draft
{
  "model_id": "model_123",
  "operation": "revoice",
  "text": "Private intermediate draft…"
}

// Edit one exact span; offsets use JavaScript string indices (end-exclusive)
{
  "model_id": "model_123",
  "operation": "edit_span",
  "text": "The complete existing artifact…",
  "selection_start": 4,
  "selection_end": 12,
  "instruction": "Replace the outdated date with August 20, 2026"
}`}</code></pre><p>For <code>edit_span</code>, the coordinator privately plans only the replacement. Voiceprint revoices that replacement and the server preserves everything outside the selected span. Responses attest <code>final_writer: voiceprint</code> and <code>finalized_by_adapter: true</code>.</p></section>
        <section id="endpoints"><span>05</span><h2>Endpoints</h2><div className="endpoint-list">{endpoints.map(([method, path, description]) => <div key={`${method}-${path}`}><b>{method}</b><code>{path}</code><span>{description}</span></div>)}</div></section>
        <section id="errors"><span>06</span><h2>Errors</h2><p>Expected invalid input is a typed 4xx response, not a failed training job. Infrastructure errors are retried; failed generation restores its credit.</p><pre><code>{`{
  "error": {
    "code": "corpus_not_ready",
    "message": "The corpus needs more usable prose before training.",
    "request_id": "req_01…",
    "details": { "usable_words": 640, "minimum_words": 1000 }
  }
}`}</code></pre></section>
      </article>
    </div>
  </main>;
}
