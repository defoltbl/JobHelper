// Asks macOS to redraw the JobHelper widget now, instead of at its next scheduled read (every 15 minutes).
//
// Only the app that holds a widget may ask WidgetKit to reload it. The app itself is Python, so this small
// program is built into JobHelper.app (Contents/MacOS/JobHelperWidgetReload); macOS sees it as part of the app.
// The app starts it after it wrote a new summary that changed what the widget shows (jobhelper/widget_feed.py).
import Foundation
import WidgetKit

WidgetCenter.shared.reloadAllTimelines()
RunLoop.main.run(until: Date().addingTimeInterval(0.5))     // let the request reach the system before the program ends
