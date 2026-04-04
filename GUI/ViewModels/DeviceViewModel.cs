using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Input;
using MusicManager.Models;
using MusicManager.Services;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace MusicManager.ViewModels
{
    public class DeviceViewModel : BaseViewModel
    {
        private readonly PythonBridge _bridge = new();
        private DeviceMonitor? _deviceMonitor;

        // ── Properties ────────────────────────────────────────────────────────────

        private string _deviceStatus = "💾 Nessun dispositivo collegato";
        public string DeviceStatus
        {
            get => _deviceStatus;
            set => SetProperty(ref _deviceStatus, value);
        }

        public ObservableCollection<PlaylistExportItem> Playlists { get; } = new();

        public int SelectedPlaylistCount => Playlists.Count(p => p.IsSelected);

        public string TotalSelectedSize
        {
            get
            {
                double total = Playlists.Where(p => p.IsSelected).Sum(p => p.EstimatedSizeMb);
                return total >= 1024
                    ? $"{total / 1024.0:F2} GB"
                    : $"{total:F1} MB";
            }
        }

        public bool CanExport => Playlists.Any(p => p.IsSelected) && IsDeviceConnected;

        private bool _isDeviceConnected;
        public bool IsDeviceConnected
        {
            get => _isDeviceConnected;
            private set
            {
                SetProperty(ref _isDeviceConnected, value);
                OnPropertyChanged(nameof(CanExport));
            }
        }

        private string _connectedDrive = string.Empty;

        // ── Commands ─────────────────────────────────────────────────────────────

        public ICommand RefreshCommand { get; }
        public ICommand ExportCommand  { get; }

        public DeviceViewModel()
        {
            RefreshCommand = new RelayCommand(_ => RefreshAsync());
            ExportCommand  = new RelayCommand(_ => ExportAsync(), _ => CanExport);

            LoadPlaylistsAsync();
        }

        // ── DeviceMonitor Wiring ──────────────────────────────────────────────────

        public void SetDeviceMonitor(DeviceMonitor monitor)
        {
            if (_deviceMonitor is not null)
            {
                _deviceMonitor.DeviceConnected    -= OnDeviceConnected;
                _deviceMonitor.DeviceDisconnected -= OnDeviceDisconnected;
            }

            _deviceMonitor = monitor;
            _deviceMonitor.DeviceConnected    += OnDeviceConnected;
            _deviceMonitor.DeviceDisconnected += OnDeviceDisconnected;
        }

        private void OnDeviceConnected(string driveLetter, string label)
        {
            Application.Current.Dispatcher.Invoke(() =>
            {
                _connectedDrive  = driveLetter;
                IsDeviceConnected = true;

                double freeGb = GetFreeSpaceGb(driveLetter);
                DeviceStatus = $"💾 {driveLetter} ({label}) — {freeGb:F1} GB liberi";

                LoadPlaylistsAsync();
            });
        }

        private void OnDeviceDisconnected()
        {
            Application.Current.Dispatcher.Invoke(() =>
            {
                _connectedDrive   = string.Empty;
                IsDeviceConnected = false;
                DeviceStatus      = "💾 Nessun dispositivo collegato";

                foreach (var p in Playlists)
                    p.ExportProgress = 0;
            });
        }

        // ── Actions ───────────────────────────────────────────────────────────────

        private async void LoadPlaylistsAsync()
        {
            try
            {
                string output = await _bridge.RunCommandAsync("--list-playlists");
                var list = JsonConvert.DeserializeObject<List<PlaylistExportItem>>(output);
                if (list is null) return;

                Application.Current.Dispatcher.Invoke(() =>
                {
                    Playlists.Clear();
                    foreach (var item in list)
                    {
                        item.PropertyChanged += (_, _) =>
                        {
                            OnPropertyChanged(nameof(SelectedPlaylistCount));
                            OnPropertyChanged(nameof(TotalSelectedSize));
                            OnPropertyChanged(nameof(CanExport));
                        };
                        Playlists.Add(item);
                    }
                });
            }
            catch { /* design-time / backend unavailable */ }
        }

        private async void RefreshAsync()
        {
            LoadPlaylistsAsync();

            if (!string.IsNullOrEmpty(_connectedDrive))
            {
                double freeGb = GetFreeSpaceGb(_connectedDrive);
                DeviceStatus = DeviceStatus.Split("—")[0].TrimEnd() + $" — {freeGb:F1} GB liberi";
            }

            await Task.CompletedTask;
        }

        private async void ExportAsync()
        {
            var selected = Playlists.Where(p => p.IsSelected).ToList();
            if (!selected.Any()) return;

            foreach (var playlist in selected)
            {
                playlist.ExportProgress = 0;

                try
                {
                    await _bridge.RunCommandWithProgressAsync(
                        $"--export \"{playlist.Name}\" --drive \"{_connectedDrive}\"",
                        line =>
                        {
                            try
                            {
                                var obj = Newtonsoft.Json.Linq.JObject.Parse(line);
                                if (obj["progress"] is not null)
                                {
                                    Application.Current.Dispatcher.Invoke(() =>
                                        playlist.ExportProgress = obj["progress"]!.Value<int>());
                                }
                            }
                            catch { }
                        });

                    Application.Current.Dispatcher.Invoke(() => playlist.ExportProgress = 100);
                }
                catch (Exception ex)
                {
                    MessageBox.Show($"Errore esportazione \"{playlist.Name}\": {ex.Message}",
                        "Errore", MessageBoxButton.OK, MessageBoxImage.Error);
                }
            }
        }

        private static double GetFreeSpaceGb(string driveLetter)
        {
            try
            {
                var drive = new System.IO.DriveInfo(driveLetter.TrimEnd('\\'));
                return drive.AvailableFreeSpace / (1024.0 * 1024 * 1024);
            }
            catch
            {
                return 0;
            }
        }
    }

    // ── PlaylistExportItem ────────────────────────────────────────────────────────

    public class PlaylistExportItem : BaseViewModel
    {
        private string _name = string.Empty;
        public string Name
        {
            get => _name;
            set => SetProperty(ref _name, value);
        }

        private int _trackCount;
        public int TrackCount
        {
            get => _trackCount;
            set => SetProperty(ref _trackCount, value);
        }

        private double _estimatedSizeMb;
        public double EstimatedSizeMb
        {
            get => _estimatedSizeMb;
            set => SetProperty(ref _estimatedSizeMb, value);
        }

        private bool _isSelected;
        public bool IsSelected
        {
            get => _isSelected;
            set => SetProperty(ref _isSelected, value);
        }

        private int _exportProgress;
        public int ExportProgress
        {
            get => _exportProgress;
            set => SetProperty(ref _exportProgress, value);
        }
    }
}
