"""核心引擎。应用层必须通过 api.Polarscan 访问，不能直接调用 core。"""
from .index import Polaroid, Asset, tag_prefix, tag_value, thumb_path_for
from .storage import (
    INDEX_FILENAME,
    read_index,
    write_index,
    list_polaroids,
)
from .asset_thumb import (
    THUMBS_DIRNAME,
    LONG_EDGE,
    QUALITY,
    HASH_ALGO,
    HASH_HEX_LEN,
    SHORT_HASH_LEN,
    encode_thumb,
)
from .cold import (
    compute_hash,
    make_thumb_if_missing,
    read_full,
)
from .find_candidates import find_candidates_by_path
from .library_resolver import Candidate, Triple, identify_candidates
from .id_gen import make_polaroid_id, parse_primary_char

__all__ = [
    "Polaroid",
    "Asset",
    "tag_prefix",
    "tag_value",
    "thumb_path_for",
    "INDEX_FILENAME",
    "read_index",
    "write_index",
    "list_polaroids",
    "THUMBS_DIRNAME",
    "LONG_EDGE",
    "QUALITY",
    "HASH_ALGO",
    "HASH_HEX_LEN",
    "SHORT_HASH_LEN",
    "encode_thumb",
    "compute_hash",
    "make_thumb_if_missing",
    "read_full",
    "find_candidates_by_path",
    "Candidate",
    "Triple",
    "identify_candidates",
    "make_polaroid_id",
    "parse_primary_char",
]
