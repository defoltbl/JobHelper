// Shows JobHelper's notifications through Apple's notification framework, from the app's own process.
//
// macOS asks the person once ("JobHelper would like to send you notifications") and then lists JobHelper in
// System Settings → Notifications. The script app used before could not ask, so macOS kept its notifications
// without showing them. This small library is in JobHelper.app (Contents/Frameworks/libJobHelperNotify.dylib);
// the app loads it into its own process (jobhelper/notify.py, AppNotifier).
import Foundation
import UserNotifications

/// A place for an answer that arrives on another thread.
final class Answer: @unchecked Sendable {
    var code: Int32 = -1
}

/// Shows a notification also while JobHelper is in front (an interview invitation is worth it); the app
/// itself decides when not to send one.
final class ShowInFront: NSObject, UNUserNotificationCenterDelegate {
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler done: @escaping (UNNotificationPresentationOptions) -> Void) {
        done([.banner, .sound, .list])
    }
}

private let showInFront = ShowInFront()

/// 1 shown, 0 not allowed in System Settings, 2 still waiting for the person's answer (it is shown once
/// they allow it), -1 macOS refused it.
@_cdecl("jobhelper_notify")
public func jobhelperNotify(_ title: UnsafePointer<CChar>, _ body: UnsafePointer<CChar>) -> Int32 {
    let content = UNMutableNotificationContent()
    content.title = String(cString: title)
    content.body = String(cString: body)
    content.sound = .default
    let center = UNUserNotificationCenter.current()
    center.delegate = showInFront
    let answered = DispatchSemaphore(value: 0)
    let answer = Answer()
    center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
        guard granted else {
            answer.code = 0
            answered.signal()
            return
        }
        center.add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)) { error in
            answer.code = error == nil ? 1 : -1
            answered.signal()
        }
    }
    return answered.wait(timeout: .now() + 1.5) == .success ? answer.code : 2
}

/// 1 allowed, 0 turned off in System Settings, 2 not asked yet, -1 not known.
@_cdecl("jobhelper_notify_permission")
public func jobhelperNotifyPermission() -> Int32 {
    let answered = DispatchSemaphore(value: 0)
    let answer = Answer()
    UNUserNotificationCenter.current().getNotificationSettings { settings in
        switch settings.authorizationStatus {
        case .authorized, .provisional: answer.code = 1
        case .denied: answer.code = 0
        case .notDetermined: answer.code = 2
        default: answer.code = -1
        }
        answered.signal()
    }
    return answered.wait(timeout: .now() + 1.5) == .success ? answer.code : -1
}
