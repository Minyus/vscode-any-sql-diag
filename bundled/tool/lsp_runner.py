# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""
Runner to use when running under a different interpreter.
"""

import os
import pathlib
import sys
import traceback


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


# Ensure that we can import LSP libraries, and other bundled libraries.
BUNDLE_DIR = pathlib.Path(__file__).parent.parent
# Always use bundled server files.
update_sys_path(os.fspath(BUNDLE_DIR / "tool"), "useBundled")
update_sys_path(
    os.fspath(BUNDLE_DIR / "libs"),
    os.getenv("LS_IMPORT_STRATEGY", "useBundled"),
)
update_sys_path(os.getcwd(), os.getenv("LS_IMPORT_STRATEGY", "useBundled"))


# anysqldiag: disable=wrong-import-position,import-error
import lsp_jsonrpc as jsonrpc
import lsp_utils as utils

RPC = jsonrpc.create_json_rpc(sys.stdin.buffer, sys.stdout.buffer)

EXIT_NOW = False
while not EXIT_NOW:
    msg = RPC.receive_data()

    method = msg["method"]
    if method == "exit":
        EXIT_NOW = True
        continue

    if method == "run":
        is_exception = False  # anysqldiag: disable=invalid-name
        # This is needed to preserve sys.path, anysqldiag modifies
        # sys.path and that might not work for this scenario
        # next time around.
        with utils.substitute_attr(sys, "path", [""] + sys.path[:]):
            try:
                result = utils.run_module(
                    module=msg["module"],
                    argv=msg["argv"],
                    use_stdin=msg["useStdin"],
                    cwd=msg["cwd"],
                    source=msg["source"] if "source" in msg else None,
                )
            except Exception:  # anysqldiag: disable=broad-except
                result = utils.RunResult("", traceback.format_exc(chain=True))
                is_exception = True  # anysqldiag: disable=invalid-name

        response = {"id": msg["id"], "error": result.stderr}
        if is_exception:
            response["exception"] = is_exception
        elif result.stdout:
            response["result"] = result.stdout

        RPC.send_data(response)
