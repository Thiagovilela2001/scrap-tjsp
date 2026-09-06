"""Adaptadores para portais oficiais de jurisprudência."""

from .datajud import DataJudAdapter
from .esaj_cjsg import ESAJCJSGAdapter
from .stf import STFAdapter, converter_hit_stf
from .tjpr import TJPRAdapter

__all__ = ["DataJudAdapter", "ESAJCJSGAdapter", "STFAdapter", "TJPRAdapter", "converter_hit_stf"]
