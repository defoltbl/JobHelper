// Asks macOS to redraw the JobHelper widget now, instead of at its next scheduled read (every 15 minutes).
//
// Only the app that holds a widget may ask WidgetKit to reload it, and macOS checks that the request comes
// from the app's own program: a second program in Contents/MacOS was refused ("Resolved bundle path does not
// match executable", ChronoCoreErrorDomain Code=10). So this is a small library in JobHelper.app
// (Contents/Frameworks/libJobHelperWidgetReload.dylib) that the app loads into its own process and calls
// after it wrote a new summary that changed what the widget shows (jobhelper/widget_feed.py).
import WidgetKit

@_cdecl("jobhelper_reload_widgets")
public func jobhelperReloadWidgets() {
    WidgetCenter.shared.reloadAllTimelines()
}
