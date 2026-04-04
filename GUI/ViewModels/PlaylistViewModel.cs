using System.Collections.ObjectModel;
using System.IO;
using System.Windows;
using System.Windows.Input;
using Microsoft.Win32;
using MusicManager.Models;
using MusicManager.Services;
using Newtonsoft.Json;

namespace MusicManager.ViewModels
{
    public class PlaylistViewModel : BaseViewModel
    {
        private readonly PythonBridge _bridge = new();

        // ── Properties ───────────────────────────────────────────────────────────

        public ObservableCollection<PlaylistInfo> Playlists { get; } = new();

        private PlaylistInfo? _selectedPlaylist;
        public PlaylistInfo? SelectedPlaylist
        {
            get => _selectedPlaylist;
            set
            {
                SetProperty(ref _selectedPlaylist, value);
                OnPropertyChanged(nameof(HasSelectedPlaylist));
                LoadTracksForPlaylist(value);
            }
        }

        public ObservableCollection<Track> Tracks { get; } = new();

        private Track? _selectedTrack;
        public Track? SelectedTrack
        {
            get => _selectedTrack;
            set => SetProperty(ref _selectedTrack, value);
        }

        public bool HasSelectedPlaylist => SelectedPlaylist is not null;
        public bool HasTracks           => Tracks.Count > 0;
        public int  TrackCount          => Tracks.Count;

        private bool _isDragOver;
        public bool IsDragOver
        {
            get => _isDragOver;
            set => SetProperty(ref _isDragOver, value);
        }

        // ── Commands ─────────────────────────────────────────────────────────────

        public ICommand NewPlaylistCommand    { get; }
        public ICommand DeletePlaylistCommand { get; }
        public ICommand AddFilesCommand       { get; }
        public ICommand AddFolderCommand      { get; }
        public ICommand RemoveTrackCommand    { get; }
        public ICommand MoveUpCommand         { get; }
        public ICommand MoveDownCommand       { get; }

        public PlaylistViewModel()
        {
            NewPlaylistCommand    = new RelayCommand(_ => CreatePlaylist());
            DeletePlaylistCommand = new RelayCommand(_ => DeletePlaylist(),   _ => HasSelectedPlaylist);
            AddFilesCommand       = new RelayCommand(_ => AddFiles(),         _ => HasSelectedPlaylist);
            AddFolderCommand      = new RelayCommand(_ => AddFolder(),        _ => HasSelectedPlaylist);
            RemoveTrackCommand    = new RelayCommand(t  => RemoveTrack(t as Track));
            MoveUpCommand         = new RelayCommand(_ => MoveUp(),           _ => SelectedTrack is not null);
            MoveDownCommand       = new RelayCommand(_ => MoveDown(),         _ => SelectedTrack is not null);

            Tracks.CollectionChanged += (_, _) =>
            {
                OnPropertyChanged(nameof(HasTracks));
                OnPropertyChanged(nameof(TrackCount));
                RefreshPositions();
            };

            LoadPlaylistsAsync();
        }

        // ── Playlist Management ───────────────────────────────────────────────────

        private async void LoadPlaylistsAsync()
        {
            try
            {
                string output = await _bridge.RunCommandAsync("--list-playlists");
                var list = JsonConvert.DeserializeObject<List<PlaylistInfo>>(output);
                if (list is null) return;

                Application.Current.Dispatcher.Invoke(() =>
                {
                    Playlists.Clear();
                    foreach (var p in list)
                        Playlists.Add(p);
                });
            }
            catch { /* backend may not be available at design time */ }
        }

        private async void CreatePlaylist()
        {
            var dialog = new InputDialog("Nuova Playlist", "Nome della playlist:");
            if (dialog.ShowDialog() != true) return;

            string name = dialog.InputText.Trim();
            if (string.IsNullOrEmpty(name)) return;

            try
            {
                await _bridge.RunCommandAsync($"--create-playlist \"{name}\"");
                LoadPlaylistsAsync();
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Errore creazione: {ex.Message}", "Errore", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }

        private async void DeletePlaylist()
        {
            if (SelectedPlaylist is null) return;

            var result = MessageBox.Show(
                $"Eliminare la playlist \"{SelectedPlaylist.Name}\"?",
                "Conferma", MessageBoxButton.YesNo, MessageBoxImage.Warning);

            if (result != MessageBoxResult.Yes) return;

            try
            {
                await _bridge.RunCommandAsync($"--delete-playlist \"{SelectedPlaylist.Name}\"");
                Playlists.Remove(SelectedPlaylist);
                SelectedPlaylist = null;
                Tracks.Clear();
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Errore eliminazione: {ex.Message}", "Errore", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }

        // ── Track Management ──────────────────────────────────────────────────────

        private async void LoadTracksForPlaylist(PlaylistInfo? playlist)
        {
            Tracks.Clear();
            if (playlist is null) return;

            try
            {
                string output = await _bridge.RunCommandAsync($"--get-playlist \"{playlist.Name}\"");
                var list = JsonConvert.DeserializeObject<List<Track>>(output);
                if (list is null) return;

                Application.Current.Dispatcher.Invoke(() =>
                {
                    foreach (var t in list)
                        Tracks.Add(t);
                    RefreshPositions();
                });
            }
            catch { /* ignore if backend not available */ }
        }

        private void AddFiles()
        {
            var dlg = new OpenFileDialog
            {
                Multiselect = true,
                Filter      = "File audio|*.flac;*.mp3;*.m4a;*.opus;*.ogg;*.wav|Tutti i file|*.*",
                Title       = "Seleziona file audio"
            };

            if (dlg.ShowDialog() != true) return;

            foreach (var file in dlg.FileNames)
                AddTrackFromFile(file);
        }

        private void AddFolder()
        {
            var dialog = new Microsoft.Win32.OpenFolderDialog
            {
                Title = "Seleziona una cartella con file audio"
            };

            if (dialog.ShowDialog() != true) return;

            var extensions = FileDropHandler.AudioExtensions;
            foreach (var file in Directory.GetFiles(dialog.FolderName)
                         .Where(f => extensions.Contains(Path.GetExtension(f).ToLowerInvariant())))
            {
                AddTrackFromFile(file);
            }
        }

        public void AddTrackFromFile(string filePath)
        {
            if (SelectedPlaylist is null) return;

            var ext  = Path.GetExtension(filePath).ToLowerInvariant();
            if (!FileDropHandler.AudioExtensions.Contains(ext)) return;

            var name = Path.GetFileNameWithoutExtension(filePath);
            var parts = name.Split(" - ", 2, StringSplitOptions.TrimEntries);

            var track = new Track
            {
                Position     = Tracks.Count + 1,
                Artist       = parts.Length > 1 ? parts[0] : string.Empty,
                Title        = parts.Length > 1 ? parts[1] : name,
                Origin       = Path.GetFileName(filePath),
                PlaylistPath = filePath,
                Added        = DateTime.Now
            };

            Tracks.Add(track);
            SavePlaylistAsync();
        }

        private void RemoveTrack(Track? track)
        {
            if (track is null) return;
            Tracks.Remove(track);
            SavePlaylistAsync();
        }

        private void MoveUp()
        {
            if (SelectedTrack is null) return;
            int idx = Tracks.IndexOf(SelectedTrack);
            if (idx <= 0) return;
            Tracks.Move(idx, idx - 1);
            RefreshPositions();
            SavePlaylistAsync();
        }

        private void MoveDown()
        {
            if (SelectedTrack is null) return;
            int idx = Tracks.IndexOf(SelectedTrack);
            if (idx < 0 || idx >= Tracks.Count - 1) return;
            Tracks.Move(idx, idx + 1);
            RefreshPositions();
            SavePlaylistAsync();
        }

        private void RefreshPositions()
        {
            for (int i = 0; i < Tracks.Count; i++)
                Tracks[i].Position = i + 1;
        }

        private async void SavePlaylistAsync()
        {
            if (SelectedPlaylist is null) return;

            try
            {
                string json   = JsonConvert.SerializeObject(Tracks.Select(t => t.PlaylistPath));
                await _bridge.RunCommandAsync($"--save-playlist \"{SelectedPlaylist.Name}\" --tracks '{json}'");
            }
            catch { /* silently ignore if backend not available */ }
        }
    }

    // ── Minimal InputDialog ───────────────────────────────────────────────────────

    internal class InputDialog : Window
    {
        private readonly System.Windows.Controls.TextBox _tb;
        public string InputText => _tb.Text;

        public InputDialog(string title, string prompt)
        {
            Title  = title;
            Width  = 360;
            Height = 150;
            WindowStartupLocation = WindowStartupLocation.CenterOwner;
            ResizeMode = ResizeMode.NoResize;
            Background = (System.Windows.Media.Brush)Application.Current.Resources["BackgroundBrush"];

            var panel = new System.Windows.Controls.StackPanel { Margin = new Thickness(16) };

            var lbl = new System.Windows.Controls.Label
            {
                Content    = prompt,
                Foreground = (System.Windows.Media.Brush)Application.Current.Resources["ForegroundBrush"]
            };

            _tb = new System.Windows.Controls.TextBox { Margin = new Thickness(0, 4, 0, 12) };

            var btn = new System.Windows.Controls.Button { Content = "OK", Width = 80, HorizontalAlignment = HorizontalAlignment.Right };
            btn.Click += (_, _) => { DialogResult = true; Close(); };

            panel.Children.Add(lbl);
            panel.Children.Add(_tb);
            panel.Children.Add(btn);
            Content = panel;

            _tb.Focus();
        }
    }
}
