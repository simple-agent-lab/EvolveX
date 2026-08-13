"""Shared declarative config fragments for mutate operators."""

from evolve.frozen.config import Config, array, boolean, integer, object, string

RUNNER_CONFIG = Config(
    {
        "runner": string(
            default="local",
            choices=("local", "harbor"),
            description="Execution backend for the mutation agent.",
        ),
        "command": string(description="Explicit local mutation command."),
        "agent": string(description="Agent implementation or built-in agent name."),
        "model": string(description="Model passed to the selected agent."),
        "environment": string(description="Harbor environment implementation."),
        "environment_kwargs": object(
            additional_properties=True,
            description="Arguments passed to the Harbor environment.",
        ),
        "image": string(description="Container image used by the Harbor environment."),
        "workdir": string(description="Agent working directory."),
        "agent_kwargs": object(
            additional_properties=True,
            description="Arguments passed to the selected agent.",
        ),
        "agent_env": object(
            additional_properties=True,
            description="Environment variables passed to the selected agent.",
        ),
        "agent_pythonpath": string(description="Additional agent Python import path."),
        "jobs_dir": string(description="Directory for Harbor job records."),
    }
)


WORKSPACE_CONFIG = RUNNER_CONFIG.extend(
    {
        "expose_gate_data": boolean(
            default=False,
            description="Expose gate artifacts to the mutation agent.",
        ),
        "editable_roots": array(
            string(),
            default=["target"],
            description="Workspace roots the mutation agent may edit.",
        ),
        "max_retries": integer(
            default=0,
            minimum=0,
            description="Additional mutation attempts after the first failure.",
        ),
    }
)
