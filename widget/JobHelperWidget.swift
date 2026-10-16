// The JobHelper widget: the state of your job search at a glance, in the macOS widget gallery.
//
// The widget runs in macOS's sandbox and cannot open the app's encrypted data. The app writes a
// small summary for it (jobhelper/widget_feed.py) to
//   ~/Library/Application Support/JobHelper/widget/snapshot.json
// and the widget may read that one folder (see JobHelperWidget.entitlements). It shows counts,
// the next dates, the last run, the Claude usage left and the weekly run. It never writes anything.
import SwiftUI
import WidgetKit

// ── what the app writes ─────────────────────────────────────────────────────
struct Snapshot: Decodable, Sendable {
    struct Counts: Decodable, Sendable {
        var leads = 0, applications = 0, interviews = 0, offers = 0, followups = 0, responses = 0
    }
    struct Event: Decodable, Sendable {
        var kind = "", company = "", title = "", date = "", time = ""
    }
    struct LastRun: Decodable, Sendable {
        var when = "", found = 0, letters = 0
    }
    struct Usage: Decodable, Sendable {
        var fiveHourLeft: Int? = nil, weekLeft: Int? = nil
        enum CodingKeys: String, CodingKey { case fiveHourLeft = "five_hour_left", weekLeft = "week_left" }
    }
    var version = 1
    var updated = ""
    var counts = Counts()
    var next: [Event] = []
    var lastRun: LastRun? = nil
    var usage = Usage()
    var weekly = "Off"
    enum CodingKeys: String, CodingKey { case version, updated, counts, next, lastRun = "last_run", usage, weekly }
}

extension Snapshot.Counts {
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        func n(_ k: String) -> Int { (try? c.decode(Int.self, forKey: Key(k))) ?? 0 }
        leads = n("leads"); applications = n("applications"); interviews = n("interviews")
        offers = n("offers"); followups = n("followups"); responses = n("responses")
    }
}

/// Keys read by name, so a field the app adds later never breaks an older widget.
struct Key: CodingKey {
    var stringValue: String
    var intValue: Int? { nil }
    init(_ s: String) { stringValue = s }
    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { nil }
}

enum Feed {
    static let file = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/JobHelper/widget/snapshot.json")

    static func read() -> Snapshot? {
        guard let data = try? Data(contentsOf: file) else { return nil }
        return try? JSONDecoder().decode(Snapshot.self, from: data)
    }
}

// ── when things are ─────────────────────────────────────────────────────────
enum When {
    static let day: DateFormatter = { let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.locale = Locale(identifier: "en_US_POSIX"); return f }()
    static let stamp: ISO8601DateFormatter = { let f = ISO8601DateFormatter(); f.formatOptions = [.withFullDate, .withTime, .withColonSeparatorInTime, .withDashSeparatorInDate]; return f }()

    /// "Today", "Tomorrow", "In 3 days", "Fri 24 Oct", with the time when there is one.
    static func label(_ e: Snapshot.Event, now: Date) -> String {
        guard let date = day.date(from: e.date) else { return e.date }
        let days = Calendar.current.dateComponents([.day], from: Calendar.current.startOfDay(for: now),
                                                   to: Calendar.current.startOfDay(for: date)).day ?? 0
        let text: String
        switch days {
        case ..<0: text = "Past"
        case 0: text = "Today"
        case 1: text = "Tomorrow"
        case 2...6: text = "In \(days) days"
        default:
            let f = DateFormatter(); f.dateFormat = "EEE d MMM"; f.locale = Locale(identifier: "en_GB")
            text = f.string(from: date)
        }
        return e.time.isEmpty ? text : "\(text) · \(e.time)"
    }

    static func isSoon(_ e: Snapshot.Event, now: Date) -> Bool {
        guard let date = day.date(from: e.date) else { return false }
        return date.timeIntervalSince(Calendar.current.startOfDay(for: now)) < 2 * 86_400
    }

    /// The summary is older than a day: the app has not been opened since.
    static func isStale(_ s: Snapshot, now: Date) -> Bool {
        let text = s.updated.count == 19 ? s.updated + "Z" : s.updated
        guard let made = stamp.date(from: text) ?? ISO8601DateFormatter().date(from: text) else { return false }
        return now.timeIntervalSince(made) > 36 * 3600
    }

    /// "10:56" from the summary's time stamp ("2026-10-16T10:56:00").
    static func time(_ updated: String) -> String {
        updated.count >= 16 ? String(updated.dropFirst(11).prefix(5)) : updated
    }

    static func nextMidnight(after now: Date) -> Date {
        Calendar.current.nextDate(after: now, matching: DateComponents(hour: 0, minute: 1), matchingPolicy: .nextTime) ?? now.addingTimeInterval(3600)
    }
}

// ── the timeline ────────────────────────────────────────────────────────────
struct Entry: TimelineEntry, Sendable {
    let date: Date
    let snapshot: Snapshot?
}

struct Provider: TimelineProvider {
    func placeholder(in context: Context) -> Entry { Entry(date: .now, snapshot: Sample.snapshot) }

    func getSnapshot(in context: Context, completion: @escaping (Entry) -> Void) {
        completion(Entry(date: .now, snapshot: context.isPreview ? (Feed.read() ?? Sample.snapshot) : Feed.read()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<Entry>) -> Void) {
        let now = Date.now
        let snapshot = Feed.read()
        // "Tomorrow" becomes "Today" at midnight; the file itself is read again every 15 minutes.
        let entries = [Entry(date: now, snapshot: snapshot), Entry(date: When.nextMidnight(after: now), snapshot: snapshot)]
        completion(Timeline(entries: entries, policy: .after(now.addingTimeInterval(15 * 60))))
    }
}

/// What the gallery shows before the app has written anything: invented numbers.
enum Sample {
    static var snapshot: Snapshot {
        var s = Snapshot()
        s.counts.leads = 9; s.counts.applications = 6; s.counts.interviews = 1; s.counts.followups = 1; s.counts.responses = 5
        var e = Snapshot.Event(); e.kind = "interview"; e.company = "Brightline Works"
        e.date = When.day.string(from: Date.now.addingTimeInterval(2 * 86_400)); e.time = "11:30"
        s.next = [e]
        s.lastRun = Snapshot.LastRun(when: "Today 09:12", found: 9, letters: 5)
        s.usage = Snapshot.Usage(fiveHourLeft: 66, weekLeft: 88)
        s.weekly = "Mon 09:00"
        s.updated = "2026-10-16T09:14:00"
        return s
    }
}

// ── how it looks ────────────────────────────────────────────────────────────
enum Look {
    static let accent = Color(red: 0.95, green: 0.62, blue: 0.20)      // the app's orange
    static let good = Color(red: 0.29, green: 0.85, blue: 0.50)
    static let lead = Color(red: 0.24, green: 0.73, blue: 0.47)
    static let applied = Color(red: 0.96, green: 0.58, blue: 0.22)
    static let interview = Color(red: 0.40, green: 0.55, blue: 0.98)
    static let follow = Color(red: 0.93, green: 0.36, blue: 0.43)
}

struct Header: View {
    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: "briefcase.fill").foregroundStyle(Look.accent).font(.caption.weight(.bold))
            Text("JobHelper").font(.caption.weight(.bold)).foregroundStyle(.secondary)
            Spacer(minLength: 0)
        }
    }
}

struct Count: View {
    let value: Int, label: String, color: Color
    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("\(value)").font(.title2.weight(.bold)).monospacedDigit().foregroundStyle(color)
            Text(label).font(.caption2).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.8)
        }
    }
}

struct NextDate: View {
    let event: Snapshot.Event?, now: Date, big: Bool
    var body: some View {
        if let e = event {
            VStack(alignment: .leading, spacing: 2) {
                Text(e.kind.capitalized).font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                Text(e.company.isEmpty ? e.title : e.company).font(big ? .headline : .subheadline.weight(.semibold)).lineLimit(2)
                Text(When.label(e, now: now)).font(.caption.weight(.semibold))
                    .foregroundStyle(When.isSoon(e, now: now) ? Look.accent : .secondary)
            }
        } else {
            VStack(alignment: .leading, spacing: 2) {
                Text("Coming up").font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                Text("No dates").font(.subheadline.weight(.semibold))
            }
        }
    }
}

struct UsageBar: View {
    let label: String, left: Int?
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label).font(.caption2).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Text(left.map { "\($0)% left" } ?? "–").font(.caption2.weight(.semibold)).monospacedDigit()
            }
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Capsule().fill(.quaternary)
                    Capsule().fill((left ?? 100) < 20 ? Look.follow : Look.good)
                        .frame(width: g.size.width * CGFloat(max(0, min(100, left ?? 0))) / 100)
                }
            }.frame(height: 4)
        }
    }
}

struct Message: View {
    let text: String
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Header()
            Spacer(minLength: 0)
            Text(text).font(.callout).foregroundStyle(.secondary)
            Spacer(minLength: 0)
        }
    }
}

struct SmallView: View {
    let s: Snapshot, now: Date
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Header()
            NextDate(event: s.next.first, now: now, big: true)
            Spacer(minLength: 0)
            HStack(spacing: 12) {
                Count(value: s.counts.leads, label: "New", color: Look.lead)
                Count(value: s.counts.applications, label: "Applied", color: Look.applied)
            }
        }
    }
}

struct MediumView: View {
    let s: Snapshot, now: Date
    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Header()
                NextDate(event: s.next.first, now: now, big: false)
                Spacer(minLength: 0)
                UsageBar(label: "Claude, 5 h", left: s.usage.fiveHourLeft)
            }
            Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 8) {
                GridRow {
                    Count(value: s.counts.leads, label: "New jobs", color: Look.lead)
                    Count(value: s.counts.applications, label: "Applied", color: Look.applied)
                }
                GridRow {
                    Count(value: s.counts.interviews, label: "Interviews", color: Look.interview)
                    Count(value: s.counts.followups, label: "Follow up", color: Look.follow)
                }
            }
        }
    }
}

struct LargeView: View {
    let s: Snapshot, now: Date
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Header()
            HStack(spacing: 0) {
                Count(value: s.counts.leads, label: "New jobs", color: Look.lead).frame(maxWidth: .infinity, alignment: .leading)
                Count(value: s.counts.applications, label: "Applied", color: Look.applied).frame(maxWidth: .infinity, alignment: .leading)
                Count(value: s.counts.interviews, label: "Interviews", color: Look.interview).frame(maxWidth: .infinity, alignment: .leading)
                Count(value: s.counts.followups, label: "Follow up", color: Look.follow).frame(maxWidth: .infinity, alignment: .leading)
            }
            Divider()
            Text("COMING UP").font(.caption2.weight(.bold)).foregroundStyle(.secondary)
            if s.next.isEmpty {
                Text("No dates").font(.subheadline).foregroundStyle(.secondary)
            }
            ForEach(Array(s.next.prefix(3).enumerated()), id: \.offset) { _, e in
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(e.company.isEmpty ? e.title : e.company).font(.subheadline.weight(.semibold)).lineLimit(1)
                        Text(e.kind.capitalized).font(.caption2).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 6)
                    Text(When.label(e, now: now)).font(.caption.weight(.semibold))
                        .foregroundStyle(When.isSoon(e, now: now) ? Look.accent : .secondary)
                }
            }
            Divider()
            if let run = s.lastRun, !run.when.isEmpty {
                Text("Last run \(run.when): \(run.found) new, \(run.letters) letters")
                    .font(.caption).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.85)
            }
            HStack(spacing: 14) {
                UsageBar(label: "Claude, 5 h", left: s.usage.fiveHourLeft)
                UsageBar(label: "Claude, 7 days", left: s.usage.weekLeft)
            }
            Divider()
            HStack(spacing: 0) {
                Count(value: s.counts.offers, label: "Offers", color: Look.good).frame(maxWidth: .infinity, alignment: .leading)
                Count(value: s.counts.responses, label: "Replies read", color: .secondary).frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .leading, spacing: 1) {
                    Text(s.weekly).font(.title3.weight(.bold)).lineLimit(1).minimumScaleFactor(0.7)
                    Text("Weekly run").font(.caption2).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            Spacer(minLength: 0)
            Text("Updated \(When.time(s.updated))").font(.caption2).foregroundStyle(.tertiary)
        }
    }
}

struct WidgetView: View {
    @Environment(\.widgetFamily) var family
    let entry: Entry

    var body: some View {
        Group {
            if let s = entry.snapshot {
                if When.isStale(s, now: entry.date) && family != .systemSmall {
                    VStack(alignment: .leading, spacing: 4) {
                        content(s)
                        Text("Open JobHelper to bring this up to date.").font(.caption2).foregroundStyle(Look.accent)
                    }
                } else {
                    content(s)
                }
            } else {
                Message(text: "Open JobHelper once to show your job search here.")
            }
        }
        .containerBackground(.background, for: .widget)
        .widgetURL(URL(string: "jobhelper://open"))
    }

    @ViewBuilder func content(_ s: Snapshot) -> some View {
        switch family {
        case .systemSmall: SmallView(s: s, now: entry.date)
        case .systemLarge: LargeView(s: s, now: entry.date)
        default: MediumView(s: s, now: entry.date)
        }
    }
}

#if !PICTURES          // scripts/widget_pictures.swift draws the views for the user guide instead
@main
#endif
struct JobHelperWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "JobHelperWidget", provider: Provider()) { entry in
            WidgetView(entry: entry)
        }
        .configurationDisplayName("JobHelper")
        .description("Your job search at a glance: new jobs, applications, the next interview and Claude usage.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}
