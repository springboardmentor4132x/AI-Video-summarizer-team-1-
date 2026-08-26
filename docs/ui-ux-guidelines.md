# UI/UX & Design System Guidelines

## Core Design Philosophy
This application must look custom, premium, and production-ready. We are explicitly avoiding generic, out-of-the-box UI component looks. The interface will be heavily stylized, immersive (Dark Mode default), and animated.

## Color Palette (Global Variables)
*   **Background (Base):** `#1E0539` (Deep Purple) - Used for the main app background.
*   **Surface/Cards:** `#DABCFA` (Lavender) - Used with high transparency (glassmorphism) for cards, sidebars, and elevated elements.
*   **Primary Accent:** `#73DDA6` (Mint) - Used for primary Call-to-Action (CTA) buttons, active states, and success indicators.
*   **Secondary Accent:** `#6BC7C5` (Teal) - Used for hover states, gradients (mixed with Mint), and data visualization.
*   **Highlight/Warning:** `#B76264` (Rose) - Used for delete actions, errors, or gamification badges.

## Animation & 3D Stack
To achieve high-performance transitions without dropping frames:
1.  **Framer Motion:** Mandatory for all page routing transitions, modal popups, and hover micro-interactions. No standard CSS transitions for complex layout shifts.
2.  **React Three Fiber:** To be used sparingly for specific hero-section 3D elements or loading states (e.g., a spinning 3D abstract object during video processing).
3.  **Glassmorphism:** Use CSS `backdrop-filter: blur(12px)` combined with our Lavender color at 10% opacity for a modern, depth-focused UI.

## Gamification & Engagement
*   **Processing States:** The transition from "Uploaded" to "Processing" to "Summarized" should be an interactive, visual journey (e.g., glowing progress rings, floating particles).
*   **Metrics:** The dashboard will feature "Time Saved" and "Insights Unlocked" counters that animate upwards when the user logs in.