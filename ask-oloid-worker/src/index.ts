/* ==========================================================================
   Ask Oloid backend: Cloudflare Worker that answers questions from the docs
   --------------------------------------------------------------------------
   The Claude API key exists ONLY here, as the Worker secret ANTHROPIC_API_KEY
   (`npx wrangler secret put ANTHROPIC_API_KEY`). It is never sent to the
   browser, never logged and never returned in an error.

   Flow: POST { messages, page } from ask-oloid.js
         -> origin check, per-IP rate limit, input validation
         -> BM25 search over docs-index.json (built by build_index.py)
         -> Claude call with the top sections as the primary source; it may
            use web search / fetch when the docs don't cover an Oloid question
         -> { reply } or { error }

   The assistant's instructions (scope, off-topic replies, related articles)
   live in system-prompt.txt - edit that file, then `npx wrangler deploy`.
   ========================================================================== */
import Anthropic from "@anthropic-ai/sdk";
import index from "./docs-index.json";
import SYSTEM_PROMPT from "./system-prompt.txt";

export interface Env {
  ANTHROPIC_API_KEY: string;
  ALLOWED_ORIGINS: string; // comma-separated, e.g. "https://docs.oloid.com,http://localhost:3000"
  MODEL?: string;
  RATE_LIMITER: RateLimit;
}

const DEFAULT_MODEL = "claude-opus-5-5";
const MAX_TURNS = 10;          // history sent to Claude
const MAX_CHARS = 2000;        // per message
const MAX_BODY_BYTES = 40_000;
const TOP_K = 8;               // doc sections per answer
const MAX_CONTINUATIONS = 3;   // pause_turn resumes during long web lookups

// Server-side tools: Anthropic runs them, the Worker only sets the caps.
// Used only when the docs don't cover an Oloid question (system-prompt.txt).
const WEB_TOOLS = [
  { type: "web_search_20260209", name: "web_search", max_uses: 3 },
  { type: "web_fetch_20260209", name: "web_fetch", max_uses: 3 },
];

/* ------------------------------------------------------------- search */
type Chunk = { t: string; h: string; u: string; x: string };
type DocsIndex = {
  stop: string[];
  avgdl: number;
  len: number[];
  post: Record<string, number[]>;
  chunks: Chunk[];
};
const IDX = index as unknown as DocsIndex;
const STOP = new Set(IDX.stop);
const N = IDX.chunks.length;
const PAGES = new Set(IDX.chunks.map((c) => c.u));

// Must match tokenize() in build_index.py.
function tokenize(text: string): string[] {
  const out: string[] = [];
  for (let w of text.toLowerCase().match(/[a-z0-9]+/g) ?? []) {
    if (w.length < 2 || STOP.has(w)) continue;
    if (w.length > 3 && w.endsWith("s") && !w.endsWith("ss")) w = w.slice(0, -1);
    out.push(w);
  }
  return out;
}

function search(query: string, k: number): Chunk[] {
  const k1 = 1.2, b = 0.75;
  const scores = new Map<number, number>();
  for (const term of new Set(tokenize(query))) {
    const post = IDX.post[term];
    if (!post) continue;
    const df = post.length / 2;
    const idf = Math.log(1 + (N - df + 0.5) / (df + 0.5));
    for (let i = 0; i < post.length; i += 2) {
      const id = post[i], tf = post[i + 1];
      const norm = tf + k1 * (1 - b + (b * IDX.len[id]) / IDX.avgdl);
      scores.set(id, (scores.get(id) ?? 0) + (idf * tf * (k1 + 1)) / norm);
    }
  }
  return [...scores.entries()]
    .sort((a, c) => c[1] - a[1])
    .slice(0, k)
    .map(([id]) => IDX.chunks[id]);
}

function formatDocs(chunks: Chunk[]): string {
  if (!chunks.length) return "<docs>\n(no matching documentation found)\n</docs>";
  const body = chunks
    .map((c) => {
      const title = c.h ? `${c.t} > ${c.h}` : c.t;
      return `<doc title="${title.replace(/"/g, "'")}" path="${c.u}">\n${c.x}\n</doc>`;
    })
    .join("\n");
  return `<docs>\n${body}\n</docs>`;
}

/* --------------------------------------------------------- validation */
type Turn = { role: "user" | "assistant"; content: string };

function parseBody(raw: unknown): { messages: Turn[]; page: string } | null {
  if (!raw || typeof raw !== "object") return null;
  const { messages, page } = raw as { messages?: unknown; page?: unknown };
  if (!Array.isArray(messages) || !messages.length) return null;

  const turns: Turn[] = [];
  for (const m of messages.slice(-MAX_TURNS)) {
    if (!m || typeof m !== "object") return null;
    const { role, content } = m as { role?: unknown; content?: unknown };
    if ((role !== "user" && role !== "assistant") || typeof content !== "string") return null;
    const text = content.trim().slice(0, MAX_CHARS);
    if (text) turns.push({ role, content: text });
  }
  // The API needs the conversation to start with a user turn and we answer
  // the last one, so trim to that shape.
  while (turns.length && turns[0].role !== "user") turns.shift();
  if (!turns.length || turns[turns.length - 1].role !== "user") return null;

  const safePage = typeof page === "string" && /^\/[\w\-/]{0,200}$/.test(page) ? page : "/";
  return { messages: turns, page: safePage };
}

/* ---------------------------------------------------------------- http */
function allowedOrigin(request: Request, env: Env): string | null {
  const origin = request.headers.get("Origin");
  if (!origin) return null;
  const list = env.ALLOWED_ORIGINS.split(",").map((s) => s.trim()).filter(Boolean);
  return list.includes(origin) ? origin : null;
}

function json(data: unknown, status: number, origin: string | null): Response {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    Vary: "Origin",
  };
  if (origin) headers["Access-Control-Allow-Origin"] = origin;
  return new Response(JSON.stringify(data), { status, headers });
}

async function answer(env: Env, messages: Turn[], page: string): Promise<string> {
  const users = messages.filter((m) => m.role === "user");
  // Include the previous question so follow-ups ("what about iOS?") still match.
  const query = users.slice(-2).map((m) => m.content).join(" ");
  const docs = formatDocs(search(query, TOP_K));

  const last = messages[messages.length - 1];
  const apiMessages: Anthropic.Beta.BetaMessageParam[] = [
    ...messages.slice(0, -1),
    {
      role: "user",
      content: `${docs}\n\nThe user is reading the page ${page}.\n\nQuestion: ${last.content}`,
    },
  ];

  const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 1, timeout: 120_000 });
  const params = {
    model: env.MODEL || DEFAULT_MODEL,
    max_tokens: 16000,
    system: SYSTEM_PROMPT,
    tools: WEB_TOOLS,
    // Adaptive thinking is always on for this model; "medium" lets it think
    // harder on troubleshooting and stay quick on simple lookups.
    output_config: { effort: "medium" },
    // On a safety-classifier decline, retry on Anthropic's recommended model.
    betas: ["server-side-fallback-2026-07-01"],
    fallbacks: "default",
  };

  let response = await client.beta.messages.create({
    ...params,
    messages: apiMessages,
  } as Anthropic.Beta.MessageCreateParamsNonStreaming);

  // A long web lookup can pause the server-side loop; resend to resume it.
  for (let i = 0; response.stop_reason === "pause_turn" && i < MAX_CONTINUATIONS; i++) {
    response = await client.beta.messages.create({
      ...params,
      messages: [...apiMessages, { role: "assistant", content: response.content }],
    } as Anthropic.Beta.MessageCreateParamsNonStreaming);
  }

  if (response.stop_reason === "refusal") {
    return "Sorry, I can't help with that request. Please contact Oloid support at support@oloid.help.";
  }
  return finalText(response.content) || "Sorry, I could not find an answer in the documentation.";
}

/* The answer is the text after the last search/fetch block; text before it is
   the model narrating its lookups ("Let me check..."). */
function finalText(content: Anthropic.Beta.BetaContentBlock[]): string {
  let start = 0;
  content.forEach((b, i) => {
    if (b.type !== "text" && b.type !== "thinking" && b.type !== "redacted_thinking") start = i + 1;
  });
  const text = content
    .slice(start)
    .filter((b): b is Anthropic.Beta.BetaTextBlock => b.type === "text")
    .map((b) => b.text)
    .join("")
    .trim();
  return unlinkUnknownPages(text);
}

/* A site-relative link that isn't a real docs page would 404: keep its text,
   drop the link, and drop list items that were nothing but such a link. */
function unlinkUnknownPages(text: string): string {
  return text
    .replace(/^\s*[-*]\s+\[[^\]]+\]\((\/[^)\s#]*)[^)]*\)\s*$/gm, (line, path) =>
      PAGES.has(path) ? line : "")
    .replace(/\[([^\]]+)\]\((\/[^)\s#]*)[^)]*\)/g, (link, label, path) =>
      PAGES.has(path) ? link : label)
    .replace(/\n{3,}/g, "\n\n");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = allowedOrigin(request, env);

    if (request.method === "OPTIONS") {
      if (!origin) return new Response(null, { status: 403 });
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": origin,
          "Access-Control-Allow-Methods": "POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
          "Access-Control-Max-Age": "86400",
          Vary: "Origin",
        },
      });
    }
    if (request.method !== "POST") return json({ error: "Method not allowed" }, 405, origin);
    if (!origin) return json({ error: "Forbidden" }, 403, null);

    const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
    const { success } = await env.RATE_LIMITER.limit({ key: ip });
    if (!success) {
      return json({ error: "Too many questions. Please wait a minute and try again." }, 429, origin);
    }

    const length = Number(request.headers.get("Content-Length") ?? 0);
    if (length > MAX_BODY_BYTES) return json({ error: "Message too long" }, 413, origin);

    let body: ReturnType<typeof parseBody>;
    try {
      const raw = await request.text();
      if (raw.length > MAX_BODY_BYTES) return json({ error: "Message too long" }, 413, origin);
      body = parseBody(JSON.parse(raw));
    } catch {
      body = null;
    }
    if (!body) return json({ error: "Invalid request" }, 400, origin);

    if (!env.ANTHROPIC_API_KEY) {
      console.error("ANTHROPIC_API_KEY secret is not set - run `npx wrangler secret put ANTHROPIC_API_KEY`");
      return json({ error: "The assistant is unavailable right now. Please try again." }, 502, origin);
    }

    try {
      const reply = await answer(env, body.messages, body.page);
      return json({ reply }, 200, origin);
    } catch (err) {
      // Log the API's status and error text only - never the request or its
      // headers, which carry the key. Visible with `npx wrangler tail`.
      if (err instanceof Anthropic.APIError) {
        console.error("Claude request failed:", err.status ?? "network", err.message);
      } else {
        console.error("Claude request failed:", err instanceof Error ? err.message : "unknown");
      }
      return json({ error: "The assistant is unavailable right now. Please try again." }, 502, origin);
    }
  },
} satisfies ExportedHandler<Env>;
