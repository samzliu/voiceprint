"use client";

import { ChangeEvent, DragEvent, FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
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
  operation: "write" | "continue" | "rewrite" | "edit_span" | "revoice";
  mode: "raw" | "edited";
  length: "short" | "medium" | "long";
  notes: string[];
  preceding_text?: string;
  text?: string;
};
type GenerationResult = {
  drafts?: string[];
  warning?: string;
  final_writer?: string;
  finalized_by_adapter?: boolean;
};
type GenerationJob = { id: string; status: string; result?: GenerationResult };
type ChatMessage = { role: "user" | "assistant"; content: string; proposal?: DraftProposal | null };

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
  const [email, setEmail] = useState("");
  const [authSent, setAuthSent] = useState(false);
  const [authNotice, setAuthNotice] = useState("");
  const [devLink, setDevLink] = useState("");

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

  async function requestSignInLink(event: FormEvent) {
    event.preventDefault();
    setAuthNotice("");
    try {
      const result = await api<{ sent: boolean; dev_link?: string }>("/v1/auth/request", {
        method: "POST",
        body: JSON.stringify({ email: email.trim() }),
      });
      setAuthSent(true);
      if (result.dev_link) setDevLink(result.dev_link);
    } catch (error) {
      setAuthNotice(error instanceof Error ? error.message : "Could not send the sign-in link.");
    }
  }

  async function signOut() {
    await fetch("/v1/auth/logout", { method: "POST" });
    window.location.href = "/";
  }

  async function buyCredits() {
    try {
      const checkout = await api<{ url?: string; granted?: boolean; amount_cents?: number }>("/v1/checkout/credits", { method: "POST", body: JSON.stringify({}) });
      if (checkout.url) window.location.assign(checkout.url);
      else if (checkout.granted) { await refresh(); setNotice(`$${((checkout.amount_cents || 0) / 100).toFixed(2)} added to your balance.`); }
    } catch (error) { setNotice(error instanceof Error ? error.message : "Could not start credit checkout."); }
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
          <p>Sign in with your email, bring a few pages of prose you wrote, and Voiceprint will verify the corpus before you spend anything.</p>
          {authSent ? (
            <div className="beta-auth-sent">
              <b>Check your email.</b>
              <p>We sent a sign-in link to {email}. It expires in 15 minutes.</p>
              {devLink && <p className="beta-auth-devlink"><a href={devLink}>Open dev sign-in link →</a></p>}
            </div>
          ) : (
            <form className="beta-signin-form" onSubmit={requestSignInLink}>
              <label>EMAIL<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label>
              <button className="button beta-signin" type="submit">EMAIL ME A SIGN-IN LINK <span>→</span></button>
              {authNotice && <small role="alert">{authNotice}</small>}
            </form>
          )}
        </section>
      </main>
    );
  }

  const needsOnboarding = !session?.user.writing_goals;
  if (needsOnboarding) {
    return (
      <main className="beta-onboard">
        <Link className="wordmark" href="/">VOICEPRINT<span className="wordmark-dot">●</span></Link>
        {notice && <div className="beta-notice" role="status"><span>{notice}</span><button onClick={() => setNotice("")} aria-label="Dismiss">×</button></div>}
        <Onboarding onComplete={refresh} />
      </main>
    );
  }
  return (
    <main className="beta-app">
      <aside className="beta-sidebar">
        <Link className="wordmark" href="/">VOICEPRINT<span className="wordmark-dot">●</span></Link>
        <nav aria-label="Workspace">
          <button className={tab === "corpus" ? "active" : ""} onClick={() => setTab("corpus")}>Corpus</button>
          <button className={tab === "models" ? "active" : ""} onClick={() => setTab("models")}>Models</button>
          <button className={tab === "write" ? "active" : ""} onClick={() => setTab("write")}>Write</button>
          <button className={tab === "api" ? "active" : ""} onClick={() => setTab("api")}>API</button>
        </nav>
        <div className="beta-account">
          <div className="beta-balance"><b>${(((session?.credits ?? 0)) / 100).toFixed(2)}</b><button className="beta-addcredits" onClick={() => void buyCredits()}>Add credits</button></div>
          <span className="beta-who">{session?.user.name || session?.user.email}</span>
          <button className="beta-signout" onClick={signOut}>Sign out</button>
        </div>
      </aside>

      <section className="beta-main">
        {notice && <div className="beta-notice" role="status"><span>{notice}</span><button onClick={() => setNotice("")} aria-label="Dismiss">×</button></div>}
        {tab === "corpus" ? (
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
      <p className="eyebrow">WELCOME</p>
      <h1>Let&rsquo;s set up your account.</h1>
      <form onSubmit={submit}>
        <label>Your name<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={120} placeholder="Jane Doe" /></label>
        <label>What&rsquo;s your role?<input value={goals} onChange={(event) => setGoals(event.target.value)} required maxLength={120} placeholder="Founder, writer, marketer…" /></label>
        <label>What do you want to use Voiceprint for?<textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} placeholder="Investor updates, launch posts, newsletters…" /></label>
        <button className="button button-generate" disabled={busy}>{busy ? "SAVING…" : "CONTINUE"}<span>→</span></button>
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
    <header className="workspace-header"><div><p className="eyebrow">02 / MODELS</p><h1>One corpus.<br />One trained voice.</h1></div><p>Train a private model on your own writing.</p></header>
    <section className="training-builder">
      <div><span>1 · CHOOSE CORPUS</span><select value={selectedCorpus} onChange={(event) => { setSelectedCorpus(event.target.value); setRevision(""); }}>{corpora.map((corpus) => <option key={corpus.id} value={corpus.id}>{corpus.name} · {corpus.usable_words} words</option>)}</select><button onClick={freezeCorpus} disabled={!selectedCorpus || busy}>{revision ? "REVISION FROZEN ✓" : "FREEZE READY CORPUS"}</button></div>
      <div><span>2 · NAME MODEL</span><input value={modelName} onChange={(event) => setModelName(event.target.value)} maxLength={80} /></div>
      <div><span>3 · TRAIN</span><b>$20</b><small>Includes a custom voice and $1 of free generation.</small>{!entitled ? <button onClick={buyTraining} disabled={!revision || busy}>PURCHASE TRAINING →</button> : <button onClick={train} disabled={!revision || !modelName || busy}>START TRAINING →</button>}</div>
    </section>
    <section className="model-list"><span>YOUR MODELS · {models.length}</span>{models.map((model) => <article key={model.id}><div className="model-mark">VP</div><div><h3>{model.name}</h3><p>Custom voice model</p></div><Status status={model.status} /></article>)}{!models.length && <p>No trained models yet.</p>}</section>
  </div>;
}

function WriteView({ models, credits, onRefresh, onNotice }: { models: Model[]; credits: number; onRefresh: () => Promise<void>; onNotice: (message: string) => void }) {
  const ready = models.filter((model) => model.status === "ready");
  const [modelId, setModelId] = useState(ready[0]?.id || "");
  const mode = "raw" as const;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [warning, setWarning] = useState("");
  const logRef = useRef<HTMLDivElement>(null);
  const selectedModel = modelId || ready[0]?.id || "";

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  async function requestDraft(input: DraftProposal) {
    setBusy(true);
    try {
      let result = await api<GenerationJob>("/v1/generations", { method: "POST", headers: { "idempotency-key": crypto.randomUUID() }, body: JSON.stringify(input) });
      for (let attempt = 0; !result.result && result.status !== "failed" && attempt < 240; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1_500));
        result = await api<GenerationJob>(`/v1/jobs/${result.id}`);
      }
      if (!result.result) throw new Error("Generation is still running. You can safely retry from the workspace shortly.");
      setDraft(result.result?.drafts?.[0] || "Generation is queued. Check back shortly.");
      setWarning(result.result?.warning || "Draft ready — verify every fact before publishing.");
      setMessages((prev) => [...prev, { role: "assistant", content: "Draft ready — it is in the editor on the right. Edit it there, or tell me what to change and I will prepare a revision." }]);
      await onRefresh();
    } catch (error) { onNotice(error instanceof Error ? error.message : "Could not generate."); }
    setBusy(false);
  }

  async function submitMessage() {
    const text = input.trim();
    if (!text || busy) return;
    const nextHistory: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages(nextHistory);
    setInput("");
    setBusy(true);
    try {
      const result = await api<{ message: string; proposal: DraftProposal | null }>("/v1/assistant", {
        method: "POST",
        body: JSON.stringify({
          messages: nextHistory.map(({ role, content }) => ({ role, content })),
          model_id: selectedModel,
          mode,
          ...(draft ? { text: draft } : {}),
        }),
      });
      setMessages((prev) => [...prev, { role: "assistant", content: result.message, proposal: result.proposal }]);
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "The assistant could not respond.");
      setMessages((prev) => [...prev, { role: "assistant", content: "Sorry — I could not process that. Please try again." }]);
    }
    setBusy(false);
  }

  function onChatSubmit(event: FormEvent) {
    event.preventDefault();
    void submitMessage();
  }

  function onChatKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitMessage();
    }
  }

  return <div className="write-view">
    {!ready.length ? <div className="empty-work"><b>No voice ready</b><p>Train a model first, or use the shared voice.</p></div> : <div className="chat-composer">
      <section className="chat-panel">
        <div className="chat-toolbar">
          <label>VOICE<select value={selectedModel} onChange={(event) => setModelId(event.target.value)}>{ready.map((model) => <option value={model.id} key={model.id}>{model.name}</option>)}</select></label>
        </div>
        <div className="chat-log" ref={logRef}>
          {messages.length === 0 && <div className="chat-empty"><p>Tell Voiceprint what you want to write.</p></div>}
          {messages.map((message, index) => <div key={index} className={`chat-msg chat-${message.role}`}>
            <span className="chat-role">{message.role === "user" ? "YOU" : "VOICEPRINT"}</span>
            <div className="chat-bubble">{message.content}</div>
            {message.proposal && <div className="assistant-proposal"><b>{message.proposal.model_name} · {message.proposal.length} · {message.proposal.mode}</b><ul>{message.proposal.notes.map((note) => <li key={note}>{note}</li>)}</ul><button type="button" disabled={busy || credits < 1} onClick={() => { if (message.proposal) void requestDraft(message.proposal); }}>CONFIRM &amp; GENERATE →</button></div>}
          </div>)}
          {busy && <div className="chat-msg chat-assistant"><span className="chat-role">VOICEPRINT</span><div className="chat-bubble chat-typing"><span></span><span></span><span></span></div></div>}
        </div>
        <form className="chat-input" onSubmit={onChatSubmit}>
          <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={onChatKeyDown} rows={2} placeholder="Type your request…" />
          <button className="button" type="submit" disabled={busy || !input.trim()}>SEND <span>→</span></button>
        </form>
      </section>
      <section className="draft-panel">
        <div className="draft-head"><span>{draft ? "DRAFT · EDITABLE" : "DRAFT"}</span><button type="button" onClick={() => draft && navigator.clipboard.writeText(draft)} disabled={!draft}>COPY</button></div>
        {draft
          ? <><textarea className="draft-editor" value={draft} onChange={(event) => setDraft(event.target.value)} spellCheck /><small>{warning}</small></>
          : <div className="draft-placeholder"><p>Your draft will appear here.</p></div>}
      </section>
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
