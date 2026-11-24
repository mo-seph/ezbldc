# 4-channel BLDC driver board — BOM (per board)

Parts were checked against JLCPCB's live catalogue on 2026-11-10 and
2026-11-11 (part number, package, basic / extended, stock). Prices are
JLCPCB's quantity-1 tier in USD on those days. `bom_jlcpcb.csv` is the
same list in JLCPCB's upload format;
`kicad/output/fab/bom_jlcpcb_smd_only.csv` is the surface-mount half, for
an order where the through-hole parts are fitted by hand. Designators
match the KiCad project.

## Surface mount (JLCPCB assembles these)

| Designators | Qty | Part | Package | LCSC | JLCPCB | $ each |
|---|---|---|---|---|---|---|
| U2, U3, U4, U5 | 4 | DRV8313PWPR (TI) | HTSSOP-28, PowerPAD | C92482 | extended | 4.47 |
| U6 | 1 | 74HC139D,653 (Nexperia) | SOIC-16 | C5603 | extended | 0.25 |
| C12 C13 C14, C22 C23 C24, C32 C33 C34, C42 C43 C44, C1, C2 | 14 | 100 nF 50 V X7R | 0805 | C49678 | basic | 0.015 |
| C11, C21, C31, C41 | 4 | 10 nF 50 V X7R | 0805 | C1710 | basic | 0.010 |
| C16, C26, C36, C46 | 4 | 470 nF 50 V X7R | 0805 | C13967 | basic | 0.019 |
| C15, C25, C35, C45, C3 | 5 | 100 µF 25 V aluminium, Ø6.3 × 7.7 mm | SMD can | C2836443 | extended | 0.04 |
| C4, C6 | 2 | 10 µF 25 V X5R (C6 is the bulk capacitor on +3V3 at the XIAO) | 0805 | C15850 | basic | 0.035 |
| D4 | 1 | SMAJ15A/TR13 (Brightking), 15 V unidirectional TVS, clamps the 12 V rail | SMA | C86819 | extended | 0.048 |
| C5 | 1 | 22 µF 25 V X5R | 0805 | C45783 | basic | 0.11 |
| R11, R21, R31, R41 | 4 | 1 kΩ 1 % | 0805 | C17513 | basic | 0.004 |
| R3, R5 | 2 | 10 kΩ 1 % | 0805 | C17414 | basic | 0.003 |
| R6 | 1 | 100 Ω 1 % (encoder data line, in series at the XIAO) | 0805 | C17408 | basic | 0.004 |
| R12, R22, R32, R42 | 4 | 47 Ω 1 % (encoder clock, one in series at each socket) | 0603 | C23182 | basic | 0.002 |
| C17, C27, C37, C47 | 4 | 100 nF 50 V X7R (3V3 decoupling at each encoder socket) | 0603 | C14663 | basic | 0.006 |
| F1, F2, F3, F4 | 4 | Polyfuse 1.1 A hold, 2.2 A trip, 33 V (SMD1812P110TF/33). 2 A hold / 24 V (SMD1812P200TF/24, C434887, $0.20) fits the same pads | 1812 | C21000 | extended | 0.147 |
| D11, D21, D31, D41 | 4 | LED red (NCD0805R1) | 0805 | C84256 | basic | 0.013 |
| D1 | 1 | SS54 Schottky 5 A 40 V | SMA | C22452 | basic | 0.045 |
| D2 | 1 | SS14 Schottky 1 A 40 V | SMA | C2480 | basic | 0.019 |
| D3 | 1 | WS2812B (XL-5050RGBC-2812B) | 5050 | C2843785 | extended | 0.055 |
| J3, J4 | 2 | JST SM04B-SRSS-TB (Qwiic) | SMD, right angle | C160404 | extended | 0.21 |

Not fitted: R1, R2 (4.7 kΩ, 0805, C17673, basic). The I2C pull-ups are
expected on the bus controller; fit these if the board is used alone.

No part: fourteen test pads TP1–TP14 (bare 1.5 mm copper pads), three
fiducials, four mounting holes.

## Through-hole and hand-fitted

| Designators | Qty | Part | LCSC | JLCPCB | $ each |
|---|---|---|---|---|---|
| J11–J14 (motors) | 4 | 1 × 3 pin header, 2.54 mm (XFCN PZ254V-11-03P). Gimbal motors usually come with a 2.54 mm socket | C2937625 | extended, through-hole | 0.02 |
| J21–J24 (encoders) | 4 | JST B5B-XH-A, 5-pin 2.5 mm | C157991 | extended, through-hole | 0.09 |
| J1, J2 (12 V in, 12 V out) | 2 | XKB DC-005-5A-2.0 barrel jack | C381116 | extended, through-hole | 0.26 |
| U7 | 1 | L7805CV (ST), linear 5 V regulator, TO-220, standing. Alternative: K7805-500R3 switching module (C2992390, $1.75), same holes, same pin order | C111887 | extended, through-hole | 0.31 |
| JP1 (Qwiic power jumper) | 1 | 1 × 2 pin header, 2.54 mm (XFCN PZ254V-11-02P) | C492401 | extended, through-hole | 0.02 |
| U1 | 1 | Seeed XIAO ESP32-S3 Plus | not stocked at JLCPCB | hand solder | ≈ 9 (not checked) |

## Totals

| | USD |
|---|---|
| Surface-mount parts | ≈ 20.12 (the four DRV8313 are 17.88 of it) |
| Through-hole parts | ≈ 1.29 |
| **Parts JLCPCB supplies and fits** | **≈ 21.41** |
| XIAO ESP32-S3 Plus (hand-fitted) | ≈ 9 (not checked) |
| **Parts per board** | **≈ 30.40** |

## JLCPCB assembly estimate (2026-11-11)

Two ways to order. Either way the XIAO is fitted by hand: JLCPCB do not
stock it.

| Who fits what | smallest order (5 boards made, 2 assembled) | 10 boards, all assembled |
|---|---|---|
| **Full**: JLCPCB fit everything except the XIAO | ≈ $108 | ≈ $295 |
| **Surface-mount only**: JLCPCB fit the SMD parts, the through-hole parts are fitted by hand | ≈ $85, plus ≈ $2.60 of through-hole parts | ≈ $256, plus ≈ $13 of through-hole parts |
| What surface-mount only saves, after buying those parts separately | ≈ $20 | ≈ $26 |

Before shipping and import tax. The bare-board price in these is
JLCPCB's own: read off their calculator on 2026-11-11 for 4 layers,
80 × 62.05 mm, 1.6 mm, green, lead-free HASL.

Surface-mount only leaves 12 parts and 43 joints a board to do by hand:
four 1 × 3 motor headers, four JST-XH encoder sockets, two barrel jacks,
the 7805 and the Qwiic-power jumper header. The XIAO is another 23 joints
either way.

How those totals are made up. Counts are from the KiCad project: 64
surface-mount placements (260 joints), 12 through-hole parts (43 joints),
29 part types of which 12 are extended (7 surface-mount, 5 through-hole).
Fees are JLCPCB's published Economic PCBA rates as read on 2026-11-10:
setup $8.18, stencil $1.53, hand-soldering labour $3.58 per order, $3.07
per extended part type per order, $0.0016 per surface-mount joint, $0.0164
per hand-soldered joint.

| | Full, smallest order | Full, 10 boards | SMD only, smallest order | SMD only, 10 boards |
|---|---|---|---|---|
| Setup and stencil | 9.71 | 9.71 | 9.71 | 9.71 |
| Hand-solder labour | 3.58 | 3.58 | – | – |
| Extended part fee ($3.07 a type) | 36.84 (12 types) | 36.84 | 21.49 (7 types) | 21.49 |
| Joints | 2.24 ($1.12 a board) | 11.21 | 0.83 ($0.42 a board) | 4.16 |
| Components | 42.82 ($21.41 a board) | 214.10 | 40.24 ($20.12 a board) | 201.20 |
| Bare 4-layer boards, lead-free HASL (5 or 10 made) | 13.10 | 19.30 | 13.10 | 19.30 |
| **JLCPCB total before shipping and tax** | **≈ $108** | **≈ $295** | **≈ $85** | **≈ $256** |
| Through-hole parts bought separately ($1.29 a board) | – | – | ≈ 2.60 | ≈ 13 |
| Per working board, with those parts and a XIAO | ≈ $63 | ≈ $38 | ≈ $53 | ≈ $36 |

- There is no one-board order: the minimum is 5 bare boards with 2 of them
  assembled.
- Bare-board price by finish, five boards: $8.00 OSP (the page's
  default), $13.10 lead-free HASL, $25.20 ENIG. Ten boards: $14.00 OSP,
  $19.30 lead-free HASL. The table uses lead-free HASL: OSP solders
  poorly once it has been through the oven and sat for a while, and the
  XIAO and (in the surface-mount-only case) the through-hole parts are
  soldered afterwards. Vias: "Plugged" is the default for four layers
  and costs nothing ("Tented" is not offered).
- The assembly lines are computed from JLCPCB's published fees, not from
  a quote: their page gives assembly prices only after the files are
  uploaded.
- Component prices are quantity-1 tiers; at 10 boards the DRV8313 (40
  pieces) may drop a tier. JLCPCB also charges for a few spare passives.
- The $1.29 for through-hole parts is JLCPCB's own price for them.
- If any part turns out to be "Standard PCBA only", the fees change to
  setup $25.56, stencil $8.21 and $1.53 per part type: about $60 more per
  order.

## Notes

- **DRV8313 price.** JLCPCB charges $4.47 for a part LCSC lists at about
  $1.70. That makes a driver channel about $5 with its passives.
- **Polyfuse size.** 1.1 A hold, 2.2 A trip per channel. Four of them
  hold 4.4 A, which stays inside the 5 A rating of the jacks and of D1,
  so the fuses still protect the board's own input. A 2 A hold part
  (SMD1812P200TF/24, C434887) fits the same pads and would let one driver
  run at its full rating, but four of those hold 8 A, more than the input
  can carry: then only the supply's own limit protects the jack and D1.
  Polyfuses lose about a third of their hold current at 60 °C.
- **Sustained power.** D1 is the warmest part of the input: about 1 W at
  2.5 A, 1.5 W at 3.5 A, in an SMA package. Treat about 3 A (36 W) for
  the whole board as the comfortable sustained figure.
- **7805.** Linear, so it burns (12 V − 0.5 V − 5 V) × the 5 V current:
  about 0.7 W with the XIAO's radio off and four encoders, about 1.25 W
  with WiFi on, which is roughly 60 °C above ambient for a bare TO-220.
  It stands about 19 mm above the board, the tallest part. If it runs too
  hot or a heatsink is in the way, the K7805-500R3 module drops into the
  same holes.
- **WS2812B at 3.3 V.** This XINGLIGHT part is rated 3.5–5.5 V; if a
  batch is unreliable, feed its VDD from +5V instead.
- **Bulk capacitors.** The 100 µF cans are rated for about 93 mA of
  ripple and each driver has only 100 nF of ceramic beside it. Above
  roughly 0.5 A of motor current they run over that rating (a matter of
  life, not function). Making Cn3 / Cn4 10 µF 25 V (C15850, same pads) is
  a BOM-only improvement.
- **Encoders** are off-board: breakout boards on the motors, wired to
  J21–J24. See the README for what can share the encoder bus.
