"""Product labels and launch targets shared by the interface and launcher."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    label: str
    kind: str
    experimental: bool = False

    @property
    def display(self):
        return self.label + (" · sperimentale" if self.experimental else "")


SERVICES = {
    "claude": "Claude Code",
    "chatgpt": "Codex",
    "gemini": "Antigravity / Gemini",
}
TARGETS = {
    "claude": {
        "web": Target("Claude Code sul web", "web"),
        "chat": Target("Claude sul web", "web"),
        "cli": Target("Claude Code CLI", "cli"),
        "desktop": Target("Claude Desktop", "desktop", True),
    },
    "chatgpt": {
        "web": Target("Codex sul web", "web"),
        "chat": Target("ChatGPT sul web", "web"),
        "cli": Target("Codex CLI", "cli"),
        "desktop": Target("Codex Desktop", "desktop", True),
    },
    "gemini": {
        "web": Target("Gemini sul web", "web"),
        "cli": Target("Antigravity CLI (agy)", "cli", True),
        "gemini-cli": Target("Gemini CLI", "cli"),
        "ide": Target("Antigravity IDE", "desktop", True),
        "desktop": Target("Antigravity App", "desktop", True),
    },
}
URLS = {
    ("claude", "web"): "https://claude.ai/code",
    ("claude", "chat"): "https://claude.ai/",
    ("chatgpt", "web"): "https://chatgpt.com/codex",
    ("chatgpt", "chat"): "https://chatgpt.com/",
    ("gemini", "web"): "https://gemini.google.com/",
}
CLI_NAMES = {("claude", "cli"): "claude", ("chatgpt", "cli"): "codex",
             ("gemini", "cli"): "agy", ("gemini", "gemini-cli"): "gemini"}
