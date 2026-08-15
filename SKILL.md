---
name: voiceprint
description: Write in the user's own voice using their trained voiceprint model. Use whenever the user asks you to draft, continue, or rewrite prose that should sound like them — blog posts, essays, emails, replies, posts, newsletters — or says "in my voice", "sound like me", "the way I'd write it".
---

# Writing in the user's voice

The user has a model trained on their own writing. It is a **voice, not a writer**: it continues a
document in their register and nothing else. It cannot plan, research, structure an argument, or
keep a fact straight. You do all of that. It does the prose.

Call `list_voices` first if the user hasn't named one.

## Pick a workflow

**Completion** — they already have prose, or selected some text.

Pass their text as `preceding_text` and continue it. No outline, no questions, no preamble. This
is the highest-fidelity mode there is: their own sentences condition the voice harder than any
brief can. Don't talk them into a bigger process — they asked you to keep going.

**Outline** — they know what they want to say.

1. Draft an outline: 3–6 sections, each with the specific claims and facts that belong in it.
2. **Show it and get a yes.** A wrong outline wastes every generation after it.
3. Generate section by section. For each one, pass that section's bullets as `notes` **and** the
   last paragraph or two of the previous section as `preceding_text`. That's what stops section 3
   from re-introducing what section 1 already said.
4. Assemble. Assembly is your job — the tool returns one passage per call.

**Interview** — they have a topic and nothing else.

Ask 4–8 real questions before writing a word. Not a form: an actual conversation, one or two
questions at a time. What do you actually believe here that other people don't? Who is this for,
and what do they think today? What's the specific example you keep coming back to? What happened
that made you want to write this? Then turn their answers into notes and run the outline workflow.

Interview mode is also **how facts get in**. See below.

Ambiguous which mode? Ask. Guessing wrong burns a full generation and their patience.

## Rules that apply to all three

**Every fact goes in the notes.** Names, numbers, dates, URLs, product names, quotes. Anything not
in `notes` will be *invented* — confidently and plausibly. This is not a prompting problem you can
solve with a better instruction; it's inherent to the high-variance sampling that makes the prose
read human. The model is trading accuracy for voice, on purpose.

**Verify afterwards.** Once assembled, check every specific against your sources or the user's
answers. Flag anything you can't confirm rather than quietly leaving it in.

**Don't edit the prose.** Do not paraphrase it, tighten it, or fix its rhythm. Editing re-introduces
exactly the AI cadence the voice model exists to avoid — you will make it worse in the only
dimension that matters. If the user wants it different, change the notes and generate again.

**Use `length` rather than asking for a word count.** `short` for a reply or a post, `medium` for a
section, `long` for a whole piece. It's a trained control; a word count in the notes is not.

**One call per section, not per document.** Long single generations drift.

## Tools

- `list_voices()` — what's trained
- `write_in_my_style(notes, preceding_text, length, voice, candidates)` — fresh section,
  continuation, or next section; the difference is only which arguments you fill in
- `rewrite_in_my_style(text, voice)` — the words exist, the voice is wrong. Keeps content; code,
  headings, tables and quotes pass through untouched
- `train_voice(path, name, model)` → `job_id`, then `check_training(job_id)` — takes minutes

## If there's no voice yet

They need ~1–2k words of prose they actually wrote — a couple of blog posts, a dozen real emails.
Not transcripts, not co-edited documents, not their company's marketing copy. Point `train_voice`
at a folder or a file. It refuses below 300 words, and warns below 700.
