using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Input;
using MusicManager.Models;
using MusicManager.Services;
using Newtonsoft.Json.Linq;

namespace MusicManager.ViewModels
{
    public class DownloadViewModel : BaseViewModel
    {
        private readonly PythonBridge _bridge = new();

        // ── Properties ──────────────────────────────────────────────────────────

        private string _urlInput = string.Empty;
        public string UrlInput
        {
            get => _urlInput;
            set => SetProperty(ref _urlInput, value);
        }

        private bool _isQueueRunning;
        public bool IsQueueRunning
        {
            get => _isQueueRunning;
            set
            {
                SetProperty(ref _isQueueRunning, value);
                OnPropertyChanged(nameof(CanStartQueue));
            }
        }

        private bool _isPaused;
        public bool IsPaused
        {
            get => _isPaused;
            set => SetProperty(ref _isPaused, value);
        }

        public bool CanStartQueue => !IsQueueRunning && QueueItems.Any(q => q.Status == "queued");

        public ObservableCollection<QueueItem> QueueItems { get; } = new();

        // ── Commands ─────────────────────────────────────────────────────────────

        public ICommand AddCommand        { get; }
        public ICommand SearchCommand     { get; }
        public ICommand StartQueueCommand { get; }
        public ICommand PauseCommand      { get; }
        public ICommand SyncAllCommand    { get; }
        public ICommand RetryCommand      { get; }

        public DownloadViewModel()
        {
            AddCommand        = new RelayCommand(_ => AddToQueue(),    _ => !string.IsNullOrWhiteSpace(UrlInput));
            SearchCommand     = new RelayCommand(_ => SearchAsync(),   _ => !string.IsNullOrWhiteSpace(UrlInput));
            StartQueueCommand = new RelayCommand(_ => StartQueue(),    _ => CanStartQueue);
            PauseCommand      = new RelayCommand(_ => PauseQueue(),    _ => IsQueueRunning);
            SyncAllCommand    = new RelayCommand(_ => SyncAllAsync());
            RetryCommand      = new RelayCommand(item => RetryItem(item as QueueItem));

            QueueItems.CollectionChanged += (_, _) => OnPropertyChanged(nameof(CanStartQueue));
        }

        // ── Actions ───────────────────────────────────────────────────────────────

        private void AddToQueue()
        {
            if (string.IsNullOrWhiteSpace(UrlInput)) return;

            var item = new QueueItem
            {
                Id        = Guid.NewGuid().ToString(),
                Url       = UrlInput.Trim(),
                Name      = UrlInput.Trim(),
                Type      = DetectType(UrlInput.Trim()),
                Status    = "queued",
                Progress  = 0,
                DateAdded = DateTime.Now
            };

            QueueItems.Add(item);
            UrlInput = string.Empty;
            OnPropertyChanged(nameof(CanStartQueue));
        }

        private async void SearchAsync()
        {
            if (string.IsNullOrWhiteSpace(UrlInput)) return;

            try
            {
                string output = await _bridge.RunCommandAsync($"--search \"{UrlInput.Trim()}\"");
                var json = JArray.Parse(output);
                foreach (var obj in json)
                {
                    Application.Current.Dispatcher.Invoke(() =>
                    {
                        var item = new QueueItem
                        {
                            Id        = Guid.NewGuid().ToString(),
                            Url       = obj["url"]?.ToString() ?? string.Empty,
                            Name      = obj["name"]?.ToString() ?? "Unknown",
                            Type      = obj["type"]?.ToString() ?? "track",
                            Status    = "queued",
                            Progress  = 0,
                            DateAdded = DateTime.Now
                        };
                        QueueItems.Add(item);
                    });
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Errore ricerca: {ex.Message}", "Errore", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }

        private async void StartQueue()
        {
            IsQueueRunning = true;
            IsPaused       = false;

            var pending = QueueItems.Where(q => q.Status == "queued").ToList();

            foreach (var item in pending)
            {
                if (IsPaused) break;

                item.Status = "downloading";
                item.Progress = 0;

                try
                {
                    await _bridge.RunCommandWithProgressAsync(
                        $"--download \"{item.Url}\"",
                        line =>
                        {
                            try
                            {
                                var obj = JObject.Parse(line);
                                if (obj["progress"] is not null)
                                {
                                    Application.Current.Dispatcher.Invoke(() =>
                                    {
                                        item.Progress = obj["progress"]!.Value<int>();
                                    });
                                }
                                if (obj["name"] is not null)
                                {
                                    Application.Current.Dispatcher.Invoke(() =>
                                    {
                                        item.Name = obj["name"]!.ToString();
                                    });
                                }
                            }
                            catch { /* non-JSON progress lines are ignored */ }
                        });

                    Application.Current.Dispatcher.Invoke(() =>
                    {
                        item.Status   = "done";
                        item.Progress = 100;
                    });
                }
                catch
                {
                    Application.Current.Dispatcher.Invoke(() => item.Status = "error");
                }
            }

            IsQueueRunning = false;
            OnPropertyChanged(nameof(CanStartQueue));
        }

        private void PauseQueue()
        {
            IsPaused = true;
        }

        private async void SyncAllAsync()
        {
            try
            {
                await _bridge.RunCommandAsync("--sync");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Errore sincronizzazione: {ex.Message}", "Errore", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }

        private void RetryItem(QueueItem? item)
        {
            if (item is null) return;
            item.Status   = "queued";
            item.Progress = 0;
            OnPropertyChanged(nameof(CanStartQueue));
        }

        private static string DetectType(string url)
        {
            if (url.Contains("artist"))   return "artist";
            if (url.Contains("album"))    return "album";
            if (url.Contains("playlist")) return "playlist";
            if (url.Contains("track"))    return "track";
            return "artist";
        }
    }

    // ── RelayCommand ──────────────────────────────────────────────────────────────

    internal sealed class RelayCommand : ICommand
    {
        private readonly Action<object?> _execute;
        private readonly Func<object?, bool>? _canExecute;

        public RelayCommand(Action<object?> execute, Func<object?, bool>? canExecute = null)
        {
            _execute    = execute;
            _canExecute = canExecute;
        }

        public event EventHandler? CanExecuteChanged
        {
            add    => CommandManager.RequerySuggested += value;
            remove => CommandManager.RequerySuggested -= value;
        }

        public bool CanExecute(object? parameter) => _canExecute?.Invoke(parameter) ?? true;
        public void Execute(object? parameter)     => _execute(parameter);
    }
}
