using System.Windows;
using MusicManager.Services;
using MusicManager.ViewModels;

namespace MusicManager
{
    public partial class MainWindow : Window
    {
        private readonly DeviceMonitor _deviceMonitor;

        public MainWindow()
        {
            InitializeComponent();

            _deviceMonitor = new DeviceMonitor();
            _deviceMonitor.DeviceConnected    += OnDeviceConnected;
            _deviceMonitor.DeviceDisconnected += OnDeviceDisconnected;
            _deviceMonitor.Start();

            Loaded += OnWindowLoaded;
        }

        private void OnWindowLoaded(object sender, RoutedEventArgs e)
        {
            // DataContext is guaranteed to be fully initialized after XAML load
            if (DeviceTabView.DataContext is DeviceViewModel vm)
                vm.SetDeviceMonitor(_deviceMonitor);
        }

        private void OnDeviceConnected(string driveLetter, string label)
        {
            Dispatcher.Invoke(() =>
            {
                DeviceStatusText.Text = $"💾 {driveLetter} ({label}) collegato";
                SetStatus($"Dispositivo {label} ({driveLetter}) rilevato.");
            });
        }

        private void OnDeviceDisconnected()
        {
            Dispatcher.Invoke(() =>
            {
                DeviceStatusText.Text = "Nessun dispositivo collegato";
                SetStatus("Dispositivo rimosso.");
            });
        }

        public void SetStatus(string message)
        {
            StatusText.Text = message;
        }

        protected override void OnClosed(EventArgs e)
        {
            _deviceMonitor.Stop();
            base.OnClosed(e);
        }
    }
}
