import { useEffect, useRef, useState, useCallback } from "react";
import GameWorld, { GameWorldHandle } from "./GameWorld";

interface ApiCall {
  timestamp: string;
  instructions: string;
  input: Array<Record<string, unknown>>;
  output: Array<Record<string, unknown>>;
  is_dream?: boolean;
  is_planning?: boolean;
}

interface CatInfo {
  id: string;
  name: string;
  pet_type: string;
  state: string;
  thought_count: number;
}

type Phase = "normal" | "dream" | "planning";
type Msg = { side: "left" | "right" | "system"; text: string; phase: Phase; image?: string; isRespond?: boolean };

/**
 * Render an INPUT item — we only care about:
 *  - user messages (nudges like "Continue." or "You're awake...")
 *  - function_call_output (tool results we sent back to the model)
 * Everything else in input is accumulated history (already rendered).
 */
function renderInputItem(item: Record<string, unknown>, phase: Phase): Msg | null {
  if (item.role === "user") {
    const content = item.content;
    // Content can be a string or an array (when it includes an image)
    if (Array.isArray(content)) {
      let text = "";
      let image: string | undefined;
      for (const part of content) {
        if (part.type === "input_text") text = part.text as string;
        if (part.type === "input_image") image = part.image_url as string;
      }
      return { side: "left", text: text || "[image]", phase, image };
    }
    return { side: "left", text: content as string, phase };
  }
  if (item.type === "function_call_output") {
    return { side: "left", text: item.output as string, phase };
  }
  return null;
}

/**
 * Render an OUTPUT item — everything the model returned:
 *  - message (thinking text)
 *  - function_call (tool invocation)
 *  - web_search_call
 */
function renderOutputItem(item: Record<string, unknown>, phase: Phase): Msg | null {
  if (item.type === "message") {
    const content = item.content as Array<Record<string, unknown>>;
    const text = content
      ?.map((c) => (c.text as string) || `[${c.type}]`)
      .join("\n");
    if (text) return { side: "right", text, phase };
    return null;
  }
  if (item.type === "function_call") {
    if (item.name === "respond") {
      try {
        const args = typeof item.arguments === "string"
          ? JSON.parse(item.arguments as string)
          : item.arguments;
        return { side: "right", text: (args as Record<string, string>).message, phase, isRespond: true };
      } catch {
        return { side: "right", text: String(item.arguments), phase, isRespond: true };
      }
    }
    let cmd: string;
    if (item.name === "shell") {
      try {
        const args = typeof item.arguments === "string"
          ? JSON.parse(item.arguments as string)
          : item.arguments;
        cmd = `$ ${(args as Record<string, string>).command}`;
      } catch {
        cmd = `$ ${item.arguments}`;
      }
    } else {
      const args = typeof item.arguments === "string"
        ? item.arguments
        : JSON.stringify(item.arguments, null, 2);
      cmd = `[${item.name}] ${args}`;
    }
    return { side: "right", text: cmd, phase };
  }
  if (item.type === "web_search_call") {
    return { side: "right", text: "[web search]", phase };
  }
  return null;
}

export default function App() {
  const [calls, setCalls] = useState<ApiCall[]>([]);
  const [position, setPosition] = useState({ x: 5, y: 5 });
  const [catState, setCatState] = useState("idle");
  const [alert, setAlert] = useState(false);
  const [activity, setActivity] = useState({ type: "idle", detail: "" });
  const [chatInput, setChatInput] = useState("");
  const [conversing, setConversing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const [countdown, setCountdown] = useState(0);
  const [hasNew, setHasNew] = useState(false);
  const [catName, setCatName] = useState("the cat");
  const [petType, setPetType] = useState("cat");
  const [focusMode, setFocusMode] = useState(false);
  const [focusTopic, setFocusTopic] = useState("");
  const [focusRemaining, setFocusRemaining] = useState(0);
  const [focusFormOpen, setFocusFormOpen] = useState(false);
  const [focusFormTopic, setFocusFormTopic] = useState("");
  const [focusFormDuration, setFocusFormDuration] = useState(30);
  const [paused, setPaused] = useState(false);
  const [pace, setPace] = useState(5);
  const [openLoops, setOpenLoops] = useState<Array<{ text: string; timestamp: string }>>([]);
  type FeedFilter = "all" | "important" | "thoughts";
  const [feedFilter, setFeedFilter] = useState<FeedFilter>("all");
  const [toolCollapsed, setToolCollapsed] = useState(true);
  const [memPanelOpen, setMemPanelOpen] = useState(false);
  const [memQuery, setMemQuery] = useState("");
  const [memKind, setMemKind] = useState("");
  const [memResults, setMemResults] = useState<Array<{
    id: string; timestamp: string; kind: string; content: string; importance: number;
    cluster: string; cluster_label: string;
  }>>([]);
  const [awaySummary, setAwaySummary] = useState("");
  const lastActiveRef = useRef<string>(new Date().toISOString());
  const [cats, setCats] = useState<CatInfo[]>([]);
  const [activeCat, setActiveCat] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const gameRef = useRef<GameWorldHandle>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const catParam = activeCat ? `?cat=${activeCat}` : "";

  const connectWs = useCallback((catId: string) => {
    // Close existing connection
    if (wsRef.current) {
      wsRef.current.onmessage = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${location.host}/ws/${catId}`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.event === "api_call") setCalls((prev) => [...prev, msg.data]);
      if (msg.event === "position") setPosition(msg.data);
      if (msg.event === "status") {
        setCatState(msg.data.state);
        if (msg.data.state === "thinking") setAlert(false);
      }
      if (msg.event === "alert") setAlert(true);
      if (msg.event === "activity") setActivity(msg.data);
      if (msg.event === "focus_mode") {
        setFocusMode(msg.data.enabled);
        if (msg.data.topic) setFocusTopic(msg.data.topic);
        if (!msg.data.enabled) { setFocusTopic(""); setFocusRemaining(0); }
      }
      if (msg.event === "paused") setPaused(msg.data.paused);
      if (msg.event === "conversation") {
        if (msg.data.state === "waiting") {
          setConversing(true);
          setCountdown(msg.data.timeout);
        } else if (msg.data.state === "ended") {
          setConversing(false);
          setCountdown(0);
        }
      }
    };

    ws.onerror = () => {
      console.warn(`WebSocket error for cat ${catId}`);
    };

    ws.onclose = () => {
      // Reconnect after a brief delay if this is still the active WS
      if (wsRef.current === ws) {
        setTimeout(() => {
          if (wsRef.current === ws) connectWs(catId);
        }, 3000);
      }
    };
  }, []);

  const loadCatState = useCallback(async (catId: string) => {
    const q = `?cat=${catId}`;
    // Fetch historical calls first (before WS connects) to avoid race
    try {
      const [rawRes, statusRes, idRes] = await Promise.all([
        fetch(`/api/raw${q}`),
        fetch(`/api/status${q}`),
        fetch(`/api/identity${q}`),
      ]);
      const rawData = await rawRes.json();
      const statusData = await statusRes.json();
      const idData = await idRes.json();
      setCalls(rawData);
      if (statusData.position) setPosition(statusData.position);
      if (statusData.focus_mode !== undefined) setFocusMode(statusData.focus_mode);
      if (statusData.focus_topic !== undefined) setFocusTopic(statusData.focus_topic);
      if (statusData.focus_remaining !== undefined) setFocusRemaining(Math.round(statusData.focus_remaining));
      if (statusData.paused !== undefined) setPaused(statusData.paused);
      if (statusData.pace !== undefined) setPace(statusData.pace);
      if (statusData.open_loops) setOpenLoops(statusData.open_loops);
      setCatState(statusData.state || "idle");
      if (idData.name) setCatName(idData.name);
      if (idData.pet_type) setPetType(idData.pet_type);
    } catch {
      // silently ignore fetch errors
    }
  }, []);

  // Initial mount: fetch cats list, load state, then connect WS
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/cats");
        const list: CatInfo[] = await res.json();
        if (cancelled) return;
        setCats(list);
        if (list.length > 0) {
          const first = list[0].id;
          setActiveCat(first);
          setCatName(list[0].name);
          setPetType(list[0].pet_type || "cat");
          // Load historical data first, then connect WS for live events
          await loadCatState(first);
          if (!cancelled) connectWs(first);
        }
      } catch { /* server not ready yet */ }
    })();

    return () => {
      cancelled = true;
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connectWs, loadCatState]);

  // Switch cat
  const switchCat = useCallback((catId: string) => {
    if (catId === activeCat) return;
    setActiveCat(catId);

    // Reset state
    setConversing(false);
    setCountdown(0);
    setAlert(false);
    setActivity({ type: "idle", detail: "" });
    setHasNew(false);

    // Update cat name and pet type immediately
    const cat = cats.find((c) => c.id === catId);
    if (cat) {
      setCatName(cat.name);
      setPetType(cat.pet_type || "cat");
    }

    // Load historical data first, then connect WS for live events
    loadCatState(catId).then(() => connectWs(catId));
  }, [activeCat, cats, loadCatState, connectWs]);

  // Poll cats list periodically to keep states fresh
  useEffect(() => {
    const interval = setInterval(() => {
      fetch("/api/cats")
        .then((r) => r.json())
        .then(setCats)
        .catch(() => {});
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  // Countdown timer for conversation window
  useEffect(() => {
    if (countdownRef.current) clearInterval(countdownRef.current);
    if (countdown > 0) {
      countdownRef.current = setInterval(() => {
        setCountdown((c) => {
          if (c <= 1) {
            clearInterval(countdownRef.current!);
            return 0;
          }
          return c - 1;
        });
      }, 1000);
    }
    return () => { if (countdownRef.current) clearInterval(countdownRef.current); };
  }, [conversing]);

  // Send canvas snapshot to backend when thinking starts
  useEffect(() => {
    if (catState === "thinking" && gameRef.current) {
      const dataUrl = gameRef.current.snapshot();
      if (dataUrl) {
        fetch(`/api/snapshot${catParam}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image: dataUrl }),
        }).catch(() => {});
      }
    }
  }, [catState, catParam]);

  // Only auto-scroll if user is already near the bottom; otherwise show indicator
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
    if (nearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    } else {
      setHasNew(true);
    }
  }, [calls.length]);

  // Clear "new messages" when user scrolls to bottom
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
      if (nearBottom) setHasNew(false);
    };
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // Detect "while you were away" — tab visibility changes
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        const lastActive = new Date(lastActiveRef.current);
        const now = new Date();
        const minutesAway = (now.getTime() - lastActive.getTime()) / 60000;
        if (minutesAway >= 5) {
          const params = new URLSearchParams({ since: lastActiveRef.current });
          if (activeCat) params.set("cat", activeCat);
          fetch(`/api/activity-since?${params}`)
            .then((r) => r.json())
            .then((data) => {
              if (data.summary) setAwaySummary(data.summary);
            })
            .catch(() => {});
        }
        lastActiveRef.current = now.toISOString();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [activeCat]);

  // Keyboard shortcut: "/" or Cmd+K to focus input
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === "/" || (e.metaKey && e.key === "k")) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, []);

  const quickActions = [
    { label: "Brain dump", prefix: "Brain dump: ", icon: "🧠" },
    { label: "I'm stuck", prefix: "I'm stuck on ", icon: "🪢" },
    { label: "Small win", prefix: "Small win: ", icon: "🎯" },
    { label: "Remember", prefix: "Remember: ", icon: "📌" },
    { label: "What's next", prefix: "What should I do next?", icon: "→" },
  ];

  const quickCapture = (prefix: string) => {
    setChatInput(prefix);
    inputRef.current?.focus();
  };

  const sendMessage = () => {
    const text = chatInput.trim();
    if (!text) return;
    // Optimistic echo — show user's message immediately
    setCalls((prev) => [...prev, {
      timestamp: new Date().toISOString(),
      instructions: "",
      input: [{ role: "user", content: text }],
      output: [],
    }]);
    fetch(`/api/message${catParam}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).catch(() => {});
    setChatInput("");
  };

  const searchMemories = () => {
    const params = new URLSearchParams();
    if (memQuery) params.set("query", memQuery);
    if (memKind) params.set("kind", memKind);
    params.set("limit", "15");
    fetch(`/api/memories${catParam ? `?cat=${activeCat}&` : "?"}${params}`)
      .then((r) => r.json())
      .then((data) => setMemResults(data.memories || []))
      .catch(() => {});
  };

  const memKindColor = (kind: string) => {
    if (kind === "reflection") return "#7c3aed";
    if (kind === "observation") return "#007aff";
    if (kind === "conversation") return "#10b981";
    return "#999";
  };

  const formatMemTime = (ts: string) => {
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch { return ""; }
  };

  const toggleFocusMode = () => {
    if (focusMode) {
      // Turn off
      setFocusMode(false);
      setFocusTopic("");
      setFocusRemaining(0);
      fetch(`/api/focus-mode${catParam}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: false }),
      }).catch(() => {});
    } else {
      // Show form
      setFocusFormOpen(true);
    }
  };

  const submitFocusForm = () => {
    setFocusFormOpen(false);
    setFocusMode(true);
    setFocusTopic(focusFormTopic);
    fetch(`/api/focus-mode${catParam}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: true,
        topic: focusFormTopic,
        duration_minutes: focusFormDuration,
      }),
    }).catch(() => {});
    setFocusFormTopic("");
  };

  const togglePause = () => {
    const next = !paused;
    setPaused(next);
    fetch(`/api/pause${catParam}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paused: next }),
    }).catch(() => {});
  };

  const setPaceValue = (val: number) => {
    setPace(val);
    fetch(`/api/pace${catParam}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pace: val }),
    }).catch(() => {});
  };

  // Build a deduplicated conversation stream.
  // Each API call's input contains the FULL accumulated history.
  // We only render NEW items in each call's input (items we haven't seen yet)
  // plus all output items (what the model returned).
  const messages: Msg[] = [];
  let seenInputItems = 0;

  calls.forEach((call, i) => {
    const isDream = call.is_dream ?? false;
    const isPlanning = call.is_planning ?? false;
    const phase: Phase = isDream ? "dream" : isPlanning ? "planning" : "normal";

    // System prompt (first call or when instructions meaningfully changed) — skip for dream/planning calls
    const strip = (s: string) => s.replace(/Right now it is .+\n/, "").replace(/## Current (mood|focus)\n[\s\S]*?(?=\n##)/, "");
    if (!isDream && !isPlanning && (i === 0 || strip(call.instructions) !== strip(calls[i - 1]?.instructions ?? ""))) {
      messages.push({ side: "system", text: call.instructions, phase: "normal" });
    }

    // Dream divider
    if (isDream && (i === 0 || !calls[i - 1]?.is_dream)) {
      messages.push({ side: "system", text: "Reflecting...", phase: "dream" });
    }

    // Planning divider
    if (isPlanning && (i === 0 || !calls[i - 1]?.is_planning)) {
      messages.push({ side: "system", text: "Planning...", phase: "planning" });
    }

    // If input didn't grow (rebuilt from scratch for a new think cycle), reset.
    // Accumulated tool-loop inputs always grow strictly (new function_call_outputs),
    // so equal-or-smaller means the input was rebuilt by _build_input().
    if (seenInputItems >= call.input.length) {
      seenInputItems = 0;
    }

    // Only render NEW input items (skip already-rendered history)
    const newInputs = call.input.slice(seenInputItems);
    for (const item of newInputs) {
      const msg = renderInputItem(item, phase);
      if (msg) messages.push(msg);
    }

    // Render all output items (what the model returned this call)
    for (const item of call.output) {
      const msg = renderOutputItem(item, phase);
      if (msg) messages.push(msg);
    }

    // Track how many items the next call's input will start with
    seenInputItems = call.input.length + call.output.length;
  });

  const stateLabel = (state: string) => {
    if (paused) return "paused";
    if (state === "thinking") return "thinking";
    if (state === "reflecting") return "reflecting";
    if (state === "planning") return "planning";
    return "idle";
  };

  const stateColor = (state: string) => {
    if (paused) return "#f59e0b";
    if (state === "thinking") return "#007aff";
    if (state === "reflecting") return "#7c3aed";
    if (state === "planning") return "#0d9488";
    return "#999";
  };

  return (
    <div style={page}>
      <div style={headerBar}>
        <img src="/icon.png" alt="Drift" style={headerIcon} />
        <span style={headerTitle}>Drift</span>
      </div>
      <div style={twoPane}>
        {/* Left pane — Game world */}
        <div style={gamePane}>
          <GameWorld ref={gameRef} position={position} state={catState} alert={alert} activity={activity} conversing={conversing} petType={petType} />
        </div>

        {/* Right pane — Chat feed */}
        <div style={chatPane}>
          {/* Cat switcher */}
          {cats.length > 1 && (
            <div style={switcherBar}>
              {cats.map((c) => {
                const isActive = c.id === activeCat;
                return (
                  <button
                    key={c.id}
                    style={isActive ? switcherBtnActive : switcherBtnInactive}
                    onClick={() => switchCat(c.id)}
                  >
                    <span>{c.name}</span>
                    <span style={{ ...switcherState, color: isActive ? "rgba(255,255,255,0.8)" : stateColor(c.state) }}>
                      {stateLabel(c.state)}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
          {awaySummary && (
            <div style={awayBanner}>
              <span>{awaySummary}</span>
              <button style={awayCloseBtn} onClick={() => setAwaySummary("")}>×</button>
            </div>
          )}
          {openLoops.length > 0 && (
            <div style={loopsBanner}>
              <span style={loopsIcon}>🔄</span>
              <div style={loopsList}>
                {openLoops.slice(-3).map((loop, i) => (
                  <span key={i} style={loopItem}>{loop.text}</span>
                ))}
              </div>
              <span style={loopsHint}>unfinished threads</span>
            </div>
          )}
          {memPanelOpen && (
            <div style={memPanel}>
              <div style={memPanelHeader}>
                <span style={{ fontWeight: 700, fontSize: 13 }}>Memory Search</span>
                <button style={memCloseBtn} onClick={() => setMemPanelOpen(false)}>×</button>
              </div>
              <div style={memSearchRow}>
                <input
                  style={memInput}
                  type="text"
                  placeholder="Search memories..."
                  value={memQuery}
                  onChange={(e) => setMemQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") searchMemories(); }}
                />
                <select
                  style={memKindSelect}
                  value={memKind}
                  onChange={(e) => setMemKind(e.target.value)}
                >
                  <option value="">All types</option>
                  <option value="observation">Observations</option>
                  <option value="conversation">Conversations</option>
                  <option value="reflection">Reflections</option>
                  <option value="system">System</option>
                </select>
                <button style={memSearchBtn} onClick={searchMemories}>Search</button>
              </div>
              <div style={memResultsList}>
                {memResults.length === 0 && (
                  <div style={{ color: "#999", fontSize: 12, padding: 8 }}>No memories found</div>
                )}
                {memResults.map((m) => (
                  <div key={m.id} style={memItem}>
                    <div style={memItemMeta}>
                      <span style={{ color: memKindColor(m.kind), fontWeight: 600 }}>{m.kind}</span>
                      {m.cluster_label && (
                        <span style={clusterTag} title={`Cluster: ${m.cluster_label}`}>{m.cluster_label}</span>
                      )}
                      <span style={{ color: "#999" }}> · imp:{m.importance}</span>
                      <span style={{ color: "#bbb", marginLeft: "auto" }}>{formatMemTime(m.timestamp)}</span>
                    </div>
                    <div style={memItemContent}>{m.content}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div style={filterBar}>
            {(["all", "important", "thoughts"] as FeedFilter[]).map((f) => (
              <button
                key={f}
                style={feedFilter === f ? filterBtnActive : filterBtnInactive}
                onClick={() => setFeedFilter(f)}
              >
                {f === "all" ? "All" : f === "important" ? "Important" : "Thoughts"}
              </button>
            ))}
          </div>
          <div ref={scrollRef} style={chatScroll}>
          <div style={container}>
            {messages.length === 0 && (
              <div style={emptyState}>
                <div style={emptyIcon}>~</div>
                <div style={emptyTitle}>Waiting for thoughts...</div>
                <div style={emptySubtitle}>{catName} is getting ready</div>
              </div>
            )}
            {messages.filter((msg) => {
              if (feedFilter === "all") return true;
              // "important" filter: hide tool calls/results, keep thoughts/reflections/planning/conversation
              if (msg.side === "system") return feedFilter === "important" ? msg.phase !== "normal" : false;
              if (msg.isRespond) return true; // always show conversation
              if (msg.side === "left") return true; // always show nudges/inputs
              // Right side: hide tool calls (start with "$ " or "[" and end with "]")
              const t = msg.text;
              const isTool = t.startsWith("$ ") || (t.startsWith("[") && !t.startsWith("[image]") && t.includes("]") && t.indexOf("]") < 40);
              if (feedFilter === "important") return !isTool;
              // "thoughts" filter: only show non-tool right-side messages
              return !isTool;
            }).map((msg, i) => {
              if (msg.side === "system") {
                const sBlock = msg.phase === "dream" ? dreamSystemBlock
                  : msg.phase === "planning" ? planSystemBlock : systemBlock;
                const sLabel = msg.phase === "dream" ? dreamSystemLabel
                  : msg.phase === "planning" ? planSystemLabel : systemLabel;
                const sText = msg.phase === "dream" ? dreamSystemText
                  : msg.phase === "planning" ? planSystemText : systemText;
                const label = msg.phase === "dream" ? "Reflection"
                  : msg.phase === "planning" ? "Planning" : "System Prompt";
                return (
                  <div key={i} style={sBlock}>
                    <div style={sLabel}>{label}</div>
                    <pre style={sText}>{msg.text}</pre>
                  </div>
                );
              }

              const isLeft = msg.side === "left";
              const p = msg.phase;

              const bubbleStyle = msg.isRespond
                ? respondBubble
                : p === "dream"
                ? isLeft ? dreamBubbleLeft : dreamBubbleRight
                : p === "planning"
                ? isLeft ? planBubbleLeft : planBubbleRight
                : isLeft ? bubbleLeft : bubbleRight;

              const textColor = isLeft && p === "normal" && !msg.isRespond ? "#111" : "#fff";

              return (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    justifyContent: isLeft ? "flex-start" : "flex-end",
                    marginBottom: 6,
                  }}
                >
                  <div style={bubbleStyle}>
                    {msg.image && (
                      <img
                        src={msg.image}
                        style={snapshotImg}
                        alt="Room snapshot"
                      />
                    )}
                    <pre style={{ ...bubbleText, color: textColor }}>
                      {msg.text}
                    </pre>
                  </div>
                </div>
              );
            })}
            <div ref={bottomRef} />
          </div>
          </div>
          {hasNew && (
            <div
              style={newMsgPill}
              onClick={() => {
                bottomRef.current?.scrollIntoView({ behavior: "smooth" });
                setHasNew(false);
              }}
            >
              New messages
            </div>
          )}
          <div style={quickCaptureBar}>
            {quickActions.map((a) => (
              <button
                key={a.label}
                style={quickChip}
                onClick={() => quickCapture(a.prefix)}
                title={`Pre-fill: "${a.prefix}"`}
              >
                <span style={quickChipIcon}>{a.icon}</span>
                <span>{a.label}</span>
              </button>
            ))}
          </div>
          <div style={inputBar}>
            {conversing && countdown > 0 && (
              <div style={countdownStyle}>{countdown}s</div>
            )}
            <button
              style={paused ? pauseBtnActive : pauseBtnInactive}
              onClick={togglePause}
              title={paused ? "Resume thinking" : "Pause thinking"}
            >
              {paused ? "▶" : "⏸"}
            </button>
            <button
              style={focusMode ? focusBtnActive : focusBtnInactive}
              onClick={toggleFocusMode}
              title={focusMode ? `Focused${focusTopic ? " on " + focusTopic : ""} — click to turn off` : "Click to focus"}
            >
              {focusMode ? (focusTopic ? `Focus: ${focusTopic.slice(0, 15)}` : "Focused") : "Focus"}
            </button>
            {focusFormOpen && (
              <div style={focusFormPopup}>
                <input
                  style={focusFormInput}
                  type="text"
                  placeholder="Topic (optional)"
                  value={focusFormTopic}
                  onChange={(e) => setFocusFormTopic(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") submitFocusForm(); }}
                  autoFocus
                />
                <select
                  style={focusFormSelect}
                  value={focusFormDuration}
                  onChange={(e) => setFocusFormDuration(Number(e.target.value))}
                >
                  <option value={15}>15 min</option>
                  <option value={30}>30 min</option>
                  <option value={60}>60 min</option>
                  <option value={0}>No limit</option>
                </select>
                <button style={focusFormGoBtn} onClick={submitFocusForm}>Go</button>
                <button style={focusFormCancelBtn} onClick={() => setFocusFormOpen(false)}>×</button>
              </div>
            )}
            <select
              style={paceSelect}
              value={pace}
              onChange={(e) => setPaceValue(Number(e.target.value))}
              title="Thinking pace"
            >
              <option value={3}>Fast (3s)</option>
              <option value={5}>Normal (5s)</option>
              <option value={15}>Slow (15s)</option>
              <option value={45}>Quiet (45s)</option>
            </select>
            <button
              style={memBtn}
              onClick={() => { setMemPanelOpen(!memPanelOpen); if (!memPanelOpen) searchMemories(); }}
              title="Search creature's memory"
            >
              Mem
            </button>
            <form
              style={inputForm}
              onSubmit={(e) => { e.preventDefault(); sendMessage(); }}
            >
              <input
                ref={inputRef}
                style={inputField}
                type="text"
                placeholder={conversing ? `Reply to ${catName}...` : `Say something to ${catName}...  (press / to focus)`}
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
              />
              <button style={sendBtn} type="submit">Send</button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Shared palette ──
const DARK = "#0f0f1a";
const DARK_MID = "#1a1a2e";
const DARK_BORDER = "#2a2a4a";
const SURFACE = "#f4f4f8";
const BORDER = "#e2e2ea";
const MONO = "'SF Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace";
const SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

const page: React.CSSProperties = {
  background: DARK,
  color: "#111",
  fontFamily: SANS,
  height: "100vh",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

// ── Header ──
const headerBar: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 16,
  padding: "10px 24px",
  background: DARK,
  borderBottom: `1px solid ${DARK_BORDER}`,
  flexShrink: 0,
};

const headerIcon: React.CSSProperties = {
  maxHeight: 48,
};

const headerTitle: React.CSSProperties = {
  fontSize: 24,
  fontWeight: 700,
  color: "#fff",
  whiteSpace: "nowrap",
  letterSpacing: "-0.3px",
};

// ── Layout ──
const twoPane: React.CSSProperties = {
  display: "flex",
  flex: 1,
  overflow: "hidden",
};

const gamePane: React.CSSProperties = {
  width: "45%",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: DARK_MID,
  padding: 20,
  flexShrink: 0,
};

const chatPane: React.CSSProperties = {
  width: "55%",
  height: "100%",
  display: "flex",
  flexDirection: "column",
  background: SURFACE,
  borderLeft: `1px solid ${BORDER}`,
  position: "relative",
};

const chatScroll: React.CSSProperties = {
  flex: 1,
  overflow: "auto",
};

const filterBar: React.CSSProperties = {
  display: "flex",
  gap: 4,
  padding: "6px 16px",
  borderBottom: `1px solid ${BORDER}`,
  background: "#fff",
  flexShrink: 0,
};

const filterBtnActive: React.CSSProperties = {
  padding: "4px 12px",
  borderRadius: 6,
  border: `1px solid ${DARK_MID}`,
  background: DARK_MID,
  color: "#fff",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
};

const filterBtnInactive: React.CSSProperties = {
  padding: "4px 12px",
  borderRadius: 6,
  border: `1px solid ${BORDER}`,
  background: "transparent",
  color: "#888",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
};

const container: React.CSSProperties = {
  maxWidth: 720,
  margin: "0 auto",
  padding: "24px 20px",
};

// ── Empty state ──
const emptyState: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  padding: "80px 20px",
  gap: 8,
};

const emptyIcon: React.CSSProperties = {
  fontSize: 32,
  color: "#c4c4d0",
  fontFamily: MONO,
};

const emptyTitle: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 600,
  color: "#8888a0",
  letterSpacing: "-0.2px",
};

const emptySubtitle: React.CSSProperties = {
  fontSize: 13,
  color: "#aaa",
};

// ── Cat switcher ──
const switcherBar: React.CSSProperties = {
  display: "flex",
  gap: 6,
  padding: "8px 16px",
  borderBottom: `1px solid ${BORDER}`,
  background: "#fff",
  overflowX: "auto",
  flexShrink: 0,
};

const switcherBtnBase: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: 2,
  padding: "6px 16px",
  borderRadius: 8,
  border: `1px solid ${BORDER}`,
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
  transition: "all 0.15s",
  background: "transparent",
};

const switcherBtnActive: React.CSSProperties = {
  ...switcherBtnBase,
  background: DARK_MID,
  color: "#fff",
  borderColor: DARK_MID,
};

const switcherBtnInactive: React.CSSProperties = {
  ...switcherBtnBase,
  background: "#fff",
  color: "#555",
};

const switcherState: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 500,
  textTransform: "uppercase",
  letterSpacing: "0.4px",
};

// ── Chat bubbles ──
const bubbleBase: React.CSSProperties = {
  padding: "10px 16px",
  maxWidth: "78%",
  boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
};

const bubbleLeft: React.CSSProperties = {
  ...bubbleBase,
  background: "#fff",
  borderRadius: "16px 16px 16px 4px",
  border: `1px solid ${BORDER}`,
};

const bubbleRight: React.CSSProperties = {
  ...bubbleBase,
  background: DARK_MID,
  color: "#fff",
  borderRadius: "16px 16px 4px 16px",
};

const dreamBubbleLeft: React.CSSProperties = {
  ...bubbleBase,
  background: "#7c3aed",
  borderRadius: "16px 16px 16px 4px",
};

const dreamBubbleRight: React.CSSProperties = {
  ...bubbleBase,
  background: "#6d28d9",
  color: "#fff",
  borderRadius: "16px 16px 4px 16px",
};

const planBubbleLeft: React.CSSProperties = {
  ...bubbleBase,
  background: "#0d9488",
  borderRadius: "16px 16px 16px 4px",
};

const planBubbleRight: React.CSSProperties = {
  ...bubbleBase,
  background: "#0f766e",
  color: "#fff",
  borderRadius: "16px 16px 4px 16px",
};

const respondBubble: React.CSSProperties = {
  ...bubbleBase,
  background: "#ea580c",
  color: "#fff",
  borderRadius: "16px 16px 4px 16px",
};

const snapshotImg: React.CSSProperties = {
  width: "100%",
  maxWidth: 200,
  borderRadius: 8,
  marginBottom: 6,
  imageRendering: "pixelated",
};

const bubbleText: React.CSSProperties = {
  margin: 0,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  fontFamily: MONO,
  fontSize: 12.5,
  lineHeight: "1.6",
};

// ── System blocks ──
const systemBlock: React.CSSProperties = {
  background: "#fff",
  borderRadius: 10,
  padding: "14px 18px",
  marginBottom: 16,
  border: `1px solid ${BORDER}`,
};

const systemLabel: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: "#aaa",
  textTransform: "uppercase",
  marginBottom: 8,
  letterSpacing: "0.8px",
};

const systemText: React.CSSProperties = {
  margin: 0,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  fontSize: 12,
  lineHeight: "1.6",
  color: "#555",
  fontFamily: MONO,
};

const dreamSystemBlock: React.CSSProperties = {
  ...systemBlock,
  background: "#faf5ff",
  borderColor: "#ddd6fe",
};

const dreamSystemLabel: React.CSSProperties = {
  ...systemLabel,
  color: "#7c3aed",
};

const dreamSystemText: React.CSSProperties = {
  ...systemText,
  color: "#5b21b6",
};

const planSystemBlock: React.CSSProperties = {
  ...systemBlock,
  background: "#f0fdfa",
  borderColor: "#a7f3d0",
};

const planSystemLabel: React.CSSProperties = {
  ...systemLabel,
  color: "#0d9488",
};

const planSystemText: React.CSSProperties = {
  ...systemText,
  color: "#115e59",
};

// ── Input bar ──
const inputBar: React.CSSProperties = {
  borderTop: `1px solid ${BORDER}`,
  padding: "12px 20px",
  background: "#fff",
  display: "flex",
  alignItems: "center",
  gap: 10,
};

const inputForm: React.CSSProperties = {
  display: "flex",
  flex: 1,
  gap: 10,
};

const inputField: React.CSSProperties = {
  flex: 1,
  padding: "10px 16px",
  borderRadius: 10,
  border: `1px solid ${BORDER}`,
  fontSize: 13,
  fontFamily: MONO,
  outline: "none",
  background: SURFACE,
  color: "#333",
};

const sendBtn: React.CSSProperties = {
  padding: "10px 20px",
  borderRadius: 10,
  border: "none",
  background: DARK_MID,
  color: "#fff",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
  letterSpacing: "0.2px",
};

const countdownStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  color: "#ea580c",
  fontFamily: MONO,
  minWidth: 30,
};

const focusBtnInactive: React.CSSProperties = {
  padding: "8px 14px",
  borderRadius: 10,
  border: `1px solid ${BORDER}`,
  background: SURFACE,
  color: "#999",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
};

const focusBtnActive: React.CSSProperties = {
  padding: "8px 14px",
  borderRadius: 10,
  border: "1px solid #ea580c",
  background: "#ea580c",
  color: "#fff",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
};

const pauseBtnInactive: React.CSSProperties = {
  padding: "8px 10px",
  borderRadius: 10,
  border: `1px solid ${BORDER}`,
  background: SURFACE,
  color: "#999",
  fontSize: 14,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
  lineHeight: 1,
};

const pauseBtnActive: React.CSSProperties = {
  padding: "8px 10px",
  borderRadius: 10,
  border: "1px solid #10b981",
  background: "#10b981",
  color: "#fff",
  fontSize: 14,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
  lineHeight: 1,
};

const paceSelect: React.CSSProperties = {
  padding: "8px 10px",
  borderRadius: 10,
  border: `1px solid ${BORDER}`,
  background: SURFACE,
  color: "#555",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
  outline: "none",
  fontFamily: MONO,
};

const memBtn: React.CSSProperties = {
  padding: "8px 12px",
  borderRadius: 10,
  border: `1px solid ${BORDER}`,
  background: SURFACE,
  color: "#7c3aed",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
};

// ── Quick capture ──
const quickCaptureBar: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  padding: "6px 16px",
  borderTop: `1px solid ${BORDER}`,
  background: "#fff",
  flexShrink: 0,
};

const quickChip: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 4,
  padding: "5px 10px",
  borderRadius: 8,
  border: `1px solid ${BORDER}`,
  background: SURFACE,
  color: "#555",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
  transition: "all 0.15s",
};

const quickChipIcon: React.CSSProperties = {
  fontSize: 12,
};

const memPanel: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  borderBottom: `1px solid ${BORDER}`,
  background: "#fafafa",
  maxHeight: 280,
  flexShrink: 0,
};

const memPanelHeader: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "8px 16px 4px",
};

const memCloseBtn: React.CSSProperties = {
  background: "none",
  border: "none",
  fontSize: 18,
  color: "#999",
  cursor: "pointer",
  padding: "0 4px",
};

const clusterTag: React.CSSProperties = {
  display: "inline-block",
  padding: "1px 6px",
  borderRadius: 6,
  background: "#ede9fe",
  color: "#7c3aed",
  fontSize: 10,
  fontWeight: 600,
  marginLeft: 6,
  maxWidth: 100,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  verticalAlign: "middle",
};

const memSearchRow: React.CSSProperties = {
  display: "flex",
  gap: 6,
  padding: "4px 16px 8px",
};

const memInput: React.CSSProperties = {
  flex: 1,
  padding: "6px 10px",
  borderRadius: 8,
  border: `1px solid ${BORDER}`,
  fontSize: 12,
  fontFamily: MONO,
  outline: "none",
};

const memKindSelect: React.CSSProperties = {
  padding: "6px 8px",
  borderRadius: 8,
  border: `1px solid ${BORDER}`,
  fontSize: 11,
  background: "#fff",
  color: "#555",
  outline: "none",
};

const memSearchBtn: React.CSSProperties = {
  padding: "6px 14px",
  borderRadius: 8,
  border: "none",
  background: DARK_MID,
  color: "#fff",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
};

const memResultsList: React.CSSProperties = {
  overflow: "auto",
  padding: "0 16px 8px",
  maxHeight: 180,
};

const memItem: React.CSSProperties = {
  padding: "6px 0",
  borderBottom: `1px solid ${BORDER}`,
};

const memItemMeta: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  fontSize: 10,
  marginBottom: 2,
};

const memItemContent: React.CSSProperties = {
  fontSize: 12,
  color: "#333",
  lineHeight: 1.4,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const awayBanner: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "10px 16px",
  background: "#eff6ff",
  borderBottom: `1px solid #bfdbfe`,
  fontSize: 13,
  color: "#1e40af",
  fontWeight: 500,
  flexShrink: 0,
};

const awayCloseBtn: React.CSSProperties = {
  background: "none",
  border: "none",
  fontSize: 18,
  color: "#1e40af",
  cursor: "pointer",
  padding: "0 4px",
};

const loopsBanner: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "8px 16px",
  background: "#fefce8",
  borderBottom: `1px solid #fde68a`,
  fontSize: 12,
  color: "#854d0e",
  flexShrink: 0,
};

const loopsIcon: React.CSSProperties = {
  fontSize: 14,
  flexShrink: 0,
};

const loopsList: React.CSSProperties = {
  display: "flex",
  gap: 8,
  overflow: "hidden",
  flex: 1,
};

const loopItem: React.CSSProperties = {
  display: "inline-block",
  padding: "2px 8px",
  borderRadius: 6,
  background: "#fef9c3",
  border: `1px solid #fde68a`,
  fontSize: 11,
  fontWeight: 500,
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
  maxWidth: 200,
};

const loopsHint: React.CSSProperties = {
  fontSize: 10,
  color: "#a16207",
  flexShrink: 0,
  fontStyle: "italic",
  opacity: 0.6,
};

const focusFormPopup: React.CSSProperties = {
  display: "flex",
  gap: 4,
  alignItems: "center",
  padding: "4px 6px",
  borderRadius: 10,
  border: `1px solid #ea580c`,
  background: "#fff7ed",
};

const focusFormInput: React.CSSProperties = {
  width: 100,
  padding: "4px 8px",
  borderRadius: 6,
  border: `1px solid ${BORDER}`,
  fontSize: 11,
  fontFamily: MONO,
  outline: "none",
};

const focusFormSelect: React.CSSProperties = {
  padding: "4px 6px",
  borderRadius: 6,
  border: `1px solid ${BORDER}`,
  fontSize: 11,
  background: "#fff",
  outline: "none",
};

const focusFormGoBtn: React.CSSProperties = {
  padding: "4px 10px",
  borderRadius: 6,
  border: "none",
  background: "#ea580c",
  color: "#fff",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
};

const focusFormCancelBtn: React.CSSProperties = {
  padding: "4px 6px",
  borderRadius: 6,
  border: "none",
  background: "transparent",
  color: "#999",
  fontSize: 14,
  cursor: "pointer",
};

const newMsgPill: React.CSSProperties = {
  textAlign: "center",
  padding: "8px 0",
  background: DARK_MID,
  color: "#fff",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
  letterSpacing: "0.4px",
};
