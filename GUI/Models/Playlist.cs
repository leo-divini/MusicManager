using MusicManager.ViewModels;

namespace MusicManager.Models
{
    /// <summary>Represents a music playlist managed by the backend.</summary>
    public class PlaylistInfo : BaseViewModel
    {
        private string _name = string.Empty;
        public string Name
        {
            get => _name;
            set => SetProperty(ref _name, value);
        }

        /// <summary>Origin source, e.g. "spotify", "local", etc.</summary>
        private string _source = string.Empty;
        public string Source
        {
            get => _source;
            set => SetProperty(ref _source, value);
        }

        /// <summary>Optional cover art path or URL.</summary>
        private string? _cover;
        public string? Cover
        {
            get => _cover;
            set => SetProperty(ref _cover, value);
        }

        private int _trackCount;
        public int TrackCount
        {
            get => _trackCount;
            set => SetProperty(ref _trackCount, value);
        }

        /// <summary>Estimated total size in megabytes.</summary>
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

        public override string ToString() => Name;
    }
}
