# Alpha Evolve Shell (`ae_shell.py`)

An interactive command-line interface for managing engines, assistants, sessions, experiments, and programs in the Google Cloud Discovery Engine API for the Alpha Evolve platform.

When you are running an experiment, this will allow you to view the state of the experiment and view the evolving code.

## Prerequisites

-   **Python 3**
-   **Google Cloud SDK (`gcloud`)** installed and authenticated.
-   **Application Default Credentials** configured:
    ```bash
    gcloud auth application-default login
    ```

## Quick start
Run:
```bash
gcloud auth application-default login
export PROJECT_ID='my_project'
export PROJECT_NUMBER='123456789012'
export ENGINE_ID='alpha-evolve-experiment-engine'
python3 ./ae_shell.py
```
Then:
```
list_engines
list_assistants
list_sessions # this will set the session id
list_experiments # this will set the experiment id
list_programs    # this will list the programs in the current experiment
```
Each of these commands will show output, but will not show values if the 
If on the first run `list_sessions` does not show any session IDs, you must try again to get the session ID. It means the process has not yet created a session. Without the Session ID, you can't get a list of experiments for that session. 

## Usage

Run the script directly:

```bash
./ae_shell.py
```

Or with python:

```bash
python3 ae_shell.py
```

## Environment Variables

The shell uses the following environment variables for default values. You can set these before running the shell or use the `set` command inside the shell.

-   `PROJECT_ID`: Google Cloud Project ID (Default: `my_project`)
-   `PROJECT_NUMBER`: Google Cloud Project Number (Default: `123456789012`)
-   `ENGINE_ID`: Discovery Engine ID (Default: `alpha-evolve-experiment-engine`)
-   `ASSISTANT_ID`: Assistant ID (Default: `default_assistant`)
-   `SESSION_ID`: Session ID (Optional)
-   `EXPERIMENT_ID`: Experiment ID (Optional)

## Commands

### Engine Management

-   `create_engine`: Creates a Discovery Engine with the current `ENGINE_ID`.
-   `delete_engine`: Deletes the Discovery Engine with the current `ENGINE_ID`.
-   `list_engines`: Lists all Discovery Engines in the project.

### Assistant Management

-   `create_assistant`: Creates an assistant for the current engine.
-   `delete_assistant`: Deletes the assistant for the current engine.
-   `list_assistants`: Lists assistants for the current engine.

### Session & Experiment Management

-   `create_session`: Creates a new session and automatically captures the `SESSION_ID`.
-   `list_sessions`: Lists sessions for the engine and captures the most recent `SESSION_ID`.
-   `list_experiments`: Lists Alpha Evolve experiments for the current session. **Requires `SESSION_ID` to be set.**
-   `list_programs`: Lists Alpha Evolve programs for the current experiment. **Requires `SESSION_ID` and `EXPERIMENT_ID` to be set.**

### Shell Configuration

-   `set <variable> <value>`: Sets a shell variable.
    -   Supported variables: `project_id`, `project_number`, `engine_id`, `assistant_id`, `session_id`, `experiment_id`
-   `show`: Displays the current values of all variables.
-   `help` or `?`: Shows help for commands.
-   `exit` or Ctrl-D: Exits the shell.
