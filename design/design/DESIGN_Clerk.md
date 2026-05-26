## Overview

This design system is a premium fusion of **Clerk.com's clean SaaS card layout**, **shadcn/ui's atomic CSS variable architecture (HSL format)**, and **Radix UI Colors' 12-step semantic scale**. 

It is designed for modern, high-contrast web applications that require strict layout precision, accessible focus indicator rings, and a refined professional tone. The system maintains the original **Primary Blue** (#175cd3) as its central brand color, mapped onto shadcn/ui variables and the Radix 12-step color scale.

**Key Characteristics:**
- **shadcn/ui CSS Variables** — uses raw HSL variables (`--primary`, `--background`, `--border`, etc.) to control elements natively in Tailwind CSS.
- **Radix UI 12-Step Scale** — utilizes a structured 12-step gray and blue scale to organize backgrounds, borders, hover states, and typography.
- **Original Blue Accent** — maintains the trustworthy Primary Blue (`#175cd3`) as `Radix Blue 9` (Solid primary) and `--primary`.
- **Soft Shadows & Card Elevation** — pages utilize the diffuse, clean shadows inspired by Clerk.com.
- **Compact Rounding** — default card rounding matches shadcn/ui specifications (`0.5rem` to `0.75rem`).

---

## Colors & Design Tokens

### 1. shadcn/ui HSL Variables (Base System)
Tailwind CSS utilizes these values via CSS variables. Colors are defined in HSL format without the `hsl()` wrapper.

| Variable | HSL Value | Hex Equivalent | Description |
| :--- | :--- | :--- | :--- |
| `--background` | `210 20% 98%` | `#fafafa` (off-white) | Default page background |
| `--foreground` | `222.2 47.4% 11.2%` | `#09090b` (zinc-950) | Default primary body text |
| `--card` | `0 0% 100%` | `#ffffff` (pure white) | Card & container background |
| `--card-foreground` | `222.2 47.4% 11.2%` | `#09090b` | Card title and body text |
| `--primary` | `217.7 80.3% 45.9%` | `#175cd3` (Primary Blue) | Primary button background, active tab indicator |
| `--primary-foreground` | `210 20% 98%` | `#ffffff` | Text on top of primary colors |
| `--muted` | `210 40% 96.1%` | `#f1f5f9` (slate-100) | Secondary tabs or inactive backgrounds |
| `--muted-foreground` | `215.4 16.3% 46.9%` | `#64748b` (slate-500) | Helper text, subtitles, and metadata |
| `--border` | `240 5.9% 90%` | `#e4e4e7` (zinc-200) | Outer container borders and dividers |
| `--input` | `240 5.9% 90%` | `#e4e4e7` (zinc-200) | Input field default border |
| `--ring` | `217.7 80.3% 45.9%` | `#175cd3` | Focus indicator ring outline |

### 2. Semantic Colors
| Variable / Token | HSL Value | Hex Value | Usage / Role |
| :--- | :--- | :--- | :--- |
| `--success` | `142.1 76.2% 36.3%` | `#16a34a` | Verified, approved, and authenticated states |
| `--error` / `--destructive` | `0 84.2% 60.2%` | `#dc2626` | Auth errors, invalid input, delete actions |
| `--warning` | `35.2 91.5% 44.1%` | `#d97706` | Session expiry, pending leaves, warnings |

---

### 3. Radix UI Blue 12-Step Scale
A highly structured scale representing progressive light-mode contrast steps. The **original blue tone (#175cd3)** anchors the solid primary action step (Step 9).

| Step | Hex Value | Semantic Role / Description |
| :--- | :--- | :--- |
| **Blue 1** | `#f8faff` | App background (Canvas base) |
| **Blue 2** | `#f0f4ff` | Subtle background (Hover states on list tables, inactive tabs) |
| **Blue 3** | `#e1ebff` | UI component background (Selected tabs, secondary action buttons) |
| **Blue 4** | `#cedeff` | UI component hover (Hover state for selected tabs/buttons) |
| **Blue 5** | `#b8d1ff` | UI component border |
| **Blue 6** | `#99bdff` | Subtle border |
| **Blue 7** | `#7da3ff` | Stronger border (Active interactive element outlines) |
| **Blue 8** | `#eff8ff` | Focus outline aura (Light blue focus background glow) |
| **Blue 9** | `#175cd3` | **Solid Primary Background** (CTA button default background) |
| **Blue 10** | `#1248a8` | **Solid Primary Hover** (CTA button hover background) |
| **Blue 11** | `#0052cc` | Low-contrast text (Primary color text links, text-on-light badges) |
| **Blue 12** | `#002566` | High-contrast text (Emphasized headings in blue boxes) |

---

## Typography

| Role | Family | Size | Weight | Line Height | Letter Spacing |
|------|--------|------|--------|-------------|----------------|
| Display | Inter | 48px | 700 | 1.1 | -0.03em |
| Heading | Inter | 32px | 600 | 1.2 | -0.02em |
| Body | Inter | 16px | 400 | 1.6 | 0 |
| Label | Inter | 13px | 500 | 1.4 | 0 |
| Caption | Inter | 12px | 400 | 1.4 | 0.01em |

---

## Spacing System

The system uses standard base-4 spacing tokens to guide form layout structure and padding rhythm.

| Token | CSS / Rem | Pixel Value | Usage |
|-------|-----------|-------------|-------|
| `space-1` | `0.25rem` | 4px | Inline gaps (icon-to-text, micro-margins) |
| `space-2` | `0.5rem` | 8px | Field gaps (input labels, date separators) |
| `space-4` | `1rem` | 16px | Form spacing (between adjacent inputs/rows) |
| `space-6` | `1.5rem` | 24px | Default card padding, calendar list gaps |
| `space-8` | `2rem` | 32px | Modal container inner padding |

---

## Elevation & Depth

By using shadcn/ui and Clerk-like soft shadows, this system provides visual separation without harsh dark blocks.

| Token / Level | CSS Treatment | Usage Example |
|---|---|---|
| **Level 0 (Flat)** | `border: 1px solid var(--border); box-shadow: none` | Main calendar grid cells, nested tables |
| **`shadow-sm`** | `box-shadow: 0 1px 3px rgba(0,0,0,0.05)` | Form text inputs, default layout buttons |
| **`shadow-md`** | `box-shadow: 0 4px 16px rgba(23,92,211,0.08)` | Dropdowns, popovers, auth cards (blue tinted) |
| **`shadow-lg`** | `box-shadow: 0 12px 40px rgba(0,0,0,0.12)` | Interactive modals, floating action banners |
| **Active Focus** | `border-color: var(--primary); box-shadow: 0 0 0 3px #eff8ff` | Active input field highlight |

---

## Shapes (Border Radius)

The rounding scale matches modern Tailwind CSS systems using responsive rem values anchored by `--radius`.

| Token | Value | Custom Mapping (SHIM) | Use |
|-------|-------|-----------------------|-----|
| `radius-sm` | `6px` | `calc(var(--radius) - 2px)` | Form inputs, selection dropdowns, buttons |
| `radius-md` | `10px` | `var(--radius)` | Action buttons, dashboard widgets |
| `radius-lg` | `16px` | `calc(var(--radius) + 8px)` | Main application cards, dialog modals |
| `radius-full`| `9999px`| `9999px` | User avatar circles, pill status badges |

---

## Components

### 1. Sign In Card (Auth / Login)
- **Structure**: Centered panel, pure white background (`var(--card)`), rounded `radius-lg` (16px) with `shadow-md`.
- **Fields**: Input fields styled with `radius-sm` (6px) and `shadow-sm`, with label text set to `13px` weight 500.
- **Button**: Primary Blue button (`#175cd3`) with `radius-sm` (6px).
- **Footer**: Centered caption text stating system version and secure branding.

### 2. User Button (Profile Dropdown GNB)
- **Structure**: Avatar circle using `radius-full`, clicking opens a dropdown.
- **Dropdown**: Floating panel with `radius-md` (10px) and `shadow-md`, bordered by `var(--border)`.
- **Content**: Displays name (weight 600) and email/role (muted-foreground, 12px), followed by a "로그아웃" or "비밀번호 변경" button.

### 3. Buttons
- **`button-primary`** — Main CTA action.
  - Background: `var(--primary)` (#175cd3), Text: `var(--primary-foreground)` (#ffffff).
  - Hover: Background `var(--primary-hover)` (#1248a8).
  - Rounded: `radius-sm` (6px), Padding: `10px 16px`, Shadow: `shadow-sm`.
- **`button-secondary`** — Clean bordered secondary action.
  - Background: `var(--card)` (#ffffff), Text: `var(--foreground)` (#09090b), Border: `1px solid var(--border)` (#e4e4e7).
  - Hover: Background `var(--muted)` (#f1f5f9).
  - Rounded: `radius-sm` (6px), Padding: `10px 16px`.

---

## Do's and Don'ts

### Do
- Maintain generous card layout padding (`space-6` / 24px minimum) to keep forms legible and breathing.
- Define layout structures using Tailwind semantic tokens: `border-border`, `bg-background`, `text-foreground`.
- Follow the Radix 12-Step hierarchy for state changes (e.g., table list row hover = `bg-blue-2`).
- Pair active inputs with a high-visibility, soft light-blue halo (`#eff8ff`).

### Don't
- Don't use raw hex codes directly in HTML components. Always reference CSS variables.
- Don't use pitch black shadows. Shadows must remain extremely diffuse (`rgba(0, 0, 0, 0.02~0.04)`).
- Don't reduce auth form padding below `space-6` (24px) under any circumstances.
- Don't mix sharp corners (`rounded-none`) with rounded elements. Maintain shape consistency.
- Don't use saturated blue tints for non-interactive backgrounds.
