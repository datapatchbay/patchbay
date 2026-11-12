"""Sphinx configuration for the datapatchbay documentation (datapatchbay.dev)."""

project = "datapatchbay"
copyright = "datapatchbay contributors"
author = "datapatchbay contributors"

extensions = ["myst_parser"]
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

source_suffix = {".md": "markdown"}
root_doc = "index"
# docs/agents and docs/adr are repo notes, not site pages (and don't trigger a deploy).
exclude_patterns = ["_build", "agents", "adr", "README.md"]
# GLOSSARY.md starts at a heading level that suits its own file.
suppress_warnings = ["myst.header"]

html_theme = "furo"
html_title = "datapatchbay"
html_baseurl = "https://datapatchbay.dev/"
html_favicon = "../assets/icon/favicon.svg"
html_static_path = ["_static", "../assets/logo", "../assets/fonts"]
html_css_files = ["custom.css"]
html_copy_source = False
html_show_sphinx = False

INK = "#16181D"
PANEL = "#F3F0E8"

html_theme_options = {
    "light_logo": "datapatchbay-logo-light.svg",
    "dark_logo": "datapatchbay-logo-dark.svg",
    "sidebar_hide_name": True,
    "announcement": "Design agreed, nothing released yet. These pages describe milestone 1 as designed.",
    "source_repository": "https://github.com/datapatchbay/patchbay/",
    "source_branch": "main",
    "source_directory": "docs/",
    "light_css_variables": {
        "color-brand-primary": INK,
        "color-brand-content": "#C2381F",  # patch red, darkened to 5.4:1 on white
        "color-announcement-background": INK,
        "color-announcement-text": PANEL,
    },
    "dark_css_variables": {
        "color-brand-primary": PANEL,
        "color-brand-content": "#F06A50",  # patch red, lightened to 6:1 on Furo's dark ground
        "color-announcement-background": PANEL,
        "color-announcement-text": INK,
    },
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/datapatchbay/patchbay",
            "html": '<svg stroke="currentColor" fill="currentColor" stroke-width="0" viewBox="0 0 16 16"><path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"></path></svg>',
            "class": "",
        },
    ],
}
