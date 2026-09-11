# Emergency Stabilization: Change Analysis

## 1. Audit of Changes Made Prior to Regression

| File | Changes Made | Potential Failure Mode |
| :--- | :--- | :--- |
| `plugin/index.html` | Added `.sp-storage-card` and hidden elements (`storagePathInput`, `chooseFolderBtn`, `saveStoragePathBtn`) | Hidden elements with `style="display: none;"` or button elements without types might cause unexpected form submission or CSS layout calculation failures. |
| `plugin/ui/design-system/components.css` | Added styles for `.sp-storage-card`, `.sp-storage-info`, `.sp-storage-title`, `.sp-storage-subtext`, `.sp-storage-actions` | `word-break: break-all` on flex items without explicit width bounds in older CEF versions can trigger flexbox layout collapse or overflow. |
| `plugin/index.js` | 1. Added elements to `el` at script execution time before DOMContentLoaded.<br>2. Added `SpeechifyStorageService.init()` in `init()`.<br>3. Directly invoked `await initializeEngine()` and `await syncTimeline()` inside `init()`. | Top-level execution: if any element ID fails, or if `init()` throws before completing, CEF page rendering gets blocked. Also, starting engine during `init()` blocks the main thread from completing first paint. |
| `plugin/state/app_state.js` | Updated defaults in `modelStorage` slice | If any component accessed `modelStorage` expecting older property names without null checks, it could throw `TypeError`. |
| `plugin/services/storage_service.js` | Added `init()` calling `rescan()` | Network fetch to `127.0.0.1:8765/api/models` during initialization could reject if engine is offline, causing unhandled promise rejections. |
| `plugin/CSXS/manifest.xml` | Checked CEFCommandLine parameters | Standard parameters. |

---

## 2. Root Cause Hypotheses

1. **Hypothesis A (Render-Blocking Script Execution)**:
   In `plugin/index.js`, `init()` runs on `DOMContentLoaded`. It performs `await initializeEngine()` and `await syncTimeline()`. If `syncTimeline()` or `initializeEngine()` blocks, or if an unhandled promise rejection occurs during CEP's synchronous render pass, CEF fails to paint and displays a black/glitched buffer.

2. **Hypothesis B (CEF GPU Compositing Artifacts)**:
   The "black panel with vertical blue lines" is the classic visual signature of an unpainted / invalid DirectX/OpenGL backbuffer in Chromium Embedded Framework when hardware acceleration fails or an invalid CSS transform/filter/backdrop is applied to a zero-height container.

3. **Hypothesis C (Top-Level Script Evaluation Exception)**:
   If an uncaught exception is thrown when `index.js` is initially parsed by Chromium, none of the event listeners or render code executes, leaving the initial CEF viewport unpainted.

---

## 3. Plan of Action

1. Establish `KNOWN_GOOD_BASELINE.md`.
2. Decouple UI rendering completely from service initialization:
   - Paint static UI and basic text immediately.
   - Guard every subsystem behind an isolated asynchronous loader.
   - Enforce an emergency fallback view in HTML that paints natively with zero JS dependencies.
3. Add top-level `window.onerror` and `window.onunhandledrejection` handlers that write directly to a visible diagnostic container and `logs/startup.log`.
4. Prevent double-initialization via a singleton `bootPromise`.
