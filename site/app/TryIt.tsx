"use client";

import { FormEvent, useState } from "react";

const SUGGESTIONS = ["Write a launch post", "Reply to an email", "Draft an essay intro"];

export function TryIt() {
  const [text, setText] = useState("");
  function start(event?: FormEvent) {
    event?.preventDefault();
    window.location.href = "/beta";
  }
  return (
    <div className="tryit-wrap">
      <form className="tryit" onSubmit={start}>
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Try writing something in your voice…"
          aria-label="Try writing something in your voice"
        />
        <button type="submit" aria-label="Send">↑</button>
      </form>
      <div className="tryit-suggestions">
        {SUGGESTIONS.map((suggestion) => (
          <button key={suggestion} type="button" onClick={() => start()}>{suggestion}</button>
        ))}
      </div>
    </div>
  );
}
