"""year-in-ai — a Wrapped-style retrospective over local AI history.

The package is deliberately split so that the deterministic core (readers,
metrics, personality, aura, redaction) never imports a rendering or LLM
dependency.  Everything under :mod:`yia.readers` is absent-tolerant: a store
that is not on this machine yields an unavailable :class:`~yia.model.SourceReport`
rather than raising, and every metric derived from it is omitted from the
payload instead of being reported as zero.
"""

__version__ = "0.1.0"
SCHEMA = "year-in-ai/v1"
