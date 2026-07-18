"""
Tree view component — renders tree.json flat section list as collapsible hierarchy.

Adapted from 0.1v_pdf_tree/streamlit_app/components/tree_view.py.
Uses tree.json section dicts instead of CanonicalDocumentGraph.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

_LEVEL_COLORS = {
    1: "#4CAF50",
    2: "#2196F3",
    3: "#FF9800",
    4: "#9C27B0",
    5: "#F44336",
    6: "#78909C",
}
_LEVEL_DOT = {1: "⬤", 2: "◉", 3: "◈", 4: "◆", 5: "▸", 6: "·"}
_SRC_ICON = {
    "toc": "📎",
    "inferred": "📄",
    "implicit": "🔍",
}
_LABEL_ICON = {
    "paragraph": "¶",
    "heading": "#",
    "table": "⊞",
    "figure": "⊡",
}
_INDENT = "    "


def render_tree(
    sections: list[dict[str, Any]],
    max_nodes: int = 500,
    auto_expand_depth: int = 1,
    show_content: bool = True,
    max_content_items: int = 8,
    images: list[Any] | None = None,
    show_images: bool = False,
    pdf_path: Path | None = None,
    page_render_dir: Path | None = None,
) -> None:
    """
    Render collapsible hierarchy from tree.json sections list.

    pdf_path/page_render_dir: when both are given, each section gets a lazy
    "render PDF page" check — rasterizes the section's actual page(s) via
    fitz_toc.render_pages so a human can compare it against the extracted
    text/tables, independent of the pipeline's own verification checks.
    """
    if not sections:
        st.warning("Empty tree — no sections to display.")
        return

    # Build lookup maps
    by_id = {s["section_id"]: s for s in sections}
    roots = [s for s in sections if s.get("parent_section_id") is None]

    # Build image index: section_id → [EmbeddedImage]
    img_index: dict[str, list[Any]] = {}
    if show_images and images:
        for img in images:
            sid = getattr(img, "section_id", None)
            if sid:
                img_index.setdefault(sid, []).append(img)

    shown = [0]
    for root in roots:
        if shown[0] >= max_nodes:
            st.caption(f"⚠ Truncated at {max_nodes} nodes")
            break
        _render_section(
            root, by_id,
            depth=0,
            auto_expand_depth=auto_expand_depth,
            max_nodes=max_nodes,
            shown=shown,
            show_content=show_content,
            max_content_items=max_content_items,
            img_index=img_index,
            pdf_path=pdf_path,
            page_render_dir=page_render_dir,
        )


def _render_section(
    section: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    depth: int,
    auto_expand_depth: int,
    max_nodes: int,
    shown: list[int],
    show_content: bool,
    max_content_items: int,
    img_index: dict[str, list[Any]],
    pdf_path: Path | None = None,
    page_render_dir: Path | None = None,
) -> None:
    if shown[0] >= max_nodes:
        return

    shown[0] += 1
    lvl = section.get("hierarchy_level", 1)
    color = _LEVEL_COLORS.get(lvl, "#78909C")
    dot = _LEVEL_DOT.get(lvl, "·")
    title = str(section.get("title", "Untitled"))[:65]
    src = section.get("structural_source", "toc")
    src_icon = _SRC_ICON.get(src, "·")
    page_start = section.get("page_start")
    page_end = section.get("page_end")
    child_ids: list[str] = section.get("child_sections", [])
    node_count = section.get("node_count", 0)
    section_id = section.get("section_id", "")
    confidence = section.get("confidence", 1.0)

    # Expander label (plain text — Streamlit renders HTML raw in expander titles)
    indent = _INDENT * depth
    page_str = f"  p{page_start}–{page_end}" if page_start is not None else ""
    child_str = f"  ↓{len(child_ids)}" if child_ids else ""
    label = f"{indent}{dot} L{lvl}  {title}{page_str}{child_str}"

    expanded = depth <= auto_expand_depth
    with st.expander(label, expanded=expanded):
        # Colored level-bar header
        st.markdown(
            f"<div style='"
            f"border-left:4px solid {color};"
            f"padding:5px 12px;"
            f"background:{color}18;"
            f"border-radius:0 6px 6px 0;"
            f"margin-bottom:8px'>"
            f"<span style='color:{color};font-weight:700;font-size:1.05em'>L{lvl}</span>"
            f"&nbsp;&nbsp;"
            f"<span style='font-weight:600'>{title}</span>"
            f"&nbsp;"
            f"<span style='font-size:0.78em;color:#888'>{src_icon} {src}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Metadata row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Pages", f"{page_start}–{page_end}" if page_start is not None else "—")
        m2.metric("Confidence", f"{confidence:.2f}")
        m3.metric("Content nodes", node_count)
        m4.metric("Children", len(child_ids))

        # Content preview
        if show_content:
            nodes: list[dict[str, Any]] = section.get("semantic_nodes", [])
            body = [
                n for n in nodes
                if n.get("node_type") in ("paragraph", "table", "heading")
                and n.get("canonical_text")
            ][:max_content_items]

            if body:
                n_tables = sum(1 for n in body if n.get("node_type") == "table")
                n_text = sum(1 for n in body if n.get("node_type") in ("paragraph", "heading"))
                _type_parts = []
                if n_text:
                    _type_parts.append(f"{n_text} text")
                if n_tables:
                    _type_parts.append(f"{n_tables} table{'s' if n_tables > 1 else ''}")
                with st.expander(f"📄 Content ({', '.join(_type_parts)})", expanded=True):
                    for item in body:
                        ntype = item.get("node_type", "paragraph")
                        icon = _LABEL_ICON.get(ntype, "¶")
                        pg = item.get("page_no", "?")
                        raw_text = str(item.get("canonical_text", ""))

                        if ntype == "table":
                            lines = raw_text.split("\n")
                            header_tag = lines[0] if lines else "[TABLE]"
                            row_lines = [line.strip() for line in lines[1:] if line.strip()]
                            st.markdown(
                                f"<div style='background:#e8f4fd;border-left:3px solid #2196F3;"
                                f"padding:5px 10px;margin:4px 0;border-radius:0 4px 4px 0;"
                                f"font-size:0.83em'>"
                                f"<span style='color:#1565C0;font-weight:600;"
                                f"font-family:monospace'>"
                                f"⊞ {header_tag}</span>"
                                f"<span style='color:#6c757d;margin-left:8px'>p{pg}</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                            if row_lines:
                                rows = [[c.strip() for c in row.split("|")] for row in row_lines]
                                max_cols = max((len(r) for r in rows), default=0)
                                rows = [r + [""] * (max_cols - len(r)) for r in rows]
                                try:
                                    import pandas as pd
                                    if len(rows) >= 2:
                                        seen: dict[str, int] = {}
                                        cols_: list[str] = []
                                        for h in rows[0]:
                                            k = h if h else "—"
                                            if k in seen:
                                                seen[k] += 1
                                                cols_.append(f"{k}.{seen[k]}")
                                            else:
                                                seen[k] = 0
                                                cols_.append(k)
                                        df = pd.DataFrame(rows[1:], columns=cols_)
                                    else:
                                        df = pd.DataFrame(rows)
                                    st.dataframe(df, hide_index=True)
                                except Exception:
                                    st.code("\n".join(row_lines[:8]), language=None)
                        else:
                            text = raw_text[:400]
                            st.markdown(
                                f"<div style='background:#f8f9fa;border-left:3px solid #dee2e6;"
                                f"padding:5px 10px;margin:3px 0;border-radius:0 4px 4px 0;"
                                f"font-size:0.85em;color:#212529'>"
                                f"<span style='color:#6c757d;margin-right:6px'>"
                                f"{icon} p{pg}</span>{text}"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

        # Verify against the actual PDF page — lazy render, only on request,
        # so opening the tree never rasterizes hundreds of pages at once.
        if pdf_path is not None and page_render_dir is not None and page_start is not None:
            _verify_key = f"verify_pdf_page_{section_id}"
            _want_verify = st.checkbox("🔎 Verify against PDF page", key=_verify_key)
            if _want_verify:
                _pages_to_render = sorted({page_start, page_end}) if page_end else [page_start]
                try:
                    from src.tree_builder.fitz_toc import render_pages
                    _rendered = render_pages(pdf_path, _pages_to_render, page_render_dir)
                    _render_cols = st.columns(len(_pages_to_render))
                    for _i, _pg in enumerate(_pages_to_render):
                        _png_path = _rendered.get(_pg)
                        with _render_cols[_i]:
                            if _png_path:
                                st.image(str(_png_path), caption=f"p{_pg} (source PDF)")
                            else:
                                st.caption(f"p{_pg} out of range")
                except Exception as exc:
                    st.warning(f"Could not render PDF page: {exc}")

        # Images for this section
        _section_imgs = img_index.get(section_id, [])
        if _section_imgs:
            with st.expander(f"🖼 Images ({len(_section_imgs)})", expanded=False):
                _img_cols = st.columns(min(len(_section_imgs), 3))
                for _i, _img in enumerate(_section_imgs):
                    with _img_cols[_i % 3]:
                        st.image(_img.image_bytes, use_container_width=True)
                        st.caption(f"p{_img.page_no}")

        st.caption(f"`{section_id}` · path: `{section.get('hierarchy_path', '/')}` ")

        # Recurse into children
        for cid in child_ids:
            if shown[0] >= max_nodes:
                st.caption(f"⚠ {len(child_ids)} children — increase max nodes")
                break
            child = by_id.get(cid)
            if child:
                _render_section(
                    child, by_id,
                    depth + 1, auto_expand_depth, max_nodes, shown,
                    show_content, max_content_items, img_index,
                    pdf_path=pdf_path, page_render_dir=page_render_dir,
                )
