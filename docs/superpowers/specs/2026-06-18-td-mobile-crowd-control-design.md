# TD Mobile Crowd Control — Design Spec

**Date:** 2026-06-18
**Status:** Approved (brainstorming) → ready for implementation planning
**Topic:** A mobile phone web frontend that lets a live crowd control a TouchDesigner projection, with a single seizable "master" controller plus a concurrent guest tier.

---

## 1. Purpose & scenario

A live installation/show where strangers' phones participate in driving a TouchDesigner projection.

- **Public crowd handoff.** Anyone can scan a QR code and open the control site on their own phone over cellular data.
- **Two control tiers:**
  - **Master** — one device holds the *full* control surface (all sliders, toggles, the grid). Claimed via a **"Seize Master" button** that reveals a 3-letter code entry; the code is displayed live on the projection. **Last-entry-wins**, but each seizure starts a **15-second lock-out** during which no one else can seize (anti-thrash). Auto-released on **2 minutes of inactivity** or a **30-minute hard cap**.
  - **Guest** — every other connected phone (no pairing required) can concurrently send a *defined subset* of public controls plus ephemeral signals. Guests are participants, not spectators.
- **Per-guest channels.** Each connected phone is assigned a slot index; its input lands in per-slot channels TD reads directly (e.g. each guest becomes one live point on the grid). Slots are capped and recycled.

### Success criteria
- A phone on cellular can scan the QR, load the site, and immediately participate as a guest.
- The projection always shows a current 3-letter code; entering it grants master and rotates the code.
- Master auto-releases on 2-min inactivity / 30-min cap / disconnect.
- Up to `slotCap` guests drive independent per-slot channels into TD concurrently, smoothly.
- The existing MCP WebServer DAT on port 9980 is never touched or disturbed.

### Non-goals (YAGNI)
- No accounts, persistence of user data, or analytics.
- No content moderation of control input beyond rate-limiting and the operator kill-switch.
- No hot-swappable control config (the panel is **fixed per show**; restart to change it).
- No master queue/fairness — seizure is intentionally last-wins.

---

## 2. Connectivity & topology

Phones stay on **cellular**, so the system is reached via a **public URL**. The TD machine sits behind venue NAT, so reachability is provided by an **outbound tunnel**, not a cloud host.

**Decision: the Node control-plane server runs on the same Khadas (x86 Windows) machine as TouchDesigner, exposed publicly via a tunnel (Cloudflare Tunnel / Tailscale Funnel / ngrok).**

Rationale:
- Node `ws` + static server is featherweight (tens of MB RAM, near-zero idle CPU) and is a **separate process** from TD — unlike the 9980 WebServer DAT it never touches TD's render thread, so co-hosting costs no frames.
- TD ↔ Node collapses to **localhost** (zero internet latency on the control→TD leg). The only internet hop is phone → tunnel.
- No separate cloud bill or cloud round-trip.

**Dependency / risk:** requires a **reliable venue uplink** (the tunnel needs outbound internet). If venue internet is flaky, an always-up cloud host degrades more gracefully — noted as a fallback, not the chosen path.

```
 Phones (cellular)          edge tunnel              Khadas (x86 Win, runs TD)
┌──────────────┐  HTTPS/WSS  (CF/ngrok)     ┌──────────────────────────────────┐
│ control site │◄───────────────────────────►│  Node server (control plane)     │
│ (PWA)        │                             │   • static site + show config    │
└──────────────┘                             │   • ws fanout + session state    │
                                             │   • pairing / roles / timers     │
                                             │   • per-slot coalescing          │
                                             │            ▲  localhost ws        │
                                             │            ▼  (role=engine)       │
                                             │  TouchDesigner                   │
                                             │   • WebSocket DAT (outbound)      │
                                             │   • slots → Table DAT → CHOP      │
                                             │   • code → Text TOP on projection │
                                             │   • 9980 MCP WebServer UNTOUCHED  │
                                             └──────────────────────────────────┘
```

---

## 3. Components

Four cleanly-separated units, each with one purpose and a well-defined interface:

| Unit | Purpose | Depends on |
|------|---------|------------|
| **(a) Phone PWA** | Renders the control UI from the show config; sends input over one WebSocket; reflects role changes. | Show config; wire protocol |
| **(b) Node control plane** | The only stateful brain: sessions, roles, slot assignment, pairing/code, timers, per-slot coalescing, fanout. Serves the static site + config. | Wire protocol |
| **(c) TD WebSocket DAT ingress** | Dials Node over localhost as the privileged `engine` client; writes slot snapshots into a Table DAT and the code into a Text TOP. | Wire protocol; binding map |
| **(d) Show config (JSON)** | Shared contract: defines controls/signals/grid, roles, slotCap. Phone renders from it; TD binds from it. | — |

The MCP bridge on 9980 is a separate, untouched system.

---

## 4. Wire protocol

JSON messages over **one WebSocket per client**. Two client classes: phones (untrusted) and the TD `engine` (trusted via shared secret).

### Phone → server
| Type | Payload | Notes |
|------|---------|-------|
| `hello` | `{clientId}` | `clientId` persisted in localStorage for slot continuity |
| `pair` | `{code}` | Attempt master seizure with the projected 3-letter code |
| `control` | `{id, v}` | Set a control value; server enforces role gating |
| `grid` | `{x, y}` | This client's XY point (normalized 0..1); throttled client-side |
| `signal` | `{id}` | Ephemeral fire-once event (e.g. burst) |
| `ping` | `{}` | Heartbeat / liveness |

### Server → phone
| Type | Payload | Notes |
|------|---------|-------|
| `welcome` | `{clientId, role, slot, config, masterPresent}` | Sent on connect; includes full show config |
| `role` | `{role, slot}` | Role/slot changed (e.g. became master, or bumped to guest) |
| `bumped` | `{}` | You lost master because someone else seized |
| `state` | `{masterPresent, guestCount, slotsUsed}` | Periodic lightweight status for UI |
| `error` | `{code, msg}` | Invalid message / rate-limited / etc. |

**The phone is never sent the master code.** It must be read off the projection — that is the physical-presence gate.

### Server ↔ TD (`engine` client, shared secret)
- On connect TD authenticates with `role=engine` + secret; it is **not** counted as a guest and receives privileged data.
- Server → TD: a **slot snapshot** at a fixed ~60 Hz tick:
  ```jsonc
  {
    "type": "snapshot",
    "code": "FOX",
    "masterSlot": 0,
    "slots": [
      {"slot": 0, "role": "master", "active": true,  "x": 0.5, "y": 0.5, "vals": {"speed": 0.3, "glow": 1}},
      {"slot": 3, "role": "guest",  "active": true,  "x": 0.2, "y": 0.8, "vals": {"hue": 0.6}}
    ]
  }
  ```
- Server → TD: one-shot `signal` events `{type:"signal", id, slot}`.
- Snapshot is coalesced (latest-value-per-slot) so high-frequency phone input never floods TD.

---

## 5. Roles, slots & pairing state machine

### Slot assignment
- On connect, assign the next free slot up to `slotCap` (default **24**). **Slot 0 reserved for master**; slots 1…N for guests.
- Overflow (all slots full): connection becomes a **spectator** — its signals are still counted, but it gets no dedicated per-slot point — until a slot frees.
- Disconnect → slot freed → recycled (LRU) for the next/overflowed connection.

### Master state machine
States: **NoMaster** and **MasterHeld(slot=0, since, lastActivity, seizeLockUntil)**.

- **Code:** `currentCode` is a 3-letter code. It **rotates on every seizure** and on a **60-second idle timer**, so a code captured in a photo goes stale.
- **Seize affordance:** the phone shows a **"Seize Master" button**; tapping it reveals the 3-letter code entry (read off the projection) and sends `pair{code}`.
- **Seize lock-out:** each grant sets `seizeLockUntil = now + 15 s`. While `now < seizeLockUntil`, all `pair` attempts are rejected with `error{code:"locked", retryInMs}` (the UI shows a brief "Master locked — Ns" state and disables the button). This prevents rapid back-and-forth takeover thrashing.
- **Seizure (`pair{code}`):** if not locked **and** `code == currentCode` →
  1. grant master to this connection (moves it to slot 0);
  2. if a master already existed, demote it to a guest slot and send it `bumped`;
  3. generate a new `currentCode`;
  4. reset `since` + `lastActivity`; set `seizeLockUntil = now + 15 s`;
  5. push the new code to TD (→ projection).
  Because seizing rotates the code, the next taker needs the freshly-displayed one — and must wait out the 15 s lock.
- **Activity:** any master `control` / `grid` / `signal` updates `lastActivity`.
- **Release** (→ NoMaster, rotate code, keep displaying a now-claimable code):
  - `now - lastActivity > 2 min` (inactivity), **or**
  - `now - since > 30 min` (hard cap, regardless of activity), **or**
  - master disconnects.

### Role gating (server-enforced)
- **Master:** may set any control, drive the master grid point, fire any signal.
- **Guest:** may set only `role:"public"` controls, drive its own grid point, fire `role:"public"` signals. Anything else → `error`.

---

## 6. Per-show config (shared contract)

A single JSON document, served by Node and read by TD. **Fixed per show**; loaded at startup on both ends.

```jsonc
{
  "show": "myshow",
  "slotCap": 24,
  "controls": [
    {"id": "speed", "type": "slider", "label": "Speed", "min": 0, "max": 1, "role": "master"},
    {"id": "glow",  "type": "toggle", "label": "Glow",  "role": "master"},
    {"id": "hue",   "type": "slider", "label": "Color", "min": 0, "max": 1, "role": "public"}
  ],
  "grid":    {"id": "xy", "perGuest": true, "role": "public"},   // each guest = one live point
  "signals": [{"id": "burst", "label": "✦", "role": "public"}]
}
```

- The phone renders its panel from `controls` filtered by the client's **current role** (re-renders on role change).
- TD holds a **binding map** `controlId → (op, par)` or channel routing, kept in sync with these ids.

---

## 7. TD-side ingestion & smoothing

- A **WebSocket DAT** dials `ws://localhost:PORT` (outbound), authenticating as `role=engine` with the shared secret. Stays entirely off the 9980 MCP WebServer DAT.
- `onReceiveText` parses each snapshot → writes a **Table DAT** of slots (one row per slot: slot, role, active, x, y, control values) and a one-cell **Text DAT** for the current code.
- A **DAT-to-CHOP** (or Script CHOP) explodes the table into channels (`slot3_x`, `slot3_speed`, …) for the existing channel logic.
- A **Lag / Filter CHOP** smooths the per-slot channels so ~30 Hz network input feels fluid.
- The code Text DAT drives a **Text TOP** composited onto the projection.

---

## 8. Failure handling, abuse & rate-limiting

### Reconnect / restart
- **Phone reconnect:** `clientId` (localStorage) restores its guest slot if still available. **Master is never auto-restored** — re-pairing is required (safety).
- **Node restart:** session state is ephemeral; it clears to NoMaster + a fresh code. Phones auto-retry their WebSocket and re-handshake; slots are reassigned. The TD WebSocket DAT auto-reconnects.
- **Tunnel blip:** phones retry; TD (localhost) is unaffected.

### Abuse mitigation (guest tier is public by design)
- `slotCap` bounds concurrent per-slot participants.
- **Per-connection rate-limit** on messages/sec; invalid/oversize messages are dropped with an `error`; repeated abuse disconnects.
- Master is gated by the **rotating, projection-only code** (presence requirement).
- **Operator kill-switch:** clear master, freeze guest input, and blank the code on demand.

---

## 9. Testing strategy

- **Session state machine (headless unit tests):** seizure, last-wins demotion + `bumped`, 15-second seize lock-out (reject during, accept after), 2-min inactivity release, 30-min cap release, disconnect release, code rotation (per-seizure + 60 s idle), slot assignment/recycling, overflow→spectator, role gating accept/reject.
- **Load / protocol:** a fake-phone script opening N WebSocket connections and driving control/grid/signal traffic to exercise coalescing and the slot cap.
- **TD format lock:** a mock `engine` client to pin the snapshot/signal message format before wiring the real WebSocket DAT.
- **Manual:** projection code render + smoothness check on the real TD network.

---

## 10. Defaults chosen (tunable at review)

- `slotCap` = **24**.
- Code rotation = **on every seizure + every 60 s idle**.
- Seize lock-out after each grant = **15 s**.
- Master inactivity release = **2 min**; hard cap = **30 min**.
- Snapshot tick to TD = **~60 Hz**, coalesced latest-per-slot.
- Grid coordinates normalized **0..1**, origin per TD convention handled in the binding map.
