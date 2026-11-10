"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { Icon } from "@/components/icons";
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
 * AI tab. The conversation lives in this browser tab only (sessionStorage): it is sent
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
        title="Ask Sukat AI"
        action={
          messages.length > 0 && (
            <button type="button" onClick={newChat} aria-label="New chat" className={headerIconClass}>
              <Icon name="plus" size={24} />
            </button>
          )
        }
      />

      {empty ? (
        <div className="pt-10 text-center">
          <div className="mx-auto mb-[22px] grid h-[52px] w-[52px] place-items-center text-text">
            <Icon name="spark" size={27} />
          </div>
          <h2 className="text-xl font-bold text-text">What do you want to know?</h2>
          <p className="mx-auto mt-2 mb-6 max-w-xs text-sm text-muted">
            Ask about sales, products, or stock. I’ll use your store records.
          </p>
          <div className="flex flex-col gap-3 text-left" role="group" aria-label="Suggested questions">
            {SUGGESTIONS.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => ask(q)}
                className="flex min-h-[60px] items-center justify-between rounded-card border border-border bg-background px-4 text-base font-semibold text-text hover:bg-surface"
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
            <AnswerCard>
              <p className="flex items-center gap-1.5 text-muted" role="status">
                Thinking
                <span className="flex gap-1" aria-hidden>
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="h-1.5 w-1.5 animate-pulse rounded-full bg-subtle"
                      style={{ animationDelay: `${i * 200}ms` }}
                    />
                  ))}
                </span>
              </p>
            </AnswerCard>
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
        className="fixed inset-x-0 bottom-[var(--nav-h,0px)] z-10 border-t border-border bg-background"
      >
        <div className="mx-auto flex h-[66px] max-w-lg gap-2 px-4 py-2">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={MAX_CHARS}
            placeholder="Ask about your store…"
            aria-label="Your question"
            enterKeyHint="send"
            className="min-w-0 flex-1 rounded-button border border-line bg-background px-3 text-sm text-text outline-none placeholder:text-subtle focus:border-text focus:ring-1 focus:ring-text"
          />
          <button
            type="submit"
            aria-label="Send"
            disabled={!text.trim() || status.name === "loading"}
            className="grid w-12 shrink-0 place-items-center rounded-button bg-text text-inverse disabled:opacity-35"
          >
            <Icon name="send" size={20} />
          </button>
        </div>
      </form>
    </>
  );
}

function AnswerCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-border bg-background p-4 text-sm">
      <p className="mb-2 flex items-center gap-1.5 text-text">
        <Icon name="spark" size={17} />
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
