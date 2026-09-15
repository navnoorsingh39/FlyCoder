"""CSS viewport environment: one square, the job is to center it.

This is the EXPERIMENTAL task. It does not live in the fly. The connectome never
sees CSS text; FlyCoder's encoder turns the numeric layout state into sensory
drive, and the decoder turns descending-neuron activity into interface controls.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config as C

INITIAL_CONTAINER = {
    "width": "100vw",
    "height": "100vh",
}

INITIAL_TARGET = {
    "width": "120px",
    "height": "120px",
    "background": "#8cff66",
}

# Semantic actions → CSS. DISPLAY_* overwrite display; the rest accumulate.
# DELETE_LAST pops the last committed action; RUN is a no-op on the stylesheet.
ACTION_LABELS = {
    "DISPLAY_BLOCK": "display: block;",
    "DISPLAY_FLEX": "display: flex;",
    "TEXT_ALIGN_CENTER": "text-align: center;",
    "MARGIN_AUTO": "margin: auto;",
    "JUSTIFY_CENTER": "justify-content: center;",
    "ALIGN_CENTER": "align-items: center;",
    "DELETE_LAST": "/* delete last rule */",
    "RUN": "/* run / evaluate */",
}


@dataclass
class EnvState:
    target_x: float
    target_y: float
    viewport_width: float
    viewport_height: float
    horizontal_error: float
    vertical_error: float
    distance_from_center: float
    previous_distance: float
    reward: float
    centered: bool
    css_text: str
    stack: list[str]
    max_distance: float


def _fmt_block(selector: str, props: dict[str, str], order: list[str]) -> str:
    lines = [f"{selector} {{"]
    for key in order:
        if key in props:
            lines.append(f"  {key}: {props[key]};")
    lines.append("}")
    return "\n".join(lines)


def compile_properties(stack: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Replay the action stack into container / target property dicts."""
    container = dict(INITIAL_CONTAINER)
    target = dict(INITIAL_TARGET)
    for action in stack:
        if action == "DISPLAY_BLOCK":
            container["display"] = "block"
        elif action == "DISPLAY_FLEX":
            container["display"] = "flex"
        elif action == "TEXT_ALIGN_CENTER":
            container["text-align"] = "center"
            target["display"] = "inline-block"
        elif action == "MARGIN_AUTO":
            target["margin"] = "auto"
        elif action == "JUSTIFY_CENTER":
            container["justify-content"] = "center"
        elif action == "ALIGN_CENTER":
            container["align-items"] = "center"
    return container, target


def render_css(stack: list[str]) -> str:
    container, target = compile_properties(stack)
    return (
        _fmt_block(
            ".container",
            container,
            ["width", "height", "display", "justify-content", "align-items", "text-align"],
        )
        + "\n\n"
        + _fmt_block(".target", target, ["width", "height", "background", "display", "margin"])
    )


def layout_position(
    container: dict[str, str],
    target: dict[str, str],
    viewport_width: float,
    viewport_height: float,
    target_w: float,
    target_h: float,
) -> tuple[float, float]:
    """Minimal layout that matches the CSS subset this experiment actually uses.

    Block: a sized block stays top-left; margin:auto centers on X only;
    text-align:center centers an inline-block child on X only.
    Flex: justify-content/align-items/margin:auto as in a one-item flex container.
    """
    display = container.get("display", "block")
    justify = container.get("justify-content", "flex-start")
    align = container.get("align-items", "stretch")
    text_align = container.get("text-align", "left")
    margin = target.get("margin", "0")
    tdisplay = target.get("display", "block")
    x, y = 0.0, 0.0
    if display == "flex":
        if justify == "center" or margin == "auto":
            x = (viewport_width - target_w) / 2.0
        if align == "center" or margin == "auto":
            y = (viewport_height - target_h) / 2.0
    else:
        if margin == "auto":
            x = (viewport_width - target_w) / 2.0
        elif text_align == "center" and tdisplay == "inline-block":
            x = (viewport_width - target_w) / 2.0
        y = 0.0
    return x, y


class CoderEnv:
    """Browser-viewport toy: one .target square inside a .container."""

    def __init__(
        self,
        viewport_width: float = C.VIEWPORT_WIDTH,
        viewport_height: float = C.VIEWPORT_HEIGHT,
        target_w: float = C.TARGET_WIDTH,
        target_h: float = C.TARGET_HEIGHT,
        tolerance: float = C.CENTER_TOLERANCE_PX,
    ):
        self.viewport_width = float(viewport_width)
        self.viewport_height = float(viewport_height)
        self.target_w = float(target_w)
        self.target_h = float(target_h)
        self.tolerance = float(tolerance)
        self.stack: list[str] = []
        self.reset()

    def reset(self) -> EnvState:
        self.stack = []
        self.previous_distance = 0.0
        self.reward = 0.0
        self._sync_layout()
        self.previous_distance = self.distance_from_center
        self.initial_distance = max(self.distance_from_center, 1.0)
        self.max_distance = self.initial_distance
        self.reward = 0.0
        return self.state()

    def _sync_layout(self) -> None:
        container, target = compile_properties(self.stack)
        self.container = container
        self.target = target
        self.target_x, self.target_y = layout_position(
            container, target,
            self.viewport_width, self.viewport_height,
            self.target_w, self.target_h,
        )
        cx = self.target_x + self.target_w / 2.0
        cy = self.target_y + self.target_h / 2.0
        self.horizontal_error = cx - self.viewport_width / 2.0
        self.vertical_error = cy - self.viewport_height / 2.0
        self.distance_from_center = (self.horizontal_error ** 2 + self.vertical_error ** 2) ** 0.5
        self.css_text = render_css(self.stack)
        self.centered = (
            abs(self.horizontal_error) <= self.tolerance
            and abs(self.vertical_error) <= self.tolerance
        )

    def apply(self, action: str) -> EnvState:
        """Commit a coding action, then score reward = previous_distance - current_distance."""
        if action not in C.ACTIONS:
            raise ValueError(f"unknown action {action!r}")
        prev = self.distance_from_center
        if action == "DELETE_LAST":
            if self.stack:
                self.stack.pop()
        elif action != "RUN":
            self.stack.append(action)
        self._sync_layout()
        self.previous_distance = prev
        self.reward = (prev - self.distance_from_center) / self.initial_distance
        return self.state()

    def state(self) -> EnvState:
        return EnvState(
            target_x=self.target_x,
            target_y=self.target_y,
            viewport_width=self.viewport_width,
            viewport_height=self.viewport_height,
            horizontal_error=self.horizontal_error,
            vertical_error=self.vertical_error,
            distance_from_center=self.distance_from_center,
            previous_distance=self.previous_distance,
            reward=self.reward,
            centered=self.centered,
            css_text=self.css_text,
            stack=list(self.stack),
            max_distance=self.max_distance,
        )

    def to_dict(self) -> dict:
        s = self.state()
        return {
            "target_x": round(s.target_x, 2),
            "target_y": round(s.target_y, 2),
            "target_w": self.target_w,
            "target_h": self.target_h,
            "viewport_width": s.viewport_width,
            "viewport_height": s.viewport_height,
            "horizontal_error": round(s.horizontal_error, 2),
            "vertical_error": round(s.vertical_error, 2),
            "distance_from_center": round(s.distance_from_center, 2),
            "previous_distance": round(s.previous_distance, 2),
            "reward": round(s.reward, 4),
            "centered": s.centered,
            "css_text": s.css_text,
            "stack": s.stack,
            "container": dict(self.container),
            "target": dict(self.target),
            "x_centered": abs(s.horizontal_error) <= self.tolerance,
            "y_centered": abs(s.vertical_error) <= self.tolerance,
        }


if __name__ == "__main__":
    env = CoderEnv()
    assert not env.centered
    assert env.horizontal_error < 0 and env.vertical_error < 0
    env.apply("DISPLAY_FLEX")
    assert not env.centered
    env.apply("JUSTIFY_CENTER")
    assert abs(env.horizontal_error) <= env.tolerance
    assert not env.centered
    env.apply("ALIGN_CENTER")
    assert env.centered, (env.horizontal_error, env.vertical_error)
    env.reset()
    env.apply("DISPLAY_FLEX")
    env.apply("MARGIN_AUTO")
    assert env.centered
    env.reset()
    env.apply("MARGIN_AUTO")
    assert abs(env.horizontal_error) <= env.tolerance
    assert not env.centered
    env.apply("DISPLAY_FLEX")
    assert env.centered
    env.reset()
    env.apply("TEXT_ALIGN_CENTER")
    assert abs(env.horizontal_error) <= env.tolerance
    assert not env.centered
    env.apply("DISPLAY_BLOCK")
    env.apply("DELETE_LAST")
    print("self-test OK")
    print(env.css_text)
