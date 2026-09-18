@Honey @Fizz

@Fizz - 1 - why get render? 3 simple reasons in as few words as possible.

2 - I am not a fan of the design that Hermes built so I had chatgpt write me a new version that included design parameters I'm going to give you here. (Please review and then assign the appropriate edits to Hermes. as im not sure all of it’s suggestions are appropriate or required, depending on what you guys built) - and see pdf and png image, because I had it build the first draft, and I like the design.

(for the just the design md: # EPIC Transcript Machine: Visual Design System

This file defines the visual language, layout rules, component styling, responsive behavior, and interaction standards for the product. It intentionally contains no page copy, marketing language, FAQ content, instructions, or feature requirements.

1\. Visual Thesis

A fast, cinematic creator tool built around a near-black canvas, neon purple-to-pink energy, oversized editorial typography, translucent glass controls, and a warm off-white workspace for results.

The interface should feel:

- Premium but not corporate
- Bold but not busy
- Modern but not sterile
- Playful but not cartoonish
- Fast, obvious, and easy to operate

The primary working control must remain visible in the first viewport. Avoid oversized navigation, decorative clutter, and excessive empty space.

2\. Design Tokens

Color

```css
:root {
  --color-bg: #09090b;
  --color-bg-raised: #0d0d10;
  --color-surface-light: #f7f6f3;
  --color-surface-light-raised: #fbfaf8;
  --color-surface-white: #ffffff;

  --color-text-on-dark: #ffffff;
  --color-text-dark: #171719;
  --color-text-body: #3f3f46;
  --color-text-muted: #71717a;

  --color-purple: #7b2ff7;
  --color-purple-bright: #c22ffc;
  --color-pink: #f107a3;
  --color-coral: #ff3d6b;
  --color-success: #059669;

  --color-error-text: #fee2e2;
  --color-error-bg: rgba(248, 113, 113, 0.08);
  --color-error-border: rgba(248, 113, 113, 0.20);

  --white-4: rgba(255, 255, 255, 0.04);
  --white-6: rgba(255, 255, 255, 0.06);
  --white-7: rgba(255, 255, 255, 0.07);
  --white-10: rgba(255, 255, 255, 0.10);
  --white-12: rgba(255, 255, 255, 0.12);
  --white-30: rgba(255, 255, 255, 0.30);
  --white-45: rgba(255, 255, 255, 0.45);
  --white-50: rgba(255, 255, 255, 0.50);
  --white-55: rgba(255, 255, 255, 0.55);
  --white-60: rgba(255, 255, 255, 0.60);

  --black-4: rgba(0, 0, 0, 0.04);
  --black-7: rgba(0, 0, 0, 0.07);
  --black-8: rgba(0, 0, 0, 0.08);
  --black-10: rgba(0, 0, 0, 0.10);
}
```

Gradients

Primary action:

```css
background: linear-gradient(115deg, #7b2ff7 0%, #c22ffc 48%, #f107a3 100%);
```

Primary action hover:

```css
background: linear-gradient(115deg, #8c41ff 0%, #cf40ff 48%, #ff1cad 100%);
```

Display-text accent:

```css
background: linear-gradient(105deg, #ffffff 0%, #dca7ff 38%, #ff77bf 72%, #ffffff 108%);
-webkit-background-clip: text;
background-clip: text;
color: transparent;
```

Typography

```css
--font-sans: "Avenir Next", Avenir, "SF Pro Display", "Segoe UI", Helvetica, Arial, sans-serif;
--font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
```

Use one sans-serif family throughout. Use monospace only for timestamps, technical values, or fixed-width metadata.

RoleMobileDesktopWeightLine heightTrackingDisplay48px78px6001.02-0.05emSection title36px48px6001.10-0.04emCard title20px24px6001.17-0.02emLead18px20px4001.60normalBody16px17px4001.88normalUI label14px14px5001.40normalEyebrow11px11px7001.000.24emBadge10px10px6001.000.18emTimestamp12px12px6001.00normal

Headings should use tight tracking and restrained weight. Do not compensate with extra-bold weights.

Spacing

Use a 4px base unit.

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-7: 28px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;
--space-14: 56px;
--space-16: 64px;
--space-18: 72px;
--space-24: 96px;
--space-36: 144px;
```

Radius

```css
--radius-small: 8px;
--radius-control: 12px;
--radius-alert: 16px;
--radius-primary-action: 18px;
--radius-form: 24px;
--radius-card: 28px;
--radius-round: 999px;
```

Do not make every component pill-shaped. Reserve full pills for badges, compact status elements, and circular step markers.

Shadows

```css
--shadow-glass: 0 30px 100px rgba(0, 0, 0, 0.35);
--shadow-action: 0 10px 35px rgba(183, 48, 255, 0.25);
--shadow-card: 0 24px 70px rgba(33, 25, 43, 0.08);
--shadow-brand: 0 0 40px rgba(242, 16, 165, 0.22);
```

Shadows must be soft and diffused. Avoid hard gray shadows or stacked material-design elevation effects.

3\. Layout System

Widths

```css
--page-max: 1152px;
--display-max: 896px;
--form-max: 896px;
--content-max: 896px;
--narrow-max: 768px;
```

Center all main containers with `margin-inline: auto`.

Horizontal page padding:

```css
/* Mobile */
padding-inline: 20px;

/* 640px and above */
padding-inline: 32px;
```

Minimum supported viewport width:\* `320px`*.*\
Mobile \*/\
padding: 48px 20px 96px;

/\* Desktop \*/\
padding: 72px 32px 144px;

```

Light supporting section:

```css
/* Mobile */
padding: 96px 20px;

/* Desktop */
padding: 144px 32px;
```

4\. Page Surfaces

The interface alternates between two purposeful modes:

1. Dark presentation and input surface
2. Warm light reading and results surface

Dark surface:

```css
background: #09090b;
color: #ffffff;
```

Raised dark section:

```css
background: #0d0d10;
border-top: 1px solid rgba(255, 255, 255, 0.06);
```

Light workspace:

```css
background: #f7f6f3;
color: #171719;
```

Do not use pure white as the full-page light background. Reserve pure white for cards and controls.

5\. Ambient Lighting

Use subtle radial gradients to add brand energy without introducing illustrations or visual noise.

Primary glow:

```css
position: absolute;
top: 20px;
left: 50%;
transform: translateX(-50%);
width: min(820px, 90vw);
height: 430px;
border-radius: 999px;
filter: blur(2px);
opacity: 0.78;
pointer-events: none;
background: radial-gradient(circle, rgba(123, 47, 247, 0.18) 0%, rgba(241, 7, 163, 0.06) 38%, transparent 72%);
```

Secondary glow:

```css
position: absolute;
top: 410px;
right: -180px;
width: 480px;
height: 480px;
border-radius: 999px;
filter: blur(2px);
opacity: 0.78;
pointer-events: none;
background: radial-gradient(circle, rgba(241, 7, 163, 0.08) 0%, transparent 68%);
```

All interactive page content must sit above ambient effects with an explicit stacking context.

6\. Brand Lockup

Icon container:

```css
width: 36px;
height: 36px;
display: grid;
place-items: center;
border-radius: 12px;
background: #ffffff;
color: #000000;
box-shadow: var(--shadow-brand);
```

Use a clean outline audio or waveform icon at 20px with approximately 2.35px stroke width.

Lockup layout:

```css
display: flex;
align-items: center;
gap: 12px;
```

The wordmark should use a small tracked eyebrow above a compact product name. Keep the complete lockup visually under 40px tall.

7\. Primary Form Surface

Desktop: input and primary action sit side by side within one glass container.

Mobile: input remains first and the primary action moves below at full width.

Container:

```css
width: 100%;
max-width: 896px;
padding: 10px;
border: 1px solid rgba(255, 255, 255, 0.12);
border-radius: 24px;
background: rgba(255, 255, 255, 0.07);
backdrop-filter: blur(24px);
box-shadow: var(--shadow-glass);
```

Input row:

```css
display: flex;
align-items: center;
gap: 12px;
padding-inline: 12px;
min-width: 0;
flex: 1;
```

Input:

```css
height: 56px;
width: 100%;
border: 0;
background: transparent;
box-shadow: none;
font-size: 16px;
color: #ffffff;
```

Input placeholder opacity:\* `30%` *white.* Mobile \*/\
padding: 20px;

/\* Desktop \*/\
padding: 28px;

```

Media preview:

```css
width: 192px;
aspect-ratio: 16 / 9;
border-radius: 16px;
overflow: hidden;
background: #18181b;
```

On mobile, media becomes full width. Use\* `object-fit: cover`*. A hover state may scale the image to* `1.03` *over 300ms.*`#e6d9ef`*.*\
,\
*::before,*\
::after {\
scroll-behavior: auto !important;\
transition-duration: 0.01ms !important;\
animation-duration: 0.01ms !important;\
animation-iteration-count: 1 !important;\
}\
}

```

## 17. Responsive Breakpoints

```css
--breakpoint-sm: 640px;
--breakpoint-md: 768px;
--breakpoint-lg: 1024px;
```

Required mobile behavior:

- No horizontal scrolling at 320px
- Primary form stacks vertically
- Main action becomes full width
- Large headings reduce without losing hierarchy
- Multi-column grids collapse to one column
- Result media becomes full width
- Toolbars wrap into clear action groups
- Reading text remains at least 16px
- Controls remain comfortably tappable

18\. Accessibility

- Minimum 4.5:1 contrast for normal text
- Visible keyboard focus states
- Semantic heading hierarchy
- Programmatic labels for inputs and icon-only controls
- `role="alert"` for blocking failures
- State must not rely on color alone
- Target size near 44px or larger for primary touch controls
- Respect reduced-motion preferences
- Preserve readable contrast across default, hover, focus, disabled, loading, success, and error states

19\. Design Guardrails

 1. Keep the primary working control in the first viewport.
 2. Keep the hero close to the header.
 3. Do not add large empty spacer regions.
 4. Do not place a marketing wall before the functional interface.
 5. Preserve the black, purple, pink, and warm-off-white palette.
 6. Use glass effects only on dark surfaces and only where hierarchy benefits.
 7. Keep light workspaces warm and readable.
 8. Maintain explicit button contrast in every state.
 9. Avoid generic SaaS card grids.
10. Avoid decorative stock imagery.
11. Avoid excessive pills, gradients, glows, and shadows.
12. New features must look native to this system.
13. Advanced controls should appear progressively, not crowd the initial interface.
14. Desktop and mobile must feel intentionally composed, not merely resized.
15. Function and readability always outrank decoration.

20\. Implementation Rule

Treat this file as the visual source of truth. It defines appearance and interaction styling only. Product copy, instructions, labels, feature scope, data behavior, and business logic belong in separate specification files.

)

EPIC Transcript Machine Design System

1\. Design Direction

EPIC Transcript Machine should feel:

- Fast

- Premium

- Modern

- Simple

- Slightly rebellious

- Easy enough to use without instructions

- More like a polished creator tool than corporate software

Visual thesis:

> A cinematic black interface with neon purple and pink energy, oversized typography, soft glass surfaces, and extremely clear actions.

The transcript form is the star of the page. Do not bury it beneath marketing copy, oversized navigation, or excessive vertical spacing.

---

2\. Brand Name

Primary name:

**EPIC Transcript Machine**

Header lockup:

- Eyebrow: `EPIC`

- Product name: `Transcript Machine`

Footer:

`EPIC Transcript Machine · Public videos · No login required · Powered by epic.media`

Link `epic.media` to:

`https://epic.media`

---

3\. Color Palette

Core colors

```css
--background: #09090b;
--foreground: #ffffff;

--dark-section: #0d0d10;
--light-section: #f7f6f3;
--light-footer-surface: #fbfaf8;

--light-text-primary: #171719;
--light-text-secondary: #3f3f46;
--light-text-muted: #71717a;

--white-60: rgba(255, 255, 255, 0.60);
--white-55: rgba(255, 255, 255, 0.55);
--white-50: rgba(255, 255, 255, 0.50);
--white-45: rgba(255, 255, 255, 0.45);
--white-30: rgba(255, 255, 255, 0.30);

--purple: #7b2ff7;
--bright-purple: #c22ffc;
--pink: #f107a3;
--coral: #ff3d6b;

--success: #059669;
--error-text: #fee2e2;
--error-background: rgba(248, 113, 113, 0.08);
--error-border: rgba(248, 113, 113, 0.20);
```

Main button gradient

```css
background: linear-gradient(
  115deg,
  #7b2ff7 0%,
  #c22ffc 48%,
  #f107a3 100%
);
```

Hover:

```css
background: linear-gradient(
  115deg,
  #8c41ff 0%,
  #cf40ff 48%,
  #ff1cad 100%
);
```

Headline gradient

Apply to the word `Generator`:

```css
background: linear-gradient(
  105deg,
  #ffffff 0%,
  #dca7ff 38%,
  #ff77bf 72%,
  #ffffff 108%
);

-webkit-background-clip: text;
background-clip: text;
color: transparent;
```

---

4\. Typography

Use this stack:

```css
font-family:
  "Avenir Next",
  Avenir,
  "SF Pro Display",
  "Segoe UI",
  Helvetica,
  Arial,
  sans-serif;
```

Do not use a decorative display font.

The personality should come from:

- Large scale

- Tight tracking

- Strong contrast

- Clean spacing

- Short copy

Hero headline

Desktop:

```css
font-size: 78px;
font-weight: 600;
line-height: 1.02;
letter-spacing: -0.05em;
```

Tablet:

```css
font-size: 72px;
```

Mobile:

```css
font-size: 48px;
```

Content:

```text
Free Video Transcript
Generator
```

Place `Generator` on its own line and apply the gradient.

Hero subheading

```css
font-size: 20px;
line-height: 32px;
font-weight: 400;
color: rgba(255, 255, 255, 0.60);
```

Mobile:

```css
font-size: 18px;
```

Content:

`Instantly, without uploading video files.`

Section headings

```css
font-size: 48px;
font-weight: 600;
letter-spacing: -0.04em;
line-height: 1.1;
```

Mobile:

```css
font-size: 30px to 36px;
```

---

5\. Page Width

Main maximum width:

```css
max-width: 1152px;
margin-inline: auto;
```

Hero headline maximum width:

```css
max-width: 896px;
```

Hero description maximum width:

```css
max-width: 672px;
```

Transcript input maximum width:

```css
max-width: 896px;
```

FAQ maximum width:

```css
max-width: 896px;
```

Horizontal page padding:

```css
/* Mobile */
padding-inline: 20px;

/* Tablet and desktop */
padding-inline: 32px;
```

---

6\. Header

The header should be compact. It must not feel like a separate oversized section.

```css
padding-top: 20px;
padding-bottom: 20px;
```

Mobile:

```css
padding-top: 16px;
padding-bottom: 16px;
```

Layout:

```css
display: flex;
align-items: center;
justify-content: space-between;
```

Logo icon

Use the Lucide `AudioLines` icon.

Container:

```css
width: 36px;
height: 36px;
border-radius: 12px;
background: #ffffff;
color: #000000;
display: grid;
place-items: center;
box-shadow: 0 0 40px rgba(242, 16, 165, 0.22);
```

Icon:

```css
width: 20px;
height: 20px;
stroke-width: 2.35;
```

EPIC eyebrow

```css
font-size: 11px;
font-weight: 700;
letter-spacing: 0.24em;
color: rgba(255, 255, 255, 0.45);
```

Product name

```css
margin-top: 4px;
font-size: 14px;
font-weight: 600;
letter-spacing: -0.01em;
```

Status pill

Text:

`FAST · FREE · V2`

Style:

```css
border: 1px solid rgba(255, 255, 255, 0.10);
background: rgba(255, 255, 255, 0.04);
border-radius: 999px;
padding: 6px 12px;

font-size: 10px;
font-weight: 600;
letter-spacing: 0.18em;
color: rgba(255, 255, 255, 0.55);
```

---

7\. Hero Spacing

The hero should begin close to the header.

Current exact top spacing:

```css
padding-top: 16px;
```

This creates approximately one-half inch or less of visual separation depending on screen density.

Hero bottom spacing:

```css
/* Mobile */
padding-bottom: 40px;

/* Desktop */
padding-bottom: 48px;
```

Headline to subheading:

```css
margin-top: 24px;
```

Subheading to transcript form:

```css
margin-top: 48px;
```

Form to reassurance copy:

```css
margin-top: 28px;
```

Reassurance copy:

`Quick and simple. No catch.`

Style:

```css
font-size: 14px;
font-weight: 500;
color: rgba(255, 255, 255, 0.50);
```

---

8\. Ambient Background

Use two blurred radial gradient orbs. They must remain subtle and never interfere with readability.

Main orb

```css
position: absolute;
top: 20px;
left: 50%;
transform: translateX(-50%);
width: min(820px, 90vw);
height: 430px;
border-radius: 999px;
opacity: 0.78;
filter: blur(2px);

background: radial-gradient(
  circle,
  rgba(123, 47, 247, 0.18) 0%,
  rgba(241, 7, 163, 0.06) 38%,
  transparent 72%
);
```

Secondary orb

```css
position: absolute;
top: 410px;
right: -180px;
width: 480px;
height: 480px;
border-radius: 999px;
opacity: 0.78;
filter: blur(2px);

background: radial-gradient(
  circle,
  rgba(241, 7, 163, 0.08) 0%,
  transparent 68%
);
```

Both orbs:

```css
pointer-events: none;
```

---

9\. Transcript Input

Desktop layout:

- URL field on the left

- CTA button on the right

- Both inside one large glass container

Mobile layout:

- URL field first

- Full-width button underneath

Outer form:

```css
width: 100%;
max-width: 896px;
padding: 10px;
border-radius: 24px;

border: 1px solid rgba(255, 255, 255, 0.12);
background: rgba(255, 255, 255, 0.07);
backdrop-filter: blur(24px);

box-shadow: 0 30px 100px rgba(0, 0, 0, 0.35);
```

Input row:

```css
display: flex;
align-items: center;
gap: 12px;
padding-inline: 12px;
```

Input:

```css
height: 56px;
font-size: 16px;
color: #ffffff;
background: transparent;
border: 0;
box-shadow: none;
```

Placeholder:

```css
color: rgba(255, 255, 255, 0.30);
```

Placeholder copy:

`Enter YouTube URL…`

Input icon:

- Lucide `Clapperboard`

- Size: `20px`

- Color: `#ff3d6b`

---

10\. Primary Button

Text:

`Get Video Transcript`

Icon:

- Lucide `ArrowUpRight`

- Size: `16px`

Desktop:

```css
height: 56px;
width: auto;
padding-inline: 24px;
```

Mobile:

```css
height: 48px;
width: 100%;
```

Shared:

```css
border: 0;
border-radius: 18px;
font-size: 15px;
font-weight: 600;
color: #ffffff;

box-shadow: 0 10px 35px rgba(183, 48, 255, 0.25);
```

Button text must always be white.

Never use dark text over the purple/pink gradient.

Loading state:

- Show a spinning `LoaderCircle`

- Initial copy: `Getting transcript…`

- Audio fallback copy: `Creating transcript from audio…`

---

11\. Error Message

Container:

```css
margin-top: 16px;
width: 100%;
max-width: 768px;
padding: 16px 20px;
border-radius: 16px;

border: 1px solid rgba(248, 113, 113, 0.20);
background: rgba(248, 113, 113, 0.08);
color: #fee2e2;

font-size: 14px;
line-height: 24px;
text-align: left;
```

Tone:

- Brief

- Friendly

- Slightly cheeky

- Never blame the user

- Immediately offer the next step

Preferred message structure:

1. Small playful acknowledgment

2. Explain that the link did not cooperate

3. Give the next action

Example:

`Whoops. That link said nope. Let’s try another way. Upload the file and we’ll see if that works.`

---

12\. “How It Works” Section

Background:

```css
background: #0d0d10;
border-top: 1px solid rgba(255, 255, 255, 0.06);
```

Padding:

```css
/* Mobile */
padding: 48px 20px 96px;

/* Desktop */
padding: 72px 32px 144px;
```

The distance between `Quick and simple. No catch.` and `How it works` must remain compact. Do not restore large Tactiq-style empty space.

Heading:

`How it works`

Steps:

1. `Copy the YouTube URL`

2. `Paste the URL above`

3. `View the YouTube transcript`

Desktop:

```css
display: grid;
grid-template-columns: repeat(3, 1fr);
gap: 48px;
margin-top: 64px;
```

Mobile:

```css
display: grid;
grid-template-columns: 1fr;
gap: 40px;
```

Step number circle:

```css
width: 48px;
height: 48px;
margin-inline: auto;
border-radius: 999px;
background: #ffffff;
color: #000000;

font-size: 18px;
font-weight: 700;
```

Step title:

```css
margin-top: 28px;
font-size: 20px;
font-weight: 600;
```

Step description:

```css
margin-top: 16px;
font-size: 14px;
line-height: 28px;
color: rgba(255, 255, 255, 0.50);
```

---

13\. Transcript Results Area

Switch from the dark landing-page background to a warm light workspace.

Section:

```css
background: #f7f6f3;
color: #171719;
border-top: 1px solid rgba(255, 255, 255, 0.07);
```

Main result card:

```css
background: #ffffff;
border: 1px solid rgba(0, 0, 0, 0.08);
border-radius: 28px;
overflow: hidden;

box-shadow: 0 24px 70px rgba(33, 25, 43, 0.08);
```

Result header padding:

```css
/* Mobile */
padding: 20px;

/* Desktop */
padding: 28px;
```

Video thumbnail:

```css
width: 192px;
aspect-ratio: 16 / 9;
border-radius: 16px;
overflow: hidden;
background: #18181b;
```

On mobile, make the thumbnail full width.

Success label:

```css
font-size: 11px;
font-weight: 700;
text-transform: uppercase;
letter-spacing: 0.16em;
color: #047857;
```

Text:

`Transcript ready`

Video title:

```css
font-size: 24px;
font-weight: 600;
line-height: 28px;
letter-spacing: -0.02em;
```

Mobile:

```css
font-size: 20px;
```

---

14\. Transcript Toolbar

Toolbar:

```css
position: sticky;
top: 0;
z-index: 20;

background: rgba(255, 255, 255, 0.95);
backdrop-filter: blur(24px);
border-bottom: 1px solid rgba(0, 0, 0, 0.07);
```

Download buttons:

```css
border: 1px solid #d4d4d8;
background: #ffffff;
color: #000000;
border-radius: 12px;
```

Hover:

```css
background: #f4f4f5;
color: #000000;
```

Formats:

- TXT

- MD

- SRT

Copy button:

```css
background: #000000;
color: #ffffff;
border-radius: 12px;
```

Hover:

```css
background: #27272a;
color: #ffffff;
```

Never allow low-contrast button text.

Contrast rules:

- White button means black text

- Black button means white text

- Gradient button means white text

---

15\. Transcript Text

Transcript content width:

```css
max-width: 896px;
margin-inline: auto;
```

Padding:

```css
/* Mobile */
padding: 32px 20px;

/* Desktop */
padding: 48px 40px;
```

Transcript paragraphs:

```css
font-size: 17px;
line-height: 32px;
color: #3f3f46;
```

Mobile:

```css
font-size: 16px;
```

Timestamp layout on desktop:

```css
display: grid;
grid-template-columns: 72px 1fr;
gap: 24px;
```

Timestamp pill:

```css
padding: 6px 10px;
border-radius: 8px;
background: #f0ebf4;
color: #7d21c8;

font-family: monospace;
font-size: 12px;
font-weight: 600;
```

Timestamp hover:

```css
background: #e6d9ef;
```

---

16\. FAQ Section

Background:

```css
background: #f7f6f3;
color: #171719;
```

Padding:

```css
/* Mobile */
padding: 96px 20px;

/* Desktop */
padding: 144px 32px;
```

FAQ items:

```css
border-color: rgba(0, 0, 0, 0.10);
```

Question:

```css
padding-block: 24px;
font-size: 16px;
color: #000000;
```

Answer:

```css
padding-bottom: 24px;
max-width: 768px;
line-height: 28px;
color: #52525b;
```

---

17\. Footer

```css
padding: 28px 20px;
border-top: 1px solid rgba(255, 255, 255, 0.06);

font-size: 12px;
text-align: center;
color: rgba(255, 255, 255, 0.30);
```

The `epic.media` link:

```css
color: rgba(255, 255, 255, 0.55);
text-underline-offset: 4px;
```

Hover:

```css
color: #ffffff;
text-decoration: underline;
```

---

18\. Border Radius System

```css
--radius-small: 8px;
--radius-button: 12px;
--radius-logo: 12px;
--radius-alert: 16px;
--radius-primary-button: 18px;
--radius-input-container: 24px;
--radius-result-card: 28px;
--radius-pill: 999px;
```

Do not make every element a pill.

Use full pills only for:

- Small badges

- Step numbers

- Status indicators

---

19\. Shadows

Glass form:

```css
box-shadow: 0 30px 100px rgba(0, 0, 0, 0.35);
```

Primary CTA:

```css
box-shadow: 0 10px 35px rgba(183, 48, 255, 0.25);
```

Result card:

```css
box-shadow: 0 24px 70px rgba(33, 25, 43, 0.08);
```

Logo glow:

```css
box-shadow: 0 0 40px rgba(242, 16, 165, 0.22);
```

Shadows should be soft and diffused. Avoid hard gray drop shadows.

---

20\. Icons

Use Lucide icons.

Approved icons:

- Brand: `AudioLines`

- URL input: `Clapperboard`

- Submit: `ArrowUpRight`

- Loading: `LoaderCircle`

- Copy: `Clipboard`

- Success: `Check`

- Download: `Download`

- Video: `Play`

- Reset: `RotateCcw`

- Back: `ArrowLeft`

Icon style:

- Clean outline

- Usually 16px to 20px

- Medium stroke

- No colorful emoji

- No mixed icon libraries

---

21\. Motion

Use motion sparingly.

Allowed:

- Button background transition

- Thumbnail scale to `1.03` on hover

- Icon opacity changes

- Smooth scroll to transcript results

- Loading spinner

- Toast notifications

Typical duration:

```css
transition-duration: 200ms to 300ms;
```

Respect reduced-motion preferences:

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
```

---

22\. Responsive Behavior

Breakpoints:

```css
--mobile: below 640px;
--tablet: 640px and above;
--desktop: 768px and above;
--large-desktop: 1024px and above;
```

Mobile requirements:

- No horizontal scrolling

- Input and CTA stack vertically

- CTA becomes full width

- Transcript toolbar buttons remain easy to tap

- Download buttons appear in a three-column row

- Copy button spans the full row

- Video thumbnail becomes full width

- How It Works steps become one column

- Hero headline remains readable at approximately 48px

- Minimum supported viewport width: 320px

---

23\. Accessibility

Required:

- Minimum 4.5:1 contrast for normal text

- White text on gradient buttons

- White text on black buttons

- Black text on white buttons

- Visible keyboard focus states

- Semantic headings

- Every input has a label

- Icon-only actions have accessible labels

- Alerts use `role="alert"`

- Do not use color as the only success or error signal

- Minimum touch target near 44px

- Respect reduced-motion settings

---

24\. Copy Style

Copy should sound:

- Casual

- Clear

- Confident

- Helpful

- Slightly cheeky

- Human

- Brief

Write like a smart friend helping you fix something.

Avoid:

- Corporate customer-service language

- Technical jargon

- Long explanations

- Fake enthusiasm

- Over-apologizing

- Em dashes

- Blaming the user

Preferred pattern:

1. Say what happened in plain English

2. Add one light, playful line

3. Give the easiest next step

Example:

`Whoops. That link said nope. Let’s try another way. Upload the file and we’ll see if that works.`

---

25\. Non-Negotiable Design Rules

 1. Keep the transcript field in the first viewport.

 2. Keep the hero close to the navigation.

 3. Do not add a login or signup gateway.

 4. Do not use excessive empty space.

 5. Do not put a giant marketing section before the tool.

 6. Maintain white text on gradient buttons.

 7. Maintain black text on white buttons.

 8. Maintain white text on black buttons.

 9. Keep the black, purple, pink, and warm-white palette.

10. Preserve the exact name `EPIC Transcript Machine`.

11. Preserve `Powered by epic.media`.

12. Prioritize speed and clarity over decoration.

13. The interface should feel premium without becoming complicated.

14. Every error state must offer a useful next step.

15. Desktop and mobile must feel intentionally designed, not merely resized.

---

26\. Hermes Implementation Instruction

Use this document as the visual source of truth.

Do not reinterpret it into a generic SaaS template. Preserve the existing EPIC Transcript Machine silhouette, palette, spacing, typography, contrast, and responsive behavior.

When adding Phase 1, Phase 2, or Phase 3 features:

- Reuse these design tokens.

- Keep the transcript form as the primary action.

- Place advanced features after the transcript succeeds.

- Do not clutter the initial page.

- Match all new cards, buttons, alerts, loading states, upload controls, summaries, and analysis tools to this system.

- Test desktop and mobile layouts.

- Verify button contrast in every state.

- Verify the primary workflow before calling the work complete. @Hermes