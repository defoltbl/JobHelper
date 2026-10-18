#!/usr/bin/env python3
"""Build JobHelper.app, then check it.

    python scripts/build_app.py            # build into dist/, then check
    python scripts/build_app.py --check    # only check the app that is in dist/

The build uses PyInstaller with packaging/JobHelper.spec. The check never touches your data:
it starts the built app on a throwaway data folder with an in-memory keychain, and it asks
Claude nothing.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from jobhelper import app_info  # noqa: E402

DIST = ROOT / "dist"
APP = DIST / f"{app_info.NAME}.app"


class AppCheck:
    """What a built app must have and do before anyone opens it."""

    def __init__(self, app: Path) -> None:
        self._app = Path(app)
        self.problems: list[str] = []

    @property
    def program(self) -> Path:
        return self._app / "Contents" / "MacOS" / app_info.NAME

    def _expect(self, ok: bool, problem: str) -> None:
        print(("  ok    " if ok else "  WRONG ") + problem)
        if not ok:
            self.problems.append(problem)

    def _find(self, *parts: str) -> Path | None:
        """A file the app carries (PyInstaller puts data in Resources and programs in Frameworks)."""
        for base in ("Resources", "Frameworks"):
            path = self._app.joinpath("Contents", base, *parts)
            if path.exists():
                return path
        return None

    def run(self) -> bool:
        print(f"Checking {self._app}")
        self._expect(self.program.is_file(), "the app has its program")
        info = plistlib.loads((self._app / "Contents" / "Info.plist").read_bytes()) if self._app.is_dir() else {}
        self._expect(info.get("CFBundleIdentifier") == app_info.BUNDLE_ID, f"the bundle id is {app_info.BUNDLE_ID}")
        self._expect(info.get("CFBundleShortVersionString") == app_info.VERSION, f"the version is {app_info.VERSION}")
        self._expect(bool(info.get("NSAppleEventsUsageDescription")), "macOS can ask before the app controls Chrome")
        for part in (("ui_qt", "Main.qml"), ("ui_qt", "icon.icns"), ("ui_qt", "sounds", "limit.wav"), ("CHANGELOG.md",)):
            self._expect(self._find(*part) is not None, "it carries " + "/".join(part))
        claude = self._find("claude_agent_sdk", "_bundled", "claude")
        self._expect(claude is not None and os.access(claude, os.X_OK), "it carries the Claude program, ready to run")
        if claude is not None:
            done = subprocess.run([str(claude), "--version"], capture_output=True, text=True, timeout=60)
            self._expect(done.returncode == 0 and "Claude Code" in done.stdout, "the Claude program starts")
        widget = WidgetBuild(self._app).appex
        widget_info = plistlib.loads((widget / "Contents" / "Info.plist").read_bytes()) if (widget / "Contents" / "Info.plist").is_file() else {}
        self._expect(widget_info.get("NSExtension", {}).get("NSExtensionPointIdentifier") == "com.apple.widgetkit-extension"
                     and (widget / "Contents" / "MacOS" / app_info.WIDGET_NAME).is_file(), "it carries the macOS widget")
        reload = WidgetBuild(self._app).reload_helper
        exported = subprocess.run(["nm", "-gU", str(reload)], capture_output=True, text=True).stdout if reload.is_file() else ""
        self._expect("_jobhelper_reload_widgets" in exported, "it carries the library that redraws the widget at once")
        notify = NotifyBuild(self._app).library
        exported = subprocess.run(["nm", "-gU", str(notify)], capture_output=True, text=True).stdout if notify.is_file() else ""
        self._expect("_jobhelper_notify" in exported and "_jobhelper_notify_permission" in exported,
                     "it carries the library that shows its own notifications")
        program = widget / "Contents" / "MacOS" / app_info.WIDGET_NAME
        if program.is_file():
            started = subprocess.run([str(program)], capture_output=True, text=True, timeout=30)
            self._expect("cannot be run directly" in started.stdout + started.stderr,
                         "the widget starts as an extension (in NSExtensionMain), so macOS can keep it running")
        schemes = [s for t in info.get("CFBundleURLTypes", []) for s in t.get("CFBundleURLSchemes", [])]
        self._expect(app_info.URL_SCHEME in schemes, f"the widget's Open button can open the app ({app_info.URL_SCHEME}://)")
        rights = subprocess.run(["codesign", "-d", "--entitlements", "-", "--xml", str(widget)], capture_output=True, text=True).stdout
        self._expect("com.apple.security.app-sandbox" in rights and "JobHelper/widget/" in rights and "read-write" not in rights,
                     "the widget is sandboxed and may only read its own folder")
        signed = subprocess.run(["codesign", "--verify", "--deep", "--strict", str(self._app)], capture_output=True, text=True)
        self._expect(signed.returncode == 0, "the app is signed (for this Mac only)")
        if self.program.is_file():
            self._window_check()
        print(f"Size: {_size(self._app) / 1_048_576:.0f} MB")
        return not self.problems

    def _window_check(self) -> None:
        with tempfile.TemporaryDirectory(prefix="jobhelper-check-") as home:
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            env.update(JOBHELPER_HOME=home, JOBHELPER_VAULT_BACKEND="memory", JOBHELPER_CHECK_PICTURE=str(DIST / "window_check.png"))
            done = subprocess.run([str(self.program), "--check-window"], capture_output=True, text=True, timeout=180, env=env)
            last = [line for line in done.stdout.splitlines() if line.strip()][-5:]
            self._expect(done.returncode == 0, "the window opens without a problem" + ("" if done.returncode == 0 else ": " + " | ".join(last)))
            self._expect((DIST / "window_check.png").is_file(), "a picture of the window is in dist/window_check.png")
            refused = subprocess.run([str(self.program), "--check-window"], capture_output=True, text=True, timeout=60,
                                     env={k: v for k, v in env.items() if k not in ("JOBHELPER_HOME", "JOBHELPER_VAULT_BACKEND")})
            self._expect(refused.returncode == 2, "the window check refuses to run on real data")


class SwiftCompiler:
    """The Swift of the Command Line Tools, set up once for this Mac: the SDK, the processor and the oldest macOS the
    app supports. Both Swift parts of the app (the widget, the notifications) are compiled through it."""

    MIN_MACOS = "14.0"

    def __init__(self) -> None:
        self.swiftc = shutil.which("swiftc")
        self._sdk = self._arch = ""

    def __bool__(self) -> bool:
        return bool(self.swiftc)

    def _base(self) -> list[str]:
        if not self._sdk:
            self._sdk = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True).stdout.strip()
            self._arch = subprocess.run(["uname", "-m"], capture_output=True, text=True).stdout.strip() or "arm64"
        return [self.swiftc, "-O", "-target", f"{self._arch}-apple-macos{self.MIN_MACOS}", "-sdk", self._sdk]

    def program(self, source: Path, out: Path, frameworks: list[str], extra: list[str]) -> int:
        flags = [f for name in frameworks for f in ("-framework", name)]
        return subprocess.run(self._base() + extra + flags + [str(source), "-o", str(out)]).returncode

    def library(self, source: Path, out: Path, frameworks: list[str], module: str) -> int:
        out.parent.mkdir(parents=True, exist_ok=True)
        flags = [f for name in frameworks for f in ("-framework", name)]
        return subprocess.run(self._base() + ["-emit-library"] + flags + ["-module-name", module, str(source), "-o", str(out)]).returncode


class WidgetBuild:
    """The macOS widget: compiled from widget/JobHelperWidget.swift with the Swift of the Command Line Tools,
    put into the app as Contents/PlugIns/JobHelperWidget.appex, signed with its sandbox entitlements.
    Beside it, Contents/Frameworks/libJobHelperWidgetReload.dylib (widget/WidgetReload.swift) lets the app ask
    macOS to redraw the widget at once, from its own process. The app is signed again afterwards, because its
    contents changed."""

    SOURCE = ROOT / "widget" / "JobHelperWidget.swift"
    RELOAD_SOURCE = ROOT / "widget" / "WidgetReload.swift"
    ENTITLEMENTS = ROOT / "widget" / "JobHelperWidget.entitlements"
    MIN_MACOS = SwiftCompiler.MIN_MACOS

    def __init__(self, app: Path, swift: SwiftCompiler | None = None) -> None:
        self._app = Path(app)
        self._swift = swift or SwiftCompiler()

    @property
    def appex(self) -> Path:
        return self._app / "Contents" / "PlugIns" / f"{app_info.WIDGET_NAME}.appex"

    @property
    def reload_helper(self) -> Path:
        return self._app / "Contents" / "Frameworks" / app_info.WIDGET_RELOAD

    def info(self) -> dict:
        return {
            "CFBundleIdentifier": app_info.WIDGET_ID, "CFBundleName": app_info.WIDGET_NAME,
            "CFBundleDisplayName": app_info.NAME, "CFBundleExecutable": app_info.WIDGET_NAME,
            "CFBundlePackageType": "XPC!", "CFBundleInfoDictionaryVersion": "6.0",
            "CFBundleShortVersionString": app_info.VERSION, "CFBundleVersion": app_info.VERSION,
            "LSMinimumSystemVersion": self.MIN_MACOS,
            "NSExtension": {"NSExtensionPointIdentifier": "com.apple.widgetkit-extension"},
        }

    def run(self) -> int:
        if not self._swift:
            print("swiftc is not installed (xcode-select --install): the app is built without its widget.")
            return 1
        shutil.rmtree(self.appex, ignore_errors=True)
        macos = self.appex / "Contents" / "MacOS"
        macos.mkdir(parents=True)
        # as Xcode does for an extension: the process starts in NSExtensionMain, which then calls
        # the widget's own main. Started in main, the widget ended at once on macOS 26.
        code = self._swift.program(self.SOURCE, macos / app_info.WIDGET_NAME, ["WidgetKit", "SwiftUI"],
                                   ["-parse-as-library", "-application-extension", "-Xlinker", "-e", "-Xlinker", "_NSExtensionMain"])
        if code:
            return code
        code = self._swift.library(self.RELOAD_SOURCE, self.reload_helper, ["WidgetKit"], "JobHelperWidgetReload")
        if code:
            return code
        (self.appex / "Contents" / "Info.plist").write_bytes(plistlib.dumps(self.info()))
        for cmd in (["codesign", "--force", "--sign", "-", "--entitlements", str(self.ENTITLEMENTS), str(self.appex)],
                    ["codesign", "--force", "--sign", "-", str(self.reload_helper)],
                    ["codesign", "--force", "--sign", "-", str(self._app)]):
            done = subprocess.run(cmd, capture_output=True, text=True)
            if done.returncode:
                print(done.stderr.strip())
                return done.returncode
        return 0


class NotifyBuild:
    """The app's own notifications: macos/Notify.swift compiled into Contents/Frameworks/libJobHelperNotify.dylib
    and signed. The app loads it into its own process, so macOS shows the notifications under JobHelper's name
    and asks the person once. WidgetBuild signs the whole app afterwards, because its contents changed."""

    SOURCE = ROOT / "macos" / "Notify.swift"

    def __init__(self, app: Path, swift: SwiftCompiler | None = None) -> None:
        self._app = Path(app)
        self._swift = swift or SwiftCompiler()

    @property
    def library(self) -> Path:
        return self._app / "Contents" / "Frameworks" / app_info.NOTIFY_LIBRARY

    def run(self) -> int:
        if not self._swift:
            print("swiftc is not installed (xcode-select --install): the app is built without its own notifications.")
            return 1
        code = self._swift.library(self.SOURCE, self.library, ["UserNotifications"], "JobHelperNotify")
        if code:
            return code
        return subprocess.run(["codesign", "--force", "--sign", "-", str(self.library)]).returncode


def _size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def build() -> int:
    if shutil.which("pyinstaller") is None and not (Path(sys.executable).parent / "pyinstaller").exists():
        print("PyInstaller is not installed: pip install -r requirements-build.txt")
        return 1
    pyinstaller = shutil.which("pyinstaller") or str(Path(sys.executable).parent / "pyinstaller")
    done = subprocess.run([pyinstaller, "--noconfirm", "--clean", "--distpath", str(DIST),
                           "--workpath", str(ROOT / "build"), str(ROOT / "packaging" / "JobHelper.spec")], cwd=ROOT)
    return done.returncode


def main(argv: list[str]) -> int:
    if "--check" not in argv:
        swift = SwiftCompiler()
        code = build() or NotifyBuild(APP, swift).run() or WidgetBuild(APP, swift).run()
        if code:
            return code
    ok = AppCheck(APP).run()
    print("The app is ready: " + str(APP) if ok else "The app has problems (see WRONG above).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
