"""The test area of the assistant: the whole request "fill in the form", on a page in a real browser engine.

    python fill_in_browser.py components.html [page.pdf] < setup.json   ->   JSON on stdout

Everything the app would do with Chrome is done here with a browser engine of its own: the page comes
from a web server started on this machine only (so it has an http address, like a real form), the
tab in front is that page, and scripts run in it. Claude is replaced by the answers in the setup.
The data folder is a temporary one and the Keychain is in memory, so nothing real is read or changed.

setup: {"details": {...}, "jobs": [...], "job_id": "", "answers": {"question": ["answer", "what to check"]},
        "choices": {"question": "the option or number Claude would choose"},
        "edit": {"field id": "what the person types over the assistant's answer, before asking it to remember"},
        "files": {"tailored_cvs/CV_Vantor.pdf": 3000} (files made in the data folder, with this many bytes), "opened": "id of the job whose posting was opened from the app",
        "review": true, "problems": [what Claude would find in the review], "skip": ["words of fields to leave out"]}
out:   {"result": what Api.assistant_fill returned, "state": every field's value afterwards,
        "sent": bool, "clicked": bool, "asked": the questions that went to Claude}
"""
import base64
import http.server
import json
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ["JOBHELPER_VAULT_BACKEND"] = "memory"
os.environ.pop("ANTHROPIC_API_KEY", None)
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
FORMS = Path(__file__).resolve().parent / "forms"

STATE_TOTAL, STATE_WAIT = 10.0, 0.25    # how long the page may take to give its state, in all, and the pause between reads (#65)
RUN_MOST = 20.0                          # seconds one script may take before the page counts as not answering
AREA_MOST = 60                           # seconds the whole area may take: after that the process ends itself
STATE = r"""
(function () {
  var out = {};
  function walk(root) {
    var all = root.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (el.shadowRoot) walk(el.shadowRoot);
      if (el.tagName === 'IFRAME') { try { if (el.contentDocument && el.contentDocument.body) walk(el.contentDocument); } catch (e) {} continue; }
      if (el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA' && el.tagName !== 'SELECT') continue;
      var key = el.id || el.name;
      out[key] = (el.type === 'checkbox' || el.type === 'radio') ? el.checked : (el.type === 'file' ? el.files.length : el.value);
      if (el.style.outline) out[key + '#outline'] = el.style.outline.indexOf('34, 197, 94') >= 0 ? 'green' : 'amber';
    }
  }
  walk(document);
  return JSON.stringify({fields: out, sent: !!window.sent, clicked: !!window.clicked, kept: window.state || null,
                         menus: window.chosen || {}, opened: window.opened || []});
})()
"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        name = self.path.split("?")[0].strip("/")
        page = FORMS / name
        if not re.fullmatch(r"[a-z_]+\.html", name) or not page.is_file():
            self.send_error(404)
            return
        other = f"http://localhost:{self.server.server_address[1]}"         # the same server under another name: another origin
        body = page.read_text(encoding="utf-8").replace("__OTHER__", other).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    page_name = sys.argv[1]
    picture = sys.argv[2] if len(sys.argv) > 2 else ""
    setup = json.loads(sys.stdin.read() or "{}")

    from PySide6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer, QUrl
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    from jobhelper import api_core, chrome, config, details, llm, store, ui_api, vault

    work = Path(tempfile.mkdtemp(prefix="jobhelper_form_test_"))
    vault.use_keychain(vault.MemoryKeychain({vault.KEY_ACCOUNT: base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")}))
    config.DATA_DIR = work
    for name, folder in (("LETTERS_DIR", "cover_letters"), ("TAILORED_CV_DIR", "tailored_cvs"), ("CV_DIR", "cv"), ("COVER_LETTERS_DIR", "my_letters"),
                         ("MY_LETTERS_DIR", "my_letters")):
        setattr(config, name, work / folder)
        (work / folder).mkdir(exist_ok=True)
    for name, size in (setup.get("files") or {}).items():       # invented files: every byte value, so that nothing is lost on the way
        (work / name).write_bytes(bytes((i * 7 + len(name)) % 256 for i in range(int(size))))
    config.JOBS_JSON, config.USAGE_JSON, config.ENV_PATH = work / "jobs.json", work / "usage.json", work / ".env"
    config.ensure_dirs = lambda: None
    api_core.agent4_tracker.render_all = lambda jobs: None
    api_core.CvSource.text = lambda self: setup.get("cv", "Alex Novak\nJunior analyst. SQL, Excel, Python.")
    api_core.CvSource.name = lambda self: "Alex Novak"
    store.save_jobs(setup.get("jobs", []))
    if setup.get("details"):
        assert details.save(setup["details"])["ok"]
    asked, chosen = [], []

    def ask_json(prompt, **kw):
        if "What the form holds now" in prompt:   # the review before sending
            return {"problems": setup.get("problems", [])}
        if "Fields:" in prompt:                 # the question about lists and numbers
            fields = re.findall(r"^(\d+)\. (.+)$", prompt[prompt.index("Fields:"):], re.M)
            chosen.extend(label for _n, label in fields)
            return {"choices": [{"n": int(n), "answer": setup.get("choices", {}).get(label)} for n, label in fields]}
        questions = re.findall(r"^\d+\. (.+)$", prompt[prompt.index("The form's questions:"):], re.M)
        asked.extend(questions)
        answers = setup.get("answers", {})
        return {"answers": [{"n": n, "answer": answers.get(q, [f"An answer to: {q}", ""])[0], "needs_you": answers.get(q, ["", ""])[1]}
                            for n, q in enumerate(questions, 1)]}
    llm.ask_json = ask_json

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    view.resize(760, 1500)
    page = view.page()

    def run(script: str, most: float = RUN_MOST) -> str:
        loop, box = QEventLoop(), []
        page.runJavaScript(script, 0, lambda result: (box.append(result), loop.quit()))
        QTimer.singleShot(max(1, int(most * 1000)), loop.quit)
        loop.exec()
        return "" if not box or box[0] is None else str(box[0])
    chrome.run = run

    def pause(seconds: float) -> None:          # waiting must let the page run: a menu draws its entries on a timer
        loop = QEventLoop()
        QTimer.singleShot(int(seconds * 1000), loop.quit)
        loop.exec()
    chrome.pause = pause
    chrome.active_tab = lambda: {"url": page.url().toString(), "title": page.title()}

    blanks = [True] * int(setup.get("blank_states", 0))     # for a test: the page first answers nothing this many times
    silent = bool(setup.get("silent_states"))               # for a test: an engine that never answers a state read

    def page_state() -> dict:
        """The page's fields as STATE reads them, waited for: right after the app changed the page, the engine can answer
        nothing for a moment, and one such empty answer failed a test at random (#65)."""
        deadline, tries = time.monotonic() + STATE_TOTAL, 0
        while time.monotonic() < deadline:    # a total time: an engine that gives no answer at all cannot hold it longer
            tries += 1
            if blanks:                  # the test's empty answer, in place of the page's
                blanks.pop()
                said = ""
            elif silent:                # no callback at all: the read waits the whole time it is given
                pause(min(RUN_MOST, max(0.0, deadline - time.monotonic())))
                said = ""
            else:
                said = run(STATE, deadline - time.monotonic())
            if said:
                try:
                    return {**json.loads(said), "tries": tries}
                except json.JSONDecodeError:
                    pass
            pause(STATE_WAIT)
        raise RuntimeError(f"The page gave no state in {STATE_TOTAL:.0f} seconds ({tries} tries): its engine stopped answering.")

    started = []

    def work_on_page(ok: bool) -> None:
        if started:                     # a frame or a later load fires loadFinished again: the work is done once (#65)
            return
        if not ok:
            app.exit(2)
            return
        started.append(True)

        def go():
            api = ui_api.Api()
            if setup.get("opened"):
                api.open_url = None
                api.note_opened(setup["opened"])
            before = api.assistant_watch()
            result = api.assistant_fill(setup.get("job_id", ""), skip=setup.get("skip"))
            reviewed = api.assistant_review(setup.get("job_id", "")) if setup.get("review") else None
            learned = None
            if setup.get("edit"):                    # the person rewrites fields on the page, then asks to have it remembered
                for field, text in setup["edit"].items():
                    run("(function(){var el=document.getElementById(%s); var p=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
                        "Object.getOwnPropertyDescriptor(p,'value').set.call(el,%s); el.dispatchEvent(new Event('input',{bubbles:true}));})()"
                        % (json.dumps(field), json.dumps(text)))
                learned = api.assistant_learn()
                from jobhelper import answer_memory
                learned["remembered"] = answer_memory.count()
            state = page_state()
            out = {"reviewed": reviewed, "learned": learned, "watch": [before, api.assistant_watch()], "result": result, "state": state["fields"], "kept": state["kept"], "sent": state["sent"], "clicked": state["clicked"], "asked": asked,
                   "chosen": chosen, "menus": state["menus"], "opened": state["opened"], "state_tries": state["tries"]}
            if picture:                              # the page as a PDF: it can be drawn without a screen
                loop = QEventLoop()
                page.printToPdf(lambda data: (Path(picture).write_bytes(bytes(data)), loop.quit()))
                QTimer.singleShot(20000, loop.quit)
                loop.exec()
            print(json.dumps(out))
            app.quit()
        def go_or_stop():
            try:
                go()
            except Exception:  # noqa: BLE001 - printed for the test, and the process ends now, not at the watchdog (#65)
                import traceback
                traceback.print_exc()
                sys.stderr.flush()
                os._exit(4)
        QTimer.singleShot(800, go_or_stop)     # the page's own scripts (and its frame) get their turn first
    page.loadFinished.connect(work_on_page)
    view.load(QUrl(f"http://127.0.0.1:{server.server_address[1]}/{page_name}"))
    def give_up():                  # app.exit ends only the outer loop: a wait inside it would keep the process alive (#65)
        print("The test area gave no answer in time.", file=sys.stderr, flush=True)
        os._exit(3)
    if setup.get("hang"):           # for a test: the work never ends (a wait that nothing ends)
        page.loadFinished.disconnect(work_on_page)
        page.loadFinished.connect(lambda ok: QTimer.singleShot(0, lambda: pause(600)))
    QTimer.singleShot(int(float(setup.get("area_most", AREA_MOST)) * 1000), give_up)
    code = app.exec()
    server.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
