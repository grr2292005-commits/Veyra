# Emergency Stabilization: Broken State Report

**Timestamp**: 2026-09-10  
**Host Application**: Adobe Premiere Pro 2024 / 2025  
**Reported Symptom**:
- Premiere Pro starts and runs normally.
- The user opens Window -> Extensions -> Speechify.
- Instead of rendering the Speechify interface, the panel is mostly black with abnormal vertical blue lines (unrendered / corrupt CEF view).
- The plugin is failing during initialization or initial layout rendering, causing Chromium Embedded Framework (CEF) within Premiere to fail compositing or crash the rendering pipeline.

---

## 1. Files Involved in Last Pass

1. `plugin/index.html`:
   - Replaced raw storage inputs with `.sp-storage-card` and hidden elements (`#storagePathInput`, `#chooseFolderBtn`, `#saveStoragePathBtn`).
   - Added `#storageTypeTitle`, `#storageSubtext`, `#storageModelsSummary`, `#changeStorageBtn`, `#resetStorageBtn`.
2. `plugin/ui/design-system/components.css`:
   - Added `.sp-storage-card`, `.sp-storage-info`, `.sp-storage-title`, `.sp-storage-subtext`, `.sp-storage-actions`.
3. `plugin/state/app_state.js`:
   - Updated default `modelStorage` slice properties.
   - Updated `setProcessingDevice` to accept string or patch object.
4. `plugin/services/storage_service.js`:
   - Added `init()` calling `rescan()`.
   - Added `resetToDefault()`.
5. `plugin/index.js`:
   - Added cached DOM element references in `el`.
   - Added `updateModelStorageUI` in `init()` and AppState subscriptions.
   - Initialized `SpeechifyStorageService.init()`.
   - Attached event listeners to `#changeStorageBtn`, `#resetStorageBtn`.
   - Synchronous/blocking initialization calls in `init()`.
6. `engine/server.py` & `models/storage_manager.py`:
   - Model storage configuration reset support.

---

## 2. Suspected Regressions

1. **Synchronous Boot Block / Uncaught Exceptions**:
   - `init()` in `plugin/index.js` performs multiple `await` and DOM operations before the DOM has completed its first layout paint.
   - If any DOM element is missing or access fails, an uncaught exception in the top-level script prevents CEF from finishing the initial render loop.
2. **CEF GPU Acceleration / Compositing Glitch**:
   - Adobe CEP's CEF engine can suffer from DirectX/OpenGL hardware acceleration texture corruption on Windows (manifesting as black screens with vertical blue/cyan artifact lines) when CSS layout or viewport sizing triggers invalid layer compositing or when an infinite layout cycle occurs.
3. **Double / Cyclic Initialization**:
   - Lack of an idempotent `bootPromise` or guard allows CEP's multiple panel lifecycle hooks (`show`, focus, DOMContentLoaded) to re-trigger initialization concurrently.
4. **Lack of Error Isolation**:
   - All initialization routines were coupled together inside `init()`. A failure in one subsystem halts everything.

---

## 3. Next Steps

1. Create Change Analysis and Known Good Baseline records.
2. Isolate rendering: test static UI boot without background engine, hardware, or model storage calls.
3. Implement strict phased boot state machine (`BOOTING` -> `UI_READY` -> `SERVICES_STARTING` -> `READY`).
4. Ensure error isolation so no subsystem failure can ever black out the panel.
