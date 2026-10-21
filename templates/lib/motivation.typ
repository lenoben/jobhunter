// Motivationsschreiben / motivation letter (user request 2026-10-22): written only on request.
// Same letterhead as the cover letter, but no address window: a title, a line naming the role,
// 1–2 pages of prose, place and date, the typed name (no signature image).
#import "common.typ": *

#let labels = (
  de: (title: "Motivationsschreiben", closing: "Mit freundlichen Grüßen"),
  en: (title: "Motivation letter", closing: "Kind regards"),
)

#let motivation(lang) = {
  let L = labels.at(lang)
  let d = data
  let sender = get(d, "sender", default: (:))
  let sender-name = get(sender, "name", default: "")

  set document(title: sender-name + " – " + L.title, author: sender-name)
  set text(font: fonts, size: 11pt, lang: lang, fill: rgb("#1d232a"))
  set par(leading: 0.62em, spacing: 1.15em, justify: true)
  set page(paper: "a4", margin: (left: 25mm, right: 20mm, top: 22mm, bottom: 20mm))

  // Letterhead: name left, contact right
  grid(columns: (1fr, auto), align: (left + bottom, right + bottom),
    text(16pt, weight: "bold", fill: accent, sender-name),
    {
      set text(9pt, fill: muted)
      (get(sender, "street"), get(sender, "city")).filter(nonempty).join(" · ")
      linebreak()
      (get(sender, "phone"), get(sender, "email")).filter(nonempty).join(" · ")
      for l in get(sender, "links", default: ()) [ \ #l]
    })
  v(0.3em)
  line(length: 100%, stroke: 0.6pt + rule-color)
  v(1.4em)

  text(18pt, weight: "bold", fill: accent, get(d, "title", default: L.title))
  if nonempty(get(d, "subtitle")) {
    linebreak()
    text(11.5pt, fill: muted, get(d, "subtitle"))
  }
  v(1.2em)
  if nonempty(get(d, "salutation")) { par(get(d, "salutation")) }
  for p in get(d, "body", default: ()) { par(p) }
  v(0.4em)
  par(justify: false, (get(d, "place"), get(d, "date")).filter(nonempty).join(", "))
  par(justify: false, get(d, "closing", default: L.closing))
  v(2em)  // room for a handwritten signature; none is invented
  par(sender-name)

  page-count-marker()
}
