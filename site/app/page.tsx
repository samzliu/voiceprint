import type { Metadata } from "next";
import { TryIt } from "./TryIt";

export const metadata: Metadata = {
  title: "Voiceprint — write in your own voice, not AI slop",
  description:
    "Train a writing model on your own words. No code, a few thousand words, and everything you draft sounds like you.",
};

export default function Home() {
  return (
    <main>
      <nav className="nav shell" aria-label="Main navigation">
        <a className="wordmark" href="#top" aria-label="Voiceprint home">
          VOICEPRINT<span className="wordmark-dot">●</span>
        </a>
        <div className="nav-links">
          <a href="/beta">Sign in →</a>
          <a href="https://github.com/samzliu/voiceprint">GitHub ↗</a>
          <a href="https://pypi.org/project/voiceprint/">PyPI ↗</a>
        </div>
      </nav>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <h1>Stop writing<br />AI slop.</h1>
          <p className="dek">
            Voiceprint trains a writing model on your own words, so everything
            you draft sounds like you — not like a chatbot. Natural again.
          </p>
          <TryIt />
        </div>
      </section>

      <section className="proof shell" aria-labelledby="proof-title">
        <header className="section-header">
          <span>THE PROOF</span>
          <h2 id="proof-title">It reads as human.</h2>
        </header>
        <p className="proof-lede">
          A full essay drafted by a Voiceprint model, scored{" "}
          <strong>100% human-written</strong> by Pangram&rsquo;s AI detector.
        </p>
        <div className="proof-shot">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/pangram-human-written.png"
            alt="Pangram AI detector rating a Voiceprint-written essay 100% human-written"
          />
        </div>
      </section>

      <section className="how shell" aria-labelledby="how-title">
        <header className="section-header">
          <span>HOW</span>
          <h2 id="how-title">No code. A few thousand words.</h2>
        </header>
        <p className="how-lede">
          Paste a few pages you&rsquo;ve written. Voiceprint learns your voice
          and keeps it consistent — no fine-tuning setup, no prompt engineering,
          no data science.
        </p>
        <ol className="steps">
          <li><b>1</b><h3>Bring your writing</h3><p>A few thousand words you actually wrote.</p></li>
          <li><b>2</b><h3>Train your voice</h3><p>One click. Voiceprint learns how you write.</p></li>
          <li><b>3</b><h3>Draft anything</h3><p>Give it the facts; it writes in your voice.</p></li>
        </ol>
      </section>

      <section className="install shell">
        <div>
          <p className="eyebrow">DEVELOPERS · OPEN SOURCE</p>
          <h2>Use your voice from code.</h2>
          <p className="install-note">
            Every model you train is available through a simple API. Voiceprint
            is open source under MIT.
          </p>
        </div>
        <code><span>$</span> pip install voiceprint</code>
        <div className="install-links">
          <a className="button button-dark" href="/api-docs">API reference <span>→</span></a>
          <a href="https://github.com/samzliu/voiceprint">GitHub ↗</a>
          <a href="https://pypi.org/project/voiceprint/">PyPI ↗</a>
        </div>
      </section>

      <footer className="footer shell">
        <span>VOICEPRINT © 2026</span>
        <a href="/beta">Start writing →</a>
      </footer>
    </main>
  );
}
