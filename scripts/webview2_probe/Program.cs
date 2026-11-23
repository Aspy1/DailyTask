using System.Diagnostics;
using System.IO;
using System.Windows;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;

internal static class Program
{
    private const string Origin = "https://week.test/";
    private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(15);

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length != 2)
        {
            Console.Error.WriteLine("Usage: WebView2Probe <fixtures> <user-data-directory>");
            return 2;
        }

        var startup = Stopwatch.StartNew();
        var app = new Application();
        var view = new WebView2();
        var window = new Window { Title = "WebView2 week benchmark", Content = view,
                                  Width = 990, Height = 638 };
        window.Closed += (_, _) => view.Dispose();
        window.Loaded += async (_, _) =>
        {
            int exitCode = 0;
            try
            {
                var environment = await CoreWebView2Environment
                    .CreateAsync(userDataFolder: Path.GetFullPath(args[1])).WaitAsync(Timeout);
                await view.EnsureCoreWebView2Async(environment).WaitAsync(Timeout);
                var core = view.CoreWebView2;
                core.SetVirtualHostNameToFolderMapping("week.test", Path.GetFullPath(args[0]),
                                                       CoreWebView2HostResourceAccessKind.Deny);
                core.NavigationStarting += (_, navigation) =>
                    navigation.Cancel = navigation.Uri != Origin + "week-0.html"
                                        && navigation.Uri != Origin + "week-1.html";
                core.NewWindowRequested += (_, request) => request.Handled = true;
                core.PermissionRequested += (_, request) => request.State = CoreWebView2PermissionState.Deny;
                core.DownloadStarting += (_, download) => download.Cancel = true;
                Console.WriteLine($"Runtime: {environment.BrowserVersionString}");
                Console.WriteLine($"Host + Core ready: {startup.Elapsed.TotalMilliseconds:F1} ms");
                Console.WriteLine($"First week: {await Navigate(core, 0):F1} ms");
                Console.WriteLine($"Start to first week: {startup.Elapsed.TotalMilliseconds:F1} ms");
                await Navigate(core, 1);
                var samples = new List<double>();
                for (int i = 0; i < 10; i++)
                    samples.Add(await Navigate(core, i % 2));
                samples.Sort();
                Console.WriteLine($"Switch median: {(samples[4] + samples[5]) / 2:F1} ms");
                Console.WriteLine($"Switch P95 (nearest rank): {samples[^1]:F1} ms");
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine(ex.Message);
                exitCode = 1;
            }
            app.Shutdown(exitCode);
        };
        return app.Run(window);
    }

    private static async Task<double> Navigate(CoreWebView2 core, int page)
    {
        var ready = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        EventHandler<object> onTitle = (_, _) =>
        {
            if (core.DocumentTitle == $"week-ready-{page}")
                ready.TrySetResult();
        };
        EventHandler<CoreWebView2NavigationCompletedEventArgs> onNavigation = (_, result) =>
        {
            if (!result.IsSuccess)
                ready.TrySetException(new IOException($"Navigation failed: {result.WebErrorStatus}"));
        };
        core.DocumentTitleChanged += onTitle;
        core.NavigationCompleted += onNavigation;
        try
        {
            var elapsed = Stopwatch.StartNew();
            core.Navigate($"{Origin}week-{page}.html");
            await ready.Task.WaitAsync(Timeout);
            return elapsed.Elapsed.TotalMilliseconds;
        }
        finally
        {
            core.DocumentTitleChanged -= onTitle;
            core.NavigationCompleted -= onNavigation;
        }
    }
}
