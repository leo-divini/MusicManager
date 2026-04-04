using System.IO;
using System.Windows;

namespace MusicManager.Services
{
    /// <summary>
    /// Handles WPF drag-and-drop events and extracts a flat list of audio file
    /// paths from the dropped items (files or folders, one level deep).
    /// </summary>
    public static class FileDropHandler
    {
        /// <summary>Supported audio file extensions (lowercase, with leading dot).</summary>
        public static readonly IReadOnlySet<string> AudioExtensions =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            {
                ".flac", ".mp3", ".m4a", ".opus", ".ogg", ".wav"
            };

        /// <summary>
        /// Extracts audio file paths from a <see cref="DragEventArgs"/>.
        /// Accepts both individual files and folders (top-level files only, not recursive).
        /// </summary>
        /// <returns>An ordered list of audio file paths found in the drop payload.</returns>
        public static IReadOnlyList<string> HandleDrop(DragEventArgs e)
        {
            if (!e.Data.GetDataPresent(DataFormats.FileDrop))
                return Array.Empty<string>();

            var dropped = e.Data.GetData(DataFormats.FileDrop) as string[];
            if (dropped is null || dropped.Length == 0)
                return Array.Empty<string>();

            var result = new List<string>();

            foreach (string path in dropped)
            {
                if (File.Exists(path))
                {
                    if (IsAudioFile(path))
                        result.Add(path);
                }
                else if (Directory.Exists(path))
                {
                    // Top-level files inside the folder only (not recursive)
                    foreach (string file in Directory.GetFiles(path))
                    {
                        if (IsAudioFile(file))
                            result.Add(file);
                    }
                }
            }

            return result;
        }

        /// <summary>
        /// Returns true when <paramref name="filePath"/> has a supported audio extension.
        /// </summary>
        public static bool IsAudioFile(string filePath) =>
            AudioExtensions.Contains(Path.GetExtension(filePath));
    }
}
