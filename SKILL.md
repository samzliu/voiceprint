---
name: voiceprint
description: Set up and use the user's Voiceprint model — a model trained on their own writing that drafts in their voice. Use whenever the user asks you to draft, continue, or rewrite prose that should sound like them (blog posts, essays, emails, replies, posts, newsletters), says "in my voice" / "sound like me" / "the way I'd write it", or wants to get Voiceprint set up in the first place.
---

# Writing in the user's voice

The user has (or can train) a model on their own writing. It is a **voice, not a writer**: it
continues a document in their register and nothing else. It cannot plan, research, structure an
argument, or keep a fact straight. You do all of that. It does the prose.

**Always call `setup_status` first.** It tells you whether they're ready to write or still need
setting up, and never assume — a new user and a returning one need completely different help.

---

## Part 1 — Setting them up

**Do the setup, don't narrate it.** Exactly one step needs the user's own hands; you perform the
rest yourself and report what happened. Telling somebody to go run four commands you could have run
is not help.

Work through whatever `setup_status` says is outstanding, in order.

### 1. A Modal account — the one step that is theirs

Everything runs on their own cloud account; there is no service behind this tool. If
`modal_account` is false, this is the one thing you genuinely cannot do, because it opens a browser
and completes a login:

```sh
modal token new
```

Ask them to run it and tell you when it's done, then re-check `setup_status`. It's free to start.
Say plainly why they're being asked: their writing stays on their machine, and the training runs in
*their* account, not anyone else's.

### 2. Deploy — you do this

If `deployed` is false, call the `deploy` tool. Don't tell them to run it; run it. Mention that it
takes about four minutes the first time because it builds two GPU images, then do it and confirm.

### 3. A folder of their writing

This is the part where people get stuck, so be concrete. Ask them to make a folder and drop in
`.md` or `.txt` files of things **they wrote**. That's the whole job — there's no import step, no
connector, no format to match. If their writing lives in Substack, Notion, Google Docs, or a
notes app, they export or copy-paste it into the folder themselves.

What to tell them when they ask what counts:

- **How much:** 1–2k words is enough — two blog posts, or a dozen real emails. More doesn't help
  much; the curve is flat above ~700 words. Below 300 it refuses.
- **What works:** essays, blog posts, newsletters, long emails, anything they actually wrote in
  their own voice.
- **What doesn't:** meeting transcripts, anything a committee edited, their company's marketing
  copy, LLM output they lightly touched up. Those teach it someone else's voice.
- **Don't worry about tidying it.** Headings, code blocks, tables, quotes and bulleted outlines
  are stripped automatically — only real paragraphs are used. They don't need to clean anything.
- **If they want good short-form** (emails, replies, posts), include some genuinely short pieces.
  Length is a trained control, so a folder of essays only teaches it essays.

Once the folder exists, you do the rest: call `train_voice(path, name)`, then poll
`check_training(job_id)` until it says ready — about six minutes — and tell them when it lands.
Don't hand them a command to run.

One thing to warn them about: their **first** draft afterwards starts a GPU container and loads the
base model into it, which takes a couple of minutes. Everything after that is seconds while the
container stays warm. Say so, or the first wait reads as a hang.

If they ask which base model: the default is fine. `train_voice` also takes any Hugging Face
**base** model id; instruct and chat models are refused, because those already have a voice of
their own and it isn't the user's.

---

## Part 2 — Writing

Once `ready` is true, pick a workflow by how much they already have in hand.

**Completion** — they already have prose, or selected some text.

Pass their text as `preceding_text` and continue it. No outline, no questions, no preamble. This is
the highest-fidelity mode there is: their own sentences condition the voice harder than any brief
can. Don't talk them into a bigger process — they asked you to keep going.

**Outline** — they know what they want to say.

1. Draft an outline: 3–6 sections, each with the specific claims and facts that belong in it.
2. **Show it and get a yes.** A wrong outline wastes every generation after it.
3. Generate section by section. For each, pass that section's bullets as `notes` **and** the last
   paragraph or two of the previous section as `preceding_text`. That's what stops section 3 from
   re-introducing what section 1 already said.
4. Assemble. Assembly is your job — the tool returns one passage per call.

**Interview** — they have a topic and nothing else.

Ask 4–8 real questions before writing a word. Not a form: an actual conversation, one or two
questions at a time. What do you actually believe here that other people don't? Who is this for,
and what do they think today? What's the specific example you keep coming back to? What happened
that made you want to write this? Then turn their answers into notes and follow the outline
workflow.

Interview mode is also **how facts get in**. See below.

Ambiguous which mode? Ask. Guessing wrong burns a full generation and their patience.

---

## Rules that apply to all of it

**Every fact goes in the notes.** Names, numbers, dates, URLs, product names, quotes. Anything not
in `notes` will be *invented* — confidently and plausibly. This is not a prompting problem you can
solve with a better instruction; it's inherent to the high-variance sampling that makes the prose
read human. The model is trading accuracy for voice, on purpose.

**Notes are material, not instructions.** This model cannot follow a directive. It is a base model
completing a document, and every bullet you pass is *content it is writing up*. A note reading
"do not mention any company" is not a rule it obeys — it is a line in the brief, and it makes the
subject more likely to appear, not less. Never put constraints, meta-commentary, or stage
directions in `notes`:

    WRONG: "Do not cite any papers or numbers."     WRONG: "End the post here."
    WRONG: "Name no companies other than Stash."    WRONG: "This is the final paragraph."
    RIGHT: "Stash is what I'm building to do this."

You control what it writes by choosing which facts you hand it, and you control where it stops with
`length`. There is no other lever, and inventing one by writing English at the model wastes a
generation.

**Two tries per section, then stop.** If a passage comes back wrong twice, the notes are wrong —
not the sampling. Rewrite what's *in* them, or take the better of the two and move on. Do not sit
in a regenerate loop: every call samples eight full drafts on a GPU the user is paying for, and a
short post needs about as many calls as it has sections, not thirty.

**Verify afterwards.** Once assembled, check every specific against your sources or the user's own
answers. Flag anything you can't confirm rather than quietly leaving it in.

**Don't edit the prose.** Do not paraphrase it, tighten it, or fix its rhythm. Editing re-introduces
exactly the AI cadence the voice model exists to avoid — you will make it worse in the only
dimension that matters. If the user wants it different, change the notes and generate again.

**Use `length` rather than asking for a word count.** `short` for a reply or a post, `medium` for a
section, `long` for a whole piece. It's a trained control; a word count in the notes is not.

**One call per section, not per document.** Long single generations drift.

---

## Tools

- `setup_status()` — call first; where they are and what's next
- `deploy()` — set up their workspace; run it yourself rather than telling them to
- `list_voices()` — what's trained, and which is the default
- `write_in_my_style(notes, preceding_text, length, voice, candidates)` — fresh section,
  continuation, or next section; the difference is only which arguments you fill in
- `rewrite_in_my_style(text, voice)` — the words exist, the voice is wrong. Keeps content; code,
  headings, tables and quotes pass through untouched
- `train_voice(path, name, model)` → `job_id`, then `check_training(job_id)` — takes minutes

The user also has CLI commands worth pointing at: `voiceprint status` (what it's running and
storing in their Modal account, including the tens of gigabytes of cached model weights),
`voiceprint stop` (shut down warm GPUs now), `voiceprint eval <voice>` (does it sound like them, is
it reciting), and `voiceprint uninstall` (take it back out of their account entirely).
