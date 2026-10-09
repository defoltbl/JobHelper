// views.js: what each list of the main window shows (New Jobs, Applications, Responses, Analytics, Insights,
// Filtered out). Imported by Main.qml and run in its scope, so win, bridge, theme and tableDialog are known here.

function open(k) {
    win.lastView = k;
    if (k === "skip") {
        var fo = bridge.filteredOut();
        var skipped = (fo.rows || []).map(function (r, i) {
            return { primary: r.title + "  ·  " + (r.company || "unknown company"), badge: "", value: "", id: "", flag: "",
                     secondary: r.reason + (r.source ? "   ·  " + r.source : ""),
                     actions: (r.url ? [{ label: "open ↗", kind: "skiplink", arg: i }] : [])
                              .concat(r.can_return ? [{ label: "bring back", kind: "bringback", arg: i }] : []),
                     group: r.group, company: r.company || "", score: 0, date: "",
                     hay: (r.title + " " + r.company + " " + r.reason + " " + (r.location || "")).toLowerCase() };
        });
        tableDialog.show("Filtered out by the last search" + (fo.when ? " (" + fo.when + ")" : "")
                         + ((fo.total || 0) > skipped.length ? ", first " + skipped.length + " of " + fo.total : ""),
                         skipped, "", [["", "Order of filtering"], ["company", "Company A–Z"]]);
    } else if (k === "new") {
        var rows = bridge.leads().map(function (j) {
            var acts = [];
            if (j.url) acts.push({ label: "open ↗", kind: "url", arg: j.id });
            if (j.letter) acts.push({ label: "letter", kind: "letter", arg: j.letter });
            if (j.cv) acts.push({ label: "CV", kind: "cv", arg: j.cv });
            acts.push({ label: "mark applied", kind: "apply", arg: j.id });
            return { primary: j.title + "  ·  " + j.company,
                     // what the score rests on, and documents left from a higher score: said in the row itself
                     secondary: [[j.posted || "", j.desired ? Number(j.desired).toLocaleString() + " CZK/mo" : ""]
                                     .filter(function (part) { return part !== ""; }).join("   "),
                                 j.basis === "title" ? "scored from the title only" : j.basis === "summary" ? "scored from a short summary" : "",
                                 j.stale_docs === true ? "documents from a higher score" : "",
                                 j.closed === true ? "no longer accepts applications" : ""]
                                .filter(function (part) { return part !== ""; }).join("   ·   "),
                     badge: j.tier || "", value: win.noScore(j.score) ? "–" : "" + j.score, actions: acts,
                     id: j.id, flag: "", was: win.noScore(j.before) ? "" : "was " + j.before, stale: j.stale_docs === true,
                     group: j.tier || (win.noScore(j.score) ? "not scored" : "no documents"),
                     company: j.company || "", score: win.noScore(j.score) ? -1 : j.score, date: j.posted || "",
                     hay: (j.title + " " + j.company + " " + (j.location || "") + " " + (j.source || "")).toLowerCase() };
        });
        // jobs you marked "not interested": only shown when you pick that filter
        bridge.dismissedLeads().forEach(function (j) {
            rows.push({ primary: j.title + "  ·  " + j.company, secondary: j.posted || "", badge: "", flag: "",
                        value: win.noScore(j.score) ? "–" : "" + j.score, id: j.id,
                        actions: [{ label: "restore", kind: "restore", arg: j.id }],
                        group: "not interested", hidden: true, company: j.company || "",
                        score: win.noScore(j.score) ? -1 : j.score, date: j.posted || "",
                        hay: (j.title + " " + j.company + " " + (j.location || "")).toLowerCase() });
        });
        tableDialog.show("New Jobs", rows, "leads",
                         [["", "Best score first"], ["date", "Newest posting first"], ["company", "Company A–Z"]]);
    } else if (k === "app") {
        var rows2 = bridge.applications().map(function (j) {
            var acts = [];
            if (j.letter) acts.push({ label: "letter", kind: "letter", arg: j.letter });
            if (j.cv) acts.push({ label: "CV", kind: "cv", arg: j.cv });
            return { primary: j.company + "  ·  " + j.title,
                     secondary: (j.followup ? (j.had_reply ? "No decision for " : "No reply for ") + win.daysText(j.days_waiting) + "   " : "")
                                + (j.stages || "") + (j.next_step ? "   → " + j.next_step : ""),
                     badge: j.status || "", value: "", actions: acts,
                     id: j.id, flag: j.followup ? "follow up" : (j.duplicate ? "duplicate?" : ""),
                     group: j.status || "", company: j.company || "", score: -1, date: j.applied || j.updated || "",
                     hay: (j.company + " " + j.title + " " + (j.stages || "") + " " + (j.next_step || "")).toLowerCase() };
        });
        tableDialog.show("Applications", rows2, "apps",
                         [["", "By status"], ["date", "Newest applied first"], ["company", "Company A–Z"]]);
    } else if (k === "resp") {
        var rows3 = bridge.responses().map(function (r) {
            return { primary: r.company + (r.summary ? "  —  " + r.summary : ""),
                     secondary: r.date, badge: r.stage || "", value: "", actions: [], rid: r.id,
                     group: r.stage || "", company: r.company || "", score: -1, date: r.date || "",
                     hay: (r.company + " " + (r.summary || "")).toLowerCase() };
        });
        tableDialog.show("Responses", rows3, "report",
                         [["", "By kind"], ["date", "Newest first"], ["company", "Company A–Z"]]);
    } else if (k === "ins") {
        var ins = bridge.insights(), out = [];
        function head(text, note) { out.push({ primary: text, secondary: note || "", badge: "", value: "", actions: [], heading: true }); }
        function row(text, value, note, badge) { out.push({ primary: text, secondary: note || "", badge: badge || "", value: "" + value, actions: [] }); }
        function mark(v) { return v.indexOf("working") === 0 ? "working" : v.indexOf("not working") === 0 ? "not working"
                                : v.indexOf("consider") === 0 ? "drop?" : v.indexOf("weak") === 0 ? "weak"
                                : (v.indexOf("too few") === 0 || v.indexOf("no jobs") === 0) ? "" : "not yet"; }
        var works = ins.works || {};
        head("What is working: kinds of role", "from your " + (works.applications || 0) + " applications · the number is how many you sent");
        (works.by_role || []).forEach(function (r) {
            row(r.name, r.applications, r.verdict + "  ·  " + r.replied + " replied, " + r.rejected + " rejected, " + r.waiting + " waiting", mark(r.verdict)); });
        head("What is working: where the job came from", "");
        (works.by_source || []).forEach(function (r) {
            row(r.name, r.applications, r.verdict + "  ·  " + r.rejected + " rejected, " + r.waiting + " waiting", mark(r.verdict)); });
        head("Week by week", "the number is how many applications you sent that week · weeks start on Monday");
        (ins.trends || []).forEach(function (t) {
            row("Week of " + t.week + (t.current ? " (this week)" : ""), t.applications,
                t.replies + (t.replies === 1 ? " reply" : " replies") + "  ·  " + t.invitations
                + (t.invitations === 1 ? " invitation" : " invitations") + ", " + t.rejections + (t.rejections === 1 ? " rejection" : " rejections")); });
        var rt = ins.reply_times || {};
        head("How long companies take to decide", (rt.decisions || 0) === 0 ? "no decisions with a known apply date yet"
             : "days from applying to the first rejection or invitation · from " + rt.decisions + " decisions");
        if ((rt.decisions || 0) > 0) {
            row("Middle value", rt.middle + " d", "half of the decisions came sooner than this");
            row("4 of 5 decisions came within", rt.most_within + " d", "the slowest took " + rt.slowest + " days");
            (rt.by_role || []).forEach(function (r) {
                row("↳ " + r.name, r.middle + " d", "middle value from " + r.decisions + " decisions  ·  between " + r.fastest + " and " + r.slowest + " days"); });
            row("Waiting longer than that", rt.waiting_late, "of " + rt.waiting + " waiting applications · after " + rt.most_within
                + " days of silence a decision is unlikely, though the slowest took " + rt.slowest, rt.waiting_late > 0 ? "weak" : "");
            (rt.late || []).forEach(function (l) {
                out.push({ primary: "↳ " + l.company + "  ·  " + l.title, secondary: "no decision for " + l.days + " days",
                           badge: "", value: l.days + " d", actions: [], id: l.id }); });
        }
        head("Search keywords", "the number is how many jobs the keyword found · score " + (ins.threshold || 30) + "+ gets a CV and letter");
        (ins.keywords || []).forEach(function (r) {
            row(r.keyword, r.leads, r.verdict + (r.average !== null && r.average !== undefined ? "  ·  average score " + r.average : "")
                + (r.guessed > 0 ? "  ·  matched by title" : ""), mark(r.verdict)); });
        var gaps = ins.gaps || {};
        head("Skills to learn", "asked for in the " + (gaps.postings || 0) + " postings with a description, but not in your CV · never added to a CV");
        (gaps.skills || []).forEach(function (r) {
            row(r.skill, r.postings, "in " + r.share + "% of postings  ·  " + r.relevant + " of them close to your profile"); });
        if ((gaps.languages || []).length > 0)
            row("Languages asked for", gaps.languages.map(function (l) { return l.postings; }).reduce(function (a, b) { return a + b; }, 0),
                gaps.languages.map(function (l) { return l.language + " in " + l.postings; }).join("  ·  "));
        var lows = ins.low_scores || {};
        head("Why jobs score low", (lows.jobs || 0) + " jobs scored below " + (lows.threshold || 30)
             + " · read from the explanation of each score · one job can count under several reasons");
        (lows.rows || []).forEach(function (r) { row(r.reason, r.jobs, "in " + r.share + "% of the low-scoring jobs"); });
        if ((lows.technologies || []).length > 0)
            row("Named most often as missing", lows.technologies.length,
                lows.technologies.map(function (t) { return t.skill + " in " + t.jobs; }).join("  ·  "));
        var pay = ins.salaries || {};
        head("What the postings pay", (pay.stated || 0) + " of " + (pay.postings || 0) + " postings state it · gross CZK per month · the number is the top of the range"
             + (pay.median ? " · middle value " + Math.round(pay.median / 1000) + "k" : ""));
        (pay.rows || []).forEach(function (r) {
            out.push({ primary: r.title + "  ·  " + r.company, badge: "", actions: [], id: r.id,
                       value: Math.round(r.high / 1000) + "k",
                       secondary: (r.low === r.high ? Math.round(r.low / 1000) + "k" : Math.round(r.low / 1000) + "–" + Math.round(r.high / 1000) + "k")
                                  + " CZK  ·  written as \"" + r.text + "\""
                                  + (r.target ? "  ·  your target " + Math.round(r.target / 1000) + "k: " + r.verdict : "") }); });
        tableDialog.show("Insights — what works, keywords, skills to learn", out, "", []);
    } else {
        var an = bridge.analytics();
        var st = an.applications_by_status || {}, em = an.by_stage || {};
        function line(label, value, note) { return { primary: label, secondary: note || "", badge: "", value: "" + value, actions: [] }; }
        var wk = bridge.weekSummary();
        var rows4 = [{ primary: "The last 7 days", secondary: (wk.from || "") + " to " + (wk.to || ""), heading: true, badge: "", value: "", actions: [] }];
        (wk.lines || []).forEach(function (r) { rows4.push(line(r.label, r.value, r.note)); });
        rows4.push({ primary: "All time", secondary: "every application and reply the app knows", heading: true, badge: "", value: "", actions: [] });
        rows4 = rows4.concat([
            line("Applications", an.applications_tracked || 0, "the four rows below add up to this"),
            line("↳ waiting for an answer", st.waiting || 0),
            line("↳ in interviews now", st.interview || 0),
            line("↳ offers", st.offer || 0),
            line("↳ rejected", (st.rejected || 0) + (st.on_hold || 0),
                 (an.rejected_by_hand || 0) > 0 ? ((an.rejected_by_hand) + " of them you marked yourself (no email in the mailbox)") : ""),
            line("Companies that replied", an.companies_replied || 0, "at least one email from them"),
            line("Applications that reached an interview", an.applications_with_interview || 0, "at any point, including ones rejected later"),
            line("Reply emails", an.response_emails || 0, "every email counted once; the five rows below add up to this"),
            line("↳ confirmations", em.acknowledged || 0, "\"we received your application\""),
            line("↳ interview emails", em.interview || 0, "invitations, scheduling, reminders"),
            line("↳ tests and tasks", em.assessment || 0),
            line("↳ rejections", em.rejection || 0),
            line("↳ other", em.other || 0, "feedback requests, account messages"),
            line("Why the rejection emails said no", em.rejection || 0, "the rows below add up to this")
        ]);
        var rr = an.rejection_reasons || {};
        for (var key in rr) rows4.push(line("↳ " + key.replace(/_/g, " "), rr[key]));
        tableDialog.show("Analytics — outcomes & rejection reasons", rows4, "", []);
    }
}
