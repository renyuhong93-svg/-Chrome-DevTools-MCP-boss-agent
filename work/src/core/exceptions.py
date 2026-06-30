from __future__ import annotations


class AgentConfigurationError(RuntimeError):
    pass


class RuntimeDependencyError(RuntimeError):
    pass


class BrowserActionError(RuntimeError):
    pass


class BrowserPageNotReadyError(BrowserActionError):
    pass
