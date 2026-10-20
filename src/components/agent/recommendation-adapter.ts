import type { ChatModelAdapter, ThreadMessage } from "@assistant-ui/react";
import { readApiJson } from "../../lib/api";
import { effectivePlannerContext } from "../../lib/planner-context";
import type { Language, Recommendation } from "../../types";

export interface RecommendationSnapshot {
  language: Language;
  context: Record<string, unknown>;
  onResult: (result: Recommendation, requestContext?: Record<string, unknown>) => void;
  onQuery?: (text: string) => void;
}

export type RetrievalStage = "retrieve" | "rank" | "validate" | "compose";
const stages: readonly string[] = ["retrieve", "rank", "validate", "compose"];
const unavailable = {
  en: "The city guide is unavailable. Please try again.",
  ru: "Городской гид недоступен. Попробуйте ещё раз.",
  kk: "Қалалық гид қолжетімсіз. Қайта көріңіз.",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function checkedResult(value: unknown, language: Language): Recommendation {
  if (!isRecord(value) || typeof value.message !== "string" ||
      !Array.isArray(value.recommendations) || !isRecord(value.route) ||
      !Number.isFinite(value.route.total_minutes) || !isRecord(value.context)) {
    throw new Error(unavailable[language]);
  }
  return value as unknown as Recommendation;
}

/** Only structured state from a result on the current branch is sent back. */
export function branchConversation(messages: readonly ThreadMessage[], requestContext?: Record<string, unknown>): Record<string, unknown> | undefined {
  for (let index = messages.length - 1; index >= 0; index--) {
    const message = messages[index];
    if (message?.role !== "assistant") continue;
    for (const part of message.content) {
      if (part.type !== "tool-call" || part.toolName !== "recommend_city_places" || !isRecord(part.result)) continue;
      if (!isRecord(part.result.conversation)) return undefined;
      const conversation = { ...part.result.conversation };
      if (!requestContext) return conversation;
      let captured: unknown;
      try { captured = typeof part.args.requestContext === "string" ? JSON.parse(part.args.requestContext) : undefined; }
      catch { return undefined; }
      if (!isRecord(captured) || !samePlanningOrigin(captured, requestContext)) return undefined;
      // Preserve the conversation's interests/exclusions when the user adjusts a
      // planner control, while those explicit UI edits override prior constraints.
      for (const field of ["duration_minutes", "group_size", "indoor", "accessible", "airport_transfer_minutes"]) {
        if (JSON.stringify(captured[field]) !== JSON.stringify(requestContext[field])) conversation[field] = requestContext[field];
      }
      if (Array.isArray(requestContext.interests) && requestContext.interests.length &&
          JSON.stringify(captured.interests) !== JSON.stringify(requestContext.interests)) conversation.interests = requestContext.interests;
      return conversation;
    }
  }
  return undefined;
}

/** Explicit version navigation may change filters, never the planning origin. */
export function samePlanningOrigin(left: Record<string, unknown>, right: Record<string, unknown>): boolean {
  const identity = (context: Record<string, unknown>) => ({
    location: isRecord(context.location) ? { lat: context.location.lat, lon: context.location.lon } : context.location,
    language: context.language,
    starts_at: context.starts_at,
  });
  return JSON.stringify(identity(left)) === JSON.stringify(identity(right));
}

type ServerEvent = { event: string; data: unknown };

/** SSE records can span network chunks, CRLF lines, and multiple data lines. */
async function* serverEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ServerEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  try {
    while (true) {
      const chunk = await reader.read();
      pending += decoder.decode(chunk.value, { stream: !chunk.done });
      if (pending.length > 2_000_000) throw new Error("The city guide returned an invalid response.");
      let separator = /\r?\n\r?\n/.exec(pending);
      while (separator) {
        const record = pending.slice(0, separator.index);
        pending = pending.slice(separator.index + separator[0].length);
        let event = "message";
        const data: string[] = [];
        for (const line of record.split(/\r?\n/)) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
        }
        if (data.length) yield { event, data: JSON.parse(data.join("\n")) };
        separator = /\r?\n\r?\n/.exec(pending);
      }
      if (chunk.done) break;
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

function toolPart(id: string, message: string, requestContext: Record<string, unknown>, stage?: RetrievalStage, result?: Recommendation) {
  const args = { message, requestContext: JSON.stringify(requestContext), ...(stage ? { stage } : {}) };
  return {
    type: "tool-call" as const,
    toolCallId: id,
    toolName: "recommend_city_places",
    args,
    argsText: JSON.stringify(args),
    ...(result ? { result } : {}),
  };
}

/** Assistant UI owns editing, branches and cancellation; this adapter owns real HTTP/SSE. */
export function createRecommendationAdapter(getSnapshot: () => RecommendationSnapshot): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }) {
      const snapshot = getSnapshot();
      const userMessage = [...messages].reverse().find((message) => message.role === "user");
      const text = userMessage?.content.filter((part) => part.type === "text").map((part) => part.text).join("\n").trim();
      if (!text) throw new Error(unavailable[snapshot.language]);
      snapshot.onQuery?.(text);
      const id = `city-plan-${userMessage?.id ?? crypto.randomUUID()}`;
      const body = JSON.stringify({ ...snapshot.context, language: snapshot.language, message: text,
        conversation: branchConversation(messages, snapshot.context) });
      const options: RequestInit = { method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" }, body, signal: abortSignal };
      try {
        let response = await fetch("/api/chat/stream", options);
        // Older deployments retain the same result contract without streaming.
        if ([404, 405, 501].includes(response.status)) response = await fetch("/api/chat", options);
        if ([404, 405, 501].includes(response.status)) response = await fetch("/api/recommend", options);
        let result: Recommendation | undefined;
        if (response.ok && response.headers.get("content-type")?.includes("text/event-stream") && response.body) {
          for await (const event of serverEvents(response.body)) {
            abortSignal.throwIfAborted();
            if (event.event === "status" && isRecord(event.data) && typeof event.data.stage === "string" && stages.includes(event.data.stage)) {
              yield { content: [toolPart(id, text, snapshot.context, event.data.stage as RetrievalStage)] };
            } else if (event.event === "result") {
              result = checkedResult(event.data, snapshot.language);
              break;
            } else if (event.event === "error") {
              throw new Error(isRecord(event.data) && typeof event.data.message === "string" ? event.data.message : unavailable[snapshot.language]);
            }
          }
          if (!result) throw new Error(unavailable[snapshot.language]);
        } else {
          result = checkedResult(await readApiJson<unknown>(response, unavailable[snapshot.language]), snapshot.language);
        }
        // Cancelled or superseded requests must never replace the map's current plan.
        abortSignal.throwIfAborted();
        getSnapshot().onResult(result, snapshot.context);
        yield {
          status: { type: "complete", reason: "stop" },
          content: [{ type: "text", text: result.message }, toolPart(id, text, effectivePlannerContext(snapshot.context, result), undefined, result)],
        };
      } catch (error) {
        if (abortSignal.aborted) throw error;
        if (error instanceof TypeError || error instanceof SyntaxError) throw new Error(unavailable[snapshot.language]);
        throw error;
      }
    },
  };
}
