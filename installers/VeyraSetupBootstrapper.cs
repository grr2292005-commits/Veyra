using System;
using System.IO;
using System.Net;
using System.Diagnostics;
using Microsoft.Win32;

namespace VeyraInstaller
{
    class Program
    {
        static int Main(string[] args)
        {
            Console.Title = "Veyra - Automated Premiere Pro Installer";
            Console.WriteLine("===============================================================================");
            Console.WriteLine("                     VEYRA — PREMIERE PRO INSTALLER");
            Console.WriteLine("            Local AI Speech Enhancement for Adobe Premiere Pro");
            Console.WriteLine("===============================================================================");
            Console.WriteLine();

            // 1. Verify 64-bit Windows
            if (!Environment.Is64BitOperatingSystem)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("[ERROR] Veyra requires a 64-bit Windows operating system.");
                Console.ResetColor();
                return 1;
            }

            // Determine root paths
            string scriptDir = AppDomain.CurrentDomain.BaseDirectory;
            if (File.Exists(Path.Combine(scriptDir, "..\\engine\\server.py")))
            {
                scriptDir = Path.GetFullPath(Path.Combine(scriptDir, ".."));
            }

            // Parse custom target dir if provided (e.g. for prototype testing)
            string veyraDir = Environment.GetEnvironmentVariable("VEYRA_DIR");
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--target-dir" && i + 1 < args.Length)
                {
                    veyraDir = args[i + 1];
                }
            }

            if (string.IsNullOrEmpty(veyraDir))
            {
                veyraDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Veyra");
            }

            string runtimeDir = Path.Combine(veyraDir, "runtime");
            string modelsDir = Path.Combine(veyraDir, "models");
            string cacheDir = Path.Combine(veyraDir, "cache");
            string configDir = Path.Combine(veyraDir, "config");
            string logsDir = Path.Combine(veyraDir, "logs");

            Directory.CreateDirectory(veyraDir);
            Directory.CreateDirectory(runtimeDir);
            Directory.CreateDirectory(modelsDir);
            Directory.CreateDirectory(cacheDir);
            Directory.CreateDirectory(configDir);
            Directory.CreateDirectory(logsDir);

            string installLog = Path.Combine(logsDir, "installer.log");
            Log(installLog, string.Format("Veyra Installation started at {0}", DateTime.Now));

            // 2. Hardware Detection
            Console.WriteLine("[1/6] Detecting System Hardware & AI Acceleration Capabilities...");
            string gpuName;
            bool hasNvidia = DetectNvidiaGpu(out gpuName);
            string reqFile = Path.Combine(scriptDir, hasNvidia ? "requirements-standard-cuda.txt" : "requirements-standard-cpu.txt");

            if (hasNvidia)
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine(string.Format("[OK] Detected NVIDIA GPU: {0}", gpuName));
                Console.WriteLine("     Hardware Profile: NVIDIA CUDA Accelerated");
                Console.ResetColor();
            }
            else
            {
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine("[OK] No NVIDIA GPU detected.");
                Console.WriteLine("     Hardware Profile: Multi-Core CPU Fallback");
                Console.ResetColor();
            }

            // 3. Provision Private Runtime
            Console.WriteLine();
            Console.WriteLine("[2/6] Provisioning Isolated Private Python Runtime...");
            string pythonExe = GetPythonExePath(runtimeDir);
            string pythonwExe = GetPythonwExePath(runtimeDir);
            bool runtimeReady = false;

            if (!string.IsNullOrEmpty(pythonExe) && File.Exists(pythonExe))
            {
                string dummyOut;
                if (RunProcess(pythonExe, "-c \"import sys; import torch; import soundfile\"", out dummyOut) == 0)
                {
                    Console.ForegroundColor = ConsoleColor.Green;
                    Console.WriteLine(string.Format("[OK] Existing private runtime validated at: {0}", runtimeDir));
                    Console.ResetColor();
                    runtimeReady = true;
                }
            }

            if (!runtimeReady)
            {
                Console.WriteLine("Provisioning Python 3.11 standalone runtime...");
                string standaloneUrl = "https://github.com/astral-sh/python-build-standalone/releases/download/20240415/cpython-3.11.9%2B20240415-x86_64-pc-windows-msvc-shared-install_only.tar.gz";
                string archivePath = Path.Combine(cacheDir, "cpython-3.11.9.tar.gz");

                bool downloaded = DownloadFileWithTls(standaloneUrl, archivePath);
                if (!downloaded)
                {
                    Console.WriteLine("Standalone archive download failed, trying official installer...");
                    string officialUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe";
                    string installerPath = Path.Combine(cacheDir, "python-3.11.9-amd64.exe");
                    if (DownloadFileWithTls(officialUrl, installerPath))
                    {
                        string dummy;
                        RunProcess(installerPath, string.Format("/quiet InstallAllUsers=0 TargetDir=\"{0}\" Include_launcher=0 Shortcuts=0 PrependPath=0", runtimeDir), out dummy);
                    }
                }
                else
                {
                    Console.WriteLine("Extracting standalone Python runtime...");
                    string dummy;
                    int extractCode = RunProcess("tar.exe", string.Format("-xzf \"{0}\" -C \"{1}\" --strip-components=1", archivePath, runtimeDir), out dummy);
                    if (extractCode != 0)
                    {
                        RunProcess("powershell", string.Format("-NoProfile -Command \"tar -xzf '{0}' -C '{1}' --strip-components=1\"", archivePath, runtimeDir), out dummy);
                    }
                }

                pythonExe = GetPythonExePath(runtimeDir);
                pythonwExe = GetPythonwExePath(runtimeDir);

                if (string.IsNullOrEmpty(pythonExe) || !File.Exists(pythonExe))
                {
                    Console.ForegroundColor = ConsoleColor.Red;
                    Console.WriteLine(string.Format("[ERROR] Failed to provision private Python runtime in {0}", runtimeDir));
                    Console.ResetColor();
                    return 1;
                }

                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine(string.Format("[OK] Private runtime provisioned: {0}", pythonExe));
                Console.ResetColor();

                // 4. Install Dependencies
                Console.WriteLine();
                Console.WriteLine("[3/6] Installing Pinned Dependencies into Private Runtime...");
                string trustedHosts = "--trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host download.pytorch.org --trusted-host www.modelscope.cn";
                string dummyPip;
                RunProcess(pythonExe, string.Format("-m pip install --upgrade pip certifi {0} --quiet --no-warn-script-location", trustedHosts), out dummyPip);

                Console.WriteLine(string.Format("Installing production packages from {0}...", Path.GetFileName(reqFile)));
                string pipErr;
                int pipResult = RunProcess(pythonExe, string.Format("-m pip install -r \"{0}\" {1} --quiet --no-warn-script-location", reqFile, trustedHosts), out pipErr);
                if (pipResult != 0)
                {
                    Console.ForegroundColor = ConsoleColor.Red;
                    Console.WriteLine("[ERROR] Dependency installation failed. Please check internet connection.");
                    Console.ResetColor();
                    Log(installLog, string.Format("Pip failure: {0}", pipErr));
                    return 1;
                }
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("[OK] All production dependencies installed into private runtime.");
                Console.ResetColor();
            }
            else
            {
                Console.WriteLine("[3/6] Private runtime dependencies already satisfied.");
            }

            // 5. Verify PyTorch
            Console.WriteLine();
            Console.WriteLine("[4/6] Verifying PyTorch and Hardware Backend...");
            string torchOut;
            int pyTorchCode = RunProcess(pythonExe, "-c \"import torch; print(f'[OK] PyTorch {torch.__version__} | CUDA Available: {torch.cuda.is_available()}')\"", out torchOut);
            if (pyTorchCode != 0)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("[ERROR] PyTorch verification check failed.");
                Console.ResetColor();
                return 1;
            }
            Console.WriteLine(torchOut.Trim());

            // 6. Deploy CEP Extension
            Console.WriteLine();
            Console.WriteLine("[5/6] Deploying Veyra to Adobe Premiere Pro CEP directory...");
            string appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            string targetCepDir = Path.Combine(appData, "Adobe\\CEP\\extensions\\com.speechify.speechenhancer");
            string sourcePluginDir = Path.Combine(scriptDir, "plugin");

            if (Directory.Exists(targetCepDir))
            {
                try { Directory.Delete(targetCepDir, true); } catch { }
            }
            Directory.CreateDirectory(targetCepDir);

            if (Directory.Exists(sourcePluginDir))
            {
                CopyDirectory(sourcePluginDir, targetCepDir);
            }

            // Clean legacy extensions
            string legacyCep = Path.Combine(appData, "Adobe\\CEP\\extensions\\com.voxforge.speechenhancer");
            if (Directory.Exists(legacyCep)) { try { Directory.Delete(legacyCep, true); } catch { } }

            // Enable CSXS PlayerDebugMode
            for (int v = 7; v <= 16; v++)
            {
                try
                {
                    using (RegistryKey key = Registry.CurrentUser.CreateSubKey(string.Format("Software\\Adobe\\CSXS.{0}", v)))
                    {
                        if (key != null) key.SetValue("PlayerDebugMode", "1", RegistryValueKind.String);
                    }
                }
                catch { }
            }

            // Write dynamic engine config
            string engineScript = Path.Combine(scriptDir, "engine\\server.py");
            string configJson = string.Format("{{\n  \"python_exe\": \"{0}\",\n  \"engine_script\": \"{1}\",\n  \"project_root\": \"{2}\"\n}}",
                EscapeJson(pythonwExe),
                EscapeJson(engineScript),
                EscapeJson(scriptDir.TrimEnd('\\', '/')));
            
            File.WriteAllText(Path.Combine(configDir, "engine_config.json"), configJson);
            File.WriteAllText(Path.Combine(targetCepDir, "engine_config.json"), configJson);
            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine("[OK] Extension deployed and dynamic engine configured.");
            Console.ResetColor();

            // 7. Verify Engine Startup and Diagnostics
            Console.WriteLine();
            Console.WriteLine("[6/6] Verifying Local AI Engine Diagnostics & Live API Health...");
            string verifyScript = Path.Combine(scriptDir, "installers\\verify_install.py");
            int verifyResult = 0;
            if (File.Exists(verifyScript))
            {
                string verifyOut;
                verifyResult = RunProcess(pythonExe, string.Format("\"{0}\"", verifyScript), out verifyOut);
                Console.WriteLine(verifyOut);
            }
            else
            {
                string inlineVerify = string.Format("import sys; sys.path.insert(0, r'{0}'); from engine.hardware.detector import HardwareDetector; hd = HardwareDetector(); print(f'[OK] Hardware Profile: {{hd.get_profile().get(\"tier_name\")}}'); from models.manager import ModelManager; mm = ModelManager(); print(f'[OK] Model Registry: {{len(mm.registry_data.get(\"models\", {{}}))}} models')", scriptDir.TrimEnd('\\'));
                string inlineOut;
                verifyResult = RunProcess(pythonExe, string.Format("-c \"{0}\"", inlineVerify), out inlineOut);
                Console.WriteLine(inlineOut);
            }

            if (verifyResult != 0)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("[ERROR] Engine self-test verification failed.");
                Console.ResetColor();
                return 1;
            }

            Console.WriteLine();
            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine("===============================================================================");
            Console.WriteLine("                      INSTALLATION SUCCESSFUL!");
            Console.WriteLine("===============================================================================");
            Console.ResetColor();
            Console.WriteLine("Veyra is now installed and ready to use in Adobe Premiere Pro.");
            Console.WriteLine("To use: Open Premiere Pro -> Window -> Extensions -> Veyra");
            Console.WriteLine();

            return 0;
        }

        static bool DetectNvidiaGpu(out string name)
        {
            name = "NVIDIA GPU";
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("nvidia-smi", "--query-gpu=name,memory.total --format=csv,noheader")
                {
                    RedirectStandardOutput = true,
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
                using (Process p = Process.Start(psi))
                {
                    string outText = p.StandardOutput.ReadToEnd();
                    p.WaitForExit();
                    if (p.ExitCode == 0 && !string.IsNullOrWhiteSpace(outText))
                    {
                        name = outText.Split(',')[0].Trim();
                        return true;
                    }
                }
            }
            catch { }

            // WMI Fallback query via PowerShell
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("powershell", "-NoProfile -Command \"(Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like '*NVIDIA*' }).Name\"")
                {
                    RedirectStandardOutput = true,
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
                using (Process p = Process.Start(psi))
                {
                    string outText = p.StandardOutput.ReadToEnd().Trim();
                    p.WaitForExit();
                    if (!string.IsNullOrWhiteSpace(outText))
                    {
                        name = outText.Split('\n')[0].Trim();
                        return true;
                    }
                }
            }
            catch { }

            return false;
        }

        static string GetPythonExePath(string runtimeDir)
        {
            string p1 = Path.Combine(runtimeDir, "python.exe");
            if (File.Exists(p1)) return p1;
            string p2 = Path.Combine(runtimeDir, "Scripts\\python.exe");
            if (File.Exists(p2)) return p2;
            return null;
        }

        static string GetPythonwExePath(string runtimeDir)
        {
            string p1 = Path.Combine(runtimeDir, "pythonw.exe");
            if (File.Exists(p1)) return p1;
            string p2 = Path.Combine(runtimeDir, "Scripts\\pythonw.exe");
            if (File.Exists(p2)) return p2;
            return GetPythonExePath(runtimeDir);
        }

        static bool DownloadFileWithTls(string url, string destPath)
        {
            try
            {
                ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
                using (WebClient client = new WebClient())
                {
                    client.Headers.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VeyraInstaller/1.0");
                    client.DownloadFile(url, destPath);
                }
                return File.Exists(destPath) && new FileInfo(destPath).Length > 0;
            }
            catch
            {
                return false;
            }
        }

        static int RunProcess(string exe, string args, out string output)
        {
            output = "";
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo(exe, args)
                {
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
                using (Process p = Process.Start(psi))
                {
                    string stdout = p.StandardOutput.ReadToEnd();
                    string stderr = p.StandardError.ReadToEnd();
                    p.WaitForExit();
                    output = stdout + "\n" + stderr;
                    return p.ExitCode;
                }
            }
            catch (Exception ex)
            {
                output = ex.Message;
                return -1;
            }
        }

        static void CopyDirectory(string sourceDir, string targetDir)
        {
            Directory.CreateDirectory(targetDir);
            foreach (string file in Directory.GetFiles(sourceDir))
            {
                string dest = Path.Combine(targetDir, Path.GetFileName(file));
                File.Copy(file, dest, true);
            }
            foreach (string subDir in Directory.GetDirectories(sourceDir))
            {
                string destSub = Path.Combine(targetDir, Path.GetFileName(subDir));
                CopyDirectory(subDir, destSub);
            }
        }

        static string EscapeJson(string str)
        {
            if (string.IsNullOrEmpty(str)) return "";
            return str.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        static void Log(string logFile, string msg)
        {
            try
            {
                File.AppendAllText(logFile, string.Format("[{0:yyyy-MM-dd HH:mm:ss}] {1}\n", DateTime.Now, msg));
            }
            catch { }
        }
    }
}
