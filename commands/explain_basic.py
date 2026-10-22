"""
commands/explain_basic.py
=========================
Deterministic fallback explainer for OmniStore Command Center.
Generates 2 to 4 concise, factual sentences directly from real tool result data.

SAFETY & WORDING RULES:
-----------------------
1. 2 to 4 short sentences.
2. Use ONLY *_human sizes, never raw byte counts.
3. Refer to folders and files by name, never mention group IDs.
4. Always say 'up to' for reclaimable or potential space.
5. NEVER say 'junk' and NEVER say 'safe to delete'.
6. Do NOT invent numbers or filenames.
7. End with exactly one suggested next step.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator


def explain_basic(tool_name: str, result: Dict[str, Any]) -> Iterator[str]:
    """
    Generate deterministic explanation sentences from real tool result data.
    Yields sentence chunks.
    """
    if not result:
        yield "No matching items were found. "
        yield "Try scanning a folder in Analyzer or asking another storage question."
        return

    sentences: list[str] = []

    if tool_name == "get_scan_overview":
        total_files = result.get("total_files", 0)
        total_size = result.get("total_size_human") or result.get("total_bytes_human") or "0 B"
        sentences.append(f"Your scan contains {total_files} files totaling {total_size}.")

        cats = result.get("categories") or result.get("top_categories") or []
        if cats:
            top_cat = cats[0]
            cat_name = top_cat.get("category", "Unknown")
            cat_sz = top_cat.get("size_human") or top_cat.get("total_bytes_human") or ""
            sentences.append(f"The largest category is {cat_name} using {cat_sz}.")

        flds = result.get("top_folders", [])
        if flds:
            top_fld = flds[0]
            fld_name = top_fld.get("name") or "the root folder"
            fld_sz = top_fld.get("size_human") or ""
            sentences.append(f"Top storage consumer is {fld_name} with {fld_sz}.")

        sentences.append("Explore individual folders in the Analyzer tab for more details.")

    elif tool_name in ("find_largest_files", "filter_files"):
        files = result.get("files") or result.get("items") or []
        count = result.get("count", len(files))
        total_sz = result.get("total_size_human") or result.get("total_bytes_human") or "0 B"

        if not files:
            sentences.append("No matching files were found for this criteria.")
            sentences.append("Try broadening your search or adjusting the size filter in the Analyzer tab.")
        else:
            sentences.append(f"Found {count} matching files totaling {total_sz}.")
            top_file = files[0]
            top_name = top_file.get("name", "Unknown file")
            top_sz = top_file.get("size_human") or top_file.get("size_bytes_human") or ""
            sentences.append(f"The largest file is {top_name} taking {top_sz}.")
            sentences.append("Review these candidates in the Cleanup tab to inspect items you no longer need.")

    elif tool_name == "get_largest_folders":
        folders = result.get("folders", [])
        count = result.get("count", len(folders))
        if not folders:
            sentences.append("No folders found in the current scan.")
            sentences.append("Please select and scan a directory in the Analyzer tab first.")
        else:
            sentences.append(f"Identified {count} folders consuming the most storage space.")
            top_f = folders[0]
            top_name = top_f.get("name", "top folder")
            top_sz = top_f.get("size_human") or top_f.get("total_bytes_human") or ""
            sentences.append(f"The heaviest folder is {top_name} using {top_sz}.")
            sentences.append("Open the Analyzer tab to drill down into subfolders and specific files.")

    elif tool_name == "get_category_breakdown":
        cats = result.get("categories", [])
        total_sz = result.get("total_size_human") or result.get("total_bytes_human") or "0 B"
        if not cats:
            sentences.append("No category breakdown is available for this scan.")
            sentences.append("Scan a folder in Analyzer to view storage distribution by file type.")
        else:
            sentences.append(f"Storage usage spans {len(cats)} categories totaling {total_sz}.")
            top_cat = cats[0]
            c_name = top_cat.get("category", "")
            c_sz = top_cat.get("size_human") or top_cat.get("total_bytes_human") or ""
            sentences.append(f"{c_name} occupies the largest share with {c_sz}.")
            sentences.append("Filter by this category in the Analyzer tab to find individual large files.")

    elif tool_name == "get_duplicate_summary":
        groups = result.get("total_groups", 0)
        rec_sz = result.get("reclaimable_human") or result.get("total_reclaimable_bytes_human") or "0 B"
        dup_files = result.get("total_duplicate_files", 0)

        if groups == 0:
            sentences.append("No duplicate files were detected in the current scan.")
            sentences.append("Run a broader scan or check the Duplicates tab for detailed options.")
        else:
            sentences.append(f"Found {groups} duplicate groups ({dup_files} files) with up to {rec_sz} of reclaimable space.")
            top_groups = result.get("top_groups", [])
            if top_groups:
                g0 = top_groups[0]
                g_sz = g0.get("reclaimable_human") or g0.get("size_human") or ""
                sentences.append(f"The largest group offers up to {g_sz} in extra copies.")
            sentences.append("Click Review in Cleanup below to select redundant copies to recycle.")

    elif tool_name == "suggest_free_space":
        target_h = result.get("target_human", "target")
        total_up_to = result.get("total_up_to_human") or result.get("cumulative_human") or "0 B"
        suggestions = result.get("suggestions", [])
        reachable = result.get("reachable", False)

        status_str = "reaches" if reachable else "partially covers"
        sentences.append(f"Identified candidates offering up to {total_up_to} which {status_str} your target of {target_h}.")

        details = []
        for s in suggestions:
            label = s.get("label", "")
            sz = s.get("size_human", "")
            if label and sz:
                details.append(f"{label} (up to {sz})")
        if details:
            sentences.append(f"Review candidates include {', '.join(details)}.")
        else:
            sentences.append("Review candidates combine extra duplicate copies and older unaccessed files.")

        sentences.append("Click Review in Cleanup to inspect each candidate before deciding.")

    else:
        sentences.append("The command completed successfully with real scan data.")
        sentences.append("Review the results above to see details.")
        sentences.append("You can navigate to the Analyzer or Duplicates tab for further exploration.")

    # Yield sentences
    for i, s in enumerate(sentences):
        suffix = " " if i < len(sentences) - 1 else ""
        yield s + suffix
