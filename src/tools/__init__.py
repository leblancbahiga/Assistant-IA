from src.tools.registry import ToolRegistry, ToolDefinition, ToolParameter, ToolExecutor, ToolResult
from src.tools.document import DocumentGenerator, DocumentSpec, DocFormat, DocSection
from src.tools.shell_exec import (
    CommandCategory,
    ValidationResult,
    ExecutionResult,
    ShellSandbox,
    ApprovalRequest,
    ApprovalManager,
    register_shell_tools,
)
from src.tools.os_control import (
    AppAction,
    WindowAction,
    SystemControlType,
    AppResult,
    WindowInfo,
    AppInfo,
    OSController,
    register_os_tools,
)
from src.tools.browser_ctrl import (
    BrowserAction,
    BrowserResult,
    BrowserPage,
    FormField,
    NavigateResult,
    BrowserController,
    register_browser_tools,
)
from src.tools.file_ops import (
    PathSafety,
    FileOpResult,
    FileOpsController,
    register_file_tools,
)
from src.tools.memory_tools import (
    register_memory_tools,
)
# AgentOrchestrator ré-exporté via lazy imports (V16 FIX : pas de chargement au démarrage)
def AgentOrchestrator(*args, **kwargs):
    from src.agent.orchestrator import AgentOrchestrator as _c
    return _c(*args, **kwargs)

def AgentTrace(*args, **kwargs):
    from src.agent.orchestrator import AgentTrace as _c
    return _c(*args, **kwargs)

def PlanResult(*args, **kwargs):
    from src.agent.orchestrator import PlanResult as _c
    return _c(*args, **kwargs)

def VerifyResult(*args, **kwargs):
    from src.agent.orchestrator import VerifyResult as _c
    return _c(*args, **kwargs)

from src.tools.agent_tools import (
    register_agent_tools,
)
