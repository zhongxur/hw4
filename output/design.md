# Design (Problem 10)

**Concept: "Bulldog Blue, printed on paper."** The site should feel like walking into a campus shop, with
a pennant on the wall, a stack of folded crewnecks and someone at the counter who knows the stock. It
should not look like a default web template.

| What changed | Why it helps people stay and buy |
|---|---|
| **Palette:** Yale blue `#00356B` on warm paper `#F6F2E9`, with ink-navy text and one secondary blue. Stock states use their own colours (green in stock, amber low, red sold out). | Reads instantly as Yale without copying official marks. The warm background makes navy and grey garments pop on white product tiles, and stock colours can be read at a glance. |
| **Type:** *Fraunces* (heavy collegiate serif) for headlines and product names, *Inter* for UI, *Space Mono* for eyebrows, badges and the ticker. | The serif gives heritage and gift-worthiness, Inter keeps prices and forms easy to read, and the mono "stamp" labels feel like screen-printed tags. |
| **Hero collage:** three real catalogue photos tilted like prints on a table, a felt **YALE pennant** that gently waves, and a rotating dashed **"BOOLA BOOLA" stamp**. Two CTAs: *Shop all 102 styles* and *Ask Dan what to get*. | Shows real product in the first second, so there is nothing abstract to decode. The second CTA brings the chatbot into the main path for undecided visitors such as parents buying gifts. |
| **Scrolling ticker** in the nav ("Ask Dan about any size, any time ✦ Boola Boola ✦ …"). | Gives the page motion and personality without blocking content, and quietly advertises the assistant. |
| **Category tiles** with a real product thumbnail, a one-line pitch and a count. | Faster than a menu: shoppers pick by look ("hoodies") and see how much choice there is. |
| **Product cards:** white "print" tile, hover lift and image zoom, category eyebrow, serif name, colour swatches, *Low stock* / *Sold out* badges, and a greyed-out image when sold out. Cards fade and rise in sequence. | Scannable grid with price and availability visible before a click. Scarcity badges create urgency, and sold-out items don't waste a shopper's click. |
| **Product page:** sticky large image with **hover-to-zoom** on the fabric/print, a price in display type, colour chips, and a size grid showing live counts with sold-out sizes struck through on a hatched background. | Answers "what does the print look like?" and "is my size there?" without scrolling, which removes the two main reasons people leave a product page. |
| **Chat as a character:** "Dan · Campus Customs" with a tilted "D" badge, a bobbing *Ask Dan* button with 🐾, spring-open animation from the corner, typing dots, product mini-cards inside the chat, tappable suggestion chips, and a "Looking at: <product>" strip. | Feels like a friendly employee rather than a support widget, so people actually use it. Cards and chips mean the chat leads straight back to products. |
| **Chat → page hand-off:** a blue banner, "Results from your chat with Dan", above the grid the chat just filled, with *Show all products* to reset. | Makes the "wow" moment obvious and keeps the shopper oriented. |
| **Promise band** (blue): "Real stock, not guesses", etc. Footer states that this is a class demo and not an official Yale site. | Builds trust in the numbers and is honest about what the site is. |
| **Responsive + accessible:** hamburger nav under 720px, full-screen chat on phones, sizes wrap 3×2, visible focus states, `aria` labels on the chat and size radios, and all animation off under `prefers-reduced-motion`. | Most students shop on their phones, and motion never gets in anyone's way. |
