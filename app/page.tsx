"use client";

import { useState } from "react";
import { Scales, ArrowUp } from "@phosphor-icons/react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");

    // Placeholder assistant response
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "This is a placeholder response. The backend is not connected yet." },
      ]);
    }, 500);
  }

  const inputBar = (
    <form
      onSubmit={handleSubmit}
      className="flex w-full max-w-2xl items-end gap-2"
    >
      <div className="relative flex-1">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a legal question..."
          className="w-full rounded-xl border border-border-light bg-white py-3 pl-4 pr-12 text-base text-foreground outline-none placeholder:text-text-tertiary focus:border-primary/40"
        />
        <button
          type="submit"
          disabled={!input.trim()}
          className="absolute right-2 top-1/2 -translate-y-1/2 flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-white transition-opacity disabled:opacity-0"
        >
          <ArrowUp size={16} weight="bold" />
        </button>
      </div>
    </form>
  );

  return (
    <div className="flex h-dvh flex-col bg-background">
      {/* Header */}
      <header className="flex h-14 shrink-0 items-center border-b border-border-light px-6">
        <div className="flex items-center gap-2">
          <Scales size={20} weight="thin" className="text-primary" />
          <span className="font-serif text-lg text-heading tracking-tight">
            Themis
          </span>
        </div>
      </header>

      {messages.length === 0 ? (
        /* Empty state — input centered */
        <main className="relative flex flex-1 flex-col items-center px-6">
          {/* Text above center */}
          <div className="flex flex-col items-center mt-[25vh]">
            <Scales size={36} weight="thin" className="text-primary mb-5" />
            <p className="font-serif text-5xl text-heading tracking-tight">
              What can I help you research?
            </p>
            <p className="mt-3 text-base text-text-tertiary">
              Ask a legal question to get started.
            </p>
          </div>
          {/* Input at vertical center */}
          <div className="absolute top-1/2 left-1/2 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 px-6">
            {inputBar}
          </div>
        </main>
      ) : (
        /* Conversation — input at bottom */
        <>
          <main className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-2xl px-6 py-8">
              <div className="space-y-6">
                {messages.map((msg, i) => (
                  <div key={i} className={msg.role === "user" ? "flex justify-end" : ""}>
                    <div
                      className={
                        msg.role === "user"
                          ? "max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-3 text-base text-white"
                          : "max-w-[80%] text-base leading-relaxed text-foreground"
                      }
                    >
                      {msg.content}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </main>
          <div className="shrink-0 border-t border-border-light px-6 py-4">
            <div className="mx-auto max-w-2xl">
              {inputBar}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
