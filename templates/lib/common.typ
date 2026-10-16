// Shared look for CV and letters. Content comes only from JSON (sys.inputs.data); strings are
// inserted as plain text, never evaluated as markup.

#let accent = rgb("#1f3a5f")
#let muted = rgb("#5b6470")
#let rule-color = rgb("#c9d1db")
#let fonts = ("Calibri", "Carlito", "Arial", "Liberation Sans", "Libertinus Serif")

#let data = json(bytes(sys.inputs.data))

#let get(d, key, default: none) = if type(d) == dictionary and key in d and d.at(key) != none { d.at(key) } else { default }

#let nonempty(x) = x != none and x != "" and x != ()

// Machine-readable page count for core/docs.py (typst.query "<jh-pagecount>").
#let page-count-marker() = context [#metadata(counter(page).final().first()) <jh-pagecount>]
