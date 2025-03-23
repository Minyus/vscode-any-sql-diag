# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Implementation of tool support over LSP."""
from __future__ import annotations

import copy
import json
import os
import pathlib
import re
import sys
import sysconfig
import traceback
from typing import Any, Callable, Dict, List, Optional, Sequence, Union


# **********************************************************
# Update sys.path before importing any bundled libraries.
# **********************************************************
def update_sys_path(path_to_add: str, strategy: str) -> None:
    """Add given path to `sys.path`."""
    if path_to_add not in sys.path and os.path.isdir(path_to_add):
        if strategy == "useBundled":
            sys.path.insert(0, path_to_add)
        else:
            sys.path.append(path_to_add)


# **********************************************************
# Update PATH before running anything.
# **********************************************************
def update_environ_path() -> None:
    """Update PATH environment variable with the 'scripts' directory.
    Windows: .venv/Scripts
    Linux/MacOS: .venv/bin
    """
    scripts = sysconfig.get_path("scripts")
    paths_variants = ["Path", "PATH"]

    for var_name in paths_variants:
        if var_name in os.environ:
            paths = os.environ[var_name].split(os.pathsep)
            if scripts not in paths:
                paths.insert(0, scripts)
                os.environ[var_name] = os.pathsep.join(paths)
                break


# Ensure that we can import LSP libraries, and other bundled libraries.
BUNDLE_DIR = pathlib.Path(__file__).parent.parent
# Always use bundled server files.
update_sys_path(os.fspath(BUNDLE_DIR / "tool"), "useBundled")
update_sys_path(
    os.fspath(BUNDLE_DIR / "libs"),
    os.getenv("LS_IMPORT_STRATEGY", "useBundled"),
)
update_environ_path()

# **********************************************************
# Imports needed for the language server goes below this.
# **********************************************************
# anysqldiag: disable=wrong-import-position,import-error
import lsp_jsonrpc as jsonrpc
import lsp_utils as utils
from lsprotocol import types as lsp
from pygls import server, uris, workspace

WORKSPACE_SETTINGS = {}
GLOBAL_SETTINGS = {}
RUNNER = pathlib.Path(__file__).parent / "runner.py"

MAX_WORKERS = 5
LSP_SERVER = server.LanguageServer(
    name="anysqldiag-server", version="v0.1.0", max_workers=MAX_WORKERS
)


# **********************************************************
# Tool specific code goes below this.
# **********************************************************
TOOL_MODULE = "anysqldiag"
TOOL_DISPLAY = "AnySqlDiag"
DOCUMENTATION_HOME = "https://github.com/Minyus/vscode-any-sql-diag"

# Default arguments always passed to anysqldiag.
TOOL_ARGS = []


# **********************************************************
# Linting features start here
# **********************************************************


# Captures version of `anysqldiag` in various workspaces.
VERSION_TABLE: Dict[str, (int, int, int)] = {}


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: lsp.DidOpenTextDocumentParams) -> None:
    """LSP handler for textDocument/didOpen request."""
    document = LSP_SERVER.workspace.get_document(params.text_document.uri)
    diagnostics: list[lsp.Diagnostic] = _linting_helper(document)
    LSP_SERVER.publish_diagnostics(document.uri, diagnostics)


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(params: lsp.DidSaveTextDocumentParams) -> None:
    """LSP handler for textDocument/didSave request."""
    document = LSP_SERVER.workspace.get_document(params.text_document.uri)
    diagnostics: list[lsp.Diagnostic] = _linting_helper(document)
    LSP_SERVER.publish_diagnostics(document.uri, diagnostics)


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(params: lsp.DidCloseTextDocumentParams) -> None:
    """LSP handler for textDocument/didClose request."""
    document = LSP_SERVER.workspace.get_document(params.text_document.uri)
    # Publishing empty diagnostics to clear the entries for this file.
    LSP_SERVER.publish_diagnostics(document.uri, [])


if os.getenv("VSCODE_ANYSQLDIAG_LINT_ON_CHANGE"):

    @LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
    def did_change(params: lsp.DidChangeTextDocumentParams) -> None:
        """LSP handler for textDocument/didChange request."""
        document = LSP_SERVER.workspace.get_document(params.text_document.uri)
        diagnostics: list[lsp.Diagnostic] = _linting_helper(document)
        LSP_SERVER.publish_diagnostics(document.uri, diagnostics)


def _linting_helper(document: workspace.Document) -> list[lsp.Diagnostic]:
    try:
        extra_args = []

        result = _run_tool_on_document(document, use_stdin=False, extra_args=extra_args)
        if result and result.stdout:
            log_to_output(f"{document.uri} :\r\n{result.stdout}")

            # deep copy here to prevent accidentally updating global settings.
            settings = copy.deepcopy(_get_settings_by_document(document))
            return _parse_output(result.stdout, severity=settings["severity"])
    except Exception:  # anysqldiag: disable=broad-except
        LSP_SERVER.show_message_log(
            f"Linting failed with error:\r\n{traceback.format_exc()}",
            lsp.MessageType.Error,
        )
    return []


def _parse_output(
    content: str,
    severity: Dict[str, str],
) -> list[lsp.Diagnostic]:
    """Parses linter messages and return LSP diagnostic object for each message."""
    diagnostics = []
    line_offset = 1
    char_offset = 1

    messages: List[Dict[str, Any]] = json.loads(content)
    for data in messages:
        assert "description" in data, data
        highlight = data.get("highlight", "")
        line: int = int(data.get("line", 1)) - line_offset
        col_start: int = int(data.get("col", 1))
        col_end: int = col_start + len(highlight)

        char_start: int = col_start - char_offset
        char_end: int = col_end - char_offset

        start = lsp.Position(
            line=line,
            character=char_start,
        )

        end = lsp.Position(
            line=line,
            character=char_end,
        )

        diag_code = data.get("description", "")
        diag_message = f"""{diag_code}: [{col_start}:{col_end}] `{highlight}`"""
        documentation_url = (
            "https://github.com/tobymao/sqlglot/blob/main/sqlglot/parser.py"
        )

        diagnostic = lsp.Diagnostic(
            range=lsp.Range(start=start, end=end),
            message=diag_message,
            severity=lsp.DiagnosticSeverity.Error,
            code=diag_code,
            code_description=lsp.CodeDescription(href=documentation_url),
            source=TOOL_DISPLAY,
        )

        diagnostics.append(diagnostic)

    return diagnostics


# **********************************************************
# Linting features end here
# **********************************************************


# **********************************************************
# Code Action features start here
# **********************************************************
class QuickFixSolutions:
    """Manages quick fixes registered using the quick fix decorator."""

    def __init__(self):
        self._solutions: Dict[
            str,
            Callable[[workspace.Document, List[lsp.Diagnostic]], List[lsp.CodeAction]],
        ] = {}

    def quick_fix(self, codes: Union[str, List[str]]):
        """Decorator used for registering quick fixes."""

        def decorator(
            func: Callable[
                [workspace.Document, List[lsp.Diagnostic]], List[lsp.CodeAction]
            ],
        ):
            if isinstance(codes, str):
                if codes in self._solutions:
                    raise utils.QuickFixRegistrationError(codes)
                self._solutions[codes] = func
            else:
                for code in codes:
                    if code in self._solutions:
                        raise utils.QuickFixRegistrationError(code)
                    self._solutions[code] = func

        return decorator

    def solutions(
        self, code: str
    ) -> Optional[
        Callable[[workspace.Document, List[lsp.Diagnostic]], List[lsp.CodeAction]]
    ]:
        """Given a anysqldiag error code returns a function, if available, that provides
        quick fix code actions."""
        return self._solutions.get(code, None)


QUICK_FIXES = QuickFixSolutions()


@LSP_SERVER.feature(
    lsp.TEXT_DOCUMENT_CODE_ACTION,
    lsp.CodeActionOptions(
        code_action_kinds=[lsp.CodeActionKind.QuickFix], resolve_provider=True
    ),
)
def code_action(params: lsp.CodeActionParams) -> List[lsp.CodeAction]:
    """LSP handler for textDocument/codeAction request."""

    document = LSP_SERVER.workspace.get_document(params.text_document.uri)
    settings = copy.deepcopy(_get_settings_by_document(document))
    code_actions = []
    if not settings["enabled"]:
        return code_actions

    diagnostics = (d for d in params.context.diagnostics if d.source == TOOL_DISPLAY)

    for diagnostic in diagnostics:
        func = QUICK_FIXES.solutions(diagnostic.code)
        if func:
            code_actions.extend(func(document, [diagnostic]))
    return code_actions


@QUICK_FIXES.quick_fix(codes=[])
def fix_format(
    _document: workspace.Document, diagnostics: List[lsp.Diagnostic]
) -> List[lsp.CodeAction]:
    """Provides quick fixes which involve formatting document."""
    return [
        _command_quick_fix(
            diagnostics=diagnostics,
            title=f"{TOOL_DISPLAY}: Run document formatting",
            command="editor.action.formatDocument",
        )
    ]


@QUICK_FIXES.quick_fix(codes=[])
def organize_imports(
    _document: workspace.Document, diagnostics: List[lsp.Diagnostic]
) -> List[lsp.CodeAction]:
    """Provides quick fixes which involve organizing imports."""
    return [
        _command_quick_fix(
            diagnostics=diagnostics,
            title=f"{TOOL_DISPLAY}: Run organize imports",
            command="editor.action.organizeImports",
        )
    ]


REPLACEMENTS: Dict[str, re.Pattern] = {}


def _get_replacement_edit(diagnostic: lsp.Diagnostic, lines: List[str]) -> lsp.TextEdit:
    new_line = lines[diagnostic.range.start.line]
    for replacement in REPLACEMENTS[diagnostic.code]:
        new_line = re.sub(
            replacement["pattern"],
            replacement["repl"],
            new_line,
        )
    return lsp.TextEdit(
        lsp.Range(
            start=lsp.Position(line=diagnostic.range.start.line, character=0),
            end=lsp.Position(line=diagnostic.range.start.line + 1, character=0),
        ),
        new_line,
    )


@QUICK_FIXES.quick_fix(
    codes=list(REPLACEMENTS.keys()),
)
def fix_with_replacement(
    document: workspace.Document, diagnostics: List[lsp.Diagnostic]
) -> List[lsp.CodeAction]:
    """Provides quick fixes which basic string replacements."""
    return [
        lsp.CodeAction(
            title=f"{TOOL_DISPLAY}: Run autofix code action",
            kind=lsp.CodeActionKind.QuickFix,
            diagnostics=diagnostics,
            edit=None,
            data=document.uri,
        )
    ]


@LSP_SERVER.feature(lsp.CODE_ACTION_RESOLVE)
def code_action_resolve(params: lsp.CodeAction) -> lsp.CodeAction:
    """LSP handler for codeAction/resolve request."""
    if params.data:
        document = LSP_SERVER.workspace.get_document(params.data)
        params.edit = _create_workspace_edits(
            document,
            [
                _get_replacement_edit(diagnostic, document.lines)
                for diagnostic in params.diagnostics
                if diagnostic.source == TOOL_DISPLAY and diagnostic.code in REPLACEMENTS
            ],
        )
    return params


def _command_quick_fix(
    diagnostics: List[lsp.Diagnostic],
    title: str,
    command: str,
    args: Optional[List[Any]] = None,
) -> lsp.CodeAction:
    return lsp.CodeAction(
        title=title,
        kind=lsp.CodeActionKind.QuickFix,
        diagnostics=diagnostics,
        command=lsp.Command(title=title, command=command, arguments=args),
    )


def _create_workspace_edits(
    document: workspace.Document, results: Optional[List[lsp.TextEdit]]
):
    return lsp.WorkspaceEdit(
        document_changes=[
            lsp.TextDocumentEdit(
                text_document=lsp.OptionalVersionedTextDocumentIdentifier(
                    uri=document.uri,
                    version=document.version if document.version else 0,
                ),
                edits=results,
            )
        ],
    )


# **********************************************************
# Code Action features end here
# **********************************************************


# **********************************************************
# Required Language Server Initialization and Exit handlers.
# **********************************************************
@LSP_SERVER.feature(lsp.INITIALIZE)
def initialize(params: lsp.InitializeParams) -> None:
    """LSP handler for initialize request."""
    log_to_output(f"CWD Server: {os.getcwd()}")
    import_strategy = os.getenv("LS_IMPORT_STRATEGY", "useBundled")
    update_sys_path(os.getcwd(), import_strategy)

    GLOBAL_SETTINGS.update(**params.initialization_options.get("globalSettings", {}))

    settings = params.initialization_options["settings"]
    _update_workspace_settings(settings)
    log_to_output(
        f"Settings used to run Server:\r\n{json.dumps(settings, indent=4, ensure_ascii=False)}\r\n"
    )
    log_to_output(
        f"Global settings:\r\n{json.dumps(GLOBAL_SETTINGS, indent=4, ensure_ascii=False)}\r\n"
    )

    # Add extra paths to sys.path
    setting = _get_settings_by_path(pathlib.Path(os.getcwd()))
    for extra in setting.get("extraPaths", []):
        update_sys_path(extra, import_strategy)

    paths = "\r\n   ".join(sys.path)
    log_to_output(f"sys.path used to run Server:\r\n   {paths}")


@LSP_SERVER.feature(lsp.EXIT)
def on_exit(_params: Optional[Any] = None) -> None:
    """Handle clean up on exit."""
    jsonrpc.shutdown_json_rpc()


@LSP_SERVER.feature(lsp.SHUTDOWN)
def on_shutdown(_params: Optional[Any] = None) -> None:
    """Handle clean up on shutdown."""
    jsonrpc.shutdown_json_rpc()


# *****************************************************
# Internal functional and settings management APIs.
# *****************************************************
def _get_global_defaults():
    return {
        "enabled": GLOBAL_SETTINGS.get("enabled", True),
        "path": GLOBAL_SETTINGS.get("path", []),
        "interpreter": GLOBAL_SETTINGS.get("interpreter", [sys.executable]),
        "args": GLOBAL_SETTINGS.get("args", []),
        "severity": GLOBAL_SETTINGS.get(
            "severity",
            {
                "convention": "Information",
                "error": "Error",
                "fatal": "Error",
                "refactor": "Hint",
                "warning": "Warning",
                "info": "Information",
            },
        ),
        "ignorePatterns": [],
        "importStrategy": GLOBAL_SETTINGS.get("importStrategy", "useBundled"),
        "showNotifications": GLOBAL_SETTINGS.get("showNotifications", "off"),
        "extraPaths": GLOBAL_SETTINGS.get("extraPaths", []),
    }


def _update_workspace_settings(settings):
    if not settings:
        key = utils.normalize_path(os.getcwd())
        WORKSPACE_SETTINGS[key] = {
            "cwd": key,
            "workspaceFS": key,
            "workspace": uris.from_fs_path(key),
            **_get_global_defaults(),
        }
        return

    for setting in settings:
        key = utils.normalize_path(uris.to_fs_path(setting["workspace"]))
        WORKSPACE_SETTINGS[key] = {
            **setting,
            "workspaceFS": key,
        }


def _get_settings_by_path(file_path: pathlib.Path):
    workspaces = {s["workspaceFS"] for s in WORKSPACE_SETTINGS.values()}

    while file_path != file_path.parent:
        str_file_path = utils.normalize_path(file_path)
        if str_file_path in workspaces:
            return WORKSPACE_SETTINGS[str_file_path]
        file_path = file_path.parent

    setting_values = list(WORKSPACE_SETTINGS.values())
    return setting_values[0]


def _get_document_key(document: workspace.Document):
    if WORKSPACE_SETTINGS:
        document_workspace = pathlib.Path(document.path)
        workspaces = {s["workspaceFS"] for s in WORKSPACE_SETTINGS.values()}

        # Find workspace settings for the given file.
        while document_workspace != document_workspace.parent:
            norm_path = utils.normalize_path(document_workspace)
            if norm_path in workspaces:
                return norm_path
            document_workspace = document_workspace.parent

    return None


def _get_settings_by_document(document: workspace.Document | None):
    if document is None or document.path is None:
        return list(WORKSPACE_SETTINGS.values())[0]

    key = _get_document_key(document)
    if key is None:
        # This is either a non-workspace file or there is no workspace.
        key = utils.normalize_path(pathlib.Path(document.path).parent)
        return {
            "cwd": key,
            "workspaceFS": key,
            "workspace": uris.from_fs_path(key),
            **_get_global_defaults(),
        }

    return WORKSPACE_SETTINGS[str(key)]


# *****************************************************
# Internal execution APIs.
# *****************************************************
def get_cwd(settings: Dict[str, Any], document: Optional[workspace.Document]) -> str:
    """Returns cwd for the given settings and document."""
    if settings["cwd"] == "${workspaceFolder}":
        return settings["workspaceFS"]

    if settings["cwd"] == "${fileDirname}":
        if document is not None:
            return os.fspath(pathlib.Path(document.path).parent)
        return settings["workspaceFS"]

    return settings["cwd"]


# anysqldiag: disable=too-many-branches,too-many-statements
def _run_tool_on_document(
    document: workspace.Document,
    use_stdin: bool = False,
    extra_args: Optional[Sequence[str]] = None,
) -> utils.RunResult | None:
    """Runs tool on the given document.

    if use_stdin is true then contents of the document is passed to the
    tool via stdin.
    """
    if extra_args is None:
        extra_args = []

    # deep copy here to prevent accidentally updating global settings.
    settings = copy.deepcopy(_get_settings_by_document(document))

    if not settings["enabled"]:
        log_warning(f"Skipping file [Linting Disabled]: {document.path}")
        log_warning("See `anysqldiag.enabled` in settings.json to enabling linting.")
        return None

    if str(document.uri).startswith("vscode-notebook-cell"):
        log_warning(f"Skipping notebook cells [Not Supported]: {str(document.uri)}")
        return None

    if utils.is_stdlib_file(document.path):
        log_warning(
            f"Skipping standard library file (stdlib excluded): {document.path}"
        )

        return None

    if utils.is_match(settings["ignorePatterns"], document.path):
        log_warning(
            f"Skipping file due to `anysqldiag.ignorePatterns` match: {document.path}"
        )
        return None

    code_workspace = settings["workspaceFS"]
    cwd = get_cwd(settings, document)

    use_path = False
    use_rpc = False
    if settings["path"]:
        # 'path' setting takes priority over everything.
        use_path = True
        argv = settings["path"]
    elif settings["interpreter"] and not utils.is_current_interpreter(
        settings["interpreter"][0]
    ):
        # If there is a different interpreter set use JSON-RPC to the subprocess
        # running under that interpreter.
        argv = [TOOL_MODULE]
        use_rpc = True
    else:
        # if the interpreter is same as the interpreter running this
        # process then run as module.
        argv = [TOOL_MODULE]

    argv += TOOL_ARGS + settings["args"] + extra_args

    # pygls normalizes the path to lowercase on windows, but we need to resolve the
    # correct capitalization to avoid https://github.com/anysqldiag-dev/anysqldiag/issues/10137
    resolved_path = str(pathlib.Path(document.path).resolve())

    if use_stdin:
        argv += ["--from_stdin"]
    else:
        argv += ["--file", resolved_path]

    env = None
    if use_path or use_rpc:
        # for path and rpc modes we need to set PYTHONPATH, for module or API mode
        # we would have already set the extra paths in the initialize handler.
        env = _get_updated_env(settings)

    if use_path:
        # This mode is used when running executables.
        log_to_output(" ".join(argv))
        log_to_output(f"CWD Server: {cwd}")
        result = utils.run_path(
            argv=argv,
            use_stdin=use_stdin,
            cwd=cwd,
            source=document.source.replace("\r\n", "\n"),
            env=env,
        )
        if result.stderr:
            log_to_output(result.stderr)
    elif use_rpc:
        # This mode is used if the interpreter running this server is different from
        # the interpreter used for running this server.
        log_to_output(" ".join(settings["interpreter"] + ["-m"] + argv))
        log_to_output(f"CWD Linter: {cwd}")

        result = jsonrpc.run_over_json_rpc(
            workspace=code_workspace,
            interpreter=settings["interpreter"],
            module=TOOL_MODULE,
            argv=argv,
            use_stdin=use_stdin,
            cwd=cwd,
            source=document.source,
            env=env,
        )
        result = _to_run_result_with_logging(result)
    else:
        # In this mode the tool is run as a module in the same process as the language server.
        log_to_output(" ".join([sys.executable, "-m"] + argv))
        log_to_output(f"CWD Linter: {cwd}")
        # This is needed to preserve sys.path, in cases where the tool modifies
        # sys.path and that might not work for this scenario next time around.
        with utils.substitute_attr(sys, "path", [""] + sys.path[:]):
            try:
                result = utils.run_module(
                    module=TOOL_MODULE,
                    argv=argv,
                    use_stdin=use_stdin,
                    cwd=cwd,
                    source=document.source,
                )
            except Exception:
                log_error(traceback.format_exc(chain=True))
                raise
        if result.stderr:
            log_to_output(result.stderr)

    return result


def _run_tool(extra_args: Sequence[str], settings: Dict[str, Any]) -> utils.RunResult:
    """Runs tool."""
    code_workspace = settings["workspaceFS"]
    cwd = get_cwd(settings, None)

    use_path = False
    use_rpc = False
    if len(settings["path"]) > 0:
        # 'path' setting takes priority over everything.
        use_path = True
        argv = settings["path"]
    elif len(settings["interpreter"]) > 0 and not utils.is_current_interpreter(
        settings["interpreter"][0]
    ):
        # If there is a different interpreter set use JSON-RPC to the subprocess
        # running under that interpreter.
        argv = [TOOL_MODULE]
        use_rpc = True
    else:
        # if the interpreter is same as the interpreter running this
        # process then run as module.
        argv = [TOOL_MODULE]

    argv += extra_args

    env = None
    if use_path or use_rpc:
        # for path and rpc modes we need to set PYTHONPATH, for module or API mode
        # we would have already set the extra paths in the initialize handler.
        env = _get_updated_env(settings)

    if use_path:
        # This mode is used when running executables.
        log_to_output(" ".join(argv))
        log_to_output(f"CWD Server: {cwd}")
        result = utils.run_path(argv=argv, use_stdin=True, cwd=cwd, env=env)
        if result.stderr:
            log_to_output(result.stderr)
    elif use_rpc:
        # This mode is used if the interpreter running this server is different from
        # the interpreter used for running this server.
        log_to_output(" ".join(settings["interpreter"] + ["-m"] + argv))
        log_to_output(f"CWD Linter: {cwd}")
        result = jsonrpc.run_over_json_rpc(
            workspace=code_workspace,
            interpreter=settings["interpreter"],
            module=TOOL_MODULE,
            argv=argv,
            use_stdin=True,
            cwd=cwd,
            env=env,
        )
        result = _to_run_result_with_logging(result)
    else:
        # In this mode the tool is run as a module in the same process as the language server.
        log_to_output(" ".join([sys.executable, "-m"] + argv))
        log_to_output(f"CWD Linter: {cwd}")
        # This is needed to preserve sys.path, in cases where the tool modifies
        # sys.path and that might not work for this scenario next time around.
        with utils.substitute_attr(sys, "path", [""] + sys.path[:]):
            try:
                result = utils.run_module(
                    module=TOOL_MODULE, argv=argv, use_stdin=True, cwd=cwd
                )
            except Exception:
                log_error(traceback.format_exc(chain=True))
                raise
        if result.stderr:
            log_to_output(result.stderr)

    log_to_output(f"\r\n{result.stdout}\r\n")
    return result


def _get_updated_env(settings: Dict[str, Any]) -> dict[str, str]:
    """Returns the updated environment variables."""
    extra_paths = settings.get("extraPaths", [])
    paths = os.environ.get("PYTHONPATH", "").split(os.pathsep) + extra_paths
    python_paths = os.pathsep.join([p for p in paths if len(p) > 0])

    env = {
        "LS_IMPORT_STRATEGY": settings["importStrategy"],
        "PYTHONUTF8": "1",
    }
    if python_paths:
        env["PYTHONPATH"] = python_paths
    return env


def _to_run_result_with_logging(rpc_result: jsonrpc.RpcRunResult) -> utils.RunResult:
    error = ""
    if rpc_result.exception:
        log_error(rpc_result.exception)
        error = rpc_result.exception
    elif rpc_result.stderr:
        log_to_output(rpc_result.stderr)
        error = rpc_result.stderr
    return utils.RunResult(rpc_result.stdout, error)


# *****************************************************
# Logging and notification.
# *****************************************************
def log_to_output(
    message: str, msg_type: lsp.MessageType = lsp.MessageType.Log
) -> None:
    """Logs messages to Output > Anysqldiag channel only."""
    LSP_SERVER.show_message_log(message, msg_type)


def log_error(message: str) -> None:
    """Logs messages with notification on error."""
    LSP_SERVER.show_message_log(message, lsp.MessageType.Error)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["onError", "onWarning", "always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Error)


def log_warning(message: str) -> None:
    """Logs messages with notification on warning."""
    LSP_SERVER.show_message_log(message, lsp.MessageType.Warning)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["onWarning", "always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Warning)


def log_always(message: str) -> None:
    """Logs messages with notification."""
    LSP_SERVER.show_message_log(message, lsp.MessageType.Info)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Info)


# *****************************************************
# Start the server.
# *****************************************************
if __name__ == "__main__":
    LSP_SERVER.start_io()
