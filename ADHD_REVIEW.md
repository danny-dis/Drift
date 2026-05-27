I'll start by exploring the project structure and reading the key source files to understand the actual implementation before making any recommendations.
Let me get a cleaner view of the project structure and start reading the core files.
Now let me read all the core source files. I'll batch the reads for efficiency.
Now let me read the core backend files.
Now let me read the remaining backend files and the frontend.
Now let me read the frontend source files and the providers module.
Let me also check the actual output files and sprites definition.
Let me check one more file to understand the actual content quality.
Now I have a thorough understanding of the entire codebase. Let me write the comprehensive review.

---

# Drift: ADHD-Cognition Architecture Review

## Part 1: Architecture Review

### 1.1 What is Already ADHD-Friendly

Drift has several design choices that are genuinely well-suited to ADHD cognition, and they are worth naming explicitly because they are non-obvious and would be easy to accidentally break during future development.

**The continuous thinking loop is the single best ADHD feature in the system.** The creature runs autonomously on a steady pulse (`thinking_pace_seconds: 5` in config.yaml, defaulting to 45 in `config.py` line 57). This means the user never has to "start" the AI. There is no activation energy. You open the page and something is already happening. This maps directly to the ADHD principle of reducing initiation friction. The creature does not wait for you. It is already thinking. You can just watch, or engage when you feel like it.

**The ambient presence model is powerful.** The pixel-art room with the wandering creature creates a sense of "someone is here working" without demanding attention. The state indicators (thought bubble, sparkles, clipboard, speech bubble) at `GameWorld.tsx` lines 241-316 provide ambient awareness without requiring the user to read text. This is body-doubling by proxy -- the user has a sense of not being alone in their work.

**File drop detection is zero-friction input.** The `_check_new_files()` method at `brain.py` lines 408-466 scans the filesystem and automatically queues new files for attention. The user does not need to navigate a UI, fill out a form, or articulate what they want. They just drop a file in a folder. This is exactly the kind of "just throw it over the wall" interaction pattern that works for ADHD cognition.

**The conversation model is time-bounded.** The 15-second reply window at `brain.py` line 360 (`timeout=15`) creates urgency without permanence. The user knows the interaction is short. This reduces the "I'll get sucked into a long conversation" avoidance that ADHD users often feel with AI tools.

**The personality genome is a bonding mechanism.** The keyboard entropy system at `identity.py` lines 138-190 creates a sense of ownership and uniqueness. For ADHD users, emotional attachment to a tool increases consistent usage. The creature is not generic -- it is *yours*.

**The planning system produces tangible artifacts.** The `projects.md` file and daily logs at `brain.py` lines 934-1021 are real files the user can read, edit, and reference outside the AI. This externalization of planning state is critical for ADHD working memory support.

### 1.2 Friction Points Especially Painful for ADHD Users

**The thinking pace is a trap.** The config.yaml sets `thinking_pace_seconds: 5` but `config.py` line 57 defaults to 45. Five seconds is extremely fast -- the creature produces a new thought, new tool calls, new events every 5 seconds. This creates a firehose of content in the chat feed. An ADHD user who looks away for 30 seconds comes back to 6 new cycles of activity. The visual overwhelm is immediate and compounding.

**There is no pause button.** The `Brain.stop()` method at `brain.py` line 1069 exists but is never exposed through the API or UI. The user cannot pause the creature's thinking. They cannot say "stop for a minute, I need to look at what you just did." The creature just keeps going. For an ADHD user who needs to process at their own pace, this is deeply frustrating.

**The chat feed is an undifferentiated stream.** Looking at `App.tsx` lines 334-380, every API call's input and output gets rendered sequentially. System prompts, tool calls, tool results, thoughts, reflections, planning -- they all appear as the same kind of chat bubble. There is no visual hierarchy. There is no way to filter. There is no way to collapse tool output. An ADHD user staring at this feed sees a wall of monospace text that grows continuously. The cognitive load of scanning this feed to find "the interesting part" is high.

**The conversation timeout is punishing.** Fifteen seconds at `brain.py` line 360 is very short. If an ADHD user gets the notification that the creature wants to talk, and they take 16 seconds to type their response, the creature has already moved on. The message arrives, the countdown ticks, and if you are not fast enough, the window closes. This creates a negative feedback loop: the user tried to engage, failed, and now feels bad about it.

**Focus mode is binary.** The `_focus_mode` boolean at `brain.py` line 208 is either on or off. When it is on, the nudge at `prompts.py` line 111 says "IGNORE your usual moods and autonomous curiosity. Your ONLY job right now is to work on whatever your owner has given you." When it is off, the creature wanders freely. There is no middle ground. There is no "focus on this specific topic for the next 20 minutes." There is no "focus but also keep one eye on incoming files." The binary nature means the user must make a decision with no gradation, which is itself a source of decision fatigue.

**The system prompt is long and undifferentiated.** The `main_system_prompt` at `prompts.py` lines 34-108 is 108 lines of instructions. It includes room descriptions, tool usage, behavioral principles, file handling instructions, voice handling, focus section, and style guidelines -- all concatenated. The creature has to process all of this every single cycle. More importantly, if an ADHD user ever reads the system prompt (which is displayed in the chat feed as a "System Prompt" block), it is an overwhelming wall of text with no visual structure.

**There is no way to give positive feedback.** The user can send messages, but there is no mechanism to say "that was a great thought" or "keep doing that." The importance scoring at `memory.py` lines 163-177 is done by the LLM itself, not by the user. For ADHD users, the ability to reinforce good behavior is a key engagement mechanism. Without it, the user feels like they are shouting into a void.

**No memory search or browsing.** The memory stream at `memory.py` is an append-only JSONL file. There is no API endpoint to search memories, browse them, or see what the creature remembers. The user cannot ask "what does my creature think about X?" or "show me all the high-importance memories." The memory is invisible. For ADHD users who struggle with their own working memory, having an opaque external memory system is frustrating rather than helpful.

**The multi-cat switcher is a context-switch tax.** When multiple cats are running, the switcher bar at `App.tsx` lines 411-429 shows buttons with name and state. But switching cats resets the entire chat feed (`App.tsx` lines 224-241). The user loses their place. For ADHD users who are already prone to losing context, this is a significant penalty.

### 1.3 Missed Opportunities for Outsized Cognitive Impact

**No "what just happened" summary.** After the user returns from being away (which happens frequently with ADHD), there is no summary of what the creature did while they were gone. The chat feed just shows a wall of new content. A simple "while you were away, I wrote 2 reports, searched for 3 things, and reflected on my research approach" would dramatically reduce re-orientation cost.

**No importance-based visual differentiation.** Every thought looks the same in the feed. But the system already scores importance 1-10 at `memory.py` line 70. This score is never shown to the user. High-importance thoughts could be highlighted, enlarged, or pinned. Low-importance thoughts could be collapsed. The data is already there.

**No quick-capture for the user.** The user can type a message, but there is no "quick thought" input that gets injected as a high-priority nudge. ADHD users often have fleeting ideas they want to throw at the creature without thinking about how to phrase it. A "just tell it" button that accepts raw, unstructured input and lets the creature figure out what to do with it would reduce friction.

**No adaptive thinking pace.** The `thinking_pace_seconds` is static. It could adapt: faster when the creature is excited about something, slower when it is in a reflective state, pausing when the user is actively typing. The data to drive this exists (cat state, user typing state) but is not connected.

**No "companion mode" for body doubling.** The creature already wanders its room, which creates ambient presence. But there is no explicit "I am working on something, please work alongside me" mode where the user states their intention and the creature mirrors focus. This is a missed opportunity for one of the most effective ADHD support patterns.

---

## Part 2: ADHD Feature Design

### 2.1 Dopamine Hooks and Reward Loops

**Tangible output celebrations.** When the creature produces a file (detected at `brain.py` lines 852-858), the frontend should show a brief visual celebration -- a subtle animation, a color pulse, a count increment. The key insight is that ADHD dopamine responds to *visible progress*. The file count is already trackable via `/api/files`. Show it growing.

**Streak tracking.** Add a lightweight streak counter: "3 research reports in a row" or "focused on mycology for 6 cycles." Display this as a subtle badge. ADHD users respond to momentum indicators. The data for this exists in `_consecutive_research_cycles` at `brain.py` line 212 but is only used internally to nudge the creature.

**"Favorite thought" mechanism.** Add a button on each thought bubble that lets the user mark it as interesting. Store this in the memory entry (a `user_rating` field in the JSONL). This gives the user a micro-interaction that feels rewarding and also improves memory retrieval quality.

**Daily digest with highlights.** At the end of each day (or on demand), generate a summary of the creature's best work: highest-importance memories, files produced, topics explored. Present this as a clean, readable card. This transforms the firehose into a curated feed.

### 2.2 Attention Management and Context-Switching Aids

**Priority inbox, not firehose.** Split the event stream into two channels: "important" (user messages, high-importance thoughts, file outputs, reflections) and "ambient" (tool calls, low-importance thoughts, movement). Let the user toggle between them. The importance score already exists. Use it.

**Filter by type.** Add filter buttons: Thoughts, Research, Code, Conversations, Reflections. Each event type is already classified (`event_type` in `_emit`). Let the user narrow their view.

**"Quiet mode."** A toggle that suppresses all ambient events and only shows important ones. The creature keeps thinking, but the user only sees the highlights. This is the antidote to the firehose problem.

**Collapsible tool output.** Tool call results (especially shell commands) are often long and uninteresting. Collapse them by default with an expand toggle. Show only the tool name and a one-line summary.

### 2.3 Hyperfocus Protection

**Session timer.** Show how long the user has been on the page. After a configurable period (default: 90 minutes), show a gentle, non-blocking notification: "You have been here for 90 minutes. Consider taking a break." This should be dismissible, not blocking.

**Focus mode auto-expiration.** Focus mode should have an optional timer. "Focus on this for 30 minutes" and then it automatically turns off. The creature returns to its normal moods. This prevents the ADHD pattern of hyperfocusing on one thing and losing track of time.

**"What time is it" awareness.** The creature already knows the time (`prompts.py` line 39: `datetime.now().strftime(...)`). It could occasionally mention the time in its thoughts: "It's 2 AM -- you're still here?" This is gentle, non-judgmental time awareness.

### 2.4 Task Initiation Scaffolding

**Quick prompts.** Add a set of one-click starter prompts: "Research something interesting," "Continue your last project," "Organize your files," "Write something." These bypass the activation energy of deciding what to say.

**"Just tell it" input.** A special input mode where the user types raw, unstructured thoughts (like "mushrooms cool what if bioluminescent tattoo ink") and the creature interprets them as a research direction. No need to formulate a complete sentence or request.

**Template tasks.** Pre-built task templates: "Compare X and Y," "Summarize this topic," "Find recent news about X," "Write a report on X." The user fills in one field and the creature executes.

### 2.5 Working Memory Externalization

**Persistent "current context" sidebar.** A small, always-visible panel showing: what the creature is currently focused on, what it last produced, what it is thinking about. This is the user's external working memory for the creature's state.

**Memory search.** Add an API endpoint and UI for searching the creature's memories by keyword. The embeddings already exist for semantic search. Expose this.

**"What does it know about X?" query.** A special input that does not send a message to the creature but instead queries its memory stream for relevant memories and displays them. This lets the user check the creature's knowledge before deciding what to ask.

### 2.6 Emotional Regulation Support

**Mood indicators that reflect the user.** Let the user set their own mood (tired, energized, scattered, focused) and have the creature adapt its behavior. If the user is scattered, the creature could switch to "organizer" mood. If energized, it could switch to "explorer."

**Calming visual mode.** A toggle that slows the creature's animations, reduces the chat feed update rate, and uses softer colors. For ADHD users who are overstimulated, this provides a calmer viewing experience.

**Non-judgmental language in prompts.** The current prompts are already good about this ("curious, earnest, sometimes confused"). But the planning prompt at `prompts.py` line 120 could be more explicitly non-judgmental: instead of "review what you've built so far," use "see what you have been exploring."

### 2.7 Body Doubling and Ambient Accountability

**"Work alongside me" mode.** The user states what they are working on (e.g., "I am writing an email") and the creature settles into a focused activity at its desk. Both are working. The creature occasionally acknowledges the shared session: "Still here. How is the email going?" This is body doubling.

**Shared focus sessions.** The user starts a focus timer (25 minutes, Pomodoro-style) and the creature also focuses on one task for that duration. At the end, both report what they accomplished.

**Ambient sound cues.** Subtle audio feedback when the creature produces output, completes a research cycle, or enters reflection. Not intrusive -- just a soft chime that says "something happened." This maintains ambient awareness without requiring visual attention.

---

## Part 3: System Redesign

### 3.1 Memory System

**Current state.** The memory system at `memory.py` is a well-designed Smallville-inspired implementation. The three-factor retrieval (recency + importance + relevance) is sound. The append-only JSONL is simple and reliable. The importance scoring via LLM is a clever approach.

**ADHD-informed problems:**

The reflection threshold of 50 (config.yaml line 12) is arbitrary. It does not account for the type of activity. A burst of low-importance research thoughts might trigger reflection when the creature has not actually learned anything meaningful. Conversely, a single high-importance insight might not trigger reflection because it is below threshold.

The retrieval count of 3 (config.yaml line 13) is too low for context-heavy tasks. When the creature is analyzing a dropped file, it needs more surrounding context. The count should be dynamic based on task type.

The recency decay rate of 0.995 means memories lose half their recency score in about 138 hours (5.75 days). Important memories from a week ago are effectively invisible unless their importance is very high. For ADHD users who think in longer cycles (picking up a project after a week), this is too aggressive.

**Recommended changes:**

1. Make reflection threshold adaptive: lower it during high-activity periods, raise it during quiet ones.
2. Increase default retrieval count to 5 and make it configurable per-query (the `retrieve` method already accepts `top_k`).
3. Add a "pinned memories" mechanism where the user can mark memories as permanent (no decay).
4. Add a memory browser API endpoint: `GET /api/memories?query=X&kind=Y&min_importance=Z`.
5. Add a memory health dashboard: how many memories, average importance, reflection count, top topics.

### 3.2 Planning System

**Current state.** Planning runs every 10 cycles (`PLAN_INTERVAL = 10` at `brain.py` line 182). It reviews projects.md, files, and recent memories, then writes an updated plan. The planning prompt at `prompts.py` lines 120-138 is well-structured with clear sections.

**ADHD-informed problems:**

The fixed interval of 10 cycles means planning happens at a fixed cadence regardless of what the creature is doing. If it is in the middle of a deep research thread, planning interrupts it. If it has been idle, planning does not happen soon enough.

The planning output overwrites projects.md entirely (`brain.py` line 998: `f.write(plan_body)`). Previous plans are lost. For ADHD users who want to see how their thinking evolved, this is a loss.

The "Ideas Backlog" section in the planning prompt (3-5 items max) is too small. ADHD users often have many ideas they want to capture. The limit creates pressure to choose, which is itself a source of friction.

**Recommended changes:**

1. Make planning frequency adaptive: plan sooner after bursts of activity, delay during focused work.
2. Archive previous plans instead of overwriting: append to a `plans/` directory with timestamps.
3. Remove the backlog size limit or increase it to 10. Let the creature capture everything.
4. Add a "quick idea" endpoint that lets the user inject an idea into the backlog without triggering a full planning cycle.
5. Show the planning output in the UI as a structured card, not as raw text.

### 3.3 Focus Mode

**Current state.** Focus mode is a boolean toggle (`_focus_mode` at `brain.py` line 208). When enabled, the nudge at `prompts.py` line 111 tells the creature to ignore its moods and focus entirely on user-provided material. The UI shows an orange "Focus" button at `App.tsx` lines 512-518.

**ADHD-informed problems:**

The binary on/off is too coarse. There is no way to say "focus for 20 minutes" or "focus on this specific topic." The nudge text is aggressive ("DROP EVERYTHING") which creates a sense of urgency that may not be appropriate.

Focus mode does not expire. If the user turns it on and walks away, the creature stays focused indefinitely. There is no natural break point.

**Recommended changes:**

1. Add focus duration: "Focus for 30 minutes" with auto-expiration.
2. Add focus topic: "Focus on bioluminescence research" instead of generic focus.
3. Add gradations: light focus (stay on topic but allow tangents), deep focus (ignore everything else).
4. Show focus mode status prominently: elapsed time, topic, intensity.
5. When focus expires, show a summary of what was accomplished during the focus session.

### 3.4 Thinking Loop Pace and Interruption Model

**Current state.** The thinking loop at `brain.py` lines 1042-1067 runs continuously with `asyncio.sleep(config["thinking_pace_seconds"])` between cycles. The pace is static. User messages are injected on the next cycle via `_user_message` at `brain.py` line 215.

**ADHD-informed problems:**

The pace does not adapt to context. Five seconds is too fast for passive observation. Forty-five seconds is too slow for active conversation. The user has no control over the pace.

When the user sends a message, it is injected on the next cycle. But if the creature is in the middle of a tool loop (up to 15 rounds at `brain.py` line 739), the message waits. The user sends a message and nothing happens for potentially minutes.

There is no way to interrupt the creature mid-cycle. If it is going down a wrong path, the user must wait for the cycle to complete.

**Recommended changes:**

1. Add a user-controllable pace slider: slow (60s), normal (15s), fast (5s), conversation (immediate response).
2. When the user sends a message, interrupt the current tool loop and inject it immediately.
3. Add a "pause" button that stops the thinking loop entirely.
4. In conversation mode (user is actively chatting), switch to immediate-response pacing.
5. When the user is idle for >5 minutes, slow down to conserve API costs.

### 3.5 The UI/Frontend Experience

**Current state.** The frontend at `App.tsx` is a two-pane layout: 45% pixel-art room, 55% chat feed. The chat feed shows a deduplicated stream of all events. The input bar has a focus button, text input, and send button.

**ADHD-informed problems:**

The 45/55 split is rigid. The room is beautiful but static -- the user cannot resize it or collapse it. On smaller screens, the chat feed is too narrow.

The chat feed has no visual hierarchy. System prompts, tool calls, thoughts, reflections, and planning all look the same. The user must read everything to find what matters.

The input bar is minimal but lacks quick-action buttons. There is no way to send a quick prompt, toggle quiet mode, or search memories without typing.

The "new messages" indicator at `App.tsx` lines 497-507 is helpful but only appears when the user scrolls up. There is no persistent indicator of unseen activity.

**Recommended changes:**

1. Make the split resizable or add a collapse toggle for the room.
2. Add visual hierarchy: larger text for thoughts, smaller for tool calls, color-coding for importance, collapsible sections for tool output.
3. Add a toolbar above the input: quick prompts, quiet mode toggle, memory search, pace control.
4. Add a persistent activity counter: "12 new thoughts since you last looked."
5. Add a "summary" tab that shows only high-level activity: files produced, reflections, planning updates.
6. Add a "digest" view that compresses the feed into a timeline: "14:32 - Researching bioluminescence. 14:35 - Wrote outline. 14:38 - Reflected on research approach."
7. Show the creature's current focus in a persistent, visible location (not buried in the chat feed).
8. Add keyboard shortcuts: Enter to send, Escape to clear, Ctrl+K for quick prompt, Ctrl+M for memory search.

---

## Summary of Highest-Impact Changes

If I had to pick five changes that would have the most outsized impact on ADHD usability, in priority order:

1. **Add a pause button and thinking pace control.** This is the single most requested feature pattern in ADHD tool design. The user must be able to control the speed of information flow. Implementation: expose `Brain.stop()` via API, add pace slider to UI, add `POST /api/pause` and `POST /api/pace` endpoints.

2. **Split the chat feed into "important" and "ambient" channels.** The firehose problem is the primary source of overwhelm. Use the existing importance scores and event types to filter. Implementation: add a toggle in the frontend that filters the `messages` array by type/importance.

3. **Add a "while you were away" summary.** When the user returns after being idle for >5 minutes, show a brief digest instead of the full feed. Implementation: track last interaction time in the frontend, fetch events since that time, summarize them.

4. **Add focus mode timer and topic.** Transform the binary toggle into a nuanced tool. Implementation: add `focus_until` and `focus_topic` fields to the Brain, modify the nudge generation, add UI controls.

5. **Add memory search and browsing.** Make the creature's memory visible and queryable. Implementation: add `GET /api/memories` endpoint with search/filter, add a simple search UI in the frontend.

---

This is a systems-level review. The underlying architecture is solid -- the Smallville-inspired memory, the continuous thinking loop, the personality genome, the file-drop interaction model. The ADHD friction is almost entirely in the UI layer and the configuration surface. The backend has the data (importance scores, event types, memory embeddings) but the frontend does not use it to reduce cognitive load. Most of the recommended changes are frontend and configuration work, not deep backend rewrites.
