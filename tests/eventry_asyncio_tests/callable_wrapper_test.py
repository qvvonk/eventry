from __future__ import annotations

from eventry.asyncio.callable_wrappers import CallableWrapper


def test_detects_varargs():
    with_varargs = CallableWrapper(lambda *_: True)
    without_varargs = CallableWrapper(lambda: False)

    assert with_varargs._has_varargs is True
    assert without_varargs._has_varargs is False


def test_detects_varkw():
    with_kwargs = CallableWrapper(lambda **_: True)
    without_kwargs = CallableWrapper(lambda: True)

    assert with_kwargs._has_varkw is True
    assert without_kwargs._has_varkw is False


def test_posonly_count():
    with_posonly = CallableWrapper(lambda a, b, /: True)
    without_posonly = CallableWrapper(lambda: True)

    assert with_posonly._posonly_c == 2
    assert without_posonly._posonly_c == 0
