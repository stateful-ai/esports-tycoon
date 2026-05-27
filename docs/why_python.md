# Why Python

Choosing the language gets glossed over too often. Documenting it here.

- **Readability** — every contributor we want has read Python before.
- **Stdlib leverage** — we lean on it heavily; few third-party deps to age.
- **Testing posture** — pytest fits how we think about contracts.
- **Speed where it matters** — numpy / Cython escape hatches if a hot path appears.

We are not Python maximalists. If a future component genuinely needs
another language, we add it; we don't fight it.
