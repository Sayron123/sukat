"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { Icon } from "@/components/icons";
import { Mascot } from "@/components/mascot";
import { PageHeader, headerIconClass } from "@/components/page-header";
import { GhostButton, Loading } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { ChatData, ChatOut, ChatRole } from "@/lib/types";

import { ChatDataView, basisLine } from "./chat-data";

const SUGGESTIONS = [
  "Top product this week",
  "Best seller this month",
  "What’s low on stock?",
  "Sales today vs yesterday",
];
const STORAGE_KEY = "sukat-chat";
const HISTORY = 10; // the server only reads the last 10 messages anyway
const MAX_CHARS = 2000;

type Message = { id: string; role: ChatRole; content: string; data?: ChatData | null };
type Status = { name: "idle" } | { name: "loading" } | { name: "error"; message: string };

const noopSubscribe = () => () => {};

/**
 * Ask Sukat tab. The conversation lives in this browser tab only (sessionStorage): it is sent
 * with each question and never saved on the server.
 */
export function ChatScreen() {
  // Render the chat only in the browser, so the saved conversation can be read on the
  // first render without a server/client mismatch.
  const ready = useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
  return ready ? <Chat /> : <Loading />;
}

function loadSaved(): Message[] {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]") as unknown;
    return Array.isArray(saved) ? (saved as Message[]) : [];
  } catch {
    return [];
  }
}

function Chat() {
  const [messages, setMessages] = useState<Message[]>(loadSaved);
  const [status, setStatus] = useState<Status>({ name: "idle" });
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-30)));
    } catch {
      // storage full or blocked: the chat still works for this visit
    }
  }, [messages]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, status]);

  /** Send the conversation (ending with the user's question) and add the answer. */
  async function request(conversation: Message[]) {
    setStatus({ name: "loading" });
    try {
      const out = await api<ChatOut>("insights/chat", {
        method: "POST",
        body: JSON.stringify({
          messages: conversation.slice(-HISTORY).map(({ role, content }) => ({ role, content })),
        }),
      });
      setMessages([
        ...conversation,
        { id: crypto.randomUUID(), role: "assistant", content: out.answer, data: out.data },
      ]);
      setStatus({ name: "idle" });
    } catch (e) {
      setStatus({
        name: "error",
        message: e instanceof ApiError ? e.message : "Couldn’t reach the assistant. Check your connection.",
      });
    }
  }

  function ask(question: string) {
    const q = question.trim().slice(0, MAX_CHARS);
    if (!q || status.name === "loading") return;
    const conversation: Message[] = [...messages, { id: crypto.randomUUID(), role: "user", content: q }];
    setMessages(conversation);
    setText("");
    void request(conversation);
  }

  function newChat() {
    setMessages([]);
    setStatus({ name: "idle" });
  }

  const empty = messages.length === 0 && status.name === "idle";

  return (
    <>
      <PageHeader
        eyebrow="Your store assistant"
        title="Ask Sukat"
        action={
          messages.length > 0 && (
            <button type="button" onClick={newChat} aria-label="New chat" className={headerIconClass}>
              <Icon name="plus" size={24} />
            </button>
          )
        }
      />

      {empty ? (
        <div className="pt-2 pb-4 text-center">
          <Mascot emote="normal" size={150} glow className="mx-auto mb-5" />
          <h2 className="text-[22px] leading-tight font-extrabold text-text">What do you want to know?</h2>
          <p className="mx-auto mt-2 mb-6 max-w-72 text-[15px] leading-snug text-muted">
            Ask about sales, products, or stock. I answer from your store records.
          </p>
          <div className="flex flex-col gap-2.5 text-left" role="group" aria-label="Suggested questions">
            {SUGGESTIONS.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => ask(q)}
                className="flex min-h-13 items-center justify-between rounded-card border border-border bg-surface px-4 text-[15px] font-bold text-text hover:bg-border/40"
              >
                {q}
                <Icon name="chevron" size={18} />
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3.5" aria-live="polite">
          {messages.map((m) =>
            m.role === "user" ? (
              <p
                key={m.id}
                className="max-w-[80%] self-end rounded-[16px_16px_4px_16px] bg-text px-3.5 py-3 text-sm whitespace-pre-wrap text-inverse"
              >
                {m.content}
              </p>
            ) : (
              <Answer key={m.id} message={m} />
            ),
          )}
          {status.name === "loading" && (
            <div role="status" className="flex items-center gap-2 self-start motion-safe:animate-pop-in">
              <Mascot emote="thinking" size={72} alt="" />
              <span className="rounded-[16px_16px_16px_4px] bg-surface px-3.5 py-2.5 text-sm text-muted">
                Sukat is thinking…
              </span>
            </div>
          )}
          {status.name === "error" && (
            <AnswerCard>
              <p role="alert" className="text-red">
                {status.message}
              </p>
              <GhostButton type="button" className="mt-3 w-full" onClick={() => void request(messages)}>
                Retry
              </GhostButton>
            </AnswerCard>
          )}
          {/* Scrolled into view on each message; the margin keeps it above the input bar. */}
          <div ref={end} style={{ scrollMarginBottom: "calc(var(--nav-h, 0px) + 82px)" }} />
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(text);
        }}
        className="fixed inset-x-0 bottom-[var(--nav-h,0px)] z-10 bg-background"
      >
        <div className="mx-auto flex h-[68px] max-w-lg gap-2.5 px-4 py-2">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={MAX_CHARS}
            placeholder="Type your question…"
            aria-label="Your question"
            enterKeyHint="send"
            className="min-w-0 flex-1 rounded-card border border-line bg-surface px-4 text-[15px] text-text outline-none placeholder:text-subtle focus:border-text focus:ring-1 focus:ring-text"
          />
          <button
            type="submit"
            aria-label="Send"
            disabled={!text.trim() || status.name === "loading"}
            className="grid w-[52px] shrink-0 place-items-center rounded-card bg-accent text-white hover:bg-accent-pressed disabled:opacity-45"
          >
            <Icon name="forward" size={22} />
          </button>
        </div>
      </form>
    </>
  );
}

function AnswerCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-border bg-surface p-4 text-sm">
      <p className="mb-2 flex items-center gap-1.5 text-text">
        <Icon name="sukat" size={18} />
        <b>Sukat AI</b>
      </p>
      {children}
    </div>
  );
}

function Answer({ message }: { message: Message }) {
  const basis = message.data ? basisLine(message.data) : null;
  return (
    <AnswerCard>
      <p className="leading-[1.55] whitespace-pre-wrap text-text">{message.content}</p>
      {message.data && <ChatDataView data={message.data} />}
      {basis && <small className="mt-3 block text-[13px] text-subtle">{basis}</small>}
    </AnswerCard>
  );
}
