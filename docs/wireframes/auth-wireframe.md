# Authentication Wireframes (Login & Register)

## Layout Structure (Split Screen)
**Inspiration:** Asymmetrical dark-mode agency layout.
**Global Background:** `#1E0539` (Deep Purple)

### Left Half (The 3D Hero Canvas)
*   **Component:** `ThreeJsCanvas`
*   **Visual:** A slow-rotating 3D abstract sphere or ribbon (using React Three Fiber).
*   **Lighting:** Tinted with `#73DDA6` (Mint) and `#6BC7C5` (Teal) point lights.
*   **Overlay Text:** Large, bold typography: "We Build Digital." or "Understand Video Instantly."

### Right Half (The Glassmorphic Form)
*   **Container:** `motion.div` floating slightly off the background.
*   **Styling:** 
    *   Background: `#DABCFA` (Lavender) at 5% opacity.
    *   Backdrop Blur: `backdrop-blur-xl`.
    *   Border: 1px solid `rgba(255,255,255,0.1)`.
    *   Border Radius: `rounded-[2.5rem]` (Extreme soft corners).
*   **Form Elements:**
    *   Inputs: Pill-shaped (`rounded-full`), floating labels.
    *   Submit Button: Solid `#73DDA6` (Mint), pill-shaped. On hover, the button scales up by 1.05x and casts a glowing box-shadow.