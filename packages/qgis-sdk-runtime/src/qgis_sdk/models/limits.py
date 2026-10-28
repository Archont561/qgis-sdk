"""Numeric limits shared by every wire representation of an SDK contract."""

# JSON has one double-precision number space, and this is the largest magnitude an
# ECMAScript peer represents exactly. The schema generator bounds integers to
# this range so Python and JavaScript peers agree on the contract.
MAX_SAFE_INTEGER = 9_007_199_254_740_991

__all__ = ["MAX_SAFE_INTEGER"]
