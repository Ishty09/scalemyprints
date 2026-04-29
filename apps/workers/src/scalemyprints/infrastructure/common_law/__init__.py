"""
Common-law use checker adapters.

Implements domain.trademark.ports.CommonLawChecker.
"""

from scalemyprints.infrastructure.common_law.no_op import NoOpCommonLawChecker

__all__ = ["NoOpCommonLawChecker"]
