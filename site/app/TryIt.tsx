"use client";

import { FormEvent, useState } from "react";

export function TryIt() {
  const [text, setText] = useState("");
  function start(event: FormEvent) {
    event.preventDefault();
    window.location.href = "/beta";
  }
  return (
    <form className="tryit" onSubmit={start}>
      <input
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Ask Voiceprint to write something in your voice…"
        aria-label="Ask Voiceprint to write something in your voice"
      />
      <div className="tryit-row">
        <span className="tryit-model">Voiceprint default</span>
        <button type="submit" className="tryit-send">Write <span>→</span></button>
      </div>
    </form>
  );
}
