using MusicManager.ViewModels;

namespace MusicManager.Models
{
    /// <summary>Represents a single item in the download queue.</summary>
    public class QueueItem : BaseViewModel
    {
        public string Id { get; set; } = Guid.NewGuid().ToString();

        private string _url = string.Empty;
        public string Url
        {
            get => _url;
            set => SetProperty(ref _url, value);
        }

        private string _name = string.Empty;
        public string Name
        {
            get => _name;
            set => SetProperty(ref _name, value);
        }

        /// <summary>artist | album | track | playlist</summary>
        private string _type = "track";
        public string Type
        {
            get => _type;
            set => SetProperty(ref _type, value);
        }

        /// <summary>queued | downloading | done | error</summary>
        private string _status = "queued";
        public string Status
        {
            get => _status;
            set
            {
                SetProperty(ref _status, value);
                OnPropertyChanged(nameof(StatusIcon));
                OnPropertyChanged(nameof(IsDownloading));
            }
        }

        private int _progress;
        public int Progress
        {
            get => _progress;
            set => SetProperty(ref _progress, value);
        }

        public DateTime DateAdded { get; set; } = DateTime.Now;

        /// <summary>Derived emoji icon based on Status.</summary>
        public string StatusIcon => Status switch
        {
            "done"        => "✅",
            "downloading" => "⏳",
            "queued"      => "🕐",
            "error"       => "❌",
            _             => "❓"
        };

        public bool IsDownloading => Status == "downloading";
    }
}
