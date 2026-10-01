// Geometry shared by every strip chart, so their x-axes line up exactly.

export interface Band { label: string; from: number; to: number }

export const MARGIN = { left: 58, right: 20, top: 26 }

/** Maps a time onto the plot's horizontal pixels. */
export function xScale(width: number, domain: [number, number]) {
  const plotWidth = Math.max(width - MARGIN.left - MARGIN.right, 1)
  return (t: number) =>
    MARGIN.left + (t - domain[0]) / (domain[1] - domain[0]) * plotWidth
}
