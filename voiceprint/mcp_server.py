"""MCP server — the surface that matters.

The tools are deliberately dumb. They do one thing: turn a brief into prose that
sounds like the user. The planning, the research, the section order and the
fact-checking are the calling agent's job, and the descriptions here say so,
because an agent reads tool descriptions even when it hasn't loaded SKILL.md.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from voiceprint import engine, registry, train
from voiceprint.scaffold import DEFAULT_N

INSTRUCTIONS = """voiceprint writes in the user's own voice, learned from their writing.

It is a voice, not a writer. It cannot plan, research, or keep facts straight — you do that. Pick
one of three workflows:

  completion  The user already has prose. Pass it as preceding_text and continue it. No planning.
  outline     The user knows what they want to say. Draft an outline, show it, get a yes, then
              generate section by section, passing the tail of the previous section as
              preceding_text so sections connect and don't repeat.
  interview   The user has a topic and nothing else. Ask 4-8 real questions — what they actually
              believe, who it's for, the specific example they have in mind — then turn their
              answers into notes and follow the outline workflow.

Interview is not just for the blank page: it is how facts get in. Every name, number, date and URL
must appear in `notes`, or the model will invent one. That is inherent to the sampling that makes
the prose read human, and it cannot be prompted away.

After assembling, verify every specific against your sources. Do not paraphrase the returned prose
to improve it — editing it re-introduces the AI cadence the voice model exists to avoid. If the
user wants it different, change the notes and generate again."""

server = MCPServer(name="voiceprint", instructions=INSTRUCTIONS)


@server.tool()
def list_voices() -> list[dict]:
    """List the voices this user has trained. Call this first if no voice is named."""
    return [
        {"name": v.name, "words": v.words, "base": v.base, "trained_at": v.trained_at}
        for v in registry.load_all()
    ]


@server.tool()
def write_in_my_style(
    notes: list[str] | None = None,
    preceding_text: str = "",
    length: str = "medium",
    voice: str | None = None,
    candidates: int = DEFAULT_N,
) -> dict:
    """Write a passage in the user's voice. One call per section, not per document.

    notes: the brief, as bullets. Put EVERY fact, name, number and URL you want in the output
        here — anything absent will be invented.
    preceding_text: prose the passage should continue from. For a continuation, this is the user's
        own text. For section N of a long piece, pass the last paragraph or two of section N-1.
        Supplying it is what keeps sections connected and stops them repeating each other.
    length: "short" (a reply or a post), "medium" (a section), "long" (a whole piece). This is a
        trained control, so use it rather than asking for a word count in the notes.
    candidates: how many drafts to sample before returning the best-ranked one.

    Returns the winning draft plus its style score. Use the prose as-is.
    """
    draft = engine.write(
        notes=notes,
        preceding_text=preceding_text,
        length=length,
        voice_name=voice,
        n=candidates,
        temperature=1.5,
    )
    return {"text": draft.text, "style_score": round(draft.score, 3), "candidates": candidates}


@server.tool()
def rewrite_in_my_style(text: str, voice: str | None = None) -> dict:
    """Rewrite existing text so it sounds like the user, keeping its content.

    Use this when the words already exist and only the voice is wrong — an AI-sounding draft, or
    the user's own rough dump. Code blocks, headings, tables and quotes pass through untouched.
    Do not use it to write something new; use write_in_my_style for that.
    """
    return {"text": engine.rewrite(text, voice_name=voice)}


@server.tool()
def train_voice(path: str, name: str, model: str = "14b") -> dict:
    """Start training a new voice from a file or folder of the user's writing.

    Takes several minutes, so this returns a job_id immediately — poll check_training with it.
    Needs ~1-2k words of prose the user actually wrote; it refuses below 300 words.
    """
    return {
        "job_id": train.spawn(path, name, model),
        "note": "training runs on the user's own Modal account; poll check_training",
    }


@server.tool()
def check_training(job_id: str) -> dict:
    """Check a training job. Returns status 'running' until the voice is ready to write with."""
    voice = train.collect(job_id)
    if voice is None:
        return {"status": "running"}
    return {
        "status": "ready",
        "voice": voice.name,
        "words": voice.words,
        "pairs": voice.pairs,
    }


def run() -> None:
    server.run("stdio")
