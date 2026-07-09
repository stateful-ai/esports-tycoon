# Map paint style briefs

Research distilled into prompt language for painting the five map blockouts
(haven, ascent, bind, lotus, split) per docs/art-pipeline.md: style is
described ENTIRELY IN TEXT and applied as a single-image edit of the
rasterized guide, never via a reference image passed into the edit call.
Sourced from official Riot dev blogs (playvalorant.com), the VALORANT wiki,
and map-guide sites (thespike.gg, mobalytics, dexerto, etc.) as of 2026-07.

## Shared style spine (use in every map prompt)

Repaint this isometric floor-plan blockout into a stylized 3D isometric
esports-broadcast map diorama: painterly-but-crisp stylized realism (not
photoreal, not flat cartoon), viewed from a fixed 3/4 broadcast-caster
angle, like a tactical-shooter overview render. CRITICAL - preserve the
floor-plan layout exactly; do not move walls, rooms, or site boundaries.
Keep floors as large, clean, evenly lit planes in one readable material per
zone - players and utility icons are drawn on top at runtime, so mid-lane
and site floor space must stay free of loose clutter, heavy cast shadows,
or high-contrast texture noise. Push material and color storytelling onto
walls, elevation changes, and cover objects instead. Grade the overall
lighting cool teal-gray in ambient and shadow, with warm amber/gold accent
light at doorways, windows, and glow props, to match a dark teal-and-amber
broadcast UI. No text, no logos, no readable signage, no people, no blood,
no HUD elements, no boundary or floor outline strips - pure environment;
the runtime draws authoritative borders as a vector overlay.

---

## Haven - Bhutanese monastery fortress

**Prompt:**
Isometric floor-plan blockout repainted as a Bhutanese dzong-monastery
fortress reclaimed by Kingdom for radianite storage. Whitewashed
rammed-earth walls with deep maroon and gold timber trim, trapezoidal
dark-slate roofs, weathered stone steps and low garden walls. Black
hexagonal basalt columns erupt through courtyards and walls, their
fractured faces glowing ember-red like cooling lava; scorch marks and char
streak nearby stone from recent fire damage. Tattered maroon-and-gold
banners hang on ropes between eaves. Cool overcast mountain daylight washes
the stone, broken by warm amber glow spilling from window openings and
lantern nooks, plus the ember-red basalt glow as the scene's signature
accent. Moss creeps up shaded stone; potted junipers and wood lattice
screens add texture without crowding open floor lanes.

**Palette:** whitewashed stone white, oxblood-maroon timber, muted gold
trim, moss green, ember-red glow accent.

**Materials/textures:** rammed-earth and whitewashed stone walls, dark
timber beams, weathered slate/stone trapezoidal roofs, black hexagonal
basalt columns, fabric prayer-flag-style banners, moss and ivy, sandbags,
carved wood lattice shutters.

**Lighting:** cool overcast high-mountain daylight as base ambient; warm
amber glow from interior windows and lanterns; molten ember-red glow from
cracked basalt columns and fire-damaged timber as the signature accent.

**Signature props:** glowing ember-red basalt columns, tattered
maroon/gold banners on rope lines, weathered stone statue fragments, carved
wood lattice screens, moss-covered stone steps, scorched/charred timber,
sandbag barricades, low stone garden walls with potted junipers.

**Site flavor:**
- A: open plant zone by a tower, basalt columns and char damage nearby.
- B: tight central courtyard, boxy cover, temple-interior feel.
- C: open ground with a long sightline, gardens and greenery framing it.

---

## Ascent - floating Venice ruin

**Prompt:**
Isometric floor-plan blockout repainted as a fragment of Venice frozen
mid-collapse, floating in open sky. Sun-bleached cream limestone paving and
warm terracotta-ochre stucco walls, framed by weathered wrought-iron
balustrades and lampposts. Green-and-white striped canvas awnings shade
market stalls; faded fresco murals in ochre and teal cover brick facades;
cracked marble columns and a broken church rose-window mark the ruin edges.
Golden late-afternoon Mediterranean light rakes low across the piazza,
throwing long warm shadows, while a cool pale-blue sky-glow bleeds in from
the fragment's open, cliff-like edges. Terracotta roof tiles cap low
buildings; hanging laundry lines and wooden fruit crates add lived-in color
without cluttering the walkable floor. Keep plaza and lane floors clean
stone; concentrate texture on walls and edges.

**Palette:** terracotta-ochre stucco, sun-bleached cream stone, awning
green, weathered wrought-iron black, faded teal mural blue.

**Materials/textures:** stucco plaster walls, limestone paving, wrought-iron
railings and balustrades, striped canvas awnings, terracotta roof tiles,
mural-painted brick, wood market crates, cracked marble.

**Lighting:** golden Mediterranean late-afternoon key light with long warm
shadows; cool pale-blue sky-glow at the floating fragment's open edges as
the signature contrast note.

**Signature props:** green/white striped market awnings, stone balustrade
railings, faded fresco murals on brick, wrought-iron lampposts, terracotta
roof tiles, hanging laundry lines, wooden produce crates, cracked marble
ruin columns.

**Site flavor:**
- A: fractured stone church facade with a broken rose window, ruin debris.
- B: tighter market alley, striped awning stalls, painted mural walls.

---

## Bind - Moroccan desert town / Kingdom refinery

**Prompt:**
Isometric floor-plan blockout repainted as a sun-baked Moroccan desert town
split between an old-world market and a Kingdom industrial refinery.
Sandy tan adobe walls, warm terracotta arches, and teal-and-white geometric
zellige tilework contrast with gunmetal-gray riveted refinery towers
trailing thin black smoke. Carved wood mashrabiya screens, brass lanterns,
and woven rugs in rust and gold line market-side walls; sandstone Moorish
archways frame doorways. Harsh desert midday sun casts high-contrast warm
amber light and hard-edged cool blue shade under canvas tarps; industrial
zones get a sodium-orange working-light glow against gray metal. Potted
palms and cacti punctuate corners. Keep floor lanes clean sand-toned stone
or packed earth; push tile pattern, rugs, and smoke texture onto walls,
archway edges, and tower silhouettes instead.

**Palette:** sandy tan adobe, warm terracotta, teal zellige tile, gunmetal
gray, brass gold accent.

**Materials/textures:** sun-baked adobe/mudbrick walls, geometric zellige
tile mosaics, carved wood mashrabiya lattice screens, woven rugs and
cushions, brass lanterns, riveted steel refinery towers and pipework,
canvas tarps, sandstone Moorish archways.

**Lighting:** harsh high-contrast desert midday sun, warm amber ambient
with hard cool-blue shade pockets under tarps; sodium-orange industrial
glow and black smoke haze near the refinery towers as the signature
contrast.

**Signature props:** teal/blue zellige tilework, hanging brass lanterns,
patterned woven rugs and cushions, carved wood mashrabiya screens, spice
sacks and dye vats, gray riveted refinery tower with smoke stacks, arched
Moorish doorways, potted palms and cacti.

**Site flavor:**
- A: open plant zone beneath a looming reactor tower, tiled bathhouse
  detail nearby.
- B: tighter refinery control-building footprint, ornate hookah-lounge
  overlook with cushions and carved wood ceiling above.

---

## Lotus - rock-cut Indian temple-city

**Prompt:**
Isometric floor-plan blockout repainted as a rediscovered rock-cut Indian
temple-city carved from rose-pink sandstone. Weathered pink and warm-ochre
stone walls bear carved reliefs of elephants and lotus petals, framed by
mossy vines and jungle-green overgrowth spilling from cracks. Radianite
lotus motifs and wall-carving grooves glow a soft teal-cyan, the map's
signature accent light against warm stone. A tiered waterfall cascades into
a still pool at one edge, throwing cool blue-green mist and reflected
light. Dappled warm sunlight filters through unseen jungle canopy above,
pooling gold on stone terraces while interiors stay dim and mystical.
Carved stone pillars and circular rotating stone doors anchor thresholds.
Keep central platform floors smooth carved sandstone and uncluttered;
concentrate moss, glow, and relief carving on walls and pillar bases.

**Palette:** rose-pink sandstone, warm ochre stone, jungle green, teal-cyan
radianite glow, charcoal carved-shadow.

**Materials/textures:** rock-cut pink/rose sandstone architecture, carved
stone reliefs (elephants, lotus petals), moss and vine overgrowth, cascading
waterfalls and still pools, carved stone pillars, stepped stone terraces.

**Lighting:** dim mystical interior base lit by teal-green glowing radianite
wall carvings; dappled warm sunlight through unseen jungle canopy on open
terraces; cool blue-green mist near the waterfall.

**Signature props:** pink lotus flowers on ledges (some with soft teal
mist), carved stone elephant reliefs, glowing teal wall-carving grooves, a
tiered waterfall into a pool, moss-covered rock-cut columns, vine-choked
stone archways, large circular rotating stone doors, stepped terraced
platforms.

**Site flavor:**
- A: dim rock-cut hallway lit only by glowing lotus-petal wall carvings.
- B: elevated pillared platform backed by a large carved lotus mural.
- C: open elevated planting platform with a central carved pillar, waterfall
  path adjacent.

---

## Split - old Tokyo district vs Kingdom tech campus

**Prompt:**
Isometric floor-plan blockout repainted as a Tokyo district split between a
weathered old town and a sterile new Kingdom tech campus. Old-town zones:
aged charcoal-gray tile roofs, warm brown wood siding, faded red paper
lanterns, corrugated tin awnings over tiny shopfronts, warm amber
shop-window glow. Kingdom zones: poured concrete and glass curtain walls,
brushed steel trim, gold corporate logo accents, cold cyan-white task
lighting and magenta neon signage glow. Braided yellow rope ascenders
stretch between elevation changes; a glowing teal-white radianite generator
anchors each site as a landmark silhouette. Overall ambient ranges cool
blue-gray dusk haze with pockets of warm lantern light against sterile
neon-cyan light. Keep street and platform floors clean asphalt or concrete;
put wood grain, neon glow, and construction texture on walls, signage, and
vertical surfaces only.

**Palette:** weathered wood brown, charcoal tile gray, cool steel gray,
neon magenta-cyan, warm lantern amber.

**Materials/textures:** weathered wood siding, paper lanterns, poured
concrete and glass curtain wall, corrugated metal awnings, braided yellow
rope, vending-machine plastic/metal, cobblestone/asphalt alleys, chain-link
and scaffolding.

**Lighting:** cool blue-gray dusk-haze ambient overall; warm amber glow from
old-town lanterns and shopfronts; cold cyan/magenta neon and sterile white
task light around new Kingdom construction as the signature contrast.

**Signature props:** yellow rope ascenders between levels, glowing
teal-white radianite generator landmark, vending machines, small
shoe/coffee shopfronts, hanging paper lanterns, corrugated tin awnings,
scaffolding/construction fencing on new Kingdom builds, overhead cable
clutter (kept off floor, on walls/eaves only).

**Site flavor:**
- A: clean-cut new wood-and-concrete Kingdom construction, gold logo
  signage, a large plain sign usable as cover.
- B: older weathered district, traditional shopfronts, narrower alleys,
  warmer lantern light throughout.
