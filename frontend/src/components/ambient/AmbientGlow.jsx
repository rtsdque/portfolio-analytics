/**
 * Slow ambient wash behind the app.
 *
 * Two oversized radial gradients drifting on long, mismatched cycles. Only
 * `transform` animates — the gradients themselves are painted once and then
 * moved on the compositor, so this costs nothing per frame. Animating the
 * gradient stops instead would force a full repaint of a viewport-sized layer
 * on every tick, which is exactly where ambient effects usually go wrong.
 */
export function AmbientGlow() {
  return (
    <div
      data-ambient
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      <span className="ambient-orb ambient-orb--violet" />
      <span className="ambient-orb ambient-orb--gilt" />
    </div>
  )
}
