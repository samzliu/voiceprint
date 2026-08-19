"use client";

import { ChangeEvent, DragEvent, FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";

type Tab = "corpus" | "models" | "write" | "api";
type Session = {
  user: { email: string; name?: string; writing_goals?: string; sample_notes?: string };
  credits: number;
};
type Corpus = {
  id: string;
  name: string;
  status: "draft" | "blocked" | "warning" | "ready";
  documents: number;
  raw_words: number;
  usable_words: number;
  updated_at: string;
};
type CorpusDetail = Corpus & {
  items: Array<{ id: string; name: string; bytes: number; raw_words: number }>;
};
type Readiness = {
  status: "blocked" | "warning" | "ready";
  ready: boolean;
  documents: number;
  usable_documents: number;
  raw_words: number;
  usable_words: number;
  duplicate_words: number;
  minimum_words: number;
  recommended_words: number;
  reasons: string[];
  warnings: string[];
};
type Model = { id: string; name: string; status: string; trained_at?: string; updated_at: string };
type ApiError = { error?: { message?: string } };
type DraftProposal = {
  model_id: string;
  model_name: string;
  operation: "write" | "continue" | "rewrite";
  mode: "raw" | "edited";
  length: "short" | "medium" | "long";
  notes: string[];
  preceding_text?: string;
  text?: string;
};

const ALL_SCOPES = [
  "corpora:read",
  "corpora:write",
  "models:read",
  "models:write",
  "generate",
  "scores:write",
  "jobs:read",
];

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  const body = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    throw new Error((body as ApiError)?.error?.message || "Something went wrong.");
  }
  return body as T;
}

export function BetaWorkspace() {
  const [session, setSession] = useState<Session | null>(null);
  const [authState, setAuthState] = useState<"loading" | "signed-in" | "signed-out">("loading");
  const [tab, setTab] = useState<Tab>("corpus");
  const [corpora, setCorpora] = useState<Corpus[]>([]);
  const [activeCorpus, setActiveCorpus] = useState<CorpusDetail | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [profile, corpusList, modelList] = await Promise.all([
        api<Session>("/v1/me"),
        api<{ data: Corpus[] }>("/v1/corpora"),
        api<{ data: Model[] }>("/v1/models"),
      ]);
      setSession(profile);
      setCorpora(corpusList.data);
      setModels(modelList.data);
      setAuthState("signed-in");
      if (!activeCorpus && corpusList.data[0]) await openCorpus(corpusList.data[0].id);
    } catch {
      setAuthState("signed-out");
    }
  }, [activeCorpus]);

  useEffect(() => {
    // The initial network synchronization intentionally populates client state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function openCorpus(corpusId: string) {
    setBusy("corpus");
    try {
      const detail = await api<CorpusDetail>(`/v1/corpora/${corpusId}`);
      setActiveCorpus(detail);
      if (detail.items.length) {
        setReadiness(await api<Readiness>(`/v1/corpora/${corpusId}/inspect`, { method: "POST" }));
      } else {
        setReadiness(null);
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not open the corpus.");
    } finally {
      setBusy("");
    }
  }

  if (authState === "loading") {
    return <main className="beta-loading"><span>VOICEPRINT●</span><p>Opening your workspace…</p></main>;
  }

  if (authState === "signed-out") {
    return (
      <main className="beta-auth">
        <Link className="wordmark" href="/">VOICEPRINT<span className="wordmark-dot">●</span></Link>
        <section>
          <p className="eyebrow">VOICEPRINT BETA</p>
          <h1>Your writing model<br />starts with your writing.</h1>
          <p>Sign in, bring a few pages of prose you wrote, and Voiceprint will verify the corpus before you spend anything.</p>
          <a className="button beta-signin" href="/signin-with-chatgpt?return_to=%2Fbeta">SIGN IN WITH CHATGPT <span>→</span></a>
          <small>$20 per trained model · training completes within 24 hours</small>
        </section>
      </main>
    );
  }

  const needsOnboarding = !session?.user.writing_goals;
  return (
    <main className="beta-app">
      <aside className="beta-sidebar">
        <Link className="wordmark" href="/">VOICEPRINT<span className="wordmark-dot">●</span></Link>
        <nav aria-label="Workspace">
          <button className={tab === "corpus" ? "active" : ""} onClick={() => setTab("corpus")}><span>01</span> Corpus</button>
          <button className={tab === "models" ? "active" : ""} onClick={() => setTab("models")}><span>02</span> Models</button>
          <button className={tab === "write" ? "active" : ""} onClick={() => setTab("write")}><span>03</span> Write</button>
          <button className={tab === "api" ? "active" : ""} onClick={() => setTab("api")}><span>04</span> API</button>
        </nav>
        <div className="beta-account">
          <b>{session?.credits ?? 0} CREDITS</b>
          <span>{session?.user.name || session?.user.email}</span>
          <a href="/signout-with-chatgpt?return_to=%2F">SIGN OUT</a>
        </div>
      </aside>

      <section className="beta-main">
        {notice && <div className="beta-notice" role="status"><span>{notice}</span><button onClick={() => setNotice("")} aria-label="Dismiss">×</button></div>}
        {needsOnboarding ? (
          <Onboarding onComplete={refresh} />
        ) : tab === "corpus" ? (
          <CorpusView
            corpora={corpora}
            active={activeCorpus}
            readiness={readiness}
            busy={busy}
            onOpen={openCorpus}
            onRefresh={refresh}
            onNotice={setNotice}
            onReady={setReadiness}
          />
        ) : tab === "models" ? (
          <ModelsView models={models} corpora={corpora} onRefresh={refresh} onNotice={setNotice} />
        ) : tab === "write" ? (
          <WriteView models={models} credits={session?.credits ?? 0} onRefresh={refresh} onNotice={setNotice} />
        ) : (
          <ApiView onNotice={setNotice} />
        )}
      </section>
    </main>
  );
}

function Onboarding({ onComplete }: { onComplete: () => Promise<void> }) {
  const [name, setName] = useState("");
  const [goals, setGoals] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    await api("/v1/me", { method: "PUT", body: JSON.stringify({ name, writing_goals: goals, sample_notes: notes }) });
    await onComplete();
    setBusy(false);
  }

  return (
    <div className="onboarding">
      <p className="eyebrow">SETUP · ABOUT TWO MINUTES</p>
      <h1>What should this voice help you write?</h1>
      <form onSubmit={submit}>
        <label>Your name<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={120} /></label>
        <label>What do you usually write?<textarea value={goals} onChange={(event) => setGoals(event.target.value)} required minLength={10} rows={4} placeholder="Essays about technology, investor updates, thoughtful emails…" /></label>
        <label>Anything we should know about the samples?<textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} placeholder="For example: the newsletters are mine; the company posts were heavily edited." /></label>
        <button className="button button-generate" disabled={busy}>{busy ? "SAVING…" : "BUILD MY CORPUS"}<span>→</span></button>
      </form>
    </div>
  );
}

function CorpusView({
  corpora, active, readiness, busy, onOpen, onRefresh, onNotice, onReady,
}: {
  corpora: Corpus[];
  active: CorpusDetail | null;
  readiness: Readiness | null;
  busy: string;
  onOpen: (id: string) => Promise<void>;
  onRefresh: () => Promise<void>;
  onNotice: (message: string) => void;
  onReady: (report: Readiness) => void;
}) {
  const [newName, setNewName] = useState("");
  const [paste, setPaste] = useState("");
  const [pasteName, setPasteName] = useState("Pasted writing");
  const [dragging, setDragging] = useState(false);

  async function createCorpus(event: FormEvent) {
    event.preventDefault();
    const created = await api<{ id: string }>("/v1/corpora", { method: "POST", body: JSON.stringify({ name: newName }) });
    setNewName("");
    await onRefresh();
    await onOpen(created.id);
  }

  async function addDocument(name: string, text: string) {
    if (!active) return;
    await api(`/v1/corpora/${active.id}/text`, { method: "POST", body: JSON.stringify({ name, text }) });
  }

  async function addPaste(event: FormEvent) {
    event.preventDefault();
    if (!active) return;
    try {
      await addDocument(pasteName || "Pasted writing", paste);
      setPaste("");
      const report = await api<Readiness>(`/v1/corpora/${active.id}/inspect`, { method: "POST" });
      onReady(report);
      await onOpen(active.id);
      await onRefresh();
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Could not add that writing.");
    }
  }

  async function addFiles(files: FileList | File[]) {
    if (!active) return;
    const accepted = Array.from(files).filter((file) => /\.(?:md|markdown|txt|mdx)$/i.test(file.name));
    if (!accepted.length) {
      onNotice("Use Markdown or plain-text files for this beta.");
      return;
    }
    try {
      for (const file of accepted) await addDocument(file.name, await file.text());
      const report = await api<Readiness>(`/v1/corpora/${active.id}/inspect`, { method: "POST" });
      onReady(report);
      await onOpen(active.id);
      await onRefresh();
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Could not upload those files.");
    }
  }

  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    void addFiles(event.dataTransfer.files);
  }

  return (
    <div className="workspace-view corpus-view">
      <header className="workspace-header"><div><p className="eyebrow">01 / CORPUS</p><h1>Your writing,<br />before the model.</h1></div><p>We extract prose, remove duplicates, and block training until there is enough real writing to learn from.</p></header>
      <div className="corpus-layout">
        <aside className="corpus-list">
          <form onSubmit={createCorpus}><input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="New corpus name" required /><button aria-label="Create corpus">+</button></form>
          {corpora.map((corpus) => <button key={corpus.id} className={active?.id === corpus.id ? "active" : ""} onClick={() => onOpen(corpus.id)}><b>{corpus.name}</b><span>{corpus.usable_words || 0} usable words</span></button>)}
          {!corpora.length && <p>No corpus yet. Name one to begin.</p>}
        </aside>
        <section className="corpus-work">
          {!active ? <div className="empty-work"><b>START HERE</b><p>Create a corpus for essays, newsletters, emails, or another consistent voice.</p></div> : <>
            <div className="corpus-title"><div><span>CORPUS</span><h2>{active.name}</h2></div>{readiness && <Status status={readiness.status} />}</div>
            <label className={`drop-zone ${dragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={drop}>
              <input type="file" multiple accept=".md,.markdown,.txt,.mdx,text/plain,text/markdown" onChange={(event: ChangeEvent<HTMLInputElement>) => event.target.files && void addFiles(event.target.files)} />
              <b>DROP WRITING HERE</b><span>or choose Markdown and text files · 2 MB each</span>
            </label>
            <form className="paste-form" onSubmit={addPaste}>
              <input value={pasteName} onChange={(event) => setPasteName(event.target.value)} aria-label="Document name" />
              <textarea value={paste} onChange={(event) => setPaste(event.target.value)} minLength={20} required rows={7} placeholder="Or paste something you wrote…" />
              <button className="button" disabled={busy === "corpus"}>ADD TO CORPUS <span>→</span></button>
            </form>
            <div className="corpus-files">
              <span>INCLUDED MATERIAL · {active.items.length}</span>
              {active.items.map((item) => <div key={item.id}><b>{item.name}</b><span>{item.raw_words} raw words · {Math.ceil(item.bytes / 1024)} KB</span></div>)}
            </div>
            {readiness && <ReadinessCard report={readiness} />}
          </>}
        </section>
      </div>
    </div>
  );
}

function Status({ status }: { status: string }) {
  return <span className={`status-pill status-${status}`}>{status.toUpperCase()}</span>;
}

function ReadinessCard({ report }: { report: Readiness }) {
  const progress = Math.min(100, Math.round((report.usable_words / report.recommended_words) * 100));
  return (
    <section className={`readiness-card readiness-${report.status}`}>
      <div className="readiness-head"><div><span>TRAINING READINESS</span><b>{report.usable_words.toLocaleString()} usable words</b></div><strong>{progress}%</strong></div>
      <div className="readiness-meter"><span style={{ width: `${progress}%` }} /></div>
      <div className="readiness-stats"><span>{report.usable_documents}/{report.documents} files used</span><span>{report.duplicate_words} duplicate words removed</span><span>{report.minimum_words.toLocaleString()} minimum</span></div>
      {[...report.reasons, ...report.warnings].map((message) => <p key={message}>{message}</p>)}
      {report.ready && <small>{report.status === "ready" ? "This corpus is ready to freeze and train." : "You can train now, or add more writing for a stronger result."}</small>}
    </section>
  );
}

function ModelsView({ models, corpora, onRefresh, onNotice }: { models: Model[]; corpora: Corpus[]; onRefresh: () => Promise<void>; onNotice: (message: string) => void }) {
  const [selectedCorpus, setSelectedCorpus] = useState(corpora[0]?.id || "");
  const [modelName, setModelName] = useState("My voice");
  const [revision, setRevision] = useState("");
  const [entitled, setEntitled] = useState(false);
  const [busy, setBusy] = useState(false);

  async function freezeCorpus() {
    setBusy(true);
    try {
      const created = await api<{ id: string }>(`/v1/corpora/${selectedCorpus}/revisions`, { method: "POST" });
      setRevision(created.id);
      onNotice("Corpus frozen. It will not change while the model trains.");
    } catch (error) { onNotice(error instanceof Error ? error.message : "Could not freeze the corpus."); }
    setBusy(false);
  }

  async function buyTraining() {
    setBusy(true);
    try {
      const checkout = await api<{ url?: string; granted?: boolean }>("/v1/checkout/training", { method: "POST", body: "{}" });
      if (checkout.url) window.location.assign(checkout.url);
      else if (checkout.granted) { setEntitled(true); onNotice("Training entitlement added for local beta testing."); }
    } catch (error) { onNotice(error instanceof Error ? error.message : "Could not start checkout."); }
    setBusy(false);
  }

  async function train() {
    setBusy(true);
    try {
      await api("/v1/training-jobs", { method: "POST", headers: { "idempotency-key": crypto.randomUUID() }, body: JSON.stringify({ revision_id: revision, name: modelName }) });
      onNotice("Training queued. We’ll email you when the model is ready, within 24 hours.");
      setEntitled(false);
      setRevision("");
      await onRefresh();
    } catch (error) { onNotice(error instanceof Error ? error.message : "Could not start training."); }
    setBusy(false);
  }

  return <div className="workspace-view models-view">
    <header className="workspace-header"><div><p className="eyebrow">02 / MODELS</p><h1>One corpus.<br />One trained voice.</h1></div><p>Training costs $20, runs in the queue, and completes within 24 hours. Generation is on demand after that.</p></header>
    <section className="training-builder">
      <div><span>1 · CHOOSE CORPUS</span><select value={selectedCorpus} onChange={(event) => { setSelectedCorpus(event.target.value); setRevision(""); }}>{corpora.map((corpus) => <option key={corpus.id} value={corpus.id}>{corpus.name} · {corpus.usable_words} words</option>)}</select><button onClick={freezeCorpus} disabled={!selectedCorpus || busy}>{revision ? "REVISION FROZEN ✓" : "FREEZE READY CORPUS"}</button></div>
      <div><span>2 · NAME MODEL</span><input value={modelName} onChange={(event) => setModelName(event.target.value)} maxLength={80} /></div>
      <div><span>3 · TRAIN</span><b>$20</b><small>Includes one custom model and 20 generation credits.</small>{!entitled ? <button onClick={buyTraining} disabled={!revision || busy}>PURCHASE TRAINING →</button> : <button onClick={train} disabled={!revision || !modelName || busy}>START TRAINING →</button>}</div>
    </section>
    <section className="model-list"><span>YOUR MODELS · {models.length}</span>{models.map((model) => <article key={model.id}><div className="model-mark">VP</div><div><h3>{model.name}</h3><p>Qwen 2.5 14B · LoRA adapter</p></div><Status status={model.status} /></article>)}{!models.length && <p>No trained models yet.</p>}</section>
  </div>;
}

function WriteView({ models, credits, onRefresh, onNotice }: { models: Model[]; credits: number; onRefresh: () => Promise<void>; onNotice: (message: string) => void }) {
  const ready = models.filter((model) => model.status === "ready");
  const [modelId, setModelId] = useState(ready[0]?.id || "");
  const [notes, setNotes] = useState("");
  const [mode, setMode] = useState<"raw" | "edited">("raw");
  const [draft, setDraft] = useState("");
  const [warning, setWarning] = useState("");
  const [busy, setBusy] = useState(false);
  const [assistantRequest, setAssistantRequest] = useState("");
  const [assistantMessage, setAssistantMessage] = useState("");
  const [proposal, setProposal] = useState<DraftProposal | null>(null);
  const [creditPacks, setCreditPacks] = useState(1);

  async function buyCredits() {
    setBusy(true);
    try {
      const checkout = await api<{ url?: string; granted?: boolean; generation_credits?: number }>("/v1/checkout/credits", {
        method: "POST",
        body: JSON.stringify({ packs: creditPacks }),
      });
      if (checkout.url) window.location.assign(checkout.url);
      else if (checkout.granted) {
        await onRefresh();
        onNotice(`${checkout.generation_credits || creditPacks * 20} generation credits added.`);
      }
    } catch (error) { onNotice(error instanceof Error ? error.message : "Could not start credit checkout."); }
    setBusy(false);
  }

  async function requestDraft(input: DraftProposal) {
    setBusy(true); setDraft("");
    try {
      const result = await api<{ result?: { drafts?: string[]; warning?: string } }>("/v1/generations", { method: "POST", headers: { "idempotency-key": crypto.randomUUID() }, body: JSON.stringify(input) });
      setDraft(result.result?.drafts?.[0] || "Generation is queued. Check back shortly.");
      setWarning(result.result?.warning || "Raw adapter output; verify every fact.");
      setMode(input.mode);
      await onRefresh();
    } catch (error) { onNotice(error instanceof Error ? error.message : "Could not generate."); }
    setBusy(false);
  }

  async function generate(event: FormEvent) {
    event.preventDefault();
    await requestDraft({
      model_id: modelId,
      model_name: ready.find((model) => model.id === modelId)?.name || "Voice",
      operation: "write",
      mode,
      length: "medium",
      notes: notes.split(/\n/).map((line) => line.replace(/^[-*]\s*/, "").trim()).filter(Boolean),
    });
  }

  async function askAssistant(event: FormEvent) {
    event.preventDefault(); setBusy(true); setProposal(null);
    try {
      const result = await api<{ message: string; proposal: DraftProposal | null }>("/v1/assistant", {
        method: "POST",
        body: JSON.stringify({ message: assistantRequest, model_id: modelId, mode }),
      });
      setAssistantMessage(result.message);
      setProposal(result.proposal);
    } catch (error) { onNotice(error instanceof Error ? error.message : "The assistant could not prepare that request."); }
    setBusy(false);
  }

  return <div className="workspace-view write-view">
    <header className="workspace-header"><div><p className="eyebrow">03 / WRITE</p><h1>Facts in.<br />Your voice out.</h1></div><p>The assistant organizes the request. Your adapter writes the prose. Nothing silently polishes the result afterward.</p></header>
    <section className="credit-store"><div><span>GENERATION BALANCE</span><b>{credits} credits</b></div><label>ADD CREDITS<select value={creditPacks} onChange={(event) => setCreditPacks(Number(event.target.value))}><option value={1}>20 credits</option><option value={2}>40 credits</option><option value={5}>100 credits</option></select></label><button onClick={() => void buyCredits()} disabled={busy}>BUY CREDITS →</button></section>
    {!ready.length ? <div className="empty-work"><b>NO READY MODEL</b><p>Train a model first. We’ll email you when it is ready.</p></div> : <div className="composer">
      <div className="composer-controls">
        <form className="assistant-card" onSubmit={askAssistant}>
          <div><span>GUIDED REQUEST</span><small>The coordinator gathers facts and calls tools. It never writes the draft.</small></div>
          <textarea value={assistantRequest} onChange={(event) => setAssistantRequest(event.target.value)} minLength={10} required rows={5} placeholder="I need a short note to engineering leaders explaining why memory control matters. Ask me for anything missing." />
          <button disabled={busy}>{busy ? "ORGANIZING…" : "PREPARE REQUEST →"}</button>
          {assistantMessage && <p className="assistant-message">{assistantMessage}</p>}
          {proposal && <div className="assistant-proposal"><b>{proposal.model_name} · {proposal.length} · {proposal.mode}</b><ul>{proposal.notes.map((note) => <li key={note}>{note}</li>)}</ul><button type="button" disabled={busy || credits < 1} onClick={() => void requestDraft(proposal)}>CONFIRM &amp; GENERATE · 1 CREDIT →</button></div>}
        </form>
        <details className="direct-composer">
          <summary>Or prepare the request yourself</summary>
          <form onSubmit={generate}><label>VOICE<select value={modelId} onChange={(event) => setModelId(event.target.value)}>{ready.map((model) => <option value={model.id} key={model.id}>{model.name}</option>)}</select></label><label>FACTS / NOTES<textarea value={notes} onChange={(event) => setNotes(event.target.value)} required minLength={20} rows={8} placeholder={'- the audience is engineering leaders\n- the problem is memory control, not storage\n- end with the practical implication'} /></label><fieldset><legend>DELIVERY</legend><label className="mode-choice"><input type="radio" checked={mode === "raw"} onChange={() => setMode("raw")} /><span><b>RAW</b>Maximum fidelity; may contain errors.</span></label><label className="mode-choice"><input type="radio" checked={mode === "edited"} onChange={() => setMode("edited")} /><span><b>EDITED</b>Facts and grammar only; detector results may change.</span></label></fieldset><button className="button button-generate" disabled={busy || credits < 1}>{busy ? "WRITING…" : "GENERATE · 1 CREDIT"}<span>→</span></button></form>
        </details>
      </div>
      <section className="composer-output"><div><span>{mode.toUpperCase()} MODE</span><button onClick={() => draft && navigator.clipboard.writeText(draft)}>COPY</button></div>{draft ? <><article>{draft.split("\n").map((paragraph, index) => paragraph ? <p key={index}>{paragraph}</p> : <br key={index} />)}</article><small>{warning}</small></> : <div className="draft-placeholder"><span>Aa</span><p>Your draft will appear here.</p></div>}</section>
    </div>}
  </div>;
}

function ApiView({ onNotice }: { onNotice: (message: string) => void }) {
  const [name, setName] = useState("My integration");
  const [key, setKey] = useState("");
  async function createKey() {
    try {
      const created = await api<{ key: string }>("/v1/api-keys", { method: "POST", body: JSON.stringify({ name, scopes: ALL_SCOPES }) });
      setKey(created.key);
    } catch (error) { onNotice(error instanceof Error ? error.message : "Could not create the key."); }
  }
  return <div className="workspace-view api-view"><header className="workspace-header"><div><p className="eyebrow">04 / API</p><h1>The same tools,<br />from your code.</h1></div><p>Create corpora, train models, generate drafts, and inspect jobs through the same capability layer used by this workspace.</p></header><div className="api-grid"><section><span>PERSONAL API KEY</span><label>KEY NAME<input value={name} onChange={(event) => setName(event.target.value)} /></label><button className="button" onClick={createKey}>CREATE KEY <span>→</span></button>{key && <div className="key-reveal"><b>Copy this now. It will not be shown again.</b><code>{key}</code><button onClick={() => navigator.clipboard.writeText(key)}>COPY</button></div>}</section><section><span>QUICK START</span><pre><code>{`curl https://voiceprint.com/v1/models \\\n  -H "Authorization: Bearer vp_live_…"`}</code></pre><a href="/api-docs">OPEN API REFERENCE →</a></section></div></div>;
}
