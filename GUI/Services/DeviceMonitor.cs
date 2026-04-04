using System.Management;

namespace MusicManager.Services
{
    /// <summary>
    /// Uses WMI ManagementEventWatcher to detect USB storage drive insertion
    /// and removal. Raises <see cref="DeviceConnected"/> and
    /// <see cref="DeviceDisconnected"/> events.
    /// </summary>
    public class DeviceMonitor : IDisposable
    {
        // ── Public Events ─────────────────────────────────────────────────────────

        /// <summary>
        /// Fired when a removable drive is inserted.
        /// Parameters: driveLetter (e.g. "D:\"), driveLabel (e.g. "TS1802").
        /// </summary>
        public event Action<string, string>? DeviceConnected;

        /// <summary>Fired when the monitored drive is removed.</summary>
        public event Action? DeviceDisconnected;

        // ── Configuration ─────────────────────────────────────────────────────────

        /// <summary>
        /// When non-empty, only a drive whose volume label equals this value
        /// will trigger <see cref="DeviceConnected"/>. Set to empty to accept
        /// any removable drive.
        /// </summary>
        public string TargetLabel { get; set; } = "TS1802";

        // ── Private Fields ────────────────────────────────────────────────────────

        private ManagementEventWatcher? _insertWatcher;
        private ManagementEventWatcher? _removeWatcher;
        private string? _currentDriveLetter;
        private bool _disposed;

        // ── Lifecycle ─────────────────────────────────────────────────────────────

        /// <summary>Starts listening for device events.</summary>
        public void Start()
        {
            try
            {
                // Win32_VolumeChangeEvent fires on logical volume arrival/removal
                var insertQuery = new WqlEventQuery(
                    "SELECT * FROM Win32_VolumeChangeEvent WHERE EventType = 2");

                var removeQuery = new WqlEventQuery(
                    "SELECT * FROM Win32_VolumeChangeEvent WHERE EventType = 3");

                _insertWatcher = new ManagementEventWatcher(insertQuery);
                _insertWatcher.EventArrived += OnInsertEvent;
                _insertWatcher.Start();

                _removeWatcher = new ManagementEventWatcher(removeQuery);
                _removeWatcher.EventArrived += OnRemoveEvent;
                _removeWatcher.Start();

                // Check for already-connected matching drive at startup
                CheckExistingDevices();
            }
            catch
            {
                // WMI may be unavailable in some environments (e.g. containers).
                // Fail silently — the UI will simply not auto-detect drives.
            }
        }

        /// <summary>Stops listening and releases resources.</summary>
        public void Stop()
        {
            Dispose();
        }

        // ── Event Handlers ────────────────────────────────────────────────────────

        private void OnInsertEvent(object sender, EventArrivedEventArgs e)
        {
            try
            {
                string driveLetter = e.NewEvent.Properties["DriveName"].Value?.ToString()
                                     ?? string.Empty;

                if (string.IsNullOrEmpty(driveLetter)) return;

                string label = GetVolumeLabel(driveLetter);

                if (!string.IsNullOrEmpty(TargetLabel) &&
                    !label.Equals(TargetLabel, StringComparison.OrdinalIgnoreCase))
                    return;

                _currentDriveLetter = driveLetter;
                DeviceConnected?.Invoke(driveLetter, label);
            }
            catch { /* ignore transient WMI errors */ }
        }

        private void OnRemoveEvent(object sender, EventArrivedEventArgs e)
        {
            try
            {
                string driveLetter = e.NewEvent.Properties["DriveName"].Value?.ToString()
                                     ?? string.Empty;

                if (string.IsNullOrEmpty(driveLetter)) return;

                if (_currentDriveLetter is not null &&
                    !_currentDriveLetter.Equals(driveLetter, StringComparison.OrdinalIgnoreCase))
                    return;

                _currentDriveLetter = null;
                DeviceDisconnected?.Invoke();
            }
            catch { }
        }

        private void CheckExistingDevices()
        {
            try
            {
                using var searcher = new ManagementObjectSearcher(
                    "SELECT * FROM Win32_LogicalDisk WHERE DriveType = 2");

                foreach (ManagementObject disk in searcher.Get())
                {
                    string letter = disk["DeviceID"]?.ToString() ?? string.Empty;
                    string label  = disk["VolumeName"]?.ToString() ?? string.Empty;

                    if (!string.IsNullOrEmpty(TargetLabel) &&
                        !label.Equals(TargetLabel, StringComparison.OrdinalIgnoreCase))
                        continue;

                    _currentDriveLetter = letter + "\\";
                    DeviceConnected?.Invoke(_currentDriveLetter, label);
                    break;
                }
            }
            catch { }
        }

        // ── Helpers ───────────────────────────────────────────────────────────────

        private static string GetVolumeLabel(string driveLetter)
        {
            try
            {
                using var searcher = new ManagementObjectSearcher(
                    $"SELECT VolumeName FROM Win32_LogicalDisk WHERE DeviceID = '{driveLetter.TrimEnd('\\')}:'");

                foreach (ManagementObject disk in searcher.Get())
                    return disk["VolumeName"]?.ToString() ?? string.Empty;
            }
            catch { }
            return string.Empty;
        }

        // ── IDisposable ───────────────────────────────────────────────────────────

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;

            if (_insertWatcher is not null)
            {
                _insertWatcher.Stop();
                _insertWatcher.Dispose();
                _insertWatcher = null;
            }

            if (_removeWatcher is not null)
            {
                _removeWatcher.Stop();
                _removeWatcher.Dispose();
                _removeWatcher = null;
            }
        }
    }
}
