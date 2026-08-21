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
          <h1>Make writing great again</h1>
          <p className="dek">
            Voiceprint trains a writing model on your own words, so everything
            you draft sounds like you, not AI slop.
          </p>
          <TryIt />
        </div>
      </section>

      <section className="proof shell" aria-labelledby="proof-title">
        <header className="section-header">
          <h2 id="proof-title">It sounds natural</h2>
        </header>
        <p className="proof-lede">Voiceprint writes in your voice.</p>
        <div className="proof-shot">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/pangram-human-written.png"
            alt="Pangram AI detector rating a Voiceprint-written essay 100% human-written"
          />
        </div>
        <div className="proof-points">
          <div>
            <b>Passes as human</b>
            <p>A full essay drafted by a Voiceprint model scored 100% human-written by Pangram&rsquo;s detector.</p>
          </div>
          <div>
            <b>No AI watermark</b>
            <p>Your final text is written by your own open model, not Claude or ChatGPT, so there&rsquo;s no hidden watermark.</p>
          </div>
        </div>
      </section>

      <section className="how shell" aria-labelledby="how-title">
        <header className="section-header">
          <h2 id="how-title">Train your own writing model, no code needed</h2>
        </header>
        <p className="how-lede">
          Voiceprint can learn your voice from just a few pages. No need for
          prompt engineering, data science, or post-training experience.
        </p>
        <ol className="steps">
          <li><b>1</b><h3>Bring your own writing</h3><p>Collect as little as a few thousand words.</p></li>
          <li><b>2</b><h3>Train your voice</h3><p>One click. Voiceprint learns how you write.</p></li>
          <li><b>3</b><h3>Draft anything</h3><p>Give it the facts or an outline. It fills in the rest in your voice.</p></li>
        </ol>
      </section>

      <section className="install shell">
        <div>
          <h2>Write via API</h2>
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
