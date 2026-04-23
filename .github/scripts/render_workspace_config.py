from __future__ import annotations

import os
from pathlib import Path

from jinja2 import Environment, StrictUndefined

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / "workspace-config.deploy.template.yml.j2"
OUTPUT_PATH = REPO_ROOT / "workspace-config.yml"


def main() -> int:
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")

    env = Environment(
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    template = env.from_string(template_text)

    rendered = template.render(
        llm_endpoint_name=os.environ["DEV_LLM_ENDPOINT_NAME"],
        agent_events_table=os.environ["DEV_AGENT_EVENTS_TABLE"],
    )

    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"Rendered {OUTPUT_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
