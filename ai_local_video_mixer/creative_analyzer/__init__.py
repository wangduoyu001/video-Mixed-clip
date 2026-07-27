"""Creative material understanding layer.

Provides structured analysis primitives for advertising video reconstruction.
"""

from .schema import CreativeAnalysis, ShotAnalysis, SubtitleRegion, ProductAppearance
from .shot_parser import ShotParser
from .subtitle_analyzer import SubtitleAnalyzer
from .product_detector import ProductDetector
from .copy_parser import CopyStructureParser

__all__ = [
    "CreativeAnalysis",
    "ShotAnalysis",
    "SubtitleRegion",
    "ProductAppearance",
    "ShotParser",
    "SubtitleAnalyzer",
    "ProductDetector",
    "CopyStructureParser",
]
