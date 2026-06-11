import os

from langchain.tools import tool

APPS = {
    "chrome":     r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "notepad":    "notepad.exe",
    "calculator": "calc.exe",
    "explorer":   "explorer.exe",
    "vscode":     r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
}


def launch_app(name: str) -> str:
    """Core launcher logic — call this directly in scripts and tests."""
    path = APPS.get(name.lower().strip())
    if not path:
        return f"Unknown app '{name}'. Known: {', '.join(APPS)}"
    os.startfile(os.path.expandvars(path))
    return f"Opened {name}"


@tool
def open_app(name: str) -> str:
    """Open a Windows application by name.
    Available: chrome, notepad, calculator, explorer, vscode."""
    return launch_app(name)


if __name__ == "__main__":
    # @tool wraps the function — use launch_app() for direct calls,
    # or open_app.invoke() for the LangChain tool interface.
    print(launch_app("calculator"))
    # print(open_app.invoke({"name": "calculator"}))
