import { NavLink } from 'react-router-dom'

import { usePortfolio } from '../../state/PortfolioContext'
import { IconAnalytics, IconCredit, IconPortfolio } from './Icons'

const NAV = [
  { to: '/', label: 'Portfolio', Icon: IconPortfolio, end: true },
  { to: '/analytics', label: 'Analytics', Icon: IconAnalytics },
  { to: '/credit', label: 'Credit Lab', Icon: IconCredit },
]

function Mark() {
  return (
    <svg width="26" height="26" viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="mark" x1="0" y1="0" x2="32" y2="32">
          <stop stopColor="var(--color-accent-bright)" />
          <stop offset="1" stopColor="var(--color-accent-deep)" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#mark)" />
      <path
        d="M8 21.5l5.5-7 4 4L24 9.5"
        stroke="white"
        strokeWidth="2.25"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.95"
      />
    </svg>
  )
}

export function Sidebar() {
  const { holdings, isEmpty } = usePortfolio()

  return (
    /* Glass lives here and nowhere else: the sidebar is fixed chrome, so its
       backdrop blur is composited once instead of being recomputed for every
       row of a scrolling list. */
    <aside className="glass relative z-10 flex h-full w-[236px] shrink-0 flex-col border-r border-line-faint">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <Mark />
        <span className="text-[15px] font-semibold tracking-tight text-ink">Portfolio Analytics</span>
      </div>

      <nav className="px-3" aria-label="Main">
        <p className="px-2 pb-2 pt-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-ghost">
          Workspace
        </p>
        <ul className="flex flex-col gap-0.5">
          {NAV.map(({ to, label, Icon, end }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={end}
                className={({ isActive }) =>
                  [
                    'group relative flex items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-[13.5px] transition-colors duration-[--dur-quick]',
                    isActive
                      ? 'bg-surface-2 text-ink'
                      : 'text-ink-muted hover:bg-surface-1 hover:text-ink',
                  ].join(' ')
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      aria-hidden="true"
                      className={[
                        'absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full bg-accent-bright transition-opacity duration-[--dur-quick]',
                        isActive ? 'opacity-100' : 'opacity-0',
                      ].join(' ')}
                    />
                    <Icon className={isActive ? 'text-accent-bright' : 'text-ink-faint'} />
                    {label}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="mt-auto px-5 pb-5">
        <div className="rounded-[10px] border border-line-faint bg-surface-1/60 px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-ghost">
            Holdings
          </p>
          <p className="mt-1 text-[13px] text-ink-muted" data-numeric>
            {isEmpty ? 'None yet' : `${holdings.length} position${holdings.length === 1 ? '' : 's'}`}
          </p>
        </div>
        <p className="mt-3 text-[10.5px] leading-relaxed text-ink-ghost">
          Stored in this browser only. Nothing is sent to an account.
        </p>
      </div>
    </aside>
  )
}
