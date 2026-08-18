"use client";

import { FormEvent, useState } from "react";

type GenerateResponse = {
  drafts?: string[];
  error?: string;
  remaining?: number;
  jobId?: string;
};

export function Demo({ initialBrief }: { initialBrief: string }) {
  const [brief, setBrief] = useState(initialBrief);
  const [length, setLength] = useState<"short" | "medium">("medium");
  const [drafts, setDrafts] = useState<string[]>([]);
  const [activeDraft, setActiveDraft] = useState(0);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [message, setMessage] = useState("");
  const [copied, setCopied] = useState(false);

  async function generate(event: FormEvent) {
    event.preventDefault();
    setStatus("loading");
    setMessage("");
    setCopied(false);
    try {
      const response = await fetch("/api/generate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ brief, length }),
      });
      const data = (await response.json()) as GenerateResponse;
      if (!response.ok || !data.jobId) {
        throw new Error(data.error || "The draft did not make it back. Try again.");
      }
      setRemaining(typeof data.remaining === "number" ? data.remaining : null);

      let completed: GenerateResponse | null = null;
      for (let attempt = 0; attempt < 180; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 3_000));
        const result = await fetch(`/api/generate?job=${encodeURIComponent(data.jobId)}`);
        const resultData = (await result.json()) as GenerateResponse;
        if (result.status === 202) continue;
        if (!result.ok || !resultData.drafts?.length) {
          throw new Error(resultData.error || "The draft did not make it back. Try again.");
        }
        completed = resultData;
        break;
      }
      if (!completed?.drafts?.length) {
        throw new Error("The model is still busy. Please try again in a moment.");
      }
      setDrafts(completed.drafts);
      setActiveDraft(0);
      setStatus("done");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Something went wrong.");
      setStatus("error");
    }
  }

  async function copyDraft() {
    await navigator.clipboard.writeText(drafts[activeDraft]);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="workbench">
      <form className="brief-panel" onSubmit={generate}>
        <label htmlFor="brief">NOTES / BRIEF</label>
        <textarea
          id="brief"
          value={brief}
          onChange={(event) => setBrief(event.target.value)}
          minLength={20}
          maxLength={1200}
          rows={11}
          disabled={status === "loading"}
        />
        <div className="brief-meta">
          <span>{brief.length} / 1200</span>
          <span>Facts in. No fact-checking out.</span>
        </div>
        <fieldset>
          <legend>LENGTH</legend>
          {(["short", "medium"] as const).map((option) => (
            <label className="length-option" key={option}>
              <input
                type="radio"
                name="length"
                value={option}
                checked={length === option}
                onChange={() => setLength(option)}
                disabled={status === "loading"}
              />
              <span>{option.toUpperCase()}</span>
            </label>
          ))}
        </fieldset>
        <button className="button button-generate" type="submit" disabled={status === "loading"}>
          {status === "loading" ? "WARMING THE MODEL…" : "WRITE THE DRAFT"}
          <span>{status === "loading" ? "◌" : "→"}</span>
        </button>
        <p className="quota-note">
          3 runs per person daily · 40 total · A cold model can take a few minutes
        </p>
      </form>

      <section className={`draft-panel state-${status}`} aria-live="polite">
        <div className="draft-toolbar">
          <span>RAW MODE · VOICE / SAM · CANDIDATE {drafts.length ? activeDraft + 1 : "—"}</span>
          {status === "done" && (
            <button type="button" onClick={copyDraft}>{copied ? "COPIED" : "COPY"}</button>
          )}
        </div>
        {status === "idle" && (
          <div className="draft-placeholder">
            <span aria-hidden="true">Aa</span>
            <p>Your draft will appear here.</p>
            <small>The first request may wake a cold GPU.</small>
          </div>
        )}
        {status === "loading" && (
          <div className="draft-loading">
            <span className="loading-line" /><span className="loading-line short" />
            <p>Loading the base model and applying the trained adapter…</p>
          </div>
        )}
        {status === "error" && (
          <div className="draft-error"><b>COULDN’T GENERATE</b><p>{message}</p></div>
        )}
        {status === "done" && (
          <>
            <article className="draft-copy">
              {drafts[activeDraft].split("\n").map((paragraph, index) => (
                paragraph ? <p key={index}>{paragraph}</p> : <br key={index} />
              ))}
            </article>
            <div className="draft-footer">
              <span>{remaining === null ? "VERIFY FACTS BEFORE USE" : `${remaining} RUN${remaining === 1 ? "" : "S"} LEFT · VERIFY FACTS`}</span>
              {drafts.length > 1 && (
                <button type="button" onClick={() => setActiveDraft((activeDraft + 1) % drafts.length)}>
                  SHOW ALTERNATE →
                </button>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
