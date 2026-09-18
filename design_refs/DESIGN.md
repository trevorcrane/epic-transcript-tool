# EPIC Transcript Machine: Visual Design System

This file defines the visual language, layout rules, component styling, responsive behavior, and interaction standards for the product. It intentionally contains no page copy, marketing language, FAQ content, instructions, or feature requirements.

## 1. Visual Thesis

A fast, cinematic creator tool built around a near-black canvas, neon purple-to-pink energy, oversized editorial typography, translucent glass controls, and a warm off-white workspace for results.

The interface should feel:

- Premium but not corporate
- Bold but not busy
- Modern but not sterile
- Playful but not cartoonish
- Fast, obvious, and easy to operate

The primary working control must remain visible in the first viewport. Avoid oversized navigation, decorative clutter, and excessive empty space.

## 2. Design Tokens

### Color

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

### Gradients

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

### Typography

```css
--font-sans: "Avenir Next", Avenir, "SF Pro Display", "Segoe UI", Helvetica, Arial, sans-serif;
--font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
```

Use one sans-serif family throughout. Use monospace only for timestamps, technical values, or fixed-width metadata.

| Role | Mobile | Desktop | Weight | Line height | Tracking |
|---|---:|---:|---:|---:|---:|
| Display | 48px | 78px | 600 | 1.02 | -0.05em |
| Section title | 36px | 48px | 600 | 1.10 | -0.04em |
| Card title | 20px | 24px | 600 | 1.17 | -0.02em |
| Lead | 18px | 20px | 400 | 1.60 | normal |
| Body | 16px | 17px | 400 | 1.88 | normal |
| UI label | 14px | 14px | 500 | 1.40 | normal |
| Eyebrow | 11px | 11px | 700 | 1.00 | 0.24em |
| Badge | 10px | 10px | 600 | 1.00 | 0.18em |
| Timestamp | 12px | 12px | 600 | 1.00 | normal |

Headings should use tight tracking and restrained weight. Do not compensate with extra-bold weights.

### Spacing

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

### Radius

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

### Shadows

```css
--shadow-glass: 0 30px 100px rgba(0, 0, 0, 0.35);
--shadow-action: 0 10px 35px rgba(183, 48, 255, 0.25);
--shadow-card: 0 24px 70px rgba(33, 25, 43, 0.08);
--shadow-brand: 0 0 40px rgba(242, 16, 165, 0.22);
```

Shadows must be soft and diffused. Avoid hard gray shadows or stacked material-design elevation effects.

## 3. Layout System

### Widths

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

Minimum supported viewport width: `320px`.

### Vertical Rhythm

- Header vertical padding: 16px mobile, 20px desktop
- Header-to-hero spacing: 16px
- Display-to-lead spacing: 24px
- Lead-to-primary-control spacing: 48px
- Primary-control-to-helper spacing: 28px
- Keep the transition from the hero helper area into the next section compact
- Avoid adding large spacer bands between adjacent sections

### Section Padding

Dark instructional or supporting section:

```css
/* Mobile */
padding: 48px 20px 96px;

/* Desktop */
padding: 72px 32px 144px;
```

Light supporting section:

```css
/* Mobile */
padding: 96px 20px;

/* Desktop */
padding: 144px 32px;
```

## 4. Page Surfaces

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

## 5. Ambient Lighting

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

## 6. Brand Lockup

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

## 7. Primary Form Surface

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

Input placeholder opacity: `30%` white.

## 8. Buttons

### Primary Action

```css
height: 56px;
padding-inline: 24px;
border: 0;
border-radius: 18px;
background: linear-gradient(115deg, #7b2ff7 0%, #c22ffc 48%, #f107a3 100%);
box-shadow: var(--shadow-action);
color: #ffffff;
font-size: 15px;
font-weight: 600;
```

On mobile:

```css
width: 100%;
height: 48px;
```

### Secondary Light Action

```css
min-height: 36px;
border: 1px solid #d4d4d8;
border-radius: 12px;
background: #ffffff;
color: #000000;
```

Hover:

```css
background: #f4f4f5;
color: #000000;
```

### Strong Dark Action

```css
min-height: 36px;
border-radius: 12px;
background: #000000;
color: #ffffff;
```

Hover:

```css
background: #27272a;
color: #ffffff;
```

### Contrast Rules

- Gradient background: white text
- Black background: white text
- White background: black text
- Never allow inherited colors to reduce button contrast
- Disabled states must remain readable while clearly inactive
- Interactive targets should be at least 44px where practical

## 9. Alerts and Status

Alert container:

```css
width: 100%;
max-width: 768px;
margin-top: 16px;
padding: 16px 20px;
display: flex;
align-items: flex-start;
justify-content: space-between;
gap: 16px;
border: 1px solid var(--color-error-border);
border-radius: 16px;
background: var(--color-error-bg);
color: var(--color-error-text);
font-size: 14px;
line-height: 24px;
text-align: left;
```

Success status should combine a small colored marker with a compact uppercase label. Never rely on color alone to communicate state.

Loading states should retain the original component dimensions to prevent layout shift.

## 10. Result Card

```css
overflow: hidden;
border: 1px solid rgba(0, 0, 0, 0.08);
border-radius: 28px;
background: #ffffff;
box-shadow: var(--shadow-card);
```

Header padding:

```css
/* Mobile */
padding: 20px;

/* Desktop */
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

On mobile, media becomes full width. Use `object-fit: cover`. A hover state may scale the image to `1.03` over 300ms.

## 11. Sticky Result Toolbar

```css
position: sticky;
top: 0;
z-index: 20;
display: flex;
align-items: center;
justify-content: space-between;
gap: 12px;
padding: 16px 28px;
border-bottom: 1px solid rgba(0, 0, 0, 0.07);
background: rgba(255, 255, 255, 0.95);
backdrop-filter: blur(24px);
```

On mobile:

- Stack toolbar groups when needed
- Place small related actions in equal-width columns
- Allow the main action to span the full row
- Preserve comfortable touch targets

## 12. Transcript Reading Layout

```css
max-width: 896px;
margin-inline: auto;
padding: 48px 40px;
```

Mobile:

```css
padding: 32px 20px;
```

Timestamp row on desktop:

```css
display: grid;
grid-template-columns: 72px 1fr;
gap: 24px;
```

Timestamp badge:

```css
width: fit-content;
align-self: start;
padding: 6px 10px;
border-radius: 8px;
background: #f0ebf4;
color: #7d21c8;
font-family: var(--font-mono);
font-size: 12px;
font-weight: 600;
```

Hover background: `#e6d9ef`.

Body text:

```css
font-size: 17px;
line-height: 32px;
color: #3f3f46;
```

Use 16px body text on mobile. Paragraph groups should have 24px to 28px vertical separation.

## 13. Repeated Content Grid

Desktop:

```css
display: grid;
grid-template-columns: repeat(3, minmax(0, 1fr));
gap: 48px;
```

Mobile:

```css
grid-template-columns: 1fr;
gap: 40px;
```

Circular marker:

```css
width: 48px;
height: 48px;
margin-inline: auto;
display: grid;
place-items: center;
border-radius: 999px;
background: #ffffff;
color: #000000;
font-size: 18px;
font-weight: 700;
```

Keep repeated items visually clean. Do not wrap every item in an unnecessary card.

## 14. Accordion and Dividers

Light-section dividers:

```css
border-color: rgba(0, 0, 0, 0.10);
```

Dark-section dividers:

```css
border-color: rgba(255, 255, 255, 0.06);
```

Accordion trigger:

```css
padding-block: 24px;
font-size: 16px;
color: #000000;
```

Accordion body:

```css
max-width: 768px;
padding-bottom: 24px;
line-height: 28px;
color: #52525b;
```

Do not underline accordion labels on hover.

## 15. Icons

Use one consistent outline icon family. Lucide is preferred.

- Standard icon size: 16px
- Prominent control icon: 20px
- Default stroke: approximately 2px
- Brand icon stroke: approximately 2.35px
- Icons should support labels, not replace clear labels unnecessarily
- Avoid emoji and mixed icon families

## 16. Motion

Motion should make the interface feel responsive, not theatrical.

Allowed:

- 200ms to 300ms color and opacity transitions
- Subtle media scale to 1.03 on hover
- Smooth scrolling to newly available results
- Loading spinner rotation
- Compact toast entrance and exit

Avoid:

- Large parallax effects
- Continuous decorative animation
- Bouncing controls
- Layout-shifting hover effects
- Long entrance sequences

Reduced motion:

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

## 18. Accessibility

- Minimum 4.5:1 contrast for normal text
- Visible keyboard focus states
- Semantic heading hierarchy
- Programmatic labels for inputs and icon-only controls
- `role="alert"` for blocking failures
- State must not rely on color alone
- Target size near 44px or larger for primary touch controls
- Respect reduced-motion preferences
- Preserve readable contrast across default, hover, focus, disabled, loading, success, and error states

## 19. Design Guardrails

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

## 20. Implementation Rule

Treat this file as the visual source of truth. It defines appearance and interaction styling only. Product copy, instructions, labels, feature scope, data behavior, and business logic belong in separate specification files.
