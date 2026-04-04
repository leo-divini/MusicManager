using System.Windows.Controls;
using MusicManager.ViewModels;
using MusicManager.Services;

namespace MusicManager.Views
{
    public partial class DeviceTab : UserControl
    {
        public DeviceTab()
        {
            InitializeComponent();
        }

        /// <summary>Allows MainWindow to inject the shared DeviceMonitor.</summary>
        public void SetDeviceMonitor(DeviceMonitor monitor)
        {
            if (DataContext is DeviceViewModel vm)
                vm.SetDeviceMonitor(monitor);
        }
    }
}
