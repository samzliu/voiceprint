import { createGateway, generateText, stepCountIs, tool, ToolLoopAgent } from "ai";
import { z } from "zod";

import type { AppEnv } from "./api";

export type AssistantUser = { id: string; email: string };

export type DraftProposal = {
  model_id: string;
  model_name: string;
  operation: "write" | "continue" | "rewrite";
  mode: "raw" | "edited";
  length: "short" | "medium" | "long";
  notes: string[];
  preceding_text?: string;
  text?: string;
};

type AssistantReply = {
  message: string;
  proposal: DraftProposal | null;
  usage?: { input_tokens?: number; output_tokens?: number; total_tokens?: number };
};

const MAX_MESSAGE_LENGTH = 4_000;
const DEFAULT_ROUTER_MODEL = "openai/gpt-5.6-luna";

async function workspace(env: AppEnv, ownerId: string) {
  const models = await env.DB.prepare(
    "SELECT id, name, status FROM models WHERE owner_id = ? ORDER BY updated_at DESC",
  ).bind(ownerId).all<{ id: string; name: string; status: string }>();
  const credits = await env.DB.prepare(
    "SELECT COALESCE(SUM(delta), 0) AS balance FROM credit_ledger WHERE owner_id = ?",
  ).bind(ownerId).first<{ balance: number }>();
  return { models: models.results, credits: Number(credits?.balance || 0) };
}

function normalizeNotes(notes: string[]): string[] {
  return notes
    .map((note) => note.replace(/^[-*\u2022]\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 12)
    .map((note) => note.slice(0, 500));
}

async function deterministicReply(
  env: AppEnv,
  user: AssistantUser,
  message: string,
  defaults: Partial<DraftProposal>,
): Promise<AssistantReply> {
  const state = await workspace(env, user.id);
  const ready = state.models.filter((model) => model.status === "ready");
  if (!ready.length) {
    return { message: "Train a model first. I can help shape the request as soon as it is ready.", proposal: null };
  }
  const selected = ready.find((model) => model.id === defaults.model_id) || ready[0];
  const notes = normalizeNotes(message.split(/\n|(?<=[.!?])\s+/));
  if (!notes.length) return { message: "What should the piece say? Give me the facts or points that must be included.", proposal: null };
  const lower = message.toLowerCase();
  const inferredLength = /\b(short|brief|concise)\b/.test(lower)
    ? "short"
    : /\b(long|detailed|in-depth)\b/.test(lower)
      ? "long"
      : defaults.length || "medium";
  const inferredMode = /\bedited\b/.test(lower) ? "edited" : defaults.mode || "raw";
  return {
    message: "I organized that into a draft request. Review the facts below before the voice model writes.",
    proposal: {
      model_id: selected.id,
      model_name: selected.name,
      operation: defaults.operation || "write",
      mode: inferredMode,
      length: inferredLength,
      notes,
      ...(defaults.preceding_text ? { preceding_text: defaults.preceding_text } : {}),
      ...(defaults.text ? { text: defaults.text } : {}),
    },
  };
}

export async function runWritingAssistant(
  env: AppEnv,
  user: AssistantUser,
  body: Record<string, unknown>,
): Promise<AssistantReply> {
  const message = typeof body.message === "string" ? body.message.trim() : "";
  if (!message || message.length > MAX_MESSAGE_LENGTH) {
    throw new Error("Use a request between 1 and 4,000 characters.");
  }
  const defaults: Partial<DraftProposal> = {
    ...(typeof body.model_id === "string" ? { model_id: body.model_id } : {}),
    ...(body.operation === "continue" || body.operation === "rewrite" || body.operation === "write"
      ? { operation: body.operation }
      : {}),
    ...(body.mode === "edited" || body.mode === "raw" ? { mode: body.mode } : {}),
    ...(body.length === "short" || body.length === "medium" || body.length === "long"
      ? { length: body.length }
      : {}),
    ...(typeof body.preceding_text === "string" ? { preceding_text: body.preceding_text.slice(0, 30_000) } : {}),
    ...(typeof body.text === "string" ? { text: body.text.slice(0, 30_000) } : {}),
  };

  if (!env.AI_GATEWAY_API_KEY) {
    if (env.DEV_AUTH === "1") return deterministicReply(env, user, message, defaults);
    throw new Error("The guided assistant is not configured.");
  }

  const gateway = createGateway({ apiKey: env.AI_GATEWAY_API_KEY });
  const inspectWorkspace = tool({
    description: "List this writer's models and credit balance. Call this before proposing a draft.",
    inputSchema: z.object({}),
    execute: async () => workspace(env, user.id),
  });
  const prepareDraft = tool({
    description: "Prepare, but do not execute, a Voiceprint generation request after the facts are sufficient.",
    inputSchema: z.object({
      model_id: z.string().min(1),
      operation: z.enum(["write", "continue", "rewrite"]),
      mode: z.enum(["raw", "edited"]),
      length: z.enum(["short", "medium", "long"]),
      notes: z.array(z.string().min(1).max(500)).min(1).max(12),
      preceding_text: z.string().max(30_000).optional(),
      text: z.string().max(30_000).optional(),
    }),
    execute: async (input): Promise<DraftProposal> => {
      const model = await env.DB.prepare(
        "SELECT id, name FROM models WHERE id = ? AND owner_id = ? AND status = 'ready'",
      ).bind(input.model_id, user.id).first<{ id: string; name: string }>();
      if (!model) throw new Error("That model is not ready or does not belong to this writer.");
      if (input.operation === "rewrite" && !input.text?.trim()) throw new Error("A rewrite needs the source text.");
      if (input.operation === "continue" && !input.preceding_text?.trim() && !input.notes.length) {
        throw new Error("A continuation needs preceding text or factual notes.");
      }
      return { ...input, model_name: model.name, notes: normalizeNotes(input.notes) };
    },
  });

  const agent = new ToolLoopAgent({
    model: gateway((env.ROUTER_MODEL || DEFAULT_ROUTER_MODEL) as Parameters<typeof gateway>[0]),
    instructions: `You are the request coordinator for Voiceprint.
You do not write or polish prose. The writer's custom adapter is the only component allowed to write the final draft.
First inspect the workspace. Extract only facts, audience, purpose, constraints, and explicit structure from the user's request.
Never invent facts. If a required fact is missing, ask one concise question and do not call prepareDraft.
When sufficient, call prepareDraft exactly once. Prefer raw mode unless the user explicitly asks for edited mode.
Edited means factual and mechanical correction only; warn that it may change AI-detector results.
Keep your response concise. Never claim the prepared request has already generated prose.`,
    tools: { inspectWorkspace, prepareDraft },
    stopWhen: stepCountIs(4),
    providerOptions: {
      gateway: {
        user: user.id,
        tags: ["feature:writing-assistant", "environment:beta"],
      },
    },
  });

  const result = await agent.generate({
    prompt: `Current defaults: ${JSON.stringify(defaults)}\n\nWriter request:\n${message}`,
  });
  const prepared = result.steps
    .flatMap((step) => step.toolResults)
    .find((item) => item.toolName === "prepareDraft");
  return {
    message: result.text || (prepared ? "Review this request before generating." : "Tell me what the piece must say."),
    proposal: prepared ? prepared.output as DraftProposal : null,
    usage: {
      input_tokens: result.totalUsage.inputTokens,
      output_tokens: result.totalUsage.outputTokens,
      total_tokens: result.totalUsage.totalTokens,
    },
  };
}

export async function applyLightEdit(
  env: AppEnv,
  user: AssistantUser,
  draft: string,
  corrections: string[],
): Promise<string> {
  if (!env.AI_GATEWAY_API_KEY) {
    if (env.DEV_AUTH !== "1") throw new Error("Edited mode is not configured.");
    const normalized = draft.replace(/[ \t]+/g, " ").replace(/\s+([,.;!?])/g, "$1").trim();
    return normalized ? normalized[0].toUpperCase() + normalized.slice(1) : normalized;
  }
  const gateway = createGateway({ apiKey: env.AI_GATEWAY_API_KEY });
  const result = await generateText({
    model: gateway((env.ROUTER_MODEL || DEFAULT_ROUTER_MODEL) as Parameters<typeof gateway>[0]),
    system: `You are a deliberately conservative copy editor.
Return only the edited text, with no preface.
Preserve the author's wording, sentence order, paragraph structure, rhythm, metaphors, transitions, and level of formality.
Only fix unambiguous spelling, punctuation, agreement, or grammar errors, and only replace facts explicitly listed in the correction notes.
Do not improve style. Do not smooth prose. Do not add facts. If a passage is merely awkward, leave it alone.`,
    prompt: `Correction notes:\n${corrections.length ? corrections.map((item) => `- ${item}`).join("\n") : "- No factual replacements supplied; mechanical corrections only."}\n\nText:\n${draft}`,
    maxOutputTokens: 2_400,
    providerOptions: {
      gateway: {
        user: user.id,
        tags: ["feature:light-edit", "environment:beta"],
        cacheControl: "max-age=0",
      },
    },
  });
  return result.text.trim() || draft;
}
