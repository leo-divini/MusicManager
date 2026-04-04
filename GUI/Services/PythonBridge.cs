using System.Diagnostics;
using System.Text;

namespace MusicManager.Services
{
    /// <summary>
    /// Launches the Python backend (main.py) as a subprocess and communicates
    /// via stdin/stdout using JSON lines.
    /// </summary>
    public class PythonBridge
    {
        /// <summary>
        /// Path to the Python executable. Defaults to "python" (assumes it is on PATH).
        /// Override before calling any method if the executable lives elsewhere.
        /// </summary>
        public string PythonExecutable { get; set; } = "python";

        /// <summary>
        /// Path to the Python entry-point script relative to the executable, or absolute.
        /// </summary>
        public string ScriptPath { get; set; } = "main.py";

        /// <summary>
        /// Raised once per output line received from the subprocess.
        /// Useful for global logging.
        /// </summary>
        public event Action<string>? OutputReceived;

        // ── Public API ────────────────────────────────────────────────────────────

        /// <summary>
        /// Runs "python main.py &lt;args&gt;", waits for the process to finish, and returns
        /// the full stdout as a string.
        /// </summary>
        public async Task<string> RunCommandAsync(string args)
        {
            var sb  = new StringBuilder();
            await RunInternalAsync(args, line =>
            {
                sb.AppendLine(line);
                OutputReceived?.Invoke(line);
            });
            return sb.ToString().Trim();
        }

        /// <summary>
        /// Runs "python main.py &lt;args&gt;" and invokes <paramref name="onOutput"/> for every
        /// line printed to stdout. Useful for streaming progress updates.
        /// </summary>
        public async Task RunCommandWithProgressAsync(string args, Action<string> onOutput)
        {
            await RunInternalAsync(args, line =>
            {
                onOutput(line);
                OutputReceived?.Invoke(line);
            });
        }

        // ── Internals ─────────────────────────────────────────────────────────────

        private Task RunInternalAsync(string args, Action<string> lineHandler)
        {
            var tcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);

            var psi = new ProcessStartInfo
            {
                FileName               = PythonExecutable,
                Arguments              = $"\"{ScriptPath}\" {args}",
                UseShellExecute        = false,
                RedirectStandardOutput = true,
                RedirectStandardError  = true,
                CreateNoWindow         = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding  = Encoding.UTF8
            };

            var process = new Process { StartInfo = psi, EnableRaisingEvents = true };

            process.OutputDataReceived += (_, e) =>
            {
                if (e.Data is not null)
                    lineHandler(e.Data);
            };

            process.ErrorDataReceived += (_, e) =>
            {
                // Forward stderr lines as output so the caller can log them
                if (e.Data is not null)
                    OutputReceived?.Invoke($"[stderr] {e.Data}");
            };

            process.Exited += (_, _) =>
            {
                process.WaitForExit(); // ensure all async output has been flushed
                int exitCode = process.ExitCode;
                process.Dispose();

                if (exitCode == 0)
                    tcs.TrySetResult(true);
                else
                    tcs.TrySetException(new InvalidOperationException(
                        $"Python process exited with code {exitCode}."));
            };

            try
            {
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
            }
            catch (Exception ex)
            {
                tcs.TrySetException(new InvalidOperationException(
                    $"Failed to start Python process: {ex.Message}", ex));
            }

            return tcs.Task;
        }
    }
}
