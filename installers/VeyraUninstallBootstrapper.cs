using System;
using System.IO;
using System.Net;

namespace VeyraUninstaller
{
    class Program
    {
        static int Main(string[] args)
        {
            Console.Title = "Veyra - Uninstaller";
            Console.WriteLine("===============================================================================");
            Console.WriteLine("                        VEYRA — UNINSTALLER");
            Console.WriteLine("===============================================================================");
            Console.WriteLine();

            string appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            string targetCepDir = Path.Combine(appData, "Adobe\\CEP\\extensions\\com.speechify.speechenhancer");
            string targetUxpDir = Path.Combine(appData, "Adobe\\UXP\\Plugins\\External\\com.speechify.speechenhancer");
            string legacyCepDir = Path.Combine(appData, "Adobe\\CEP\\extensions\\com.voxforge.speechenhancer");
            string legacyUxpDir = Path.Combine(appData, "Adobe\\UXP\\Plugins\\External\\com.voxforge.speechenhancer");
            string veyraDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Veyra");

            Console.WriteLine("Stopping any active Veyra background engine process...");
            try
            {
                HttpWebRequest request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:8765/shutdown");
                request.Method = "POST";
                request.Timeout = 1500;
                using (HttpWebResponse response = (HttpWebResponse)request.GetResponse()) { }
            }
            catch { }

            Console.WriteLine("Removing Veyra from Adobe Premiere Pro extensions...");

            if (Directory.Exists(targetCepDir))
            {
                try { Directory.Delete(targetCepDir, true); Console.WriteLine("[OK] Removed from Adobe CEP extensions directory."); } catch { }
            }
            if (Directory.Exists(targetUxpDir))
            {
                try { Directory.Delete(targetUxpDir, true); Console.WriteLine("[OK] Removed from Adobe UXP plugins directory."); } catch { }
            }
            if (Directory.Exists(legacyCepDir))
            {
                try { Directory.Delete(legacyCepDir, true); } catch { }
            }
            if (Directory.Exists(legacyUxpDir))
            {
                try { Directory.Delete(legacyUxpDir, true); } catch { }
            }

            bool fullCleanup = false;
            foreach (string arg in args)
            {
                if (arg.Equals("--full-cleanup", StringComparison.OrdinalIgnoreCase))
                {
                    fullCleanup = true;
                }
            }

            if (fullCleanup && Directory.Exists(veyraDir))
            {
                try
                {
                    Directory.Delete(veyraDir, true);
                    Console.WriteLine("[OK] Fully removed private runtime and model cache from %LOCALAPPDATA%\\Veyra.");
                }
                catch (Exception ex)
                {
                    Console.WriteLine(string.Format("[WARN] Could not completely delete {0}: {1}", veyraDir, ex.Message));
                }
            }
            else
            {
                Console.WriteLine();
                Console.WriteLine("===============================================================================");
                Console.WriteLine("                     VEYRA UNINSTALLED SUCCESSFULLY!");
                Console.WriteLine("===============================================================================");
                Console.WriteLine();
                Console.WriteLine("NOTE REGARDING AI MODEL WEIGHTS & RUNTIME:");
                Console.WriteLine("Your downloaded neural model weights and private runtime in:");
                Console.WriteLine(string.Format("  {0}", veyraDir));
                Console.WriteLine("were PRESERVED so you do not need to re-download them if you reinstall.");
            }

            return 0;
        }
    }
}
