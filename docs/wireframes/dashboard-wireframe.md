# Dashboard Wireframe

## Layout Structure (Floating Bento-Box)
**Inspiration:** Soft, overlapping container UI.
**Global Background:** `#1E0539` (Deep Purple) with subtle radial gradients of `#6BC7C5` in the corners.

### 1. Left Sidebar (Floating Navigation)
*   **Styling:** Pill-shaped, completely detached from the left edge of the screen (floating).
*   **Active State:** Icons glow with `#73DDA6` (Mint) when selected.
*   **Animation:** Staggered slide-in from the left on page load using Framer Motion.

### 2. Main Content Area
*   **Header:** 
    *   Greeting: "Hey [User Name]!"
    *   Gamification: A small pill-badge showing "Hours Saved: 12.5" outlined in `#73DDA6`.
*   **Video Upload Zone (Top Center):**
    *   **Styling:** A massive, dashed-border squircle (`rounded-[3rem]`).
    *   **Interaction:** Drag-and-drop triggers a liquid/wave distortion effect (Framer Motion).
    *   **Processing State:** When a video is uploading, the container border animates with a glowing gradient of Mint and Teal circling the perimeter.

### 3. Right Sidebar (Recent Activity & Status)
*   **Cards:** Overlapping glassmorphic cards (Lavender at 10% opacity).
*   **Status Indicators:** Small pulsing dots. Green (`#73DDA6`) for Completed, Yellow for Processing, Red (`#B76264`) for Failed.