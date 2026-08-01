import { Outlet, useLocation } from 'react-router-dom'

import { AmbientGlow } from '../ambient/AmbientGlow'
import { StarField } from '../ambient/StarField'
import { Sidebar } from './Sidebar'

export function AppShell() {
  const { pathname } = useLocation()

  return (
    <div className="relative flex h-dvh overflow-hidden bg-base">
      <AmbientGlow />
      <StarField />

      <Sidebar />

      {/* `key` on the scroll container restarts the reveal sequence per route
          and resets scroll position, so each page arrives rather than
          appearing mid-scroll. */}
      <main key={pathname} className="relative z-10 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1400px] px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

export function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <header className="mb-7 flex items-start justify-between gap-6">
      <div>
        {eyebrow && (
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-ghost">
            {eyebrow}
          </p>
        )}
        <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-ink">
          {title}
        </h1>
        {subtitle && <p className="mt-1.5 max-w-[62ch] text-[13.5px] text-ink-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  )
}
