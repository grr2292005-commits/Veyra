/**
 * Speechify — Core Panel Controller
 * Minimal, fast, and responsive controller connecting Premiere Pro to local neural models.
 */

(function () {
  'use strict';

  // Model Specifications & Verification Metadata
  const MODEL_METADATA = {
    "mp_senet": {
      name: "MP-SENet",
      badge: "Recommended",
      subtitle: "Studio speech restoration",
      metaLine: "Very high quality \u2022 ~8\u00d7 realtime \u2022 GPU",
      rtf: 0.121,
      sizeMb: 9
    },
    "zipenhancer": {
      name: "ZipEnhancer-S",
      badge: null,
      subtitle: "Balanced voice enhancement",
      metaLine: "High quality \u2022 ~7\u00d7 realtime \u2022 GPU",
      rtf: 0.146,
      sizeMb: 8
    },
    "deepfilternet3": {
      name: "DeepFilterNet3",
      badge: "Fast",
      subtitle: "Fast broadband filter",
      metaLine: "Good quality \u2022 ~15\u00d7 realtime \u2022 CPU / GPU",
      rtf: 0.065,
      sizeMb: 8
    },
    "mossformergan": {
      name: "MossFormerGAN-SE",
      badge: null,
      subtitle: "Deep acoustic reconstruction",
      metaLine: "Very high quality \u2022 ~1.6\u00d7 realtime \u2022 Heavy GPU",
      rtf: 0.623,
      sizeMb: 39
    }
  };

  // State
  const state = {
    engineUrl: "http://127.0.0.1:8765",
    engineStatus: "starting", // 'starting' | 'ready' | 'processing' | 'error' | 'off'
    isEngineOnline: false,
    selectedModelId: "mp_senet",
    placementMode: "new_track",
    scope: "selected_clips", // 'selected_clips' | 'in_out' | 'full_sequence'
    selectedDevice: "auto", // 'auto' | 'cuda' | 'cpu'
    isCancelled: false,
    activeSequence: null,
    activeSequenceId: null,
    tracks: [], // [{ id, index, name, type: 'audio', enabled }]
    savedTrackPrefs: {}, // seqId -> { trackId: bool }
    selectedClips: [],
    lastSyncedStateKey: "",
    modelsList: {},
    storagePath: "",
    currentJobId: null,
    jobPollTimer: null,
    hardwareProfile: null,
    jobStartTime: 0
  };

  function isEngineReady() {
    return state.isEngineOnline && (state.engineStatus === 'ready' || state.engineStatus === 'processing');
  }

  // DOM Cache
  const el = {};

  function cacheElements() {
    // Views
    el.mainView = document.getElementById('mainView');
    el.processingView = document.getElementById('processingView');
    el.successView = document.getElementById('successView');

    // Engine Header Status Indicator
    el.engineStatusIndicator = document.getElementById('engineStatusIndicator');
    el.statusStartingText = document.getElementById('statusStartingText');
    el.statusReadyCheck = document.getElementById('statusReadyCheck');
    el.statusErrorWrap = document.getElementById('statusErrorWrap');
    el.retryEngineBtn = document.getElementById('retryEngineBtn');

    // Main View Controls
    el.activeSequenceTitle = document.getElementById('activeSequenceTitle');
    el.sequenceSpecs = document.getElementById('sequenceSpecs');
    el.scopeSelector = document.getElementById('scopeSelector');
    el.selectionSummary = document.getElementById('selectionSummary');
    el.selectionCountText = document.getElementById('selectionCountText');
    el.selectionDurationText = document.getElementById('selectionDurationText');
    el.selectionEmptyState = document.getElementById('selectionEmptyState');
    el.selectionEmptyTitle = document.getElementById('selectionEmptyTitle');
    el.selectionEmptyDesc = document.getElementById('selectionEmptyDesc');
    el.enhanceBtn = document.getElementById('enhanceBtn');

    // Audio Tracks Section & Compact Track Selector Dropdown
    el.audioTracksSection = document.getElementById('audioTracksSection');
    el.trackDropdown = document.getElementById('trackDropdown');
    el.trackDropdownTrigger = document.getElementById('trackDropdownTrigger');
    el.selectedTracksSummary = document.getElementById('selectedTracksSummary');
    el.trackDropdownMenu = document.getElementById('trackDropdownMenu');
    el.trackListContainer = document.getElementById('trackListContainer');
    el.trackDoneBtn = document.getElementById('trackDoneBtn');

    // Model Dropdown
    el.modelDropdown = document.getElementById('modelDropdown');
    el.modelDropdownTrigger = document.getElementById('modelDropdownTrigger');
    el.selectedModelName = document.getElementById('selectedModelName');
    el.selectedModelBadge = document.getElementById('selectedModelBadge');
    el.modelDropdownMenu = document.getElementById('modelDropdownMenu');
    el.modelMetadataLine = document.getElementById('modelMetadataLine');
    el.modelRecommendMeta = document.getElementById('modelRecommendMeta');

    // Output Dropdown
    el.outputDropdown = document.getElementById('outputDropdown');
    el.outputDropdownTrigger = document.getElementById('outputDropdownTrigger');
    el.selectedOutputText = document.getElementById('selectedOutputText');
    el.outputDropdownMenu = document.getElementById('outputDropdownMenu');

    // Processing View Elements
    el.procScopeContext = document.getElementById('procScopeContext');
    el.procTrackDetail = document.getElementById('procTrackDetail');
    el.procModelName = document.getElementById('procModelName');
    el.procClipIndicator = document.getElementById('procClipIndicator');
    el.progressBarFill = document.getElementById('progressBarFill');
    el.progressPctText = document.getElementById('progressPctText');
    el.progressCountdownText = document.getElementById('progressCountdownText');
    el.cancelJobBtn = document.getElementById('cancelJobBtn');

    // Success View Elements
    el.successSummaryText = document.getElementById('successSummaryText');
    el.successPlacementNote = document.getElementById('successPlacementNote');
    el.doneSuccessBtn = document.getElementById('doneSuccessBtn');

    // Settings Modal
    el.openSettingsBtn = document.getElementById('openSettingsBtn');
    el.settingsModal = document.getElementById('settingsModal');
    el.closeSettingsModalBtn = document.getElementById('closeSettingsModalBtn');
    el.doneSettingsModalBtn = document.getElementById('doneSettingsModalBtn');
    el.storageTypeTitle = document.getElementById('storageTypeTitle');
    el.storageSubtext = document.getElementById('storageSubtext');
    el.storageModelsSummary = document.getElementById('storageModelsSummary');
    el.storageBadge = document.getElementById('storageBadge');
    el.storageLocationUnavailable = document.getElementById('storageLocationUnavailable');
    el.changeStorageBtn = document.getElementById('changeStorageBtn');
    el.resetStorageBtn = document.getElementById('resetStorageBtn');
    el.storagePathInput = document.getElementById('storagePathInput');
    el.chooseFolderBtn = document.getElementById('chooseFolderBtn');
    el.saveStoragePathBtn = document.getElementById('saveStoragePathBtn');
    el.openMigrateModalBtn = document.getElementById('openMigrateModalBtn');
    el.storageSaveStatus = document.getElementById('storageSaveStatus');
    el.discoveredModelsNotice = document.getElementById('discoveredModelsNotice');
    el.discoveredModelsText = document.getElementById('discoveredModelsText');
    el.openModelManagerBtn = document.getElementById('openModelManagerBtn');
    el.hardwareInfoText = document.getElementById('hardwareInfoText');
    el.deviceDropdown = document.getElementById('deviceDropdown');
    el.deviceDropdownTrigger = document.getElementById('deviceDropdownTrigger');
    el.selectedDeviceText = document.getElementById('selectedDeviceText');
    el.deviceDropdownMenu = document.getElementById('deviceDropdownMenu');
    el.deviceSelector = document.getElementById('deviceSelector');
    el.toggleAdvancedBtn = document.getElementById('toggleAdvancedBtn');
    el.advancedSection = document.getElementById('advancedSection');
    el.normalizeCheck = document.getElementById('normalizeCheck');

    // Migration Modal
    el.migrateModal = document.getElementById('migrateModal');
    el.closeMigrateModalBtn = document.getElementById('closeMigrateModalBtn');
    el.cancelMigrateBtn = document.getElementById('cancelMigrateBtn');
    el.confirmMigrateBtn = document.getElementById('confirmMigrateBtn');
    el.migrateSourceText = document.getElementById('migrateSourceText');
    el.migrateTargetText = document.getElementById('migrateTargetText');
    el.migrateInfoText = document.getElementById('migrateInfoText');
    el.migrateStatusText = document.getElementById('migrateStatusText');

    // Model Manager Modal
    el.modelManagerModal = document.getElementById('modelManagerModal');
    el.closeModelManagerBtn = document.getElementById('closeModelManagerBtn');
    el.doneModelManagerBtn = document.getElementById('doneModelManagerBtn');
    el.installedModelsList = document.getElementById('installedModelsList');
    el.availableModelsList = document.getElementById('availableModelsList');

    el.toastContainer = document.getElementById('toastContainer');
  }


  // --------------------------------------------------------------------------
  // Helpers: Sanitization & User Error Translation
  // --------------------------------------------------------------------------
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }

  function formatUserErrorMessage(err, fallback = "An unexpected error occurred.") {
    if (!err) return fallback;
    const msg = typeof err === 'string' ? err : (err.message || fallback);
    if (msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('ECONNREFUSED') || msg.includes('connection refused')) {
      return "The speech engine is unreachable. Please verify it is running or click Retry.";
    }
    if (msg.includes('ENOENT') || msg.includes('FileNotFoundError')) {
      return "The specified audio file or model could not be found.";
    }
    if (msg.includes('EACCES') || msg.includes('PermissionError')) {
      return "Access was denied by your system. Please check folder permissions.";
    }
    if (msg.includes("Missing 'source_file'")) {
      return "Speechify couldn't locate source audio for the selected clips.";
    }
    return msg.replace(/^(Error|TypeError|RuntimeError):\s*/i, '');
  }

  // --------------------------------------------------------------------------
  // Synchronous UI Rendering & Phased Boot Entrypoint
  // --------------------------------------------------------------------------
  function renderUI() {
    cacheElements();
    renderModelDropdownMenu();
    const initDevices = (window.SpeechifyHardwareManager ? window.SpeechifyHardwareManager.getAvailableDevices() : [
      { id: 'auto', name: 'Automatic (Recommended)', type: 'auto' },
      { id: 'cpu', name: 'CPU — System Processor', type: 'cpu' }
    ]);
    renderDeviceDropdownMenu(initDevices, state.selectedDevice || 'auto');
    bindEvents();
    updateEngineStatusUI('starting', { message: "Starting…" });
    updateSelectionDisplay();
  }

  async function startBootSequence() {
    // 1. Synchronously mount static UI & bind events immediately
    renderUI();

    // 2. Subscribe to authoritative AppState slices safely (no circular updates)
    if (window.SpeechifyAppState) {
      window.SpeechifyAppState.subscribe('engine', (engineState) => {
        if (engineState) {
          updateEngineStatusUI(engineState.status, {
            message: engineState.error,
            pid: engineState.pid
          });
        }
      });
      window.SpeechifyAppState.subscribe('processingDevice', (devState) => {
        if (devState && devState.availableDevices) {
          renderDeviceDropdownMenu(devState.availableDevices, state.selectedDevice || devState.mode || 'auto');
        }
      });
      window.SpeechifyAppState.subscribe('modelStorage', (storageState) => {
        if (storageState) {
          updateModelStorageUI(storageState);
        }
      });
      if (window.SpeechifyAppState.modelStorage) {
        updateModelStorageUI(window.SpeechifyAppState.modelStorage);
      }
    }

    // Hook into EngineManager status updates
    if (window.SpeechifyEngineManager) {
      window.SpeechifyEngineManager.addStatusListener((status, detail) => {
        updateEngineStatusUI(status, detail);
      });
    }

    // 3. Phased async service initializations via BootController
    if (window.SpeechifyBootController) {
      window.SpeechifyBootController.boot({
        initPremiere: async () => {
          await syncTimeline();
        },
        initStorage: async () => {
          if (window.SpeechifyStorageService) {
            const p = await window.SpeechifyStorageService.init();
            if (p) {
              state.storagePath = p;
              if (el.storagePathInput) el.storagePathInput.value = p;
            }
          }
        },
        initHardware: async () => {
          // Default seeded; full GPU profile populated once engine is up
        },
        initEngine: async () => {
          if (window.SpeechifyEngineManager) {
            const res = await window.SpeechifyEngineManager.ensureEngineRunning();
            if (!res.success) throw new Error(res.error || "Engine startup failed");
            return res;
          } else {
            return await checkEngineHealth();
          }
        },
        initModels: async () => {
          await loadSystemProfile();
          await loadModelsList();
        },
        onEngineReady: () => {
          state.isEngineOnline = true;
          updateEngineStatusUI('ready');
          updateSelectionDisplay();
        },
        onEngineFailed: (err) => {
          state.isEngineOnline = false;
          updateEngineStatusUI('error', {
            message: formatUserErrorMessage(err, "Speech engine couldn't start.")
          });
        },
        onBootComplete: (bootState) => {
          console.log(`[Speechify] Phased boot complete. State: ${bootState}`);
        }
      });
    } else {
      // Fallback if BootController is not present
      initializeEngine().catch(e => console.warn("Engine init fallback error:", e));
      syncTimeline().catch(e => console.warn("Timeline sync fallback error:", e));
    }

    // Start passive auto-polling if not in test environment
    if (!window.__SPEECHIFY_TEST_ENV__) {
      setInterval(autoPollTimeline, 800);
      window.addEventListener('focus', autoPollTimeline);
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden) autoPollTimeline();
      });
      setInterval(checkEngineHealth, 5000);
    }
  }

  function bindEvents() {
    // Retry connection button
    if (el.retryEngineBtn) {
      el.retryEngineBtn.addEventListener('click', onRetryEngine);
    }

    // Scope selection buttons (Exactly 3 scopes: selected_clips, in_out, full_sequence)
    if (el.scopeSelector) {
      el.scopeSelector.querySelectorAll('.sp-segmented-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          el.scopeSelector.querySelectorAll('.sp-segmented-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const chosenScope = (btn.dataset && btn.dataset.scope) || btn.getAttribute('data-scope') || 'selected_clips';
          state.scope = chosenScope;
          if (window.SpeechifyAppState) {
            window.SpeechifyAppState.setPremiere({ scope: chosenScope });
          }
          closeTrackDropdown();
          closeModelDropdown();
          closeOutputDropdown();
          closeDeviceDropdown();
          updateSelectionDisplay();
        });
      });
    }

    // Custom Track Dropdown Events
    if (el.trackDropdownTrigger && el.trackDropdown) {
      el.trackDropdownTrigger.addEventListener('click', (e) => {
        e.stopPropagation();
        closeModelDropdown();
        closeOutputDropdown();
        closeDeviceDropdown();
        const isOpen = el.trackDropdown.classList.toggle('open');
        el.trackDropdownTrigger.setAttribute('aria-expanded', isOpen);
      });
    }

    if (el.trackDoneBtn) {
      el.trackDoneBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        closeTrackDropdown();
      });
    }

    // Custom Model Dropdown Events
    if (el.modelDropdownTrigger && el.modelDropdown) {
      el.modelDropdownTrigger.addEventListener('click', (e) => {
        e.stopPropagation();
        closeTrackDropdown();
        closeOutputDropdown();
        closeDeviceDropdown();
        el.modelDropdown.classList.toggle('open');
        el.modelDropdownTrigger.setAttribute('aria-expanded', el.modelDropdown.classList.contains('open'));
      });
    }

    // Custom Output Dropdown Events
    if (el.outputDropdownTrigger && el.outputDropdown) {
      el.outputDropdownTrigger.addEventListener('click', (e) => {
        e.stopPropagation();
        closeTrackDropdown();
        closeModelDropdown();
        closeDeviceDropdown();
        el.outputDropdown.classList.toggle('open');
      });
    }

    if (el.outputDropdownMenu) {
      el.outputDropdownMenu.querySelectorAll('.sp-dropdown-option').forEach(opt => {
        opt.addEventListener('click', () => {
          el.outputDropdownMenu.querySelectorAll('.sp-dropdown-option').forEach(o => o.classList.remove('selected'));
          opt.classList.add('selected');
          state.placementMode = (opt.dataset && opt.dataset.value) || opt.getAttribute('data-value') || 'new_track';
          const titleEl = opt.querySelector('.sp-dropdown-opt-title');
          if (el.selectedOutputText && titleEl) {
            el.selectedOutputText.textContent = titleEl.textContent;
          }
          closeOutputDropdown();
        });
      });
    }

    // Custom Device Dropdown Events
    if (el.deviceDropdownTrigger) {
      el.deviceDropdownTrigger.addEventListener('click', (e) => {
        e.stopPropagation();
        closeTrackDropdown();
        closeModelDropdown();
        closeOutputDropdown();
        if (el.deviceDropdown) {
          const isOpen = el.deviceDropdown.classList.toggle('open');
          el.deviceDropdownTrigger.setAttribute('aria-expanded', isOpen);
        }
      });
    }

    // Global outside click dismisses dropdowns
    document.addEventListener('click', (e) => {
      if (el.trackDropdown && !el.trackDropdown.contains(e.target)) closeTrackDropdown();
      if (el.modelDropdown && !el.modelDropdown.contains(e.target)) closeModelDropdown();
      if (el.outputDropdown && !el.outputDropdown.contains(e.target)) closeOutputDropdown();
      if (el.deviceDropdown && !el.deviceDropdown.contains(e.target)) closeDeviceDropdown();
    });

    // Global escape key dismisses dropdowns
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeTrackDropdown();
        closeModelDropdown();
        closeOutputDropdown();
        closeDeviceDropdown();
      }
    });

    // Primary Enhance Button
    if (el.enhanceBtn) el.enhanceBtn.addEventListener('click', onStartEnhance);

    // Cancel Active Job
    if (el.cancelJobBtn) el.cancelJobBtn.addEventListener('click', onCancelJob);

    // Done Success Button
    if (el.doneSuccessBtn) {
      el.doneSuccessBtn.addEventListener('click', () => {
        switchView('main');
        syncTimeline();
      });
    }

    // Settings Modal
    if (el.openSettingsBtn) el.openSettingsBtn.addEventListener('click', openSettingsModal);
    if (el.closeSettingsModalBtn) el.closeSettingsModalBtn.addEventListener('click', closeSettingsModal);
    if (el.doneSettingsModalBtn) el.doneSettingsModalBtn.addEventListener('click', closeSettingsModal);
    if (el.changeStorageBtn) el.changeStorageBtn.addEventListener('click', onChooseFolder);
    if (el.resetStorageBtn) el.resetStorageBtn.addEventListener('click', onResetStorage);
    if (el.chooseFolderBtn) el.chooseFolderBtn.addEventListener('click', onChooseFolder);
    if (el.saveStoragePathBtn) el.saveStoragePathBtn.addEventListener('click', () => onSaveStoragePath());
    if (el.openMigrateModalBtn) el.openMigrateModalBtn.addEventListener('click', openMigrateModal);

    if (el.toggleAdvancedBtn && el.advancedSection) {
      el.toggleAdvancedBtn.addEventListener('click', () => {
        const isHidden = el.advancedSection.style.display === 'none';
        el.advancedSection.style.display = isHidden ? 'flex' : 'none';
        const span = el.toggleAdvancedBtn.querySelector('span');
        if (span) span.innerHTML = isHidden ? 'Advanced settings &#9652;' : 'Advanced settings &#9662;';
      });
    }

    // Fallback native device selector if present
    if (el.deviceSelector) {
      el.deviceSelector.addEventListener('change', (e) => {
        selectDevice(e.target.value);
      });
    }

    // Migration Modal
    if (el.closeMigrateModalBtn) el.closeMigrateModalBtn.addEventListener('click', closeMigrateModal);
    if (el.cancelMigrateBtn) el.cancelMigrateBtn.addEventListener('click', closeMigrateModal);
    if (el.confirmMigrateBtn) el.confirmMigrateBtn.addEventListener('click', onConfirmMigrate);

    // Model Manager Modal
    // Note: Do NOT close settings modal when opening Model Manager.
    // Manage Models sits directly on top of Settings (z-index: 250).
    // Closing Manage Models seamlessly returns user to Settings.
    if (el.openModelManagerBtn) {
      el.openModelManagerBtn.addEventListener('click', () => {
        openModelManagerModal();
      });
    }
    if (el.closeModelManagerBtn) el.closeModelManagerBtn.addEventListener('click', closeModelManagerModal);
    if (el.doneModelManagerBtn) el.doneModelManagerBtn.addEventListener('click', closeModelManagerModal);

    // Hierarchical ESC key handler: Model Manager -> Settings -> Dropdowns
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' || e.key === 'Esc') {
        if (el.migrateModal && el.migrateModal.classList.contains('open')) {
          closeMigrateModal();
        } else if (el.modelManagerModal && el.modelManagerModal.classList.contains('open')) {
          closeModelManagerModal();
        } else if (el.settingsModal && el.settingsModal.classList.contains('open')) {
          closeSettingsModal();
        } else {
          closeModelDropdown();
          closeOutputDropdown();
          closeDeviceDropdown();
        }
      }
    });

    // Clean engine lifecycle teardown on panel close or window reload
    window.addEventListener('beforeunload', () => {
      if (window.SpeechifyEngineManager) {
        window.SpeechifyEngineManager.stop();
      }
    });
    window.addEventListener('unload', () => {
      if (window.SpeechifyEngineManager) {
        window.SpeechifyEngineManager.stop();
      }
    });
  }

  function closeModelDropdown() {
    if (el.modelDropdown) {
      el.modelDropdown.classList.remove('open');
    }
    if (el.modelDropdownTrigger) {
      el.modelDropdownTrigger.setAttribute('aria-expanded', 'false');
    }
  }

  function closeOutputDropdown() {
    if (el.outputDropdown) {
      el.outputDropdown.classList.remove('open');
    }
    if (el.outputDropdownTrigger) {
      el.outputDropdownTrigger.setAttribute('aria-expanded', 'false');
    }
  }

  function closeDeviceDropdown() {
    if (el.deviceDropdown) {
      el.deviceDropdown.classList.remove('open');
    }
    if (el.deviceDropdownTrigger) {
      el.deviceDropdownTrigger.setAttribute('aria-expanded', 'false');
    }
  }

  function closeTrackDropdown() {
    if (el.trackDropdown) {
      el.trackDropdown.classList.remove('open');
    }
    if (el.trackDropdownTrigger) {
      el.trackDropdownTrigger.setAttribute('aria-expanded', 'false');
    }
  }

  function updateTrackSummary() {
    const total = state.tracks.length;
    const selected = state.tracks.filter(t => t.enabled).length;
    let summary = "Select audio tracks";
    if (selected === 0) {
      summary = "Select audio tracks";
    } else if (total > 0 && selected === total) {
      summary = "All audio tracks";
    } else if (selected === 1) {
      summary = "1 track selected";
    } else {
      summary = `${selected} tracks selected`;
    }

    if (el.selectedTracksSummary) {
      el.selectedTracksSummary.textContent = summary;
    }
    return summary;
  }

  function updateTracksForSequence(seq) {
    if (!seq || !seq.available) {
      state.tracks = [];
      renderTrackList();
      return;
    }
    const audioTrackCount = seq.audioTrackCount || (seq.audioTracks ? seq.audioTracks.length : 4);
    const existingPrefs = state.savedTrackPrefs && state.activeSequenceId ? state.savedTrackPrefs[state.activeSequenceId] : null;

    const newTracks = [];
    for (let i = 0; i < audioTrackCount; i++) {
      const trackObj = (seq.audioTracks && seq.audioTracks[i]) || {};
      const customName = trackObj.name && String(trackObj.name).trim();
      const defaultName = customName || (i === 0 ? "Dialogue" : (i === 1 ? "Music" : (i === 2 ? "Commentary" : (i === 3 ? "SFX" : `Audio ${i + 1}`))));
      // Stable track identity by index prevents rename from losing selection
      const trackId = `audio_track_${i}`;
      const isEnabled = existingPrefs ? (existingPrefs[trackId] !== undefined ? !!existingPrefs[trackId] : false) : (i === 0);
      const displayLabel = customName ? `A${i + 1} \u2022 ${customName}` : (trackObj.name ? `A${i + 1} \u2022 ${trackObj.name}` : `A${i + 1} \u2022 Audio ${i + 1}`);

      newTracks.push({
        id: trackId,
        index: i,
        name: customName || defaultName,
        display_label: displayLabel,
        type: 'audio',
        enabled: isEnabled
      });
    }
    state.tracks = newTracks;
    renderTrackList();

    if (window.SpeechifyAppState) {
      const enabledIds = state.tracks.filter(t => t.enabled).map(t => t.id);
      window.SpeechifyAppState.setSelectedTrackIds(enabledIds);
    }
  }

  function renderTrackList() {
    if (!el.trackListContainer) return;
    el.trackListContainer.innerHTML = '';
    updateTrackSummary();

    if (state.tracks.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.className = 'sp-dropdown-opt-desc';
      emptyDiv.style.padding = '8px 10px';
      emptyDiv.textContent = 'No audio tracks found in sequence.';
      el.trackListContainer.appendChild(emptyDiv);
      return;
    }

    state.tracks.forEach(track => {
      const item = document.createElement('div');
      item.className = `sp-track-item ${track.enabled ? 'selected' : ''}`;
      item.setAttribute('data-track-id', track.id);

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'sp-track-checkbox';
      checkbox.checked = track.enabled;

      const label = document.createElement('span');
      label.className = 'sp-track-label';
      label.textContent = track.display_label || `A${track.index + 1} \u2022 ${track.name}`;

      const toggle = (e) => {
        if (e.target !== checkbox) {
          checkbox.checked = !checkbox.checked;
        }
        track.enabled = checkbox.checked;
        item.classList.toggle('selected', track.enabled);
        updateTrackSummary();

        if (state.activeSequenceId) {
          if (!state.savedTrackPrefs) state.savedTrackPrefs = {};
          if (!state.savedTrackPrefs[state.activeSequenceId]) state.savedTrackPrefs[state.activeSequenceId] = {};
          state.savedTrackPrefs[state.activeSequenceId][track.id] = track.enabled;
        }

        if (window.SpeechifyAppState) {
          const enabledIds = state.tracks.filter(t => t.enabled).map(t => t.id);
          window.SpeechifyAppState.setSelectedTrackIds(enabledIds);
        }

        updateSelectionDisplay();
      };

      item.addEventListener('click', toggle);
      item.appendChild(checkbox);
      item.appendChild(label);
      el.trackListContainer.appendChild(item);
    });
  }

  // --------------------------------------------------------------------------
  // Model Selector & Metadata
  // --------------------------------------------------------------------------
  function renderModelDropdownMenu() {
    if (!el.modelDropdownMenu) return;
    el.modelDropdownMenu.innerHTML = '';

    Object.keys(MODEL_METADATA).forEach(modelId => {
      const meta = MODEL_METADATA[modelId];
      const modelInfo = state.modelsList[modelId] || {};
      const actualSizeMb = modelInfo.size_bytes ? Math.round(modelInfo.size_bytes / (1024 * 1024)) : meta.sizeMb;

      const opt = document.createElement('div');
      opt.className = `sp-dropdown-option ${modelId === state.selectedModelId ? 'selected' : ''}`;
      opt.setAttribute('data-model-id', modelId);
      if (opt.dataset) opt.dataset.modelId = modelId;

      opt.innerHTML = `
        <div class="sp-dropdown-opt-header">
          <span class="sp-dropdown-opt-title">${meta.name}</span>
          ${meta.badge ? `<span class="sp-dropdown-opt-badge">${meta.badge}</span>` : ''}
        </div>
        <span class="sp-dropdown-opt-desc">${meta.subtitle}</span>
        <span class="sp-dropdown-opt-meta">${meta.metaLine} &bull; ~${actualSizeMb} MB</span>
      `;

      opt.addEventListener('click', () => {
        selectModel(modelId);
        closeModelDropdown();
      });

      el.modelDropdownMenu.appendChild(opt);
    });

    updateModelDisplay();
  }

  function selectModel(modelId) {
    state.selectedModelId = modelId;

    if (el.modelDropdownMenu) {
      el.modelDropdownMenu.querySelectorAll('.sp-dropdown-option').forEach(opt => {
        const optModelId = (opt.dataset && opt.dataset.modelId) || opt.getAttribute('data-model-id');
        if (optModelId === modelId) {
          opt.classList.add('selected');
        } else {
          opt.classList.remove('selected');
        }
      });
    }

    updateModelDisplay();
  }

  function updateModelDisplay() {
    const meta = MODEL_METADATA[state.selectedModelId];
    if (!meta) return;

    if (el.selectedModelName) el.selectedModelName.textContent = meta.name;
    if (el.selectedModelBadge) {
      if (meta.badge) {
        el.selectedModelBadge.textContent = meta.badge;
        el.selectedModelBadge.style.display = 'inline-block';
      } else {
        el.selectedModelBadge.style.display = 'none';
      }
    }

    if (el.modelMetadataLine) el.modelMetadataLine.textContent = meta.metaLine;
  }

  // --------------------------------------------------------------------------
  // Passive Premiere Pro Timeline Synchronization
  // --------------------------------------------------------------------------
  async function autoPollTimeline() {
    // Only poll when on the main view and not actively enhancing
    if (!el.mainView.classList.contains('active')) return;
    await syncTimeline();
  }

  async function syncTimeline() {
    try {
      const seq = await window.VoxForgeDOMBridge.getActiveSequenceInfo();
      const clips = await window.VoxForgeDOMBridge.getSelectedAudioClips();

      // Form unique state signature to avoid redundant DOM touching
      const stateKey = `${seq ? (seq.id || seq.sequenceID || seq.name) : 'none'}_${seq ? seq.durationSec : 0}_${seq ? seq.inPointSec : 0}_${seq ? seq.outPointSec : 0}_${clips.length}_${clips.map(c => (c.clipId || c.name) + ':' + (c.mediaPath || '') + ':' + (c.startTimeSec || 0) + ':' + (c.durationSec || 0)).join(';')}`;
      if (stateKey === state.lastSyncedStateKey) {
        return; // State unchanged, keep DOM calm
      }
      state.lastSyncedStateKey = stateKey;

      state.activeSequence = seq;
      state.selectedClips = clips;

      const seqId = seq ? (seq.id || seq.sequenceID || seq.name) : null;
      const trackCount = seq ? (seq.audioTrackCount || (seq.audioTracks ? seq.audioTracks.length : 0)) : 0;
      if (seqId !== state.activeSequenceId || (trackCount > 0 && state.tracks.length !== trackCount)) {
        state.activeSequenceId = seqId;
        updateTracksForSequence(seq);
      }

      if (!seq || !seq.available) {
        el.activeSequenceTitle.textContent = "No sequence open";
        el.sequenceSpecs.textContent = "Open a sequence in Premiere Pro";
        el.selectionSummary.style.display = 'none';
        el.selectionEmptyState.style.display = 'flex';
        if (el.enhanceBtn) el.enhanceBtn.disabled = true;
        return;
      }

      el.activeSequenceTitle.textContent = seq.name;
      el.sequenceSpecs.textContent = `${(seq.sampleRate / 1000).toFixed(0)} kHz \u2022 ${seq.fps} fps`;

      updateSelectionDisplay();
    } catch (err) {
      console.warn("Auto-sync error:", err);
    }
  }

  function updateSelectionDisplay() {
    const ready = isEngineReady();

    if (!state.activeSequence || !state.activeSequence.available) {
      if (el.enhanceBtn) el.enhanceBtn.disabled = true;
      if (el.audioTracksSection) el.audioTracksSection.style.display = 'none';
      return;
    }

    let hasSelection = false;

    if (state.scope === "selected_clips") {
      // 1. Selected Clips: NO track selector, independent of any track preferences
      if (el.audioTracksSection) el.audioTracksSection.style.display = 'none';
      closeTrackDropdown();

      const count = state.selectedClips.length;
      if (count > 0) {
        const totalDur = state.selectedClips.reduce((acc, c) => acc + (c.durationSec || 0), 0);
        el.selectionCountText.textContent = `${count} audio clip${count > 1 ? 's' : ''}`;
        el.selectionDurationText.textContent = formatDuration(totalDur);
        el.selectionSummary.style.display = 'flex';
        el.selectionEmptyState.style.display = 'none';
        hasSelection = true;
      } else {
        el.selectionSummary.style.display = 'none';
        el.selectionEmptyState.style.display = 'flex';
        if (el.selectionEmptyTitle) el.selectionEmptyTitle.textContent = "No audio clips selected";
        if (el.selectionEmptyDesc) el.selectionEmptyDesc.textContent = "Select an audio clip in the timeline.";
        hasSelection = false;
      }

    } else if (state.scope === "in_out") {
      // 2. In / Out: Compact track selector shown; requires valid range AND at least 1 track
      if (el.audioTracksSection) el.audioTracksSection.style.display = 'block';

      const inSec = state.activeSequence.inPointSec || 0;
      const outSec = state.activeSequence.outPointSec || 0;
      const dur = Math.max(0, outSec - inSec);
      const selectedTracks = state.tracks.filter(t => t.enabled);

      if (dur <= 0) {
        el.selectionSummary.style.display = 'none';
        el.selectionEmptyState.style.display = 'flex';
        if (el.selectionEmptyTitle) el.selectionEmptyTitle.textContent = "No In/Out range set";
        if (el.selectionEmptyDesc) el.selectionEmptyDesc.textContent = "Set an In/Out range.";
        hasSelection = false;
      } else if (selectedTracks.length === 0) {
        el.selectionSummary.style.display = 'none';
        el.selectionEmptyState.style.display = 'flex';
        if (el.selectionEmptyTitle) el.selectionEmptyTitle.textContent = "No audio tracks selected";
        if (el.selectionEmptyDesc) el.selectionEmptyDesc.textContent = "Select at least one audio track.";
        hasSelection = false;
      } else {
        const fps = state.activeSequence.fps || 29.97;
        const inTc = state.activeSequence.inPointTimecode || (window.TimeUtils ? window.TimeUtils.formatTimecode(inSec, fps) : formatDuration(inSec));
        const outTc = state.activeSequence.outPointTimecode || (window.TimeUtils ? window.TimeUtils.formatTimecode(outSec, fps) : formatDuration(outSec));
        el.selectionCountText.textContent = `${inTc} \u2192 ${outTc}`;
        el.selectionDurationText.textContent = formatDuration(dur);
        el.selectionSummary.style.display = 'flex';
        el.selectionEmptyState.style.display = 'none';
        hasSelection = true;
      }

    } else {
      // 3. Full Sequence: Compact track selector shown; requires at least 1 track
      if (el.audioTracksSection) el.audioTracksSection.style.display = 'block';

      const dur = state.activeSequence.durationSec || 0;
      const selectedTracks = state.tracks.filter(t => t.enabled);

      if (selectedTracks.length === 0) {
        el.selectionSummary.style.display = 'none';
        el.selectionEmptyState.style.display = 'flex';
        if (el.selectionEmptyTitle) el.selectionEmptyTitle.textContent = "No audio tracks selected";
        if (el.selectionEmptyDesc) el.selectionEmptyDesc.textContent = "Select at least one audio track.";
        hasSelection = false;
      } else if (dur <= 0) {
        el.selectionSummary.style.display = 'none';
        el.selectionEmptyState.style.display = 'flex';
        if (el.selectionEmptyTitle) el.selectionEmptyTitle.textContent = "Sequence is empty";
        if (el.selectionEmptyDesc) el.selectionEmptyDesc.textContent = "The active sequence contains no media.";
        hasSelection = false;
      } else {
        el.selectionCountText.textContent = "Full sequence";
        el.selectionDurationText.textContent = formatDuration(dur);
        el.selectionSummary.style.display = 'flex';
        el.selectionEmptyState.style.display = 'none';
        hasSelection = true;
      }
    }

    if (el.enhanceBtn) {
      el.enhanceBtn.disabled = !(ready && hasSelection);
    }
  }

  /**
   * Clean duration formatter (e.g. "26.5 s" or "02:14")
   */
  function formatDuration(sec) {
    if (window.TimeUtils && typeof window.TimeUtils.formatDuration === 'function') {
      return window.TimeUtils.formatDuration(sec);
    }
    if (isNaN(sec) || sec <= 0) return "0.0 s";
    // Check for corrupt/astronomical numbers
    if (sec > 864000) return "0.0 s";

    if (sec < 60) {
      return `${sec.toFixed(1)} s`;
    }

    const totalSecs = Math.floor(sec);
    const m = Math.floor(totalSecs / 60);
    const s = totalSecs % 60;
    const pad = (n) => String(n).padStart(2, '0');

    if (m >= 60) {
      const h = Math.floor(m / 60);
      const remM = m % 60;
      return `${pad(h)}:${pad(remM)}:${pad(s)}`;
    }

    return `${pad(m)}:${pad(s)}`;
  }

  // --------------------------------------------------------------------------
  // Silent Hardware Inspection & Custom Device Selector
  // --------------------------------------------------------------------------
  async function loadSystemProfile() {
    if (el.hardwareInfoText) {
      el.hardwareInfoText.textContent = "Detecting hardware…";
    }

    try {
      let devices = [];
      let profile = null;

      if (window.SpeechifyHardwareManager) {
        devices = await window.SpeechifyHardwareManager.detect(state.engineUrl);
        profile = window.SpeechifyHardwareManager.getProfile();
      } else {
        const resp = await fetch(`${state.engineUrl}/api/system`);
        if (resp.ok) {
          profile = await resp.json();
          devices = profile.available_devices || [];
        }
      }

      state.hardwareProfile = profile;
      console.log("[Speechify] System profile loaded:", profile);

      // Restore saved device preference from localStorage if previously set
      let savedPref = "auto";
      try {
        savedPref = localStorage.getItem('speechify_device_preference') || "auto";
      } catch (err) {}

      const hasPref = devices.some(d => d.id === savedPref || (savedPref.startsWith('cuda') && d.id.startsWith('cuda')));
      const chosenDevice = hasPref ? savedPref : (profile && profile.recommendedDevice ? profile.recommendedDevice : "auto");
      state.selectedDevice = chosenDevice;

      // Render custom device dropdown
      renderDeviceDropdownMenu(devices, chosenDevice);

      // Populate fallback native select if present
      if (el.deviceSelector) {
        el.deviceSelector.innerHTML = '';
        devices.forEach(d => {
          const opt = document.createElement('option');
          opt.value = d.id;
          opt.textContent = d.name || d.label;
          el.deviceSelector.appendChild(opt);
        });
        el.deviceSelector.value = chosenDevice;
      }

      // Update hardware text
      const gpuObj = profile ? (profile.gpu || (profile.gpus && profile.gpus[0])) : null;
      if (gpuObj && (gpuObj.available || gpuObj.cuda || gpuObj.cuda_available)) {
        const vram = Math.round(gpuObj.total_vram_gb || gpuObj.vramGB || 6);
        const name = gpuObj.name || gpuObj.device_name || "NVIDIA GPU";
        if (el.hardwareInfoText) {
          el.hardwareInfoText.textContent = `${name} \u2022 ${vram} GB VRAM`;
        }
        if (el.modelRecommendMeta) {
          el.modelRecommendMeta.textContent = `Recommended for ${name}`;
        }
      } else if (profile && profile.cpu) {
        if (el.hardwareInfoText) {
          el.hardwareInfoText.textContent = profile.cpu.name ? `${profile.cpu.name}` : "CPU processing mode";
        }
        if (el.modelRecommendMeta) {
          el.modelRecommendMeta.textContent = "";
        }
      }

      if (profile && profile.recommended_model && MODEL_METADATA[profile.recommended_model]) {
        selectModel(profile.recommended_model);
      }
    } catch (e) {
      console.warn("[Speechify] Hardware detection failed:", e);
      if (el.hardwareInfoText) {
        el.hardwareInfoText.textContent = "Hardware information unavailable";
      }
      const fallback = (window.SpeechifyHardwareManager ? window.SpeechifyHardwareManager.getAvailableDevices() : []);
      renderDeviceDropdownMenu(fallback, state.selectedDevice || 'auto');
    }
  }

  function renderDeviceDropdownMenu(availableDevices, selectedDeviceId) {
    if (!el.deviceDropdownMenu) return;
    el.deviceDropdownMenu.innerHTML = '';

    const devices = (availableDevices && availableDevices.length > 0)
      ? availableDevices
      : [
          { id: 'auto', name: 'Automatic (Recommended)', type: 'auto' },
          { id: 'cpu', name: 'CPU — System Processor', type: 'cpu' }
        ];

    const currentSelectedId = selectedDeviceId || state.selectedDevice || 'auto';

    devices.forEach(dev => {
      const opt = document.createElement('div');
      const isSelected = (dev.id === currentSelectedId) || (currentSelectedId === 'cuda' && dev.id.startsWith('cuda'));
      opt.className = `sp-dropdown-option ${isSelected ? 'selected' : ''}`;
      opt.setAttribute('data-device-id', dev.id);
      if (opt.dataset) opt.dataset.deviceId = dev.id;
      opt.setAttribute('role', 'option');
      opt.setAttribute('aria-selected', isSelected ? 'true' : 'false');

      const isGpu = dev.type === 'cuda' || (dev.id && dev.id.startsWith('cuda'));
      const badgeHtml = dev.id === 'auto' ? '<span class="sp-dropdown-opt-badge">Recommended</span>' : '';
      const descHtml = isGpu
        ? `${dev.vram_gb ? dev.vram_gb + ' GB VRAM \u2022 ' : ''}Accelerated neural processing`
        : (dev.id === 'auto' ? 'Chooses the fastest available hardware' : 'System CPU fallback');

      opt.innerHTML = `
        <div class="sp-dropdown-opt-header">
          <span class="sp-dropdown-opt-title">${escapeHtml(dev.name || dev.label)}</span>
          ${badgeHtml}
        </div>
        <span class="sp-dropdown-opt-desc">${descHtml}</span>
      `;

      opt.addEventListener('click', () => {
        selectDevice(dev.id, dev.name || dev.label);
        closeDeviceDropdown();
      });

      el.deviceDropdownMenu.appendChild(opt);
    });

    updateSelectedDeviceDisplay(devices, currentSelectedId);
  }

  function selectDevice(deviceId, deviceName) {
    state.selectedDevice = deviceId;
    try {
      localStorage.setItem('speechify_device_preference', deviceId);
    } catch (e) {}

    if (window.SpeechifyHardwareManager) {
      window.SpeechifyHardwareManager.setSelectedDevice(deviceId);
    } else if (window.SpeechifyAppState) {
      window.SpeechifyAppState.setProcessingDevice(deviceId);
    }

    if (el.deviceDropdownMenu) {
      el.deviceDropdownMenu.querySelectorAll('.sp-dropdown-option').forEach(opt => {
        const optDeviceId = (opt.dataset && opt.dataset.deviceId) || opt.getAttribute('data-device-id');
        const isMatch = (optDeviceId === deviceId) || (deviceId === 'cuda' && optDeviceId && optDeviceId.startsWith('cuda'));
        opt.classList.toggle('selected', isMatch);
        opt.setAttribute('aria-selected', isMatch ? 'true' : 'false');
      });
    }

    if (el.selectedDeviceText) {
      if (deviceName) {
        el.selectedDeviceText.textContent = deviceName;
      } else {
        const match = el.deviceDropdownMenu ? el.deviceDropdownMenu.querySelector(`[data-device-id="${deviceId}"] .sp-dropdown-opt-title`) : null;
        if (match) {
          el.selectedDeviceText.textContent = match.textContent;
        } else {
          el.selectedDeviceText.textContent = deviceId === 'auto' ? 'Automatic (Recommended)' : deviceId;
        }
      }
    }

    if (el.deviceSelector && el.deviceSelector.value !== deviceId) {
      el.deviceSelector.value = deviceId;
    }
  }

  function updateSelectedDeviceDisplay(devices, selectedId) {
    if (!el.selectedDeviceText) return;
    let match = devices.find(d => d.id === selectedId);
    if (!match && (selectedId === 'cuda' || (selectedId && selectedId.startsWith('cuda')))) {
      match = devices.find(d => d.type === 'cuda' || d.id.startsWith('cuda'));
    }
    if (match) {
      el.selectedDeviceText.textContent = match.name || match.label;
    } else if (selectedId === 'auto') {
      el.selectedDeviceText.textContent = 'Automatic (Recommended)';
    } else {
      el.selectedDeviceText.textContent = selectedId;
    }
  }

  // --------------------------------------------------------------------------
  // Engine Lifecycle & Health Monitoring
  // --------------------------------------------------------------------------
  async function initializeEngine() {
    updateEngineStatusUI('starting', { message: "Starting…" });

    if (window.SpeechifyEngineManager) {
      const res = await window.SpeechifyEngineManager.ensureEngineRunning();
      if (res.success) {
        state.isEngineOnline = true;
        updateEngineStatusUI('ready');
        await loadSystemProfile();
        await loadModelsList();
      } else {
        state.isEngineOnline = false;
        updateEngineStatusUI('error', {
          message: "Speech engine couldn't start."
        });
      }
    } else {
      await checkEngineHealth();
    }
  }

  function updateModelStorageUI(storageState) {
    if (!storageState) return;
    const isManaged = storageState.isManaged !== false;
    const storagePath = storageState.storage_directory || storageState.path || storageState.rawPath || "";
    const pathExists = storageState.exists !== false;

    if (el.storageTypeTitle) {
      el.storageTypeTitle.textContent = isManaged ? "Veyra managed storage" : "Custom location";
    }
    if (el.storageBadge) {
      el.storageBadge.textContent = isManaged ? "Managed" : "Custom";
      el.storageBadge.style.background = isManaged ? "rgba(99, 102, 241, 0.12)" : "rgba(251, 191, 36, 0.12)";
      el.storageBadge.style.color = isManaged ? "var(--sp-accent-primary-hover)" : "#f59e0b";
    }
    if (el.storageSubtext) {
      el.storageSubtext.textContent = storagePath || "Unknown";
      el.storageSubtext.title = storagePath || "";
    }
    if (el.storageLocationUnavailable) {
      el.storageLocationUnavailable.style.display = (!pathExists && storagePath) ? "block" : "none";
    }
    if (el.storageModelsSummary) {
      const count = storageState.modelsCount !== undefined
        ? storageState.modelsCount
        : Object.values(state.modelsList || {}).filter(m => m.installed).length;
      el.storageModelsSummary.textContent = count > 0
        ? `${count} model${count === 1 ? '' : 's'} installed`
        : "No models installed yet";
    }
    if (el.resetStorageBtn) {
      el.resetStorageBtn.style.display = isManaged ? "none" : "inline-flex";
    }
    if (el.storagePathInput && document.activeElement !== el.storagePathInput) {
      el.storagePathInput.value = storagePath;
    }
    state.storagePath = storagePath;
  }

  function updateEngineStatusUI(status, detail = {}) {
    if (status === 'ready') {
      state.engineStatus = 'ready';
      state.isEngineOnline = true;

      if (el.engineStatusIndicator) {
        el.engineStatusIndicator.className = 'sp-engine-status ready';
      }
      if (el.statusStartingText) el.statusStartingText.style.display = 'none';
      if (el.statusErrorWrap) el.statusErrorWrap.style.display = 'none';
      if (el.statusReadyCheck) el.statusReadyCheck.style.display = 'inline-flex';

      // Re-evaluate enhance button
      updateSelectionDisplay();
      return;
    }

    if (status === 'processing') {
      state.engineStatus = 'processing';
      if (el.engineStatusIndicator) {
        el.engineStatusIndicator.className = 'sp-engine-status processing';
      }
      if (el.statusStartingText) el.statusStartingText.style.display = 'none';
      if (el.statusErrorWrap) el.statusErrorWrap.style.display = 'none';
      if (el.statusReadyCheck) el.statusReadyCheck.style.display = 'inline-flex';
      return;
    }

    if (status === 'starting' || status === 'restarting') {
      state.engineStatus = 'starting';
      state.isEngineOnline = false;

      if (el.engineStatusIndicator) {
        el.engineStatusIndicator.className = 'sp-engine-status starting';
      }
      if (el.statusStartingText) {
        el.statusStartingText.style.display = 'inline';
        el.statusStartingText.textContent = (detail && detail.message) || "Starting…";
      }
      if (el.statusReadyCheck) el.statusReadyCheck.style.display = 'none';
      if (el.statusErrorWrap) el.statusErrorWrap.style.display = 'none';

      // Enhance button must remain strictly disabled while starting
      updateSelectionDisplay();
      return;
    }

    if (status === 'error') {
      state.engineStatus = 'error';
      state.isEngineOnline = false;

      if (el.engineStatusIndicator) {
        el.engineStatusIndicator.className = 'sp-engine-status error';
      }
      if (el.statusStartingText) el.statusStartingText.style.display = 'none';
      if (el.statusReadyCheck) el.statusReadyCheck.style.display = 'none';
      if (el.statusErrorWrap) el.statusErrorWrap.style.display = 'inline-flex';

      updateSelectionDisplay();
      return;
    }

    if (status === 'stopped' || status === 'off') {
      state.engineStatus = 'off';
      state.isEngineOnline = false;

      if (el.engineStatusIndicator) {
        el.engineStatusIndicator.className = 'sp-engine-status off';
      }
      if (el.statusStartingText) el.statusStartingText.style.display = 'none';
      if (el.statusReadyCheck) el.statusReadyCheck.style.display = 'none';
      if (el.statusErrorWrap) el.statusErrorWrap.style.display = 'inline-flex';

      updateSelectionDisplay();
    }
  }

  async function onRetryEngine() {
    updateEngineStatusUI('starting', { message: "Starting…" });
    if (window.SpeechifyBootController) {
      window.SpeechifyBootController.reset();
    }
    if (window.SpeechifyEngineManager) {
      const res = await window.SpeechifyEngineManager.restartEngine();
      if (res.success) {
        state.isEngineOnline = true;
        updateEngineStatusUI('ready');
        await loadSystemProfile();
        await loadModelsList();
      } else {
        updateEngineStatusUI('error', { message: "Speech engine couldn't be restarted." });
      }
    } else {
      await checkEngineHealth();
    }
  }

  async function checkEngineHealth() {
    const controller = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), 1500) : null;

    try {
      const fetchOpts = controller ? { signal: controller.signal, method: 'GET' } : { method: 'GET' };
      const resp = await fetch(`${state.engineUrl}/health`, fetchOpts);
      if (timer) clearTimeout(timer);

      if (resp.ok) {
        const data = await resp.json();
        if (data && (data.status === 'ready' || data.status === 'healthy')) {
          if (!state.isEngineOnline) {
            state.isEngineOnline = true;
            updateEngineStatusUI('ready');
            await loadSystemProfile();
            await loadModelsList();
          }
          return;
        }
      }
      throw new Error('Non-ready response');
    } catch (e) {
      if (timer) clearTimeout(timer);
      if (state.isEngineOnline) {
        state.isEngineOnline = false;
        if (window.SpeechifyEngineManager) {
          window.SpeechifyEngineManager._handleUnexpectedExit();
        } else {
          updateEngineStatusUI('error', { message: "The speech engine stopped unexpectedly." });
        }
      }
    }
  }

  async function loadModelsList() {
    const controller = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), 3000) : null;

    try {
      const fetchOpts = controller ? { signal: controller.signal } : {};
      const resp = await fetch(`${state.engineUrl}/api/models`, fetchOpts);
      if (timer) clearTimeout(timer);
      if (!resp.ok) return;
      const data = await resp.json();
      state.modelsList = data.models || {};
      state.storagePath = data.storage_directory || "";
      if (el.storagePathInput) el.storagePathInput.value = state.storagePath;

      if (window.SpeechifyAppState) {
        window.SpeechifyAppState.setModels(state.modelsList);
        window.SpeechifyAppState.setModelStorage({
          path: state.storagePath,
          rawPath: state.storagePath,
          isManaged: data.is_managed !== false,
          displayTitle: data.display_title || (data.is_managed !== false ? "Speechify managed storage" : "Custom storage folder"),
          displaySubtext: data.display_subtext || (data.is_managed !== false ? "Models are stored locally on this computer." : state.storagePath),
          modelsCount: data.models_count !== undefined ? data.models_count : Object.values(state.modelsList).filter(m => m.installed).length
        });
      }

      // Update discovered models notice in Settings
      const installedModels = Object.values(state.modelsList).filter(m => m.installed);
      if (el.discoveredModelsNotice && el.discoveredModelsText) {
        if (installedModels.length > 0) {
          el.discoveredModelsText.textContent = `${installedModels.length} compatible model${installedModels.length > 1 ? 's' : ''} discovered and verified locally.`;
          el.discoveredModelsNotice.style.display = 'block';
          el.discoveredModelsNotice.style.borderLeftColor = 'var(--sp-accent-primary)';
        } else {
          el.discoveredModelsText.textContent = "No installed models found in this folder.";
          el.discoveredModelsNotice.style.display = 'block';
          el.discoveredModelsNotice.style.borderLeftColor = 'var(--sp-accent-warning)';
        }
      }

      renderModelDropdownMenu();
      renderModelManagerLists();
    } catch (err) {
      if (timer) clearTimeout(timer);
      console.warn("Failed to load models list:", err);
    }
  }


  // --------------------------------------------------------------------------
  // Audio Enhancement Execution Flow (Multi-Clip Queue Architecture)
  // --------------------------------------------------------------------------
  async function onStartEnhance() {
    if (!isEngineReady()) {
      if (state.engineStatus === 'off' || state.engineStatus === 'error') {
        if (window.SpeechifyEngineManager) {
          window.SpeechifyEngineManager.restartEngine();
        }
      }
      return;
    }

    const selectedTracks = state.tracks.filter(t => t.enabled);
    const selectedTrackIndices = selectedTracks.map(t => t.index);
    const selectedTrackIds = selectedTracks.map(t => t.id);

    if (state.scope !== "selected_clips" && selectedTracks.length === 0) {
      showToast("Select at least one audio track.", "error");
      return;
    }

    // 1. FRESH SNAPSHOT: Directly query Premiere Pro live state at the exact moment of click
    let rawSnapshot;
    try {
      rawSnapshot = await window.VoxForgeDOMBridge.createFreshEnhancementSnapshot({
        scope: state.scope,
        selectedTrackIds: selectedTrackIds,
        selectedTrackIndices: selectedTrackIndices
      });
    } catch (snapErr) {
      if (window.SpeechifyContextManager) {
        window.SpeechifyContextManager.logValidation({
          stage: 'snapshot_query',
          valid: false,
          errors: [{ code: 'SNAPSHOT_QUERY_EXCEPTION', message: snapErr.message }]
        });
      }
      showToast("Couldn't read the current Premiere selection. Please try again.", "error");
      return;
    }

    // Single safe deserialization boundary
    let snapshot;
    try {
      snapshot = window.SpeechifyContextManager
        ? window.SpeechifyContextManager.parseContext(rawSnapshot)
        : (typeof rawSnapshot === 'string' ? JSON.parse(rawSnapshot) : rawSnapshot);
    } catch (parseErr) {
      if (window.SpeechifyContextManager) {
        window.SpeechifyContextManager.logValidation({
          stage: 'snapshot_parse',
          valid: false,
          errors: [{ code: 'SNAPSHOT_PARSE_EXCEPTION', message: parseErr.message }]
        });
      }
      showToast("Couldn't read the current Premiere selection. Please try again.", "error");
      return;
    }

    if (!snapshot || !snapshot.success) {
      const errReason = (snapshot && snapshot.error) ? snapshot.error : "Couldn't read the current Premiere selection. Please try again.";
      showToast(errReason, "error");
      return;
    }

    // Structural schema validation
    if (window.SpeechifyContextManager) {
      const structCheck = window.SpeechifyContextManager.validateStructure(snapshot);
      if (!structCheck.valid) {
        window.SpeechifyContextManager.logValidation({
          stage: 'structural_validation',
          valid: false,
          errors: structCheck.errors
        });
        const firstErr = structCheck.errors[0];
        if (firstErr && firstErr.code === "NO_CLIPS_SELECTED") {
          showToast("Select an audio clip in the timeline.", "error");
        } else {
          showToast("Couldn't read the current Premiere selection. Please try again.", "error");
        }
        return;
      }
    }

    if (!snapshot.clips || snapshot.clips.length === 0) {
      if (state.scope === "selected_clips") {
        showToast("Select an audio clip in the timeline.", "error");
      } else {
        showToast("No audio clips found on selected tracks within specified range.", "error");
      }
      return;
    }

    // 2. PRE-FLIGHT VALIDATION: Confirm context is immutable and matches current timeline state
    let validation;
    try {
      validation = await window.VoxForgeDOMBridge.validateCurrentPremiereContext(snapshot);
    } catch (vErr) {
      validation = { valid: false, errors: [{ code: "VALIDATE_CALL_FAIL", message: vErr.message }] };
    }

    if (window.SpeechifyContextManager) {
      window.SpeechifyContextManager.logValidation({
        stage: 'preflight_premiere_check',
        valid: !!(validation && validation.valid),
        sequenceGuid: snapshot.sequenceGuid || (snapshot.sequence && snapshot.sequence.guid),
        scope: state.scope,
        errors: validation && validation.errors
      });
    }

    if (!validation || !validation.valid) {
      let userMsg = "The timeline audio changed before processing could start. Please run enhancement again.";
      if (validation && validation.errors && validation.errors.length > 0) {
        const errCode = validation.errors[0].code;
        if (errCode === 'SEQUENCE_CHANGED' || errCode === 'CLIP_REMOVED_OR_REPLACED' || errCode === 'NO_ACTIVE_SEQUENCE') {
          userMsg = validation.errors[0].message;
        } else {
          userMsg = "Couldn't read the current Premiere selection. Please try again.";
        }
      } else if (validation && validation.reason && !validation.reason.includes('JSON.parse')) {
        userMsg = validation.reason;
      } else {
        userMsg = "Couldn't read the current Premiere selection. Please try again.";
      }
      showToast(userMsg, "error");
      return;
    }

    // Generate authoritative Master Job ID
    const masterJobId = "job-" + (window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : (Date.now().toString(36) + Math.random().toString(36).slice(2, 8)));
    const tempJobIdsToCleanup = [];

    // Clear batch reservations at the start of every enhancement batch
    if (window.SpeechifyPlacementService) {
      window.SpeechifyPlacementService.clearReservations();
    }

    // Build individual EnhancementJob objects for actual audio clips / intersections
    // (Enforces invariant: A timeline track is not an audio file; gaps are never rendered as silence)
    const queue = window.SpeechifyContextManager
      ? window.SpeechifyContextManager.buildEnhancementJobs(snapshot, masterJobId)
      : [];

    if (queue.length === 0) {
      if (state.scope === "selected_clips") {
        showToast("Select an audio clip in the timeline.", "error");
      } else {
        showToast("No audio clips found on selected tracks within specified range.", "error");
      }
      return;
    }

    state.isCancelled = false;
    updateEngineStatusUI('processing');
    switchView('processing');
    const modelMeta = MODEL_METADATA[state.selectedModelId] || MODEL_METADATA["mp_senet"];
    el.procModelName.textContent = modelMeta.name;

    // Update processing scope context labels (Requirements 61 & 62)
    if (state.scope === "selected_clips") {
      if (el.procScopeContext) el.procScopeContext.textContent = "Selected Clips";
      if (el.procTrackDetail) el.procTrackDetail.textContent = `${queue.length} selected clip${queue.length > 1 ? 's' : ''}`;
    } else {
      const selectedTrackCount = state.tracks.filter(t => t.enabled).length;
      if (el.procScopeContext) el.procScopeContext.textContent = (state.scope === "in_out" ? "In / Out" : "Full Sequence");
      if (el.procTrackDetail) el.procTrackDetail.textContent = `${selectedTrackCount} audio track${selectedTrackCount > 1 ? 's' : ''}`;
    }

    const totalClips = queue.length;
    const totalAudioDuration = queue.reduce((acc, q) => acc + q.durationSec, 0);
    const overallWallClockStart = performance.now();
    const failedItems = [];
    let completedCount = 0;
    let timelinePlacedCount = 0;
    let timelineFailedCount = 0;

    try {
      for (let i = 0; i < totalClips; i++) {
        if (state.isCancelled) break;

        const item = queue[i];
        if (totalClips > 1) {
          const trackLabel = item.trackName ? ` (${item.trackName})` : '';
          el.procClipIndicator.textContent = `Clip ${i + 1} of ${totalClips}${trackLabel}: ${item.clipName}`;
          el.procClipIndicator.style.display = 'block';
        } else {
          el.procClipIndicator.style.display = 'none';
        }

        try {
          const placementRes = await processSingleClipJob(item, i, totalClips, totalAudioDuration, modelMeta, snapshot, tempJobIdsToCleanup);
          completedCount++;
          if (placementRes && placementRes.placedOnTimeline) {
            timelinePlacedCount++;
          } else if (state.placementMode === 'new_track') {
            timelineFailedCount++;
          }
        } catch (itemErr) {
          console.warn(`[Speechify] Error processing ${item.trackName || item.clipName}:`, itemErr);
          failedItems.push({
            name: item.trackName || item.clipName || `Item ${i + 1}`,
            error: itemErr.message || "Enhancement failed"
          });
        }
      }

      if (state.isCancelled) {
        switchView('main');
        showToast("Enhancement cancelled.", "info");
        return;
      }

      if (completedCount === 0 && failedItems.length > 0) {
        switchView('main');
        showToast(failedItems[0].error || "Enhancement failed.", "error");
        return;
      }

      // Completed successfully! Calculate wall-clock duration
      const wallClockElapsedSec = Math.max(0.1, (performance.now() - overallWallClockStart) / 1000);
      const formattedTime = (window.TimeUtils ? window.TimeUtils.formatDuration(wallClockElapsedSec) : formatDuration(wallClockElapsedSec));
      const uniqueTracks = new Set(queue.map(q => q.trackName || `A${q.trackIndex + 1}`)).size;
      const trackSummary = uniqueTracks > 1 ? ` across ${uniqueTracks} tracks` : '';

      if (totalClips > 1) {
        if (failedItems.length > 0) {
          el.successSummaryText.textContent = `${completedCount} of ${totalClips} clips enhanced${trackSummary} \u2022 Completed in ${formattedTime}`;
          showToast(`${completedCount} of ${totalClips} clips enhanced. ${failedItems.map(f => f.name).join(', ')} could not be processed.`, "warning");
        } else {
          el.successSummaryText.textContent = `${totalClips} clips enhanced${trackSummary} \u2022 Completed in ${formattedTime}`;
        }
      } else {
        el.successSummaryText.textContent = `${modelMeta.name} \u2022 Completed in ${formattedTime}`;
      }

      // Rules 31, 32, 63, 64: Accurate placement status messaging
      if (el.successPlacementNote) {
        if (state.placementMode === 'project_only') {
          el.successPlacementNote.textContent = "Saved to Speechify bin";
        } else {
          if (timelineFailedCount === 0 && timelinePlacedCount > 0) {
            el.successPlacementNote.textContent = "Added to Speechify bin and timeline";
          } else if (timelinePlacedCount > 0 && timelineFailedCount > 0) {
            el.successPlacementNote.textContent = `${timelinePlacedCount} placed on timeline, ${timelineFailedCount} saved to bin`;
            showToast("Some clips could not be placed on the timeline and were saved to the bin.", "warning");
          } else {
            el.successPlacementNote.textContent = `${completedCount} file${completedCount > 1 ? 's' : ''} saved to Speechify bin. Timeline placement failed. Original audio was not changed.`;
            showToast("Couldn't place the enhanced audio on the timeline. The original audio was left unchanged.", "warning");
          }
        }
      }

      switchView('success');

    } catch (err) {
      if (!state.isCancelled) {
        switchView('main');
        showToast(formatUserErrorMessage(err, "Enhancement failed."), "error");
      }
    } finally {
      if (state.isEngineOnline) {
        updateEngineStatusUI('ready');
      }
      // Safely cleanup temporary sequence composites in the background
      for (const tempId of tempJobIdsToCleanup) {
        try {
          fetch(`${state.engineUrl}/api/audio/cleanup-temp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: tempId })
          }).catch(() => {});
        } catch (e) {}
      }
    }
  }

  function processSingleClipJob(item, clipIndex, totalClips, totalAudioDuration, modelMeta, snapshot, tempJobIdsToCleanup = []) {
    return new Promise(async (resolve, reject) => {
      const tJobStart = performance.now();
      const telemetry = {
        extraction_ms: 0,
        inference_ms: 0,
        output_validation_ms: 0,
        import_ms: 0,
        placement_ms: 0,
        verification_ms: 0,
        total_ms: 0
      };

      try {
        if (!item.sourceFile) {
          reject(new Error("Speechify couldn't find source media for clip: " + (item.clipName || "unknown")));
          return;
        }

        // Step 1: Model Inference Dispatch
        if (el.procClipIndicator) {
          const trackLabel = item.trackName ? ` (${item.trackName})` : '';
          el.procClipIndicator.textContent = totalClips > 1
            ? `Clip ${clipIndex + 1} of ${totalClips}${trackLabel}: Enhancing with ${modelMeta.name}...`
            : `Enhancing with ${modelMeta.name}...`;
        }

        const payload = {
          job_id: item.clipJobId,
          batch_id: item.batchId || item.masterJobId,
          track_id: item.trackId,
          source_file: item.sourceFile,
          in_point_sec: item.inPointSec,
          out_point_sec: item.outPointSec,
          model_id: state.selectedModelId,
          sequence_sample_rate: snapshot ? (snapshot.sampleRate || 48000) : 48000,
          clip_name: item.clipName,
          track_index: item.trackIndex,
          track_name: item.trackName,
          device: state.selectedDevice || "auto",
          metadata: {
            jobId: item.clipJobId,
            masterJobId: item.masterJobId,
            batchId: item.batchId || item.masterJobId,
            sequenceGuid: item.sequenceGuid,
            sequenceName: item.sequenceName,
            trackName: item.trackName,
            trackIndex: item.trackIndex,
            trackId: item.trackId,
            scope: state.scope,
            sourceFile: item.sourceFile,
            fileSize: item.fileSize,
            fileMtime: item.fileMtime,
            createdAt: new Date().toISOString()
          },
          settings: {
            placement_mode: state.placementMode,
            normalize: el.normalizeCheck ? el.normalizeCheck.checked : false
          }
        };

        const tInferStart = performance.now();
        const resp = await fetch(`${state.engineUrl}/api/enhance`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          reject(new Error(errData.detail || errData.error || `Engine returned HTTP ${resp.status}`));
          return;
        }

        const data = await resp.json();
        const jobId = data.job_id;
        state.currentJobId = jobId;

        // Bounded Polling Loop (Max 180 seconds to prevent endless hangs)
        let pollCount = 0;
        const maxPolls = 900; // 900 * 200ms = 180 seconds

        state.jobPollTimer = setInterval(async () => {
          pollCount++;
          if (state.isCancelled) {
            clearInterval(state.jobPollTimer);
            state.currentJobId = null;
            resolve({ success: false, cancelled: true });
            return;
          }

          if (pollCount > maxPolls) {
            clearInterval(state.jobPollTimer);
            state.currentJobId = null;
            reject(new Error("Enhancement job timed out after 180 seconds."));
            return;
          }

          try {
            const pollResp = await fetch(`${state.engineUrl}/api/jobs/${jobId}`);
            if (!pollResp.ok) return;

            const job = await pollResp.json();
            const jobPct = job.progress_pct || 0;
            const overallPct = Math.min(99, Math.round(((clipIndex + (jobPct / 100)) / totalClips) * 100));
            updateOverallProgress(overallPct, totalAudioDuration, modelMeta.rtf);

            if (job.status === "failed") {
              clearInterval(state.jobPollTimer);
              state.currentJobId = null;
              reject(new Error(job.error || "Enhancement inference failed."));
              return;
            }

            if (job.status === "completed") {
              clearInterval(state.jobPollTimer);
              state.currentJobId = null;
              telemetry.inference_ms = Math.round(performance.now() - tInferStart);

              // Validate job ID ownership
              if (job.result && job.result.job_id && job.result.job_id !== item.clipJobId) {
                reject(new Error(`Security mismatch: Job ID ${job.result.job_id} does not match request ${item.clipJobId}`));
                return;
              }

              const enhancedWav = (job.result && (job.result.enhanced_file || job.result.output_file)) || null;
              if (!enhancedWav) {
                reject(new Error("Enhancement finished but output file was not found."));
                return;
              }

              // Step 4: Output Audio Signal Integrity Gate
              const tValStart = performance.now();
              if (job.result && job.result.audio_diagnostics) {
                const diag = job.result.audio_diagnostics;
                const srcRms = (diag.source && typeof diag.source.rms === 'number') ? diag.source.rms : 0;
                const outRms = (diag.output && typeof diag.output.rms === 'number') ? diag.output.rms : 0;
                console.log(`[Speechify Audio Diagnostic] Job ${item.clipJobId}: Source RMS: ${srcRms} | Output RMS: ${outRms}`);
                if (srcRms > 0.0001 && outRms < 0.000001) {
                  reject(new Error("Enhanced audio collapsed to silence. Placement aborted to protect sequence."));
                  return;
                }
              }
              telemetry.output_validation_ms = Math.round(performance.now() - tValStart);

              // Step 5: Import & Non-Destructive Placement on Next Safe Track
              if (el.procClipIndicator) {
                const trackLabel = item.trackName ? ` (${item.trackName})` : '';
                el.procClipIndicator.textContent = totalClips > 1
                  ? `Clip ${clipIndex + 1} of ${totalClips}${trackLabel}: Placing on timeline...`
                  : `Placing on timeline...`;
              }

              const tPlaceStart = performance.now();
              let placementRes = null;
              try {
                const targetEnd = item.targetEndTime || (item.targetStartTime + (item.durationSec || 1.0));
                placementRes = await window.VoxForgeDOMBridge.placeEnhancedClip({
                  wavPath: enhancedWav,
                  clipName: item.clipName,
                  startTimeSec: item.targetStartTime,
                  durationSec: item.durationSec || 0,
                  endTimeSec: targetEnd,
                  placementMode: state.placementMode,
                  sourceTrackIndex: item.trackIndex,
                  trackIndex: item.trackIndex,
                  trackName: item.trackName,
                  reservedIntervals: window.SpeechifyPlacementService ? window.SpeechifyPlacementService.getReservations() : {}
                });

                // Reserve destination interval in batch map to protect against subsequent job collisions
                if (placementRes && placementRes.success && placementRes.placedOnTimeline) {
                  if (window.SpeechifyPlacementService && placementRes.trackIndex !== undefined) {
                    window.SpeechifyPlacementService.reserveDestination(
                      placementRes.trackIndex,
                      item.targetStartTime,
                      targetEnd,
                      item.clipJobId
                    );
                  }
                }
              } catch (domErr) {
                console.warn("[Speechify Bridge] placeEnhancedClip error:", domErr);
              }

              telemetry.placement_ms = Math.round(performance.now() - tPlaceStart);
              telemetry.total_ms = Math.round(performance.now() - tJobStart);

              console.log(`[Speechify Track Job Completed] Track: ${item.trackName || item.clipName} | ` +
                `Extraction: ${telemetry.extraction_ms}ms | Inference: ${telemetry.inference_ms}ms | ` +
                `Validation: ${telemetry.output_validation_ms}ms | Placement: ${telemetry.placement_ms}ms | Total: ${telemetry.total_ms}ms`);

              resolve(placementRes || { success: true, placedOnTimeline: false });
            }
          } catch (pErr) {
            console.warn("Polling error:", pErr);
          }
        }, 200);

      } catch (err) {
        if (state.jobPollTimer) clearInterval(state.jobPollTimer);
        state.currentJobId = null;
        reject(err);
      }
    });
  }

  function updateOverallProgress(pct, totalAudioSec, rtf) {
    el.progressBarFill.style.width = `${pct}%`;
    el.progressPctText.textContent = `${pct}%`;

    const estTotalSec = Math.max(2, totalAudioSec * rtf);
    const remPct = Math.max(0, 1 - (pct / 100));
    const remSec = Math.max(1, Math.round(estTotalSec * remPct));

    if (pct >= 98) {
      el.progressCountdownText.textContent = "Finalizing audio...";
    } else {
      el.progressCountdownText.textContent = `About ${remSec} second${remSec === 1 ? '' : 's'} remaining`;
    }
  }

  async function onCancelJob() {
    state.isCancelled = true;
    if (state.currentJobId) {
      try {
        await fetch(`${state.engineUrl}/api/jobs/${state.currentJobId}/cancel`, { method: 'POST' });
      } catch (err) {
        console.warn("Cancel request error:", err);
      }
      state.currentJobId = null;
    }
    if (state.jobPollTimer) {
      clearInterval(state.jobPollTimer);
      state.jobPollTimer = null;
    }
    switchView('main');
  }

  function switchView(viewName) {
    el.mainView.classList.remove('active');
    el.processingView.classList.remove('active');
    el.successView.classList.remove('active');

    if (viewName === 'processing') {
      el.processingView.classList.add('active');
    } else if (viewName === 'success') {
      el.successView.classList.add('active');
    } else {
      el.mainView.classList.add('active');
    }
  }

  // --------------------------------------------------------------------------
  // Settings & Model Storage Directory
  // --------------------------------------------------------------------------
  function openSettingsModal() {
    el.settingsModal.classList.add('open');
    // Ensure authoritative hardware state is refreshed when settings modal opens
    loadSystemProfile().catch(() => {});
  }

  function closeSettingsModal() {
    el.settingsModal.classList.remove('open');
  }

  async function onChooseFolder() {
    try {
      if (window.SpeechifyStorageService) {
        const pickRes = await window.SpeechifyStorageService.pickFolder();
        const chosen = (typeof pickRes === 'string') ? pickRes : (pickRes && !pickRes.cancelled ? pickRes.path : null);
        if (chosen) {
          if (el.storagePathInput) el.storagePathInput.value = chosen;
          await onSaveStoragePath(chosen);
        }
      } else {
        showToast("Storage service is initializing. Please enter folder path manually.", "info");
      }
    } catch (err) {
      showToast(formatUserErrorMessage(err, "Failed to select folder."), "error");
    }
  }

  async function onResetStorage() {
    try {
      if (window.SpeechifyStorageService) {
        if (el.changeStorageBtn) el.changeStorageBtn.disabled = true;
        if (el.resetStorageBtn) el.resetStorageBtn.disabled = true;
        const res = await window.SpeechifyStorageService.resetToDefault();
        if (!res.success) {
          throw new Error(res.error || "Failed to reset storage location");
        }
        state.storagePath = res.storagePath;
        if (el.storagePathInput) el.storagePathInput.value = res.storagePath;
        showToast("Model storage reset to default managed location.", "success");
        await loadModelsList();
      }
    } catch (err) {
      showToast(formatUserErrorMessage(err, "Failed to reset storage location."), "error");
    } finally {
      if (el.changeStorageBtn) el.changeStorageBtn.disabled = false;
      if (el.resetStorageBtn) el.resetStorageBtn.disabled = false;
    }
  }

  async function onSaveStoragePath(specifiedPath) {
    const newPath = (specifiedPath || (el.storagePathInput ? el.storagePathInput.value : '')).trim();
    if (!newPath) {
      showToast("Please enter or select a valid storage folder path.", "info");
      return;
    }

    if (el.saveStoragePathBtn) el.saveStoragePathBtn.disabled = true;
    if (el.changeStorageBtn) el.changeStorageBtn.disabled = true;
    if (el.chooseFolderBtn) el.chooseFolderBtn.disabled = true;
    if (el.storageSaveStatus) {
      el.storageSaveStatus.style.display = "block";
      el.storageSaveStatus.style.color = "var(--sp-accent-primary-hover)";
      el.storageSaveStatus.textContent = "Updating location...";
    }

    try {
      let resolvedPath = newPath;
      if (window.SpeechifyStorageService) {
        const res = await window.SpeechifyStorageService.setLocation(newPath);
        if (!res.success) {
          throw new Error(res.error || "Failed to update storage location");
        }
        resolvedPath = res.storagePath;
      } else {
        const resp = await fetch(`${state.engineUrl}/api/models/set-storage-path`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: newPath })
        });
        const res = await resp.json();
        if (!resp.ok) throw new Error(res.error || "Failed to update storage location");
        resolvedPath = res.storage_path;
      }

      state.storagePath = resolvedPath;
      if (el.storagePathInput) el.storagePathInput.value = resolvedPath;
      if (el.storageSaveStatus) {
        el.storageSaveStatus.style.color = "var(--sp-accent-success)";
        el.storageSaveStatus.textContent = "Location updated successfully";
      }
      showToast("Model storage location updated.", "success");
      await loadModelsList();
    } catch (err) {
      if (el.storageSaveStatus) el.storageSaveStatus.style.display = "none";
      showToast(formatUserErrorMessage(err, "Failed to update storage location."), "error");
    } finally {
      if (el.saveStoragePathBtn) el.saveStoragePathBtn.disabled = false;
      if (el.changeStorageBtn) el.changeStorageBtn.disabled = false;
      if (el.chooseFolderBtn) el.chooseFolderBtn.disabled = false;
    }
  }

  // --------------------------------------------------------------------------
  // Explicit Model Migration Workflow
  // --------------------------------------------------------------------------
  async function openMigrateModal() {
    const currentPath = state.storagePath || "";
    let targetPath = (el.storagePathInput ? el.storagePathInput.value.trim() : "") || "";

    // If target equals current, let user pick the destination folder
    if (!targetPath || targetPath === currentPath) {
      if (window.SpeechifyStorageService) {
        const pickRes = await window.SpeechifyStorageService.pickFolder();
        const chosen = (typeof pickRes === 'string') ? pickRes : (pickRes && !pickRes.cancelled ? pickRes.path : null);
        if (chosen && chosen !== currentPath) {
          targetPath = chosen;
          if (el.storagePathInput) el.storagePathInput.value = chosen;
        } else {
          return;
        }
      }
    }

    const installed = Object.values(state.modelsList || {}).filter(m => m.installed);
    const totalMb = installed.reduce((acc, m) => {
      const meta = MODEL_METADATA[m.id] || {};
      return acc + (m.size_bytes ? Math.round(m.size_bytes / (1024 * 1024)) : (meta.sizeMb || 10));
    }, 0);

    el.migrateSourceText.textContent = `Source: ${currentPath}`;
    el.migrateTargetText.textContent = `Target: ${targetPath}`;
    el.migrateInfoText.textContent = `${installed.length} model${installed.length === 1 ? '' : 's'} available to move \u2022 ~${totalMb} MB`;
    el.migrateStatusText.style.display = 'none';
    el.confirmMigrateBtn.disabled = (installed.length === 0 || !targetPath || currentPath === targetPath);
    el.migrateModal.classList.add('open');
  }

  function closeMigrateModal() {
    el.migrateModal.classList.remove('open');
  }

  async function onConfirmMigrate() {
    const targetPath = el.storagePathInput.value.trim();
    if (!targetPath) return;

    el.confirmMigrateBtn.disabled = true;
    el.cancelMigrateBtn.disabled = true;
    el.migrateStatusText.style.display = 'block';
    el.migrateStatusText.style.color = 'var(--sp-accent-primary-hover)';
    el.migrateStatusText.textContent = "Moving models...";

    try {
      let res;
      if (window.SpeechifyStorageService) {
        res = await window.SpeechifyStorageService.migrateModels(state.storagePath, targetPath);
        if (!res.success) throw new Error(res.error || "Migration failed");
      } else {
        const resp = await fetch(`${state.engineUrl}/api/models/migrate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_path: state.storagePath,
            target_path: targetPath
          })
        });
        res = await resp.json();
        if (!resp.ok) throw new Error(res.error || "Migration failed");
      }

      el.migrateStatusText.style.color = 'var(--sp-accent-success)';
      el.migrateStatusText.textContent = `Successfully moved ${res.migrated_count || 0} models.`;
      showToast("Models moved successfully.", "success");
      await loadModelsList();
      setTimeout(() => {
        closeMigrateModal();
        el.confirmMigrateBtn.disabled = false;
        el.cancelMigrateBtn.disabled = false;
      }, 1000);
    } catch (err) {
      el.migrateStatusText.style.color = 'var(--sp-accent-warning)';
      el.migrateStatusText.textContent = `Error: ${err.message}`;
      el.confirmMigrateBtn.disabled = false;
      el.cancelMigrateBtn.disabled = false;
      showToast(formatUserErrorMessage(err, "Migration failed."), "error");
    }
  }


  // --------------------------------------------------------------------------
  // Dedicated Model Manager View
  // --------------------------------------------------------------------------
  function openModelManagerModal() {
    renderModelManagerLists();
    el.modelManagerModal.classList.add('open');
  }

  function closeModelManagerModal() {
    el.modelManagerModal.classList.remove('open');
  }

  function renderModelManagerLists() {
    el.installedModelsList.innerHTML = '';
    el.availableModelsList.innerHTML = '';

    Object.keys(MODEL_METADATA).forEach(modelId => {
      const meta = MODEL_METADATA[modelId];
      const modelInfo = state.modelsList[modelId] || {};
      const isInstalled = modelInfo.installed || false;

      const row = document.createElement('div');
      row.className = 'sp-model-row';

      if (isInstalled) {
        row.innerHTML = `
          <div class="sp-model-row-left">
            <span class="sp-model-row-name">${meta.name}</span>
            <span class="sp-model-row-meta">${meta.subtitle} \u2022 ~${meta.sizeMb} MB</span>
          </div>
          <div class="sp-model-row-status">
            <span class="sp-status-dot installed"></span>
            <span>Installed</span>
          </div>
        `;
        el.installedModelsList.appendChild(row);
      } else {
        row.innerHTML = `
          <div class="sp-model-row-left">
            <span class="sp-model-row-name">${meta.name}</span>
            <span class="sp-model-row-meta">${meta.subtitle} \u2022 ~${meta.sizeMb} MB</span>
          </div>
          <button class="sp-btn sp-btn-secondary btn-download-model" data-model-id="${modelId}" style="height: 26px; padding: 0 10px;">Download</button>
        `;
        row.querySelector('.btn-download-model').addEventListener('click', (e) => {
          onDownloadModel(modelId, e.target);
        });
        el.availableModelsList.appendChild(row);
      }
    });

    if (el.installedModelsList.children.length === 0) {
      el.installedModelsList.innerHTML = '<span class="sp-meta">No models installed.</span>';
    }
    if (el.availableModelsList.children.length === 0) {
      el.availableModelsList.innerHTML = '<span class="sp-meta">All supported models are installed locally.</span>';
    }
  }

  async function onDownloadModel(modelId, btnElement) {
    btnElement.disabled = true;
    btnElement.textContent = "Starting...";

    try {
      const resp = await fetch(`${state.engineUrl}/api/models/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId })
      });

      const res = await resp.json();
      if (!resp.ok) throw new Error(res.error || "Download failed");

      // Poll download progress
      const pollTimer = setInterval(async () => {
        try {
          const pResp = await fetch(`${state.engineUrl}/api/downloads/${modelId}`);
          if (!pResp.ok) return;
          const task = await pResp.json();

          const pct = Math.round(task.progress_pct || 0);
          btnElement.textContent = `${pct}%`;

          if (task.status === "completed") {
            clearInterval(pollTimer);
            btnElement.textContent = "Installed";
            loadModelsList();
          } else if (task.status === "failed") {
            clearInterval(pollTimer);
            btnElement.disabled = false;
            btnElement.textContent = "Download";
            showToast(formatUserErrorMessage(task.error, "Download failed."), "error");
          }
        } catch (e) {
          console.warn("Poll download error:", e);
        }
      }, 500);

    } catch (err) {
      btnElement.disabled = false;
      btnElement.textContent = "Download";
      showToast(formatUserErrorMessage(err, "Download failed."), "error");
    }
  }

  // --------------------------------------------------------------------------
  // Toast Notifications
  // --------------------------------------------------------------------------
  function showToast(message, type = "info") {
    const toast = document.createElement('div');
    toast.className = `sp-toast ${type}`;
    toast.textContent = message;
    el.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 200);
    }, 4000);
  }

  // Phased boot entrypoint: guarantees UI renders immediately before services start
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startBootSequence);
  } else {
    startBootSequence();
  }

})();
