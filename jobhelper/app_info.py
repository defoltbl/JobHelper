"""The app's name, version and identity, in one place (the window, the build and the docs use them)."""
NAME = "JobHelper"
VERSION = "1.0.0"
BUNDLE_ID = "local.jobhelper.app"
APPLE_EVENTS_REASON = ("JobHelper fills in the job forms you open in Google Chrome, and opens Terminal "
                       "when you sign in to Claude.")
WIDGET_ID = BUNDLE_ID + ".widget"        # the widget inside the app (widget/JobHelperWidget.swift)
WIDGET_NAME = "JobHelperWidget"
WIDGET_RELOAD = "JobHelperWidgetReload"   # the helper in Contents/MacOS that asks macOS to redraw the widget (widget/WidgetReload.swift)
URL_SCHEME = "jobhelper"                  # jobhelper://open: the widget's Open button and a click on the widget
