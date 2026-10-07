"""Inline SVG icons for the website.

Tabler outline icons (MIT), the same set the dashboard uses through
DashIconify, so a thermometer looks the same on every CompostIQ page. They are
inlined rather than loaded, which keeps every page a single request and lets
the icon take its colour from the surrounding text.
"""
from markupsafe import Markup

_PATHS = {
    "leaf": '<path d="M5 21c.5-4.5 2.5-8 7-10"/><path d="M9 18c6.218 0 10.5-3.288 11-12v-2h-4.014c-9 0-11.986 4-12 9c0 1 0 3 2 5h3z"/>',
    "arrow-right": '<path d="M5 12h14"/><path d="M13 18l6-6"/><path d="M13 6l6 6"/>',
    "temperature": '<path d="M10 13.5a4 4 0 1 0 4 0v-8.5a2 2 0 0 0-4 0v8.5"/><path d="M10 9l4 0"/>',
    "droplet": '<path d="M7.502 19.423c2.602 2.105 6.395 2.105 8.996 0c2.602-2.105 3.262-5.708 1.566-8.546l-4.89-7.26c-.42-.625-1.287-.803-1.936-.397a1.376 1.376 0 0 0-.41.397l-4.893 7.26c-1.695 2.838-1.035 6.441 1.567 8.546z"/>',
    "wind": '<path d="M5 8h8.5a2.5 2.5 0 1 0-2.34-3.24"/><path d="M3 12h15.5a2.5 2.5 0 1 1-2.34 3.24"/><path d="M4 16h5.5a2.5 2.5 0 1 1-2.34 3.24"/>',
    "co2": '<path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0-18 0"/><path d="M9 10a2 2 0 1 0 0 4"/><path d="M13 12a2 2 0 1 0 4 0a2 2 0 1 0-4 0"/>',
    "ammonia": '<path d="M12 3c-1.5 3-5 5.5-5 9.5a5 5 0 0 0 10 0c0-4-3.5-6.5-5-9.5z"/><path d="M10 14h4"/>',
    "alert": '<path d="M12 9v4"/><path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636-2.87l-8.106-13.536a1.914 1.914 0 0 0-3.274 0z"/><path d="M12 16h.01"/>',
    "device": '<path d="M5 6a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1h-12a1 1 0 0 1-1-1z"/><path d="M9 9h6v6h-6z"/><path d="M3 10h2"/><path d="M3 14h2"/><path d="M10 3v2"/><path d="M14 3v2"/><path d="M21 10h-2"/><path d="M21 14h-2"/><path d="M14 21v-2"/><path d="M10 21v-2"/>',
    "link": '<path d="M9 15l6-6"/><path d="M11 6l.463-.536a5 5 0 0 1 7.071 7.072l-.534.464"/><path d="M13 18l-.397.534a5.068 5.068 0 0 1-7.127 0a4.972 4.972 0 0 1 0-7.071l.524-.463"/>',
    "chart": '<path d="M4 19l16 0"/><path d="M4 15l4-6l4 2l4-5l4 4"/>',
    "download": '<path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/><path d="M7 11l5 5l5-5"/><path d="M12 4l0 12"/>',
    "info": '<path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0-18 0"/><path d="M12 9h.01"/><path d="M11 12h1v4h1"/>',
}


def icon(name, cls="icon"):
    """An icon as inline SVG. Decorative, so hidden from screen readers."""
    return Markup(
        f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{_PATHS[name]}</svg>'
    )
