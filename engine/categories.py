"""
engine/categories.py
====================
File extension categorization for OmniStore.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

CATEGORIES: list[str] = [
    "Videos",
    "Images",
    "Audio",
    "Documents",
    "Archives",
    "Code",
    "Installers",
    "Other",
]

_EXTENSION_MAP: dict[str, str] = {
    # Videos
    "mp4": "Videos",
    "mkv": "Videos",
    "avi": "Videos",
    "mov": "Videos",
    "wmv": "Videos",
    "flv": "Videos",
    "webm": "Videos",
    "m4v": "Videos",
    "ts": "Videos",
    "mpg": "Videos",
    "mpeg": "Videos",
    "3gp": "Videos",
    "m2ts": "Videos",
    "vob": "Videos",

    # Images
    "jpg": "Images",
    "jpeg": "Images",
    "png": "Images",
    "gif": "Images",
    "webp": "Images",
    "heic": "Images",
    "heif": "Images",
    "bmp": "Images",
    "svg": "Images",
    "ico": "Images",
    "tiff": "Images",
    "tif": "Images",
    "psd": "Images",
    "raw": "Images",
    "cr2": "Images",
    "nef": "Images",
    "avif": "Images",

    # Audio
    "mp3": "Audio",
    "wav": "Audio",
    "flac": "Audio",
    "aac": "Audio",
    "ogg": "Audio",
    "m4a": "Audio",
    "wma": "Audio",
    "opus": "Audio",
    "aiff": "Audio",
    "mid": "Audio",
    "midi": "Audio",
    "alac": "Audio",

    # Documents
    "pdf": "Documents",
    "docx": "Documents",
    "doc": "Documents",
    "xlsx": "Documents",
    "xls": "Documents",
    "pptx": "Documents",
    "ppt": "Documents",
    "txt": "Documents",
    "rtf": "Documents",
    "csv": "Documents",
    "tsv": "Documents",
    "md": "Documents",
    "odt": "Documents",
    "ods": "Documents",
    "odp": "Documents",
    "epub": "Documents",
    "rst": "Documents",
    "log": "Documents",

    # Archives
    "zip": "Archives",
    "rar": "Archives",
    "7z": "Archives",
    "tar": "Archives",
    "gz": "Archives",
    "bz2": "Archives",
    "xz": "Archives",
    "tgz": "Archives",
    "7zip": "Archives",
    "cab": "Archives",

    # Code
    "py": "Code",
    "js": "Code",
    "jsx": "Code",
    "ts": "Code",
    "tsx": "Code",
    "html": "Code",
    "htm": "Code",
    "css": "Code",
    "scss": "Code",
    "c": "Code",
    "cpp": "Code",
    "h": "Code",
    "hpp": "Code",
    "cs": "Code",
    "java": "Code",
    "go": "Code",
    "rs": "Code",
    "rb": "Code",
    "php": "Code",
    "sh": "Code",
    "bat": "Code",
    "ps1": "Code",
    "json": "Code",
    "xml": "Code",
    "yml": "Code",
    "yaml": "Code",
    "toml": "Code",
    "sql": "Code",
    "kt": "Code",
    "swift": "Code",
    "vue": "Code",

    # Installers
    "exe": "Installers",
    "msi": "Installers",
    "iso": "Installers",
    "dmg": "Installers",
    "pkg": "Installers",
    "deb": "Installers",
    "rpm": "Installers",
    "appx": "Installers",
    "msix": "Installers",
}


def category_for(extension: str) -> str:
    """
    Return the high-level category for a given file extension.
    Accepts extensions with or without a leading dot, case-insensitive.
    """
    if not extension:
        return "Other"
    clean_ext = extension.lstrip(".").strip().lower()
    return _EXTENSION_MAP.get(clean_ext, "Other")
