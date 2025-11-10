from fasthtml.common import *  # type: ignore
from typing import Any


def modal_open_handler(ref_name: str) -> str:
    return f"$refs.{ref_name}.showModal(); document.documentElement.classList.add('modal-is-open', 'modal-is-opening'); setTimeout(() => document.documentElement.classList.remove('modal-is-opening'), 400)"


def modal_close_handler(ref_name: str) -> str:
    return f"$refs.{ref_name}.close(); document.documentElement.classList.add('modal-is-closing'); setTimeout(() => document.documentElement.classList.remove('modal-is-open', 'modal-is-closing'), 400)"


def modal_click_outside_handler() -> str:
    return "if ($event.target === $el) { $el.close(); document.documentElement.classList.add('modal-is-closing'); setTimeout(() => document.documentElement.classList.remove('modal-is-open', 'modal-is-closing'), 400); }"


def Modal(
    content: Any,
    ref_name: str,
    modal_id: str | None = None,
    **kwargs,
) -> Any:
    return Dialog(
        content,
        id=modal_id,
        x_ref=ref_name,
        _at_click=modal_click_outside_handler(),
        *kwargs,
    )


def ModalOpenButton(
    label: str,
    ref_name: str,
    **kwargs,
) -> Any:
    return Button(label, _at_click=modal_open_handler(ref_name), *kwargs)


def ModalCloseButton(ref_name: str, **kwargs) -> Any:
    return Button(
        aria_label="Close", rel="prev", _at_click=modal_close_handler(ref_name), *kwargs
    )
