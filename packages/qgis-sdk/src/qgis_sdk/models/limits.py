"""Numeric limits shared by every wire representation of an SDK contract."""

# JSON has one double-precision number space, and this is the largest magnitude an
# ECMAScript peer represents exactly. The schema generator and the optional Pydantic
# adapter both bound integers with it, so the number lives here rather than in either
# backend: a contract that both sides can generate must not be able to disagree.
MAX_SAFE_INTEGER = 9_007_199_254_740_991

__all__ = ["MAX_SAFE_INTEGER"]
