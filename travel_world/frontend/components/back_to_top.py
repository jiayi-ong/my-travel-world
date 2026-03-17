"""
Reusable back-to-top button rendered via an inline HTML component.

Streamlit renders each tab inside an iframe; window.parent gives access to
the host page so we can scroll the main content area to the top.
"""
import streamlit.components.v1 as components


def render_back_to_top() -> None:
    """Render a small 'Back to top' button at the current position in the page."""
    components.html(
        """
        <style>
          .btt-btn {
            background: #FF4B4B;
            color: #fff;
            border: none;
            padding: 6px 14px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            font-family: sans-serif;
          }
          .btt-btn:hover { background: #e03e3e; }
        </style>
        <button class="btt-btn"
          onclick="window.parent.document.querySelector('section.main').scrollTo({top:0,behavior:'smooth'})">
          ⬆ Back to top
        </button>
        """,
        height=40,
    )
