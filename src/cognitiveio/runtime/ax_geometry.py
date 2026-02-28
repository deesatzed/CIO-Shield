from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass
class CaretPoint:
    x: float
    y: float
    source: str


class AXCaretLocator:
    """Best-effort caret geometry locator using Accessibility APIs."""

    def __init__(self):
        self._ax: Optional[Dict[str, Any]] = None

        try:
            from ApplicationServices import (  # type: ignore
                AXUIElementCopyAttributeValue,
                AXUIElementCopyParameterizedAttributeValue,
                AXUIElementCreateSystemWide,
                AXValueCreate,
                kAXBoundsForRangeParameterizedAttribute,
                kAXFocusedUIElementAttribute,
                kAXPositionAttribute,
                kAXSelectedTextRangeAttribute,
                kAXSizeAttribute,
                kAXValueCFRangeType,
            )
        except Exception:
            self._ax = None
            return

        self._ax = {
            "copy": AXUIElementCopyAttributeValue,
            "copy_param": AXUIElementCopyParameterizedAttributeValue,
            "system": AXUIElementCreateSystemWide,
            "value_create": AXValueCreate,
            "bounds_for_range": kAXBoundsForRangeParameterizedAttribute,
            "focused": kAXFocusedUIElementAttribute,
            "position": kAXPositionAttribute,
            "selected_range": kAXSelectedTextRangeAttribute,
            "size": kAXSizeAttribute,
            "value_cf_range": kAXValueCFRangeType,
        }

    @property
    def available(self) -> bool:
        return self._ax is not None

    @staticmethod
    def _rect_to_point(rect_obj: Any) -> Optional[Tuple[float, float]]:
        if rect_obj is None:
            return None
        try:
            if all(hasattr(rect_obj, k) for k in ("origin", "size")):
                x = float(rect_obj.origin.x)
                y = float(rect_obj.origin.y)
                h = float(rect_obj.size.height)
                return x + 6.0, y + h + 6.0
            if all(hasattr(rect_obj, k) for k in ("x", "y", "height")):
                return float(rect_obj.x + 6.0), float(rect_obj.y + rect_obj.height + 6.0)
        except Exception:
            return None
        return None

    @staticmethod
    def _range_to_tuple(rng: Any) -> Optional[Tuple[int, int]]:
        if rng is None:
            return None
        try:
            if hasattr(rng, "location") and hasattr(rng, "length"):
                return int(rng.location), int(rng.length)
            if hasattr(rng, "rangeValue"):
                rv = rng.rangeValue()
                return int(rv.location), int(rv.length)
            if isinstance(rng, tuple) and len(rng) == 2:
                return int(rng[0]), int(rng[1])
        except Exception:
            return None
        return None

    def _focused_element(self):
        assert self._ax is not None
        system = self._ax["system"]()
        err, focused = self._ax["copy"](system, self._ax["focused"], None)
        if err or not focused:
            return None
        return focused

    def _bounds_for_range(self, focused: Any, range_obj: Any) -> Optional[Tuple[float, float]]:
        assert self._ax is not None
        try:
            err_bounds, bounds = self._ax["copy_param"](
                focused,
                self._ax["bounds_for_range"],
                range_obj,
                None,
            )
            if err_bounds or bounds is None:
                return None
            return self._rect_to_point(bounds)
        except Exception:
            return None

    def locate(self) -> Optional[CaretPoint]:
        if self._ax is None:
            return None

        focused = self._focused_element()
        if focused is None:
            return None

        # 1) Direct selected text range bounds.
        try:
            err, selected_range = self._ax["copy"](focused, self._ax["selected_range"], None)
            if not err and selected_range is not None:
                pt = self._bounds_for_range(focused, selected_range)
                if pt:
                    return CaretPoint(pt[0], pt[1], "selected_range_bounds")

                # 2) Collapsed caret at end of selected range.
                parsed = self._range_to_tuple(selected_range)
                if parsed is not None:
                    end_loc = parsed[0] + parsed[1]
                    collapsed = self._ax["value_create"](self._ax["value_cf_range"], (end_loc, 0))
                    if collapsed is not None:
                        pt2 = self._bounds_for_range(focused, collapsed)
                        if pt2:
                            return CaretPoint(pt2[0], pt2[1], "collapsed_end_range")
        except Exception:
            pass

        # 3) Fallback to focused element frame.
        try:
            err_pos, pos = self._ax["copy"](focused, self._ax["position"], None)
            err_size, size = self._ax["copy"](focused, self._ax["size"], None)
            if (not err_pos) and (not err_size) and pos and size:
                x = float(pos.x)
                y = float(pos.y)
                h = float(size.height)
                return CaretPoint(x + 6.0, y + h + 6.0, "focused_frame")
        except Exception:
            return None

        return None
