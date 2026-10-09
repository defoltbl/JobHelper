"""Run scripts in a real browser engine on a local page, for the tests of the form filler.

    python run_in_page.py page.html < scripts.json    ->  one JSON list of answers on stdout

No network is used: the page is a local file and the engine is told to load nothing else.
"""
import json
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWidgets import QApplication


def main() -> int:
    page_file, scripts = Path(sys.argv[1]).resolve(), json.loads(sys.stdin.read())
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])
    page = QWebEnginePage()
    page.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
    answers = []

    def step(_result=None, first=False):
        if not first:
            answers.append(_result)
        if len(answers) == len(scripts):
            print(json.dumps(answers))
            app.quit()
            return
        page.runJavaScript(scripts[len(answers)], 0, step)

    page.loadFinished.connect(lambda ok: QTimer.singleShot(150, lambda: step(first=True)) if ok else app.exit(2))
    page.load(QUrl.fromLocalFile(str(page_file)))
    QTimer.singleShot(40000, lambda: app.exit(3))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
