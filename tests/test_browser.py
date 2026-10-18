"""chrome.Browser: one browser the assistant works in, with its own words and AppleScript."""
from jobhelper import chrome
from jobhelper.chrome import Browser


def test_each_browser_is_one_object_with_named_fields():
    assert all(isinstance(b, Browser) and b.key == k for k, b in chrome.BROWSERS.items())
    safari, edge = chrome.BROWSERS["safari"], chrome.BROWSERS["edge"]
    assert (safari.app, safari.short, safari.safari) == ("Safari", "Safari", True)
    assert edge.switch.startswith("Tools > Developer") and not edge.safari


def test_a_browser_words_its_own_messages_and_builds_its_own_script():
    safari, chrome_ = chrome.BROWSERS["safari"], chrome.BROWSERS["chrome"]
    assert "Develop > Allow JavaScript" in safari.said("no_scripts") and "Safari" in safari.said("not_running")
    assert safari.tab == "current tab of front window" and chrome_.tab == "active tab of front window"
    assert "do JavaScript" in safari.run_action() and "execute active tab" in chrome_.run_action()
    script = chrome_.wrap("ACTION")
    assert script[0] == "on run argv" and 'tell application "Google Chrome"' in script and "ACTION" in script


def test_the_browser_in_use_is_chosen_once_and_anything_unknown_means_chrome():
    try:
        assert chrome.use("safari") == "safari" and chrome.browser().key == "safari" and chrome.short() == "Safari"
        assert chrome.use("netscape") == "chrome" and chrome.name() == "Google Chrome"
        assert chrome.browser("edge").short == "Edge" and chrome.current() == "chrome"   # asking about one does not choose it
    finally:
        chrome.use(chrome.DEFAULT)


def test_an_error_text_is_traced_back_to_its_kind_for_any_browser():
    assert chrome.ChromeError(chrome.BROWSERS["brave"].said("no_consent")).kind == "no_consent"
    assert chrome.ChromeError("something else").kind == "refused"
