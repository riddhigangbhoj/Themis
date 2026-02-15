"use client";

import { useState, useRef, useEffect } from "react";
import { Scales, ArrowUp, Terminal, Robot, GearSix, Check } from "@phosphor-icons/react";
import ReactMarkdown from "react-markdown";
import { useBackendUrl } from "./use-backend-url";

interface ToolEvent {
  name: string;
  input?: string;
  output?: string;
  startedAt?: number;
  timedOut?: boolean;
}

interface Message {
  role: "user" | "assistant" | "subagent";
  content: string;
  // sub-agent fields
  agentId?: string;
  instructions?: string;
  toolEvents?: ToolEvent[];
  subagentResult?: string;
  done?: boolean;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const { backendUrl, updateUrl } = useBackendUrl();
  const [showSettings, setShowSettings] = useState(false);
  const [urlDraft, setUrlDraft] = useState(backendUrl);

  useEffect(() => {
    setUrlDraft(backendUrl);
  }, [backendUrl]);

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
      const res = await fetch(`${backendUrl}/query`, {
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

          if (event.type === "token") {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = { ...last, content: last.content + event.content };
              }
              return updated;
            });
          } else if (event.type === "subagent_start") {
            setMessages((prev) => [
              ...prev,
              { role: "subagent", content: "", agentId: event.agent_id, instructions: event.instructions, toolEvents: [], done: false },
            ]);
          } else if (event.type === "subagent_event") {
            const inner = event.event;
            setMessages((prev) => {
              const updated = [...prev];
              // Find subagent message by agent_id
              for (let j = updated.length - 1; j >= 0; j--) {
                if (updated[j].role === "subagent" && updated[j].agentId === event.agent_id) {
                  const sa = { ...updated[j], toolEvents: [...(updated[j].toolEvents || [])] };
                  if (inner.type === "tool_start") {
                    const cmdStr = inner.input?.command || JSON.stringify(inner.input);
                    sa.toolEvents.push({ name: inner.name, input: cmdStr, startedAt: Date.now() });
                  } else if (inner.type === "tool_end") {
                    const outputStr = inner.output?.output || inner.output?.error || JSON.stringify(inner.output);
                    for (let k = sa.toolEvents.length - 1; k >= 0; k--) {
                      if (!sa.toolEvents[k].output) {
                        const elapsed = sa.toolEvents[k].startedAt ? Date.now() - sa.toolEvents[k].startedAt! : 0;
                        const timedOut = elapsed > 20000;
                        sa.toolEvents[k] = { ...sa.toolEvents[k], output: outputStr, timedOut };
                        break;
                      }
                    }
                  } else if (inner.type === "token") {
                    sa.content = (sa.content || "") + inner.content;
                  }
                  updated[j] = sa;
                  break;
                }
              }
              return updated;
            });
          } else if (event.type === "subagent_end") {
            setMessages((prev) => {
              const updated = [...prev];
              for (let j = updated.length - 1; j >= 0; j--) {
                if (updated[j].role === "subagent" && updated[j].agentId === event.agent_id) {
                  updated[j] = { ...updated[j], done: true, subagentResult: event.result };
                  break;
                }
              }
              // If all subagents are done, add an assistant message for the next planner response
              const allDone = updated.filter(m => m.role === "subagent" && !m.done).length === 0;
              if (allDone && updated[updated.length - 1].role !== "assistant") {
                updated.push({ role: "assistant", content: "" });
              }
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
      <textarea
        value={input}
        onChange={(e) => {
          setInput(e.target.value);
          e.target.style.height = "auto";
          e.target.style.height = e.target.scrollHeight + "px";
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
          }
        }}
        placeholder="Ask a legal question..."
        rows={1}
        className="flex-1 resize-none rounded-xl border border-border-light bg-white py-3 pl-4 pr-4 text-base text-foreground outline-none placeholder:text-text-tertiary focus:border-primary/40"
        style={{ maxHeight: "200px", overflowY: "auto" }}
      />
      <button
        type="submit"
        disabled={!input.trim() || loading}
        className="flex h-8 w-8 shrink-0 items-center justify-center self-center rounded-lg bg-primary text-white transition-opacity disabled:opacity-0"
      >
        <ArrowUp size={16} weight="bold" />
      </button>
    </form>
  );

  return (
    <div className="flex h-dvh flex-col bg-background">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border-light px-6">
        <div className="flex items-center gap-2">
          <Scales size={20} weight="thin" className="text-primary" />
          <span className="font-serif text-lg text-heading tracking-tight">
            Themis
          </span>
        </div>
        <div className="relative">
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary hover:bg-black/[0.04] hover:text-foreground transition-colors"
            title="Backend settings"
          >
            <GearSix size={18} weight="regular" />
          </button>
          {showSettings && (
            <div className="absolute right-0 top-10 z-50 w-80 rounded-lg border border-border-light bg-white p-4 shadow-lg">
              <label className="mb-1.5 block text-xs font-medium text-text-secondary">
                Backend URL
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={urlDraft}
                  onChange={(e) => setUrlDraft(e.target.value)}
                  placeholder="http://localhost:8000"
                  className="flex-1 rounded-md border border-border-light bg-background px-2.5 py-1.5 font-mono text-xs text-foreground outline-none focus:border-primary/40"
                />
                <button
                  onClick={() => {
                    updateUrl(urlDraft);
                    setShowSettings(false);
                  }}
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary text-white hover:bg-primary-dark transition-colors"
                >
                  <Check size={14} weight="bold" />
                </button>
              </div>
              <p className="mt-2 text-[11px] text-text-tertiary">
                Paste your ngrok or remote backend URL here.
              </p>
            </div>
          )}
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
            <div className="mx-auto max-w-5xl px-6 py-8">
              <div className="grid grid-cols-2 gap-3">
                {messages.map((msg, i) => (
                  <div
                    key={i}
                    className={msg.role === "subagent" ? "" : "col-span-2" + (msg.role === "user" ? " flex justify-end" : "")}
                  >
                    {msg.role === "subagent" ? (
                      <SubAgentBlock
                        instructions={msg.instructions}
                        toolEvents={msg.toolEvents || []}
                        result={msg.content}
                        done={msg.done}
                      />
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

function SubAgentBlock({
  instructions,
  toolEvents,
  result,
  done,
}: {
  instructions?: string;
  toolEvents: ToolEvent[];
  result?: string;
  done?: boolean;
}) {
  const [open, setOpen] = useState(true);

  return (
    <div className="w-full rounded-lg border border-primary/20 bg-primary/[0.03] overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-primary hover:bg-primary/[0.05]"
      >
        <Robot size={14} weight="bold" className="shrink-0" />
        <span className="font-mono">research_agent</span>
        {!done && <span className="ml-1 text-text-tertiary italic">running...</span>}
        <span className="ml-auto text-text-tertiary">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="border-t border-primary/10">
          {instructions && (
            <div className="px-3 py-2 border-b border-primary/10">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">Instructions</div>
              <p className="text-xs text-foreground">{instructions}</p>
            </div>
          )}

          {toolEvents.length > 0 && (
            <div className="px-3 py-2 space-y-2">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">Tool Calls</div>
              {toolEvents.map((te, i) => (
                <ToolBlock key={i} name={te.name} input={te.input} output={te.output} timedOut={te.timedOut} />
              ))}
            </div>
          )}

          {result && (
            <div className="border-t border-primary/10 px-3 py-2">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">Agent Response</div>
              <div className="prose-themis text-xs text-foreground">
                <ReactMarkdown>{result}</ReactMarkdown>
              </div>
            </div>
          )}

          {!done && toolEvents.length === 0 && (
            <div className="px-3 py-2 text-xs italic text-text-tertiary">Starting...</div>
          )}
        </div>
      )}
    </div>
  );
}

function ToolBlock({ name, input, output, timedOut }: { name: string; input?: string; output?: string; timedOut?: boolean }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="w-full rounded border border-border-light bg-surface overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs font-medium text-text-secondary hover:bg-black/[0.02]"
      >
        <Terminal size={12} weight="bold" className="shrink-0 text-primary" />
        <span className="font-mono text-[11px]">{name}</span>
        <span className="ml-auto text-text-tertiary text-[10px]">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="border-t border-border-light">
          {input && (
            <div className="px-2 py-1.5">
              <div className="mb-0.5 text-[9px] font-semibold uppercase tracking-wider text-text-tertiary">Input</div>
              <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded bg-black/[0.03] px-1.5 py-1 font-mono text-[11px] text-foreground">
                {input}
              </pre>
            </div>
          )}
          {output && (
            <div className="border-t border-border-light px-2 py-1.5">
              <div className="mb-0.5 text-[9px] font-semibold uppercase tracking-wider text-text-tertiary">Output</div>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all rounded bg-black/[0.03] px-1.5 py-1 font-mono text-[11px] text-foreground">
                {output}
              </pre>
            </div>
          )}
          {timedOut && (
            <div className="border-t border-border-light px-2 py-1.5 text-[11px] font-medium text-amber-600">
              Tool took more than 20 seconds, please use a lighter query.
            </div>
          )}
          {!output && (
            <div className="px-2 py-1.5 text-[11px] italic text-text-tertiary">Running...</div>
          )}
        </div>
      )}
    </div>
  );
}
