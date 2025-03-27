# AnySqlDiag extension for Visual Studio Code

A Visual Studio Code extension to diagnose any SQL dialects supported by [sqlglot](https://github.com/tobymao/sqlglot) package:

- Athena
- BigQuery
- ClickHouse
- Databricks
- Doris
- Drill
- Druid
- DuckDB
- Dune
- Hive
- Materialize
- MySQL
- Oracle
- Postgres
- Presto
- PRQL
- Redshift
- RisingWave
- Snowflake
- Spark
- Spark2
- SQLite
- StarRocks
- Tableau
- Teradata
- Trino
- TSQL

This extension uses [AnySqlDiag](https://github.com/Minyus/any-sql-diag) CLI.

### Requirements

Prepare Python 3.9+ environment and install:

```
pip install pygls packaging anysqldiag
```

### Disabling AnySqlDiag

You can skip diagnosis with AnySqlDiag for specific files or directories by setting the `anysqldiag.ignorePatterns` setting.

But if you wish to disable diagnosis with AnySqlDiag for your entire workspace or globally, you can [disable this extension](https://code.visualstudio.com/docs/editor/extension-marketplace#_disable-an-extension) in Visual Studio Code.

## Settings

There are several settings you can configure to customize the behavior of this extension.

| Settings                    | Default              | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| --------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| anysqldiag.args             | `[]`                 | Arguments passed to anysqldiag. Each argument should be provided as a separate string in the array. <br> Examples:  <br>- `\"anysqldiag.args\": [\"--max_errors=5\"]` <br> - `\"anysqldiag.args\": [\"--max_errors=5\", \"--dialect=spark\"]`                                                                                                                                                                                                                                                                                                                                              |
| anysqldiag.cwd              | `${workspaceFolder}` | Sets the current working directory. By default, it uses the root directory of the workspace `${workspaceFolder}`. You can set it to `${fileDirname}` to use the parent folder of the file being diagnosed as the working directory.                                                                                                                                                                                                                                                                                                                                                        |
| anysqldiag.enabled          | `true`               | Enable/disable diagnosis of SQL files with Anysqldiag.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| anysqldiag.severity         | Not supported        |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| anysqldiag.path             | `[]`                 | Path or command to be used by the extension. Accepts an array of a single or multiple strings. If passing a command, each argument should be provided as a separate string in the array. If set to `[\"anysqldiag\"]`, it will use the version of anysqldiag available in the `PATH` environment variable. Note: Using this option may slowdown. <br>Examples: <br>- `[\"~/global_env/anysqldiag\"]` <br>- `[\"conda\", \"run\", \"-n\", \"lint_env\", \"python\", \"-m\", \"anysqldiag\"]` <br> `[\"anysqldiag\"]`                                                                        |
| anysqldiag.interpreter      | `[]`                 | Path to a Python executable or a command that will be used to launch the Anysqldiag server and any subprocess. Accepts an array of a single or multiple strings.  When set to `[]`, the extension will use the path to the selected Python interpreter. If passing a command, each argument should be provided as a separate string in the array.                                                                                                                                                                                                                                          |
| anysqldiag.importStrategy   | `useBundled`         | Defines which Anysqldiag binary to be used to lint Python files. When set to `useBundled`, the extension will use the Anysqldiag binary that is shipped with the extension. When set to `fromEnvironment`, the extension will attempt to use the Anysqldiag binary and all dependencies that are available in the currently selected environment. Note: If the extension can't find a valid Anysqldiag binary in the selected environment, it will fallback to using the Anysqldiag binary that is shipped with the extension. This setting will be overriden if `anysqldiag.path` is set. |
| anysqldiag.showNotification | `off`                | Controls when notifications are shown by this extension. Accepted values are `onError`, `onWarning`, `always` and `off`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| anysqldiag.lintOnChange     | `false`              | Enable diagnosis as you type.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| anysqldiag.ignorePatterns   | `[]`                 | Configure [glob patterns](https://docs.python.org/3/library/fnmatch.html) as supported by the fnmatch Python library to exclude files or folders from being linted with Anysqldiag.                                                                                                                                                                                                                                                                                                                                                                                                        |

The following variables are supported for substitution in the `anysqldiag.args`, `anysqldiag.cwd`, `anysqldiag.path`, `anysqldiag.interpreter` and `anysqldiag.ignorePatterns` settings:

- `${workspaceFolder}`
- `${workspaceFolder:FolderName}`
- `${userHome}`
- `${env:EnvVarName}`

The `anysqldiag.path` setting also supports the `${interpreter}` variable as one of the entries of the array. This variable is subtituted based on the value of the `anysqldiag.interpreter` setting.

## Commands

| Command                    | Description                       |
| -------------------------- | --------------------------------- |
| Anysqldiag: Restart Server | Force re-start the linter server. |

## Logging

From the Command Palette (**View** > **Command Palette ...**), run the **Developer: Set Log Level...** command. Select **Anysqldiag** from the **Extension logs** group. Then select the log level you want to set.

Alternatively, you can set the `anysqldiag.trace.server` setting to `verbose` to get more detailed logs from the AnySqlDiag server. This can be helpful when filing bug reports.

To open the logs, click on the language status icon (`{}`) on the bottom right of the Status bar, next to the Python language mode. Locate the **Anysqldiag** entry and select **Open logs**.

## Troubleshooting

In this section, you will find some common issues you might encounter and how to resolve them. If you are experiencing any issues that are not covered here, please [file an issue](https://github.com/Minyus/vscode-any-sql-diag/issues).

- If the `anysqldiag.importStrategy` setting is set to `fromEnvironment` but AnySqlDiag is not found in the selected environment, this extension will fallback to using the AnySqlDiag binary that is shipped with the extension. However, if there are dependencies installed in the environment, those dependencies will be used along with the shipped AnySqlDiag binary. This can lead to problems if the dependencies are not compatible with the shipped AnySqlDiag binary.

    To resolve this issue, you can:

  - Set the `anysqldiag.importStrategy` setting to `useBundled` and the `anysqldiag.path` setting to point to the custom binary of AnySqlDiag you want to use; or
  - Install AnySqlDiag in the selected environment.

## Credit

This extension was developed as a fork of [Pylint](https://marketplace.visualstudio.com/items?itemName=ms-python.pylint) VS Code extension.
