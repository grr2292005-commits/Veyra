# Emergency Stabilization: Known Good Baseline

## 1. Known Good State Definition

The last known good state of Speechify satisfied the following functional baseline:

1. **Panel Rendering**:
   - Extension opened in Premiere Pro via `Window -> Extensions -> Speechify`.
   - The dark slate UI loaded immediately without black screens or rendering artifacts.
   - Header displayed: `Speechify   Starting…` transitioning to `Speechify   ✓`.
   - Main view displayed: Sequence info, Scope selector (`Selected clips`, `In / Out`, `Entire sequence`), Model selector, Output dropdown, and `Enhance Speech` button.

2. **Engine Execution**:
   - Engine started silently in the background via `pythonw.exe`.
   - Zero command prompts, PowerShell windows, or terminal windows appeared.
   - Responded to `GET /health` with HTTP 200.
   - Engine maintained a 15s watchdog fed by 4s heartbeats from the panel.

3. **Audio Enhancement**:
   - Selected audio clip was extracted and processed via MP-SENet, ZipEnhancer, MossFormerGAN, or DeepFilterNet3.
   - Processed audio was imported non-destructively into a `"Speechify"` bin and placed onto the timeline with exact synchronization and gap preservation.

---

## 2. Baseline Architecture Invariants

To return to and permanently secure this baseline:

1. **UI Must Render FIRST**:
   - The HTML and CSS must paint a complete, static, valid user interface synchronously without waiting on any `fetch`, Node child process, ExtendScript call, or filesystem operation.
2. **Subsystems Must Be Asynchronously Isolated**:
   - Engine startup, hardware detection, model scanning, and timeline synchronization must be triggered *after* initial paint.
   - Every subsystem must catch its own errors and never let an unhandled promise rejection bubble up.
3. **No Double Initialization**:
   - Initialization must be gated behind a singleton `bootPromise`.
4. **Resilient Fallback**:
   - If any subsystem fails (e.g., engine fails to start), the UI must display a clear inline status (`Speech engine unavailable [Retry]`), while the rest of the panel remains fully rendered and responsive.
