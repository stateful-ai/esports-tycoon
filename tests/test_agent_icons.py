from pathlib import Path

import yaml
from PIL import Image


REPO = Path(__file__).resolve().parents[1]


def test_every_authored_agent_has_a_square_portrait() -> None:
    registry = yaml.safe_load((REPO / "data" / "agents.yaml").read_text(encoding="utf-8"))
    agent_ids = {agent["id"] for agent in registry["agents"]}
    icon_dir = REPO / "assets" / "agents"
    icon_ids = {path.stem for path in icon_dir.glob("*.webp")}

    assert icon_ids == agent_ids

    for agent_id in sorted(agent_ids):
        with Image.open(icon_dir / f"{agent_id}.webp") as image:
            assert image.width == image.height
            assert image.width >= 256
