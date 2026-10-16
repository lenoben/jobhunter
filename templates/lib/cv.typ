// CV layout (Lebenslauf / résumé): tabular, reverse-chronological, dates MM/YYYY, max 2 pages.
#import "common.typ": *

#let labels = (
  de: (
    profile: "Kurzprofil", experience: "Berufserfahrung", education: "Ausbildung",
    projects: "Projekte", skills: "Kenntnisse", languages: "Sprachen",
    certificates: "Zertifikate", personal: "Persönliche Daten", tech: "Technologien",
    present: "heute", page: "Seite", of: "von", cv: "Lebenslauf",
  ),
  en: (
    profile: "Profile", experience: "Experience", education: "Education",
    projects: "Projects", skills: "Skills", languages: "Languages",
    certificates: "Certificates", personal: "Personal details", tech: "Tech",
    present: "present", page: "Page", of: "of", cv: "CV",
  ),
)

#let cv(lang) = {
  let L = labels.at(lang)
  let d = data

  set document(title: get(d, "name", default: "") + " – " + L.cv, author: get(d, "name", default: ""))
  set page(
    paper: "a4",
    margin: (left: 20mm, right: 20mm, top: 18mm, bottom: 18mm),
    footer: context {
      let total = counter(page).final().first()
      if total > 1 {
        set text(8pt, fill: muted)
        get(d, "name", default: "") + " · " + L.cv
        h(1fr)
        L.page + " " + str(counter(page).get().first()) + " " + L.of + " " + str(total)
      }
    },
  )
  set text(font: fonts, size: 10pt, lang: lang, fill: rgb("#1d232a"))
  set par(leading: 0.55em, spacing: 0.7em, justify: false)
  set list(marker: text(fill: accent)[•], indent: 0.2em, body-indent: 0.5em, spacing: 0.45em)

  let fmt-date(s) = if s == none { "" } else if lower(s) in ("present", "heute") { L.present } else { s }
  let period(e) = {
    let from = fmt-date(get(e, "from"))
    let to = fmt-date(get(e, "to"))
    if from == "" { to } else if to == "" or to == from { from } else { from + " – " + to }
  }

  let section(title) = {
    v(0.9em, weak: true)
    block(below: 0.55em, sticky: true)[
      #text(11pt, weight: "bold", fill: accent, tracking: 0.04em, upper(title))
      #v(-0.65em)
      #line(length: 100%, stroke: 0.6pt + rule-color)
    ]
  }

  let row(left, right) = block(breakable: false, below: 0.75em, grid(
    columns: (27mm, 1fr),
    column-gutter: 4mm,
    text(9pt, fill: muted, left),
    right,
  ))

  let entry(e, title-key, org-key, items-key) = {
    let org = (get(e, org-key), get(e, "place")).filter(nonempty).join(", ")
    row(period(e))[
      #text(weight: "bold", get(e, title-key, default: ""))
      #if nonempty(org) [ \ #text(style: "italic", fill: muted, org)]
      #let items = get(e, items-key, default: ())
      #if items.len() > 0 { v(0.15em); list(..items) }
      #let tech = get(e, "tech", default: ())
      #if tech.len() > 0 { text(8.5pt, fill: muted, L.tech + ": " + tech.join(", ")) }
    ]
  }

  // ── Header ──────────────────────────────────────────────────────────────
  let contact = get(d, "contact", default: (:))
  let contact-items = (get(contact, "address"), get(contact, "phone"), get(contact, "email")) + get(contact, "links", default: ())
  let header = [
    #text(22pt, weight: "bold", fill: accent, get(d, "name", default: ""))
    #if nonempty(get(d, "headline")) [ \ #text(11.5pt, fill: muted, get(d, "headline"))]
    #v(0.3em)
    #text(9pt, contact-items.filter(nonempty).join([#h(0.45em)·#h(0.45em)]))
  ]
  let photo = get(d, "photo")
  if nonempty(photo) {
    grid(columns: (1fr, 30mm), column-gutter: 6mm, align: (left + horizon, right),
      header, image(photo, width: 30mm, height: 38mm, fit: "cover"))
  } else {
    header
  }

  // ── Sections (fixed order; empty ones are left out) ─────────────────────
  if nonempty(get(d, "summary")) {
    section(L.profile)
    par(get(d, "summary"))
  }

  let personal = get(d, "personal", default: ())
  if personal.len() > 0 {
    section(L.personal)
    for p in personal { row(get(p, "label", default: ""), get(p, "value", default: "")) }
  }

  let experience = get(d, "experience", default: ())
  if experience.len() > 0 {
    section(L.experience)
    for e in experience { entry(e, "title", "org", "bullets") }
  }

  let education = get(d, "education", default: ())
  if education.len() > 0 {
    section(L.education)
    for e in education { entry(e, "title", "org", "details") }
  }

  let projects = get(d, "projects", default: ())
  if projects.len() > 0 {
    section(L.projects)
    for p in projects {
      block(breakable: false, below: 0.6em)[
        #text(weight: "bold", get(p, "name", default: ""))
        #if nonempty(get(p, "url")) [#h(0.4em)#text(8.5pt, fill: muted, get(p, "url"))]
        \ #get(p, "description", default: "")
        #let tech = get(p, "tech", default: ())
        #if tech.len() > 0 [ \ #text(8.5pt, fill: muted, L.tech + ": " + tech.join(", "))]
      ]
    }
  }

  // Short table sections stay on one page together with their heading.
  let skills = get(d, "skills", default: ())
  if skills.len() > 0 {
    block(breakable: false, {
      section(L.skills)
      for s in skills { row(get(s, "group", default: ""), get(s, "items", default: ()).join(", ")) }
    })
  }

  let languages = get(d, "languages", default: ())
  if languages.len() > 0 {
    block(breakable: false, {
      section(L.languages)
      for l in languages {
        let note = get(l, "note")
        row(get(l, "language", default: ""), get(l, "level", default: "") + if nonempty(note) { " (" + note + ")" } else { "" })
      }
    })
  }

  let certificates = get(d, "certificates", default: ())
  if certificates.len() > 0 {
    section(L.certificates)
    for c in certificates {
      row(get(c, "date", default: ""), (get(c, "name"), get(c, "issuer")).filter(nonempty).join(" – "))
    }
  }

  page-count-marker()
}
