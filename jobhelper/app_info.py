"""The app's name, version and identity, in one place (the window, the build and the docs use them)."""
NAME = "JobHelper"
VERSION = "1.0.0"
BUNDLE_ID = "local.jobhelper.app"
APPLE_EVENTS_REASON = ("JobHelper fills in the job forms you open in Google Chrome, and opens Terminal "
                       "when you sign in to Claude.")
WIDGET_ID = BUNDLE_ID + ".widget"        # the widget inside the app (widget/JobHelperWidget.swift)
WIDGET_NAME = "JobHelperWidget"
NOTIFY_LIBRARY = "libJobHelperNotify.dylib"       # in Contents/Frameworks: the app's own notifications (macos/Notify.swift)
WIDGET_RELOAD = "libJobHelperWidgetReload.dylib"   # in Contents/Frameworks: the app calls it to have macOS redraw the widget (widget/WidgetReload.swift)
URL_SCHEME = "jobhelper"                  # jobhelper://open: the widget's Open button and a click on the widget
