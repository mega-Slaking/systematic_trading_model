/**
 * ThemeToggle: a circular control in the header that switches the colour theme.
 *
 * Three icons sit on a circle 120° apart — sun (light), moon (dark), star
 * (contrast). The active mode's icon sits at the top (12 o'clock); the other two
 * are clickable. Clicking an icon brings it to the top by rotating the SHORTER
 * way, so the ring spins in whichever direction matches what you clicked — the
 * right-hand icon comes up counter-clockwise, the left-hand icon clockwise. Each
 * glyph counter-rotates to stay upright. Purely a colour control — see ThemeContext.
 */

import { useState } from "react";

import { useTheme, THEME_MODES, type ThemeMode } from "../theme/ThemeContext";

const STEP = 360 / THEME_MODES.length; // 120° between icons

const RING_DIAMETER = 52; // px — the circle
const ICON_RADIUS = 16; // px — how far each icon sits from the centre

const LABELS: Record<ThemeMode, string> = {
  light: "Light",
  dark: "Dark",
  contrast: "High contrast",
};

export function ThemeToggle() {
  const { mode, setMode } = useTheme();
  const activeIndex = THEME_MODES.indexOf(mode);

  // A *continuous* ring rotation (accumulates, so each move animates the short
  // way regardless of wrap-around). Glyphs counter-rotate by the same amount.
  const [rotation, setRotation] = useState(() => -activeIndex * STEP);

  function select(i: number) {
    if (i === activeIndex) return;
    // One step forward in array order (the lower-RIGHT icon) → rotate CCW (-STEP);
    // one step back (the lower-LEFT icon) → rotate CW (+STEP). This keeps the ring
    // consistent with the active mode while spinning the minimal, intuitive way.
    const forward = (i - activeIndex + THEME_MODES.length) % THEME_MODES.length === 1;
    setRotation((r) => r + (forward ? -STEP : STEP));
    setMode(THEME_MODES[i]);
  }

  return (
    <div
      role="group"
      aria-label={`Colour theme: ${LABELS[mode]}. Pick a theme.`}
      style={{
        position: "relative",
        width: RING_DIAMETER,
        height: RING_DIAMETER,
        flex: "0 0 auto",
        borderRadius: "50%",
        border: "1px solid var(--border-strong)",
        background: "var(--surface-raised)",
      }}
    >
      {/* A small notch marking the "active" slot at the top of the circle. */}
      <span
        aria-hidden
        style={{
          position: "absolute",
          top: 3,
          left: "50%",
          width: 4,
          height: 4,
          marginLeft: -2,
          borderRadius: "50%",
          background: "var(--accent)",
        }}
      />
      <span
        style={{
          position: "absolute",
          inset: 0,
          transform: `rotate(${rotation}deg)`,
          transition: "transform 0.55s cubic-bezier(0.34, 1.56, 0.64, 1)",
        }}
      >
        {THEME_MODES.map((m, i) => {
          const angle = i * STEP;
          const isActive = i === activeIndex;
          return (
            <button
              key={m}
              type="button"
              onClick={() => select(i)}
              title={isActive ? `Theme: ${LABELS[m]}` : `Switch to ${LABELS[m]}`}
              aria-label={isActive ? `${LABELS[m]} (current theme)` : `Switch to ${LABELS[m]} theme`}
              aria-pressed={isActive}
              style={{
                position: "absolute",
                left: "50%",
                top: "50%",
                width: 22,
                height: 22,
                padding: 0,
                border: "none",
                background: "transparent",
                // Place the (upright) icon box onto the circle.
                transform: `translate(-50%, -50%) rotate(${angle}deg) translateY(-${ICON_RADIUS}px) rotate(${-angle}deg)`,
                color: isActive ? "var(--accent)" : "var(--text-faint)",
                opacity: isActive ? 1 : 0.55,
                cursor: isActive ? "default" : "pointer",
                transition: "color 0.3s ease, opacity 0.3s ease",
              }}
            >
              {/* Counter-rotate the ring's spin so the glyph stays upright. */}
              <span
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: "100%",
                  height: "100%",
                  transform: `rotate(${-rotation}deg) scale(${isActive ? 1.1 : 0.85})`,
                  transition: "transform 0.55s cubic-bezier(0.34, 1.56, 0.64, 1)",
                }}
              >
                <ModeIcon mode={m} />
              </span>
            </button>
          );
        })}
      </span>
    </div>
  );
}

function ModeIcon({ mode }: { mode: ThemeMode }) {
  switch (mode) {
    case "light":
      return <SunIcon />;
    case "dark":
      return <MoonIcon />;
    case "contrast":
      return <StarIcon />;
  }
}

const SVG_PROPS = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function SunIcon() {
  return (
    <svg {...SVG_PROPS} aria-hidden>
      <circle cx="12" cy="12" r="4.2" />
      <line x1="12" y1="2.2" x2="12" y2="4.6" />
      <line x1="12" y1="19.4" x2="12" y2="21.8" />
      <line x1="2.2" y1="12" x2="4.6" y2="12" />
      <line x1="19.4" y1="12" x2="21.8" y2="12" />
      <line x1="5.1" y1="5.1" x2="6.8" y2="6.8" />
      <line x1="17.2" y1="17.2" x2="18.9" y2="18.9" />
      <line x1="18.9" y1="5.1" x2="17.2" y2="6.8" />
      <line x1="6.8" y1="17.2" x2="5.1" y2="18.9" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg {...SVG_PROPS} aria-hidden>
      <path d="M20 14.5A8 8 0 1 1 9.5 4a6.2 6.2 0 0 0 10.5 10.5z" fill="currentColor" stroke="none" />
    </svg>
  );
}

function StarIcon() {
  return (
    <svg {...SVG_PROPS} aria-hidden>
      <path
        d="M12 2.6l2.7 5.9 6.4.7-4.8 4.3 1.3 6.3L12 16.8 6.2 20.1l1.3-6.3L2.7 9.5l6.4-.7z"
        fill="currentColor"
        stroke="none"
      />
    </svg>
  );
}
