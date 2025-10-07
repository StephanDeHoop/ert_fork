#
# Configuration file for the Sphinx documentation builder.
#
# This file does only contain a selection of the most common options. For a
# full list see the documentation:
# http://www.sphinx-doc.org/en/master/config
import json

# -- Path setup --------------------------------------------------------------
# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
from importlib import metadata
from pathlib import Path

from everest.config import EverestConfig

sys.path.append(os.path.abspath("_ext"))

from generate_markdown_from_json import render_schema_markdown

# -- Project information -----------------------------------------------------

project = "Everest"
copyright = "2024, Equinor & TNO"  # noqa: A001
author = "Equinor & TNO"


try:
    dist_version = metadata.version("ert")
except metadata.PackageNotFoundError:
    dist_version = "0.0.0"

# The short X.Y version
version = ".".join(dist_version.split(".")[:2])
# The full version, including alpha/beta/rc tags
release = dist_version


def _write_everest_schema(app) -> None:
    out = Path(__file__).parent / "_static" / "everest.schema.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(EverestConfig.model_json_schema(), indent=2))


def _pointer_and_options_for_property(name: str, spec: dict) -> tuple[str, list[str]]:
    """
    Decide the best :pointer: and any extra options for the jsonschema directive.
    Returns (pointer_str, options_lines).
    """
    options: list[str] = []

    t = spec.get("type")
    # Sometimes Pydantic produces schema with 'items' even if 'type' is missing
    is_array = t == "array" or ("items" in spec and t is None)
    if is_array and "items" in spec:
        # Render the entry schema, not the array container
        pointer = f"/properties/{name}/items"
        return pointer, options

    # Map-like objects: arbitrary key -> value pairs
    # (object with 'additionalProperties' and no explicit 'properties')
    is_object = t == "object" or (
        "properties" in spec or "additionalProperties" in spec
    )
    has_additional = "additionalProperties" in spec
    has_properties = "properties" in spec
    is_map_like = is_object and has_additional and not has_properties
    if is_map_like:
        pointer = f"/properties/{name}"
        # Avoid deep traversal into arbitrary keys (often causes crashes/noise)
        options.append("   :collapse: additionalProperties")
        return pointer, options

    # Plain object or everything else: render as-is
    pointer = f"/properties/{name}"
    return pointer, options


def _write_keywords_md(app) -> None:
    src_dir = Path(__file__).parent
    schema_path = src_dir / "_static" / "everest.schema.json"
    keywords_md = src_dir / "keywords.md"

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    props: dict = schema.get("properties", {})

    lines: list[str] = []

    # Top label and title (MyST label syntax: (label)=)
    lines += ["(_cha_everest_keyword_reference)=\n"]
    lines += ["# Keyword reference\n\n"]
    lines += [
        "The keywords recognized by the Everest configuration system "
        "are described below. Each section is linkable; you can "
        "reference it from anywhere in the docs.\n\n"
    ]

    # lines += [
    #     "```{eval-rst}\n"
    #     ".. jsonschema:: _static/everest.schema.json\n"
    #     "  :lift_definitions:\n"
    #     "  :auto_target:\n"
    #     "```\n\n"
    # ]

    for name in sorted(props):
        # if not name == "controls":
        #     print(f"Processing keyword '{name}'")
        #     continue
        prop_spec: dict = props.get(name, {})
        desc = (prop_spec.get("description") or "").rstrip()

        # Stable per-keyword label + heading
        lines += [f"(keywords-{name})=\n", f"## {name}\n\n"]
        if desc:
            lines += [desc, "\n\n"]

        # Decide pointer/options for this keyword
        pointer, extra_opts = _pointer_and_options_for_property(name, prop_spec)

        # MyST fenced block that evaluates the rST directive
        print(f"DEBUG:     {pointer}  ----- {extra_opts}")
        lines += [
            "```{eval-rst}\n",
            ".. jsonschema:: _static/everest.schema.json#/",
            pointer.lstrip("/"),
            "\n",
            # "   :auto_reference:\n"
        ]
        lines += [opt + "\n" for opt in extra_opts]
        lines += ["```\n\n"]

    keywords_md.write_text("".join(lines), encoding="utf-8")


# def setup(app):
#     app.connect("builder-inited", _write_everest_schema)
#     # app.connect("builder-inited", _write_keywords_md)
#     return {"parallel_read_safe": True, "parallel_write_safe": True}


myst_enable_extensions = [
    "colon_fence",      # to support ::: directives
    "linkify",          # optional
    "substitution",     # optional
    "deflist",          # optional
    "attrs_inline",     # optional
]

# Optional: default role for bare `code` etc
myst_heading_anchors = 6  # ensure MyST generates anchors up to H6


def _generate_config_reference(app):
    """
    Import your Pydantic model, get its schema, render to MyST Markdown,
    and write docs/reference/keywords.md
    """
    schema = EverestConfig.model_json_schema()

    md = render_schema_markdown(
        schema,
        title=schema.get("title") or "Configuration Reference",
        root_id=schema.get("title") or "config",
        page_caption="Configuration keyword reference",
    )

    out_path = Path(__file__).parent / "keywords.md"
    out_path.write_text(md, encoding="utf-8")
    app.info(f"[schema] wrote {out_path}") if hasattr(app, "info") else None


def setup(app):
    app.connect("builder-inited", _generate_config_reference)
    return {"version": "1.0", "parallel_read_safe": True}


# -- General configuration ---------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx_copybutton",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinxcontrib.autodoc_pydantic",
    "sphinx.ext.ifconfig",
    "sphinx.ext.viewcode",
    "sphinxarg.ext",
    "everest_jobs",
    "myst_parser",
    "sphinx-jsonschema",
    "sphinx.ext.autosectionlabel",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
#
# source_suffix = ['.rst', '.md']
source_suffix = {".rst": "restructuredtext"}

# The master toctree document.
master_doc = "index"

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language = "en"

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"

autosectionlabel_prefix_document = True
autosectionlabel_maxdepth = 1
autosummary_generate = True  # if you use autosummary pages

jsonschema_options = {
    "lift_definitions": True,
    "auto_target": True,
    "auto_reference": True,
    "lift_description": True,
}

# Show just fields (nice summary + per-field sections)
autodoc_pydantic_model_show_field_summary = True

# Hide validators entirely (no section, no “Validated by:” lines)
autodoc_pydantic_model_show_validator_summary = False
autodoc_pydantic_model_show_validator_members = False
autodoc_pydantic_field_list_validators = False

# Hide config/JSON schema blocks unless you explicitly need them
autodoc_pydantic_model_show_config_summary = False
autodoc_pydantic_model_show_json = False
# autodoc_pydantic_model_members = False

# Hide the long constructor param list in the class header
autodoc_pydantic_model_hide_paramlist = True

# autodoc_default_options = {"members": False}  # or remove 'members' entirely

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "furo"
html_title = f"{project} {version} documentation"
html_logo = "./images/everest_icon.svg"

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.

html_theme_options = {
    "source_repository": "https://github.com/equinor/ert/",
    "source_branch": "main",
    "source_directory": "docs/everest",
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
# html_static_path = ['_static']

# Custom sidebar templates, must be a dictionary that maps document names
# to template names.
#
# The default sidebars (for documents that don't match any pattern) are
# defined by theme itself.  Builtin themes are using these templates by
# default: ``['localtoc.html', 'relations.html', 'sourcelink.html',
# 'searchbox.html']``.
#
# html_sidebars = {}


# -- Options for HTMLHelp output ---------------------------------------------

# Output file base name for HTML help builder.
htmlhelp_basename = "Everestdoc"


# -- Options for LaTeX output ------------------------------------------------

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    #
    # 'papersize': 'letterpaper',
    # The font size ('10pt', '11pt' or '12pt').
    #
    # 'pointsize': '10pt',
    # Additional stuff for the LaTeX preamble.
    #
    # 'preamble': '',
    # Latex figure (float) alignment
    #
    # 'figure_align': 'htbp',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [
    (master_doc, "Everest.tex", "Everest Documentation", "Equinor \\& TNO", "manual"),
]


# -- Options for manual page output ------------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [(master_doc, "everest", "Everest Documentation", [author], 1)]


# -- Options for Texinfo output ----------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (
        master_doc,
        "Everest",
        "Everest Documentation",
        author,
        "Everest",
        "One line description of project.",
        "Miscellaneous",
    ),
]


# -- Options for Epub output -------------------------------------------------

# Bibliographic Dublin Core info.
epub_title = project

# The unique identifier of the text. This can be a ISBN number
# or the project homepage.
#
# epub_identifier = ''

# A unique identification for the text.
#
# epub_uid = ''

# A list of files that should not be packed into the epub file.
epub_exclude_files = ["search.html"]


# -- Extension configuration -------------------------------------------------

# -- Options for intersphinx extension ---------------------------------------

# Allow to refer to a figure using its number
numfig = True

# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}
