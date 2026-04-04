using MusicManager.ViewModels;

namespace MusicManager.Models
{
    /// <summary>Represents a single audio track inside a playlist.</summary>
    public class Track : BaseViewModel
    {
        private int _position;
        public int Position
        {
            get => _position;
            set => SetProperty(ref _position, value);
        }

        private string _title = string.Empty;
        public string Title
        {
            get => _title;
            set => SetProperty(ref _title, value);
        }

        private string _artist = string.Empty;
        public string Artist
        {
            get => _artist;
            set => SetProperty(ref _artist, value);
        }

        /// <summary>Filename or Spotify/source label.</summary>
        private string _origin = string.Empty;
        public string Origin
        {
            get => _origin;
            set => SetProperty(ref _origin, value);
        }

        /// <summary>Full path to the audio file on disk.</summary>
        private string _playlistPath = string.Empty;
        public string PlaylistPath
        {
            get => _playlistPath;
            set => SetProperty(ref _playlistPath, value);
        }

        public DateTime Added { get; set; } = DateTime.Now;

        public override string ToString() =>
            string.IsNullOrWhiteSpace(Artist) ? Title : $"{Artist} – {Title}";
    }
}
