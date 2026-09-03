import sys, os
from playwright.sync_api import sync_playwright
src, out = sys.argv[1], sys.argv[2]
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=['--no-sandbox'])
    pg = b.new_page()
    pg.goto('file://' + os.path.abspath(src), wait_until='load')
    pg.evaluate('document.fonts.ready')
    pg.wait_for_timeout(800)
    pg.pdf(path=out, format='Letter', print_background=True, prefer_css_page_size=True, display_header_footer=False)
    b.close()
print('pdf written', out, os.path.getsize(out))
