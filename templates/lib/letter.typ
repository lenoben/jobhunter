// Cover letter. German: DIN 5008 Form B positions (address field 45 mm from the top, subject at
// ~98.5 mm, left margin 25 mm, fold/punch marks). English uses the same clean layout.
// Exactly one page; no signature image (only the typed name).
#import "common.typ": *

#let labels = (
  de: (attachments: "Anlagen", closing: "Mit freundlichen Grüßen", letter: "Anschreiben"),
  en: (attachments: "Enclosures", closing: "Kind regards", letter: "Cover letter"),
)

#let letter(lang) = {
  let L = labels.at(lang)
  let d = data
  let sender = get(d, "sender", default: (:))
  let sender-name = get(sender, "name", default: "")

  // DIN 5008 Form B (mm from the top-left corner of the page)
  let margin-left = 25mm
  let address-top = 45mm       // Zusatz-/Vermerkzone 45–62.7, Anschriftzone 62.7–90
  let subject-top = 98.46mm

  set document(title: sender-name + " – " + L.letter, author: sender-name)
  set text(font: fonts, size: 11pt, lang: lang, fill: rgb("#1d232a"))
  set par(leading: 0.6em, spacing: 1.15em, justify: false)
  set page(
    paper: "a4",
    margin: (left: margin-left, right: 20mm, top: subject-top, bottom: 18mm),
    background: {
      // Fold marks (105 / 210 mm) and punch mark (148.5 mm) at the left edge
      for y in (105mm, 210mm) { place(top + left, dx: 4mm, dy: y, line(length: 4mm, stroke: 0.4pt + rule-color)) }
      place(top + left, dx: 4mm, dy: 148.5mm, line(length: 6mm, stroke: 0.4pt + rule-color))

      // Letterhead: sender block, top right
      place(top + right, dx: -20mm, dy: 15mm, align(right, block[
        #text(16pt, weight: "bold", fill: accent, sender-name) \
        #set text(9pt, fill: muted)
        #(get(sender, "street"), get(sender, "city")).filter(nonempty).join(" · ") \
        #(get(sender, "phone"), get(sender, "email")).filter(nonempty).join(" · ")
        #for l in get(sender, "links", default: ()) [ \ #l]
      ]))

      // Return address line at the bottom of the Zusatz- und Vermerkzone
      place(top + left, dx: margin-left, dy: address-top + 12.5mm, text(7.5pt, fill: muted,
        (sender-name, get(sender, "street"), get(sender, "city")).filter(nonempty).join(" · ")))

      // Recipient (Anschriftzone, 85 mm wide)
      place(top + left, dx: margin-left, dy: address-top + 17.7mm, block(width: 80mm,
        get(get(d, "recipient", default: (:)), "lines", default: ()).join(linebreak())))

      // Date (and place), top right of the information block area
      place(top + right, dx: -20mm, dy: address-top + 40mm,
        text((get(d, "place"), get(d, "date")).filter(nonempty).join(", ")))
    },
  )

  text(weight: "bold", get(d, "subject", default: ""))
  if nonempty(get(d, "reference")) {
    linebreak()
    text(9.5pt, fill: muted, get(d, "reference"))
  }
  v(1.2em)
  par(get(d, "salutation", default: ""))
  for p in get(d, "body", default: ()) { par(p) }
  v(0.2em)
  par(get(d, "closing", default: L.closing))
  v(2.2em)  // room for a handwritten signature; none is invented
  par(sender-name)

  let attachments = get(d, "attachments", default: ())
  if attachments.len() > 0 {
    v(0.8em)
    text(9.5pt)[#text(weight: "bold", L.attachments) \ #attachments.join(linebreak())]
  }

  page-count-marker()
}
