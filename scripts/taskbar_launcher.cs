using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        try
        {
            string appRoot = AppDomain.CurrentDomain.BaseDirectory;
            string script = Path.Combine(appRoot, "taskbar_launcher.ps1");
            string powershell = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.System),
                @"WindowsPowerShell\v1.0\powershell.exe");

            if (!File.Exists(script))
            {
                throw new FileNotFoundException("The game launcher script is missing.", script);
            }

            Process.Start(new ProcessStartInfo
            {
                FileName = powershell,
                Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + script + "\"",
                WorkingDirectory = appRoot,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            });
        }
        catch (Exception error)
        {
            MessageBox.Show(
                error.Message,
                "ESports Simulator launcher",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }
}
