"""
Floating back-to-top button injected into the Streamlit parent document.

Instead of rendering a button at a fixed page position, this injects a
floating button (position:fixed, bottom-right) into the parent DOM once.
The button appears after the user scrolls 200 px and disappears at the top.
Call render_back_to_top() once per tab render — the injection is idempotent
(guarded by document.getElementById check).
"""
import streamlit.components.v1 as components


def render_back_to_top() -> None:
    """Inject a sticky floating back-to-top button into the parent page."""
    components.html(
        """
        <script>
        (function() {
            var doc = window.parent.document;
            if (doc.getElementById('tworld-btt')) return; // already injected

            // Create floating button
            var btn = doc.createElement('button');
            btn.id = 'tworld-btt';
            btn.innerHTML = '&#8679;';
            btn.title = 'Back to top';
            btn.style.cssText = [
                'position:fixed',
                'bottom:28px',
                'right:28px',
                'z-index:99999',
                'width:44px',
                'height:44px',
                'border-radius:50%',
                'background:#FF4B4B',
                'color:#fff',
                'border:none',
                'font-size:22px',
                'cursor:pointer',
                'display:none',
                'box-shadow:0 3px 10px rgba(0,0,0,0.25)',
                'transition:opacity 0.2s',
                'line-height:1',
            ].join(';');

            btn.onclick = function() {
                // Try to scroll the Streamlit main container
                var selectors = [
                    '[data-testid="stMain"]',
                    'section.main',
                    '.main'
                ];
                var scrolled = false;
                for (var i = 0; i < selectors.length; i++) {
                    var el = doc.querySelector(selectors[i]);
                    if (el) { el.scrollTo({top:0, behavior:'smooth'}); scrolled=true; break; }
                }
                window.parent.scrollTo({top:0, behavior:'smooth'});
            };

            doc.body.appendChild(btn);

            // Show/hide on scroll — listen on both window and main container
            function onScroll() {
                var y = window.parent.pageYOffset || 0;
                // Also check main container scroll
                var selectors = ['[data-testid="stMain"]', 'section.main', '.main'];
                for (var i = 0; i < selectors.length; i++) {
                    var el = doc.querySelector(selectors[i]);
                    if (el) { y = Math.max(y, el.scrollTop); break; }
                }
                btn.style.display = y > 200 ? 'block' : 'none';
            }

            window.parent.addEventListener('scroll', onScroll, true);
            // Also poll occasionally since Streamlit re-renders can detach listeners
            setInterval(onScroll, 1000);
        })();
        </script>
        """,
        height=0,
    )
