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


class WidgetBuild:
    """The macOS widget: compiled from widget/JobHelperWidget.swift with the Swift of the Command Line Tools,
    put into the app as Contents/PlugIns/JobHelperWidget.appex, signed with its sandbox entitlements.
    The app is signed again afterwards, because its contents changed."""

    SOURCE = ROOT / "widget" / "JobHelperWidget.swift"
    ENTITLEMENTS = ROOT / "widget" / "JobHelperWidget.entitlements"
    MIN_MACOS = "14.0"

    def __init__(self, app: Path) -> None:
        self._app = Path(app)

    @property
    def appex(self) -> Path:
        return self._app / "Contents" / "PlugIns" / f"{app_info.WIDGET_NAME}.appex"

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
        swiftc = shutil.which("swiftc")
        if not swiftc:
            print("swiftc is not installed (xcode-select --install): the app is built without its widget.")
            return 1
        shutil.rmtree(self.appex, ignore_errors=True)
        macos = self.appex / "Contents" / "MacOS"
        macos.mkdir(parents=True)
        sdk = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True).stdout.strip()
        arch = subprocess.run(["uname", "-m"], capture_output=True, text=True).stdout.strip() or "arm64"
        done = subprocess.run([swiftc, "-parse-as-library", "-application-extension", "-O",
                               "-target", f"{arch}-apple-macos{self.MIN_MACOS}", "-sdk", sdk,
                               "-framework", "WidgetKit", "-framework", "SwiftUI",
                               str(self.SOURCE), "-o", str(macos / app_info.WIDGET_NAME)])
        if done.returncode:
            return done.returncode
        (self.appex / "Contents" / "Info.plist").write_bytes(plistlib.dumps(self.info()))
        for cmd in (["codesign", "--force", "--sign", "-", "--entitlements", str(self.ENTITLEMENTS), str(self.appex)],
                    ["codesign", "--force", "--sign", "-", str(self._app)]):
            done = subprocess.run(cmd, capture_output=True, text=True)
            if done.returncode:
                print(done.stderr.strip())
                return done.returncode
        return 0


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
        code = build() or WidgetBuild(APP).run()
        if code:
            return code
    ok = AppCheck(APP).run()
    print("The app is ready: " + str(APP) if ok else "The app has problems (see WRONG above).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
