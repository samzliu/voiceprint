import type { Metadata } from "next";
import { Demo } from "./Demo";

export const metadata: Metadata = {
  title: "Voiceprint — write in a trained human voice",
  description:
    "A live demo of Voiceprint: a personal writing model trained on real prose.",
};

const exampleBrief = `Explain why AI memory is a control problem, not just a storage problem.
Mention context distillation, selective retrieval, and habits that become reusable skills.
End with a practical implication for people building agents.`;

export default function Home() {
  return (
    <main>
      <nav className="nav shell" aria-label="Main navigation">
        <a className="wordmark" href="#top" aria-label="Voiceprint home">
          VOICEPRINT<span className="wordmark-dot">●</span>
        </a>
        <div className="nav-links">
          <a href="https://github.com/samzliu/voiceprint">GitHub ↗</a>
          <a href="https://pypi.org/project/voiceprint/">PyPI ↗</a>
        </div>
      </nav>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow"><span className="live-dot" /> LIVE MODEL · QWEN 2.5 14B + LORA</p>
          <h1>Give it the facts.<br />Get back a voice.</h1>
          <p className="dek">
            Voiceprint trains an open model on writing you actually wrote. This
            demo runs one real voice—not a prompt pretending to be a person.
          </p>
        </div>
        <div className="hero-stamp" aria-hidden="true">
          <span>8793</span>
          <small>TRAINING<br />WORDS</small>
        </div>
      </section>

      <section className="demo-section shell" aria-labelledby="demo-title">
        <header className="section-header">
          <span>01 / TRY IT</span>
          <h2 id="demo-title">What should it write?</h2>
        </header>
        <Demo initialBrief={exampleBrief} />
      </section>

      <section className="proof shell" aria-labelledby="proof-title">
        <header className="section-header">
          <span>02 / THE OUTPUT</span>
          <h2 id="proof-title">Not a style prompt.</h2>
        </header>
        <div className="proof-grid">
          <blockquote>
            “The valuable thing an agent carries forward may not be a fact. It
            may be a policy: check your answer before you ship it; split an
            ambiguous task before acting; back out when the evidence changes.”
          </blockquote>
          <div className="proof-note">
            <p>
              The raw Voiceprint draft scored <strong>0.851</strong> before editing.
              The quotation shown here comes from the substantially edited,
              fact-checked version; that final version was not assigned the raw score.
            </p>
            <a href="https://github.com/samzliu/voiceprint/blob/main/examples/ai-memory-is-a-control-problem.raw.md">Read the raw output ↗</a>
            <a href="https://github.com/samzliu/voiceprint/blob/main/examples/ai-memory-is-a-control-problem.md">Read the edited sample ↗</a>
          </div>
        </div>
      </section>

      <section className="how shell" aria-labelledby="how-title">
        <header className="section-header">
          <span>03 / HOW IT WORKS</span>
          <h2 id="how-title">Your prose, compressed.</h2>
        </header>
        <ol className="steps">
          <li><b>1</b><h3>Bring a corpus</h3><p>Consistent writing you authored—essays, posts, notes, or newsletters.</p></li>
          <li><b>2</b><h3>Train the adapter</h3><p>A small LoRA learns the recurring choices in your prose on your Modal account.</p></li>
          <li><b>3</b><h3>Write from facts</h3><p>Give it notes, not a costume prompt. It returns candidate drafts and ranks the match.</p></li>
        </ol>
        <div className="mode-note">
          <p><strong>RAW MODE</strong> preserves the adapter output and its measured voice, but may contain errors.</p>
          <p><strong>EDITED MODE</strong> fixes facts and grammar only. Any AI editing can change detector results, so score the exact final text.</p>
        </div>
      </section>

      <section className="install shell">
        <div>
          <p className="eyebrow">OPEN SOURCE · MIT</p>
          <h2>Run your own voice.</h2>
        </div>
        <code><span>$</span> pip install voiceprint</code>
        <a className="button button-dark" href="https://github.com/samzliu/voiceprint">
          View source <span>↗</span>
        </a>
      </section>

      <footer className="footer shell">
        <span>VOICEPRINT © 2026</span>
        <span>THE DEMO IS AI-GENERATED. THE VOICE IS TRAINED.</span>
      </footer>
    </main>
  );
}
