import { LogIn, UserRound } from 'lucide-react'
import {
  SIDEBAR_GROUPS,
  collectionNavItems,
  mainNavItems,
  utilityNavItems,
  type ActivePage,
  type CuratedPreset,
  type MainPage,
  type UtilityPage,
} from '../catalog/config'
import type { Collections } from '../state/collections'

interface SideRailProps {
  activePage: ActivePage
  activePreset: string | null
  collections: Collections
  isSignedIn: boolean
  onOpenAccount: () => void
  onOpenMainPage: (id: MainPage) => void
  onOpenPreset: (preset: CuratedPreset) => void
  onOpenUtilityPage: (id: UtilityPage) => void
}

export function SideRail({
  activePage,
  activePreset,
  collections,
  isSignedIn,
  onOpenAccount,
  onOpenMainPage,
  onOpenPreset,
  onOpenUtilityPage,
}: SideRailProps) {
  const isActiveNav = (id: string) => activePage === id && activePreset === null

  return (
    <aside className="side-rail" aria-label="Workspace navigation">
      <div className="rail-top">
        <div className="rail-group">
          {mainNavItems.map(({ icon: Icon, id, label }) => (
            <button
              type="button"
              className={isActiveNav(id) ? 'is-active' : ''}
              key={id}
              title={label}
              onClick={() => onOpenMainPage(id)}
            >
              <Icon size={22} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </div>
        <div>
          <div className="rail-divider" />
          <div className="rail-group rail-group-curated rail-group-lists">
            <span className="rail-section-label">My Lists</span>
            {collectionNavItems.map(({ icon: Icon, id, label }) => {
              const count = collections[id].length
              return (
                <button
                  type="button"
                  data-collection={id}
                  className={isActiveNav(id) ? 'is-active' : ''}
                  key={id}
                  title={label}
                  onClick={() => onOpenMainPage(id)}
                >
                  <Icon size={18} aria-hidden="true" />
                  <span>{label}</span>
                  {count > 0 ? <small>{count}</small> : null}
                </button>
              )
            })}
          </div>
        </div>
        {SIDEBAR_GROUPS.map((group) => (
          <div key={group.label}>
            <div className="rail-divider" />
            <div className="rail-group rail-group-curated">
              <span className="rail-section-label">{group.label}</span>
              {group.items.map((preset) => {
                const Icon = preset.icon
                return (
                  <button
                    type="button"
                    className={activePreset === preset.id ? 'is-active' : ''}
                    key={preset.id}
                    title={preset.label}
                    onClick={() => onOpenPreset(preset)}
                  >
                    <Icon size={18} aria-hidden="true" />
                    <span>{preset.label}</span>
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="rail-group rail-utility-group">
        <button type="button" title={isSignedIn ? 'Account' : 'Login'} onClick={onOpenAccount}>
          {isSignedIn ? <UserRound size={22} aria-hidden="true" /> : <LogIn size={22} aria-hidden="true" />}
          <span>{isSignedIn ? 'Account' : 'Login'}</span>
        </button>
        {utilityNavItems.map(({ icon: Icon, id, label }) => (
          <button
            type="button"
            className={activePage === id ? 'is-active' : ''}
            key={id}
            title={label}
            onClick={() => onOpenUtilityPage(id)}
          >
            <Icon size={22} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </div>
    </aside>
  )
}
