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
        placeholder="Describe something you want to write…"
        aria-label="Describe something you want to write"
      />
      <button type="submit">Try it <span>→</span></button>
    </form>
  );
}
