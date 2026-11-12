"""Sphinx configuration for the datapatchbay documentation (datapatchbay.dev)."""

from pathlib import Path

project = "datapatchbay"
copyright = "datapatchbay contributors"
author = "datapatchbay contributors"

extensions = [
    "myst_parser",
    "notfound.extension",
    "sphinx_copybutton",
    "sphinx_sitemap",
    "sphinxext.opengraph",
]
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
html_static_path = ["_static", "../assets/logo", "../assets/fonts", "../assets/social"]
html_css_files = ["custom.css"]
html_copy_source = False
html_show_sphinx = False

# The copy button leaves out the prompt of a console block, and the output lines with it.
copybutton_prompt_text = "$ "
copybutton_only_copy_prompt_lines = True

# GitHub Pages serves 404.html for every missing URL, at any depth, so its links start at the root.
notfound_urls_prefix = "/"
notfound_context = {
    "title": "Page not found",
    "body": "<h1>Page not found</h1>"
    '<p>This page does not exist, or it has moved. Start again from the <a href="/">home page</a>, '
    "or use the search box.</p>",
}

# The link preview that chat and social apps show.
ogp_site_url = html_baseurl
ogp_site_name = "datapatchbay"
ogp_image = html_baseurl + "_static/social-preview.png"
ogp_image_alt = "datapatchbay: data products as code"
ogp_social_cards = {"enable": False}

# sitemap.xml: the site has one language and one version.
sitemap_url_scheme = "{link}"
sitemap_excludes = ["404.html", "genindex.html", "search.html"]

# llms.txt: the pages of the site as one list, for agents. Written from the sidebar, so it cannot fall behind.
LLMS_SUMMARY = (
    "datapatchbay (`dpb`) is a file-based CLI for data products as code. A data product is a folder of YAML files "
    "that state its owner, its input and output ports, its tables, its freshness and its readers. `dpb` scaffolds "
    "and validates those files, and generates the orchestrator files (Airflow 3, Dagster or a local script) and "
    "the warehouse SQL (Postgres or DuckDB) from them."
)


def write_llms_txt(app, exception):
    """Write `llms.txt` at the root of the site: one section per sidebar caption, one link per page."""
    if exception is not None or app.builder.name != "html":
        return
    from sphinx import addnodes

    lines = [f"# {project}", "", f"> {LLMS_SUMMARY}"]
    for toctree in app.env.get_doctree(root_doc).findall(addnodes.toctree):
        lines += ["", f"## {toctree['caption']}", ""]
        for title, target in toctree["entries"]:
            if target in app.env.titles:
                title = title or app.env.titles[target].astext()
                target = f"{html_baseurl}{target}.html"
            lines.append(f"- [{title}]({target})")
    (Path(app.outdir) / "llms.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def drop_avoid_lines(app, relative_path, parent_docname, content):
    """Leave the `_Avoid_:` lines of `GLOSSARY.md` out of the site: they guide contributors, not readers."""
    if relative_path.name == "GLOSSARY.md":
        content[0] = "".join(line for line in content[0].splitlines(keepends=True) if not line.startswith("_Avoid_"))


def setup(app):
    app.connect("include-read", drop_avoid_lines)
    app.connect("build-finished", write_llms_txt)


INK = "#16181D"
PANEL = "#F3F0E8"

html_theme_options = {
    "light_logo": "datapatchbay-logo-light.svg",
    "dark_logo": "datapatchbay-logo-dark.svg",
    "sidebar_hide_name": True,
    "announcement": "Not released yet: install from GitHub. The plugin interface may still change.",
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
