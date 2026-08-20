// Shared lucide-react sizing/stroke, so every icon in the app reads as
// part of one deliberate scale instead of a size and stroke weight
// picked ad hoc per use site. Sizes tie into the spacing scale
// (tokens.css) -- lg == --space-32.
export const ICON_SIZE = {
  sm: 14, // inline with small text/buttons (Replace roster)
  md: 18, // step badges, secondary icons
  lg: 32, // a standalone focal icon (the dropzone)
}

export const ICON_STROKE_WIDTH = 1.75
