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
    /// The real home folder. In the sandbox, "the home folder" (homeDirectoryForCurrentUser, NSHomeDirectory)
    /// is the widget's own container, where the app's summary is not; the user record names the real one.
    static var realHome: URL {
        if let record = getpwuid(getuid()), let dir = record.pointee.pw_dir {
            return URL(fileURLWithPath: String(cString: dir), isDirectory: true)
        }
        return FileManager.default.homeDirectoryForCurrentUser
    }

    static let file = realHome.appendingPathComponent("Library/Application Support/JobHelper/widget/snapshot.json")

    static func read() -> Snapshot? {
        guard let data = try? Data(contentsOf: file) else { return nil }
        return try? JSONDecoder().decode(Snapshot.self, from: data)
    }
}

// ── when things are ─────────────────────────────────────────────────────────
enum When {
    static let day: DateFormatter = { let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.locale = Locale(identifier: "en_US_POSIX"); return f }()

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

    static let month: DateFormatter = { let f = DateFormatter(); f.dateFormat = "MMM"; f.locale = Locale(identifier: "en_GB"); return f }()
    static let dayNumber: DateFormatter = { let f = DateFormatter(); f.dateFormat = "d"; return f }()

    /// The app writes its local time as "2026-10-16T10:56:00".
    static let local: DateFormatter = { let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"; f.locale = Locale(identifier: "en_US_POSIX"); return f }()

    /// When the app wrote the summary.
    static func made(_ s: Snapshot) -> Date? { local.date(from: s.updated) }

    static func stamp(_ date: Date) -> String { local.string(from: date) }

    /// "call with HR" -> "Call with HR": only the first letter changes (capitalized would give "Call With Hr").
    static func sentence(_ text: String) -> String { text.prefix(1).uppercased() + text.dropFirst() }
    static let clock: DateFormatter = { let f = DateFormatter(); f.dateFormat = "HH:mm"; return f }()
    static let dayMonth: DateFormatter = { let f = DateFormatter(); f.dateFormat = "d MMM"; f.locale = Locale(identifier: "en_GB"); return f }()

    static func isSoon(_ e: Snapshot.Event, now: Date) -> Bool {
        guard let date = day.date(from: e.date) else { return false }
        return date.timeIntervalSince(Calendar.current.startOfDay(for: now)) < 2 * 86_400
    }

    /// The summary is older than a day: the app has not been opened since.
    static func isStale(_ s: Snapshot, now: Date) -> Bool {
        guard let made = made(s) else { return false }
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
        var call = Snapshot.Event(); call.kind = "call with HR"; call.company = "Northwind Data"
        call.date = When.day.string(from: Date.now.addingTimeInterval(6 * 86_400)); call.time = "15:00"
        s.next = [e, call]
        s.lastRun = Snapshot.LastRun(when: "Today 09:12", found: 9, letters: 5)
        s.usage = Snapshot.Usage(fiveHourLeft: 66, weekLeft: 88)
        s.weekly = "Mon 09:00"
        s.updated = When.stamp(Date.now.addingTimeInterval(-300))       // written five minutes ago
        return s
    }
}

// ── how it looks: the way macOS's own widgets look ──────────────────────────
// No padding of its own (macOS gives every widget its margins), the system background, the system
// rounded font for numbers, SF Symbols, and colours marked accentable, so the widget also reads well
// when the desktop shows widgets dimmed or tinted.
enum Look {
    static let accent = Color.orange
    static let lead = Color.green
    static let applied = Color.orange
    static let interview = Color.blue
    static let follow = Color.pink
    static let offer = Color.mint
    static let openURL = URL(string: "jobhelper://open")!
}

/// "JobHelper" with the briefcase, as macOS widgets name their app.
struct Header: View {
    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "briefcase.fill").foregroundStyle(Look.accent).widgetAccentable()
            Text("JobHelper")
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(.secondary)
    }
}

/// The button that opens the app (medium and large; a small widget opens the app wherever it is clicked).
struct OpenButton: View {
    var body: some View {
#if PICTURES
        face                                          // the pictures of the guide cannot draw a link
#else
        Link(destination: Look.openURL) { face }
#endif
    }

    var face: some View {
        Label("Open", systemImage: "arrow.up.forward.app.fill")
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 9).padding(.vertical, 4)
            .background(Capsule().fill(Look.accent.opacity(0.18)))
            .foregroundStyle(Look.accent)
            .widgetAccentable()
    }
}

/// One number with its symbol and name.
struct Stat: View {
    let value: Int, label: String, symbol: String, color: Color
    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Label(label, systemImage: symbol)
                .font(.caption2.weight(.medium)).foregroundStyle(.secondary).lineLimit(1)
                .labelStyle(StatLabel(color: color))
            Text(value, format: .number)
                .font(.system(.title2, design: .rounded).weight(.semibold)).monospacedDigit()
                .contentTransition(.numericText())
        }
    }
}

struct StatLabel: LabelStyle {
    let color: Color
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 3) {
            configuration.icon.foregroundStyle(color).widgetAccentable()
            configuration.title
        }
    }
}

/// The day of a date as a little calendar page, as in the Calendar app.
struct DayTile: View {
    let event: Snapshot.Event, now: Date, size: CGFloat
    var body: some View {
        let date = When.day.date(from: event.date)
        VStack(spacing: 0) {
            Text(date.map { When.month.string(from: $0).uppercased() } ?? "")
                .font(.system(size: size * 0.22, weight: .bold)).foregroundStyle(When.isSoon(event, now: now) ? Look.accent : .red)
                .widgetAccentable()
            Text(date.map { When.dayNumber.string(from: $0) } ?? "–")
                .font(.system(size: size * 0.46, weight: .medium, design: .rounded)).monospacedDigit()
        }
        .frame(width: size, height: size)
        .background(RoundedRectangle(cornerRadius: size * 0.22, style: .continuous).fill(.quaternary))
    }
}

/// The next date: its day tile, the company, what it is, and when.
struct NextDate: View {
    let event: Snapshot.Event?, now: Date, tile: CGFloat
    var body: some View {
        if let e = event {
            HStack(spacing: 8) {
                DayTile(event: e, now: now, size: tile)
                VStack(alignment: .leading, spacing: 1) {
                    Text(e.company.isEmpty ? e.title : e.company).font(.headline).lineLimit(1)
                    Text(When.sentence(e.kind)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    Text(When.label(e, now: now)).font(.caption.weight(.semibold))
                        .foregroundStyle(When.isSoon(e, now: now) ? Look.accent : .secondary).widgetAccentable()
                }
            }
        } else {
            Label("No dates coming up", systemImage: "calendar").font(.caption).foregroundStyle(.secondary)
        }
    }
}

/// A Claude limit as a slim bar with its name and what is left, as in the battery widget.
struct UsageGauge: View {
    let label: String, left: Int?
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(label)
                Spacer(minLength: 4)
                Text(left.map { "\($0)% left" } ?? "–").monospacedDigit().foregroundStyle(.primary)
            }
            .font(.caption2.weight(.medium)).foregroundStyle(.secondary)
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Capsule().fill(.quaternary)
                    Capsule().fill((left ?? 100) < 20 ? Color.red : Color.green)
                        .frame(width: max(4, g.size.width * CGFloat(max(0, min(100, left ?? 0))) / 100))
                        .widgetAccentable()
                }
            }
            .frame(height: 5)
        }
    }
}

/// When the summary was written: "Updated 10:56", or "Updated 15 Oct" when it is from another day.
struct Updated: View {
    let s: Snapshot, now: Date
    var body: some View {
        if let made = When.made(s) {
            Text("Updated " + (Calendar.current.isDate(made, inSameDayAs: now) ? When.clock.string(from: made) : When.dayMonth.string(from: made)))
                .font(.caption2).foregroundStyle(.tertiary)
        }
    }
}

struct SmallView: View {
    let s: Snapshot, now: Date
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Header()
            Spacer(minLength: 0)
            if let e = s.next.first {
                DayTile(event: e, now: now, size: 34)
                Text(e.company.isEmpty ? e.title : e.company).font(.headline).lineLimit(1)
                Text(When.label(e, now: now)).font(.caption.weight(.semibold))
                    .foregroundStyle(When.isSoon(e, now: now) ? Look.accent : .secondary).widgetAccentable()
            } else {
                Text(s.counts.leads, format: .number).font(.system(.largeTitle, design: .rounded).weight(.semibold))
                Text("new jobs").font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            HStack(spacing: 10) {
                Label("\(s.counts.leads)", systemImage: "sparkles").labelStyle(StatLabel(color: Look.lead))
                Label("\(s.counts.applications)", systemImage: "paperplane.fill").labelStyle(StatLabel(color: Look.applied))
            }
            .font(.caption.weight(.semibold)).monospacedDigit()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

struct MediumView: View {
    let s: Snapshot, now: Date
    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 8) {
                Header()
                NextDate(event: s.next.first, now: now, tile: 40)
                Spacer(minLength: 0)
                OpenButton()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 10) {
                GridRow {
                    Stat(value: s.counts.leads, label: "New", symbol: "sparkles", color: Look.lead)
                    Stat(value: s.counts.applications, label: "Applied", symbol: "paperplane.fill", color: Look.applied)
                }
                GridRow {
                    Stat(value: s.counts.interviews, label: "Interviews", symbol: "person.2.fill", color: Look.interview)
                    Stat(value: s.counts.followups, label: "Follow up", symbol: "arrow.uturn.left", color: Look.follow)
                }
            }
        }
    }
}

struct LargeView: View {
    let s: Snapshot, now: Date
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack { Header(); Spacer(minLength: 0); OpenButton() }
            HStack(alignment: .top, spacing: 0) {
                Stat(value: s.counts.leads, label: "New", symbol: "sparkles", color: Look.lead).frame(maxWidth: .infinity, alignment: .leading)
                Stat(value: s.counts.applications, label: "Applied", symbol: "paperplane.fill", color: Look.applied).frame(maxWidth: .infinity, alignment: .leading)
                Stat(value: s.counts.interviews, label: "Interviews", symbol: "person.2.fill", color: Look.interview).frame(maxWidth: .infinity, alignment: .leading)
                Stat(value: s.counts.followups, label: "Follow up", symbol: "arrow.uturn.left", color: Look.follow).frame(maxWidth: .infinity, alignment: .leading)
            }
            VStack(alignment: .leading, spacing: 8) {
                Text("Coming up").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                if s.next.isEmpty {
                    Label("No dates coming up", systemImage: "calendar").font(.callout).foregroundStyle(.secondary)
                }
                ForEach(Array(s.next.prefix(3).enumerated()), id: \.offset) { _, e in
                    NextDate(event: e, now: now, tile: 34)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)     // takes the room that is left
            .padding(10)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(.quaternary.opacity(0.6)))
            HStack(spacing: 14) {
                UsageGauge(label: "Claude · 5 hours", left: s.usage.fiveHourLeft)
                UsageGauge(label: "Claude · 7 days", left: s.usage.weekLeft)
            }
            HStack(spacing: 14) {
                Label("\(s.counts.offers) offers", systemImage: "checkmark.seal.fill").labelStyle(StatLabel(color: Look.offer))
                Label("\(s.counts.responses) replies", systemImage: "envelope.fill").labelStyle(StatLabel(color: .secondary))
                Label(s.weekly == "Off" ? "Weekly run off" : "Weekly \(s.weekly)", systemImage: "calendar.badge.clock").labelStyle(StatLabel(color: .secondary))
                Spacer(minLength: 0)
            }
            .font(.caption).foregroundStyle(.secondary).lineLimit(1)
            HStack {
                if let run = s.lastRun, !run.when.isEmpty {
                    Text("Last run \(run.when) · \(run.found) new · \(run.letters) letters").font(.caption2).foregroundStyle(.tertiary).lineLimit(1)
                }
                Spacer(minLength: 0)
                Updated(s: s, now: now)
            }
        }
    }
}

/// Extra large (macOS 14+): the numbers, the next dates and the state of the app side by side.
struct ExtraLargeView: View {
    let s: Snapshot, now: Date
    var body: some View {
        HStack(alignment: .top, spacing: 18) {
            VStack(alignment: .leading, spacing: 12) {
                HStack { Header(); Spacer(minLength: 0); OpenButton() }
                Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 12) {
                    GridRow {
                        Stat(value: s.counts.leads, label: "New", symbol: "sparkles", color: Look.lead)
                        Stat(value: s.counts.applications, label: "Applied", symbol: "paperplane.fill", color: Look.applied)
                    }
                    GridRow {
                        Stat(value: s.counts.interviews, label: "Interviews", symbol: "person.2.fill", color: Look.interview)
                        Stat(value: s.counts.followups, label: "Follow up", symbol: "arrow.uturn.left", color: Look.follow)
                    }
                    GridRow {
                        Stat(value: s.counts.offers, label: "Offers", symbol: "checkmark.seal.fill", color: Look.offer)
                        Stat(value: s.counts.responses, label: "Replies", symbol: "envelope.fill", color: .secondary)
                    }
                }
                Spacer(minLength: 0)
            }
            .frame(width: 200, alignment: .leading)
            VStack(alignment: .leading, spacing: 10) {
                Text("Coming up").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                if s.next.isEmpty {
                    Label("No dates coming up", systemImage: "calendar").font(.callout).foregroundStyle(.secondary)
                }
                ForEach(Array(s.next.prefix(5).enumerated()), id: \.offset) { _, e in
                    NextDate(event: e, now: now, tile: 38)
                }
                Spacer(minLength: 0)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .padding(12)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(.quaternary.opacity(0.6)))
            VStack(alignment: .leading, spacing: 12) {
                Text("Claude").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                UsageGauge(label: "5 hours", left: s.usage.fiveHourLeft)
                UsageGauge(label: "7 days", left: s.usage.weekLeft)
                Divider()
                Label(s.weekly == "Off" ? "Weekly run off" : "Weekly run \(s.weekly)", systemImage: "calendar.badge.clock")
                    .labelStyle(StatLabel(color: .secondary)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                if let run = s.lastRun, !run.when.isEmpty {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Last run \(run.when)").font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        Text("\(run.found) new · \(run.letters) letters").font(.caption.weight(.semibold)).monospacedDigit()
                    }
                }
                Spacer(minLength: 0)
                Updated(s: s, now: now)
            }
            .frame(width: 190, alignment: .leading)
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
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
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
        .widgetURL(Look.openURL)                      // a click anywhere opens the app
    }

    @ViewBuilder func content(_ s: Snapshot) -> some View {
        switch family {
        case .systemSmall: SmallView(s: s, now: entry.date)
        case .systemLarge: LargeView(s: s, now: entry.date)
        case .systemExtraLarge: ExtraLargeView(s: s, now: entry.date)
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
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge, .systemExtraLarge])
    }
}
