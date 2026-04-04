using System.Windows;
using System.Windows.Controls;
using MusicManager.Services;
using MusicManager.ViewModels;

namespace MusicManager.Views
{
    public partial class PlaylistTab : UserControl
    {
        public PlaylistTab()
        {
            InitializeComponent();
        }

        private void UserControl_DragEnter(object sender, DragEventArgs e)
        {
            if (e.Data.GetDataPresent(DataFormats.FileDrop))
            {
                e.Effects = DragDropEffects.Copy;
                if (DataContext is PlaylistViewModel vm)
                    vm.IsDragOver = true;
            }
            else
            {
                e.Effects = DragDropEffects.None;
            }
            e.Handled = true;
        }

        private void UserControl_DragOver(object sender, DragEventArgs e)
        {
            if (e.Data.GetDataPresent(DataFormats.FileDrop))
                e.Effects = DragDropEffects.Copy;
            else
                e.Effects = DragDropEffects.None;
            e.Handled = true;
        }

        private void UserControl_Drop(object sender, DragEventArgs e)
        {
            if (DataContext is PlaylistViewModel vm)
            {
                vm.IsDragOver = false;
                var files = FileDropHandler.HandleDrop(e);
                foreach (var file in files)
                    vm.AddTrackFromFile(file);
            }
            e.Handled = true;
        }
    }
}
