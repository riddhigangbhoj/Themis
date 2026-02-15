"use client";

import { useState, useRef, useEffect } from "react";
import { Scales, ArrowUp, Terminal } from "@phosphor-icons/react";
import ReactMarkdown from "react-markdown";

interface Message {
  role: "user" | "assistant" | "tool";
  content: string;
  toolInput?: string;
  toolOutput?: string;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);

    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const res = await fetch("http://localhost:8000/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: text }),
      });

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const event = JSON.parse(line.slice(6));

          if (event.type === "tool_start") {
            const cmdStr = event.input?.command || JSON.stringify(event.input);
            setMessages((prev) => [
              ...prev,
              { role: "tool", content: event.name, toolInput: cmdStr },
              { role: "assistant", content: "" },
            ]);
          } else if (event.type === "tool_end") {
            const outputStr = event.output?.output || event.output?.error || JSON.stringify(event.output);
            setMessages((prev) => {
              const updated = [...prev];
              // Find the last tool message to attach output
              for (let j = updated.length - 1; j >= 0; j--) {
                if (updated[j].role === "tool" && !updated[j].toolOutput) {
                  updated[j] = { ...updated[j], toolOutput: outputStr };
                  break;
                }
              }
              return updated;
            });
          } else if (event.type === "token") {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              updated[updated.length - 1] = { ...last, content: last.content + event.content };
              return updated;
            });
          }
        }
      }
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: "Error: could not reach backend." };
        return updated;
      });
    } finally {
      setLoading(false);
    }
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
          disabled={!input.trim() || loading}
          className="absolute right-2 top-1/2 -translate-y-1/2 flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-white transition-opacity disabled:opacity-0"
        >
          <ArrowUp size={16} weight="bold" />
        </button>
      </div>
    </form>
  );

  return (
    <div className="flex h-dvh flex-col bg-background">
      <header className="flex h-14 shrink-0 items-center border-b border-border-light px-6">
        <div className="flex items-center gap-2">
          <Scales size={20} weight="thin" className="text-primary" />
          <span className="font-serif text-lg text-heading tracking-tight">
            Themis
          </span>
        </div>
      </header>

      {messages.length === 0 ? (
        <main className="relative flex flex-1 flex-col items-center px-6">
          <div className="flex flex-col items-center mt-[25vh]">
            <Scales size={36} weight="thin" className="text-primary mb-5" />
            <p className="font-serif text-5xl text-heading tracking-tight">
              What can I help you research?
            </p>
            <p className="mt-3 text-base text-text-tertiary">
              Ask a legal question to get started.
            </p>
          </div>
          <div className="absolute top-1/2 left-1/2 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 px-6">
            {inputBar}
          </div>
        </main>
      ) : (
        <>
          <main ref={scrollRef} className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-2xl px-6 py-8">
              <div className="space-y-6">
                {messages.map((msg, i) => (
                  <div key={i} className={msg.role === "user" ? "flex justify-end" : ""}>
                    {msg.role === "tool" ? (
                      <ToolBlock name={msg.content} input={msg.toolInput} output={msg.toolOutput} />
                    ) : msg.role === "user" ? (
                      <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-3 text-base text-white">
                        {msg.content}
                      </div>
                    ) : (
                      <div className="prose-themis max-w-[80%] text-base leading-relaxed text-foreground">
                        {msg.content ? (
                          <ReactMarkdown>{msg.content}</ReactMarkdown>
                        ) : (
                          loading && i === messages.length - 1 ? "Thinking..." : ""
                        )}
                      </div>
                    )}
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

function ToolBlock({ name, input, output }: { name: string; input?: string; output?: string }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="w-full rounded-lg border border-border-light bg-surface overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-text-secondary hover:bg-black/[0.02]"
      >
        <Terminal size={14} weight="bold" className="shrink-0 text-primary" />
        <span className="font-mono">{name}</span>
        <span className="ml-auto text-text-tertiary">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="border-t border-border-light">
          {input && (
            <div className="px-3 py-2">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">Input</div>
              <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded bg-black/[0.03] px-2 py-1.5 font-mono text-xs text-foreground">
                {input}
              </pre>
            </div>
          )}
          {output && (
            <div className="border-t border-border-light px-3 py-2">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">Output</div>
              <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-all rounded bg-black/[0.03] px-2 py-1.5 font-mono text-xs text-foreground">
                {output}
              </pre>
            </div>
          )}
          {!output && (
            <div className="px-3 py-2 text-xs italic text-text-tertiary">Running...</div>
          )}
        </div>
      )}
    </div>
  );
}
