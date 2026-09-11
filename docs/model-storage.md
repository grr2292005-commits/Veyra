# Speechify — Centralized Model Storage Architecture

## 1. Architectural Overview

Model management in Speechify is governed exclusively by **`ModelStorageManager`** (`models/storage_manager.py` on the backend, and `plugin/services/storage_service.js` on the frontend). It serves as the single authority for:
1. Resolving the active neural model storage directory.
2. Managing the zero-setup default storage location.
3. Creating required model subdirectories automatically.
4. Discovering and validating local neural checkpoints.
5. Providing non-destructive path switching.
6. Performing explicit, user-confirmed weight migrations.

---

## 2. Managed Default Storage (Zero Setup)

Speechify requires **zero storage configuration** on first launch.

- **Default Location**:
  - Windows: `%APPDATA%\Speechify\Models` (e.g. `C:\Users\<username>\AppData\Roaming\Speechify\Models`)
  - Fallback / Development: `SpeechEnhancerPro/models/storage`
- **Automatic Directory Scaffolding**:
  Upon initialization, `ModelStorageManager` automatically verifies and creates the following subfolders if they do not exist:
  ```text
  %APPDATA%\Speechify\Models\
  ├── MP-SENet\
  ├── ZipEnhancer-S\
  ├── MossFormerGAN-SE\
  └── DeepFilterNet3\
  ```
- **Seeding on First Run**:
  If the managed directory is empty on first boot, `ModelStorageManager` automatically checks local development directories (`SpeechEnhancerPro/models/storage` and `benchmark_archive/checkpoints/`) and cleanly links or copies existing checkpoints so the user never needs to download existing models again.

---

## 3. Clean Settings UI Contract

In accordance with product design principles, Speechify never shows confusing raw filesystem paths for default storage:

### When using Managed Storage:
```text
Model Storage
Speechify managed storage
Models are stored locally on this computer.
[ Change location ] [ Move existing models… ]
```

### When using a Custom Location:
```text
Model Storage
Custom storage folder
D:\AI\Models
[ Change location ] [ Reset to default ] [ Move existing models… ]
```

---

## 4. Non-Destructive Storage Switching

Changing the storage location via **`[ Change location ]`** is strictly **non-destructive**:
- The user selects a target folder via the native OS folder picker.
- The path is transactionally validated and persisted in `models/storage_config.json`.
- **Files are NEVER moved or copied automatically** during a location change.
- The new directory is immediately rescanned:
  - If checkpoints exist in the target folder, they are verified and marked as installed.
  - If the target folder is empty, models transition to available for download.
- Clicking **`[ Reset to default ]`** immediately reverts the active storage path back to `%APPDATA%\Speechify\Models`.

---

## 5. Explicit Model Migration Workflow

To move existing weights without re-downloading, users open the **`[ Move existing models… ]`** modal:
1. **Pre-flight verification**: Inspects the source directory and target directory, calculating total models found and total size in MB.
2. **User Confirmation**: The modal presents source, target, model count, and required disk space. The "Move Models" button is disabled if the paths are identical.
3. **Transactional Copy & Verify**: Files are copied and verified with size checks before updating active configuration. If any step fails, the previous valid location remains untouched.

---

## 6. Model Verification & Checkpoint Integrity

A model is marked as `installed` **only if** its checkpoint file physically exists in the active directory and meets size constraints:

| Model ID | Folder Aliases | Checkpoint Filename | Minimum Size |
| :--- | :--- | :--- | :--- |
| `mp_senet` | `MP-SENet`, `mp_senet` | `mp_senet.pt` / `model.pt` | $\ge 5\text{ MB}$ |
| `zipenhancer` | `ZipEnhancer-S`, `zipenhancer` | `zipenhancer.pt` / `model.pt` | $\ge 5\text{ MB}$ |
| `mossformergan` | `MossFormerGAN-SE`, `mossformergan` | `mossformergan.pt` / `model.pt` | $\ge 20\text{ MB}$ |
| `deepfilternet3` | `DeepFilterNet3`, `deepfilternet3` | `deepfilternet3.pt` / cache | $\ge 5\text{ MB}$ |

Both folder names (`MP-SENet` and `mp_senet`) and checkpoint names are validated seamlessly via alias resolution.
