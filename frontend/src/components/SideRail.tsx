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

interface MainNavigationProps {
  activePage: ActivePage
  activePreset: string | null
  onOpenMainPage: (id: MainPage) => void
}

function MainNavigation({
  activePage,
  activePreset,
  onOpenMainPage,
}: MainNavigationProps) {
  const isActive = (id: string) => activePage === id && activePreset === null
  return (
    <>
      <div className="rail-group">
        {mainNavItems.map(({ icon: Icon, id, label }) => (
          <button type="button" className={isActive(id) ? 'is-active' : ''} key={id} title={label} onClick={() => onOpenMainPage(id)}>
            <Icon size={22} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </div>
    </>
  )
}

function CollectionNavigation({
  activePage,
  activePreset,
  collections,
  onOpenMainPage,
}: MainNavigationProps & { collections: Collections }) {
  return (
    <div>
      <div className="rail-divider" />
      <div className="rail-group rail-group-curated rail-group-lists">
        <span className="rail-section-label">My Lists</span>
        {collectionNavItems.map(({ icon: Icon, id, label }) => {
          const count = collections[id].length
          const active = activePage === id && activePreset === null
          return (
            <button type="button" data-collection={id} className={active ? 'is-active' : ''} key={id} title={label} onClick={() => onOpenMainPage(id)}>
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
              {count > 0 ? <small>{count}</small> : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function CuratedNavigation({
  activePreset,
  onOpenPreset,
}: Pick<SideRailProps, 'activePreset' | 'onOpenPreset'>) {
  return SIDEBAR_GROUPS.map((group) => (
    <div key={group.label}>
      <div className="rail-divider" />
      <div className="rail-group rail-group-curated">
        <span className="rail-section-label">{group.label}</span>
        {group.items.map((preset) => {
          const Icon = preset.icon
          return (
            <button type="button" className={activePreset === preset.id ? 'is-active' : ''} key={preset.id} title={preset.label} onClick={() => onOpenPreset(preset)}>
              <Icon size={18} aria-hidden="true" />
              <span>{preset.label}</span>
            </button>
          )
        })}
      </div>
    </div>
  ))
}

function UtilityNavigation({
  activePage,
  isSignedIn,
  onOpenAccount,
  onOpenUtilityPage,
}: Pick<
  SideRailProps,
  'activePage' | 'isSignedIn' | 'onOpenAccount' | 'onOpenUtilityPage'
>) {
  return (
    <div className="rail-group rail-utility-group">
      <button type="button" title={isSignedIn ? 'Account' : 'Login'} onClick={onOpenAccount}>
        {isSignedIn ? <UserRound size={22} aria-hidden="true" /> : <LogIn size={22} aria-hidden="true" />}
        <span>{isSignedIn ? 'Account' : 'Login'}</span>
      </button>
      {utilityNavItems.map(({ icon: Icon, id, label }) => (
        <button type="button" className={activePage === id ? 'is-active' : ''} key={id} title={label} onClick={() => onOpenUtilityPage(id)}>
          <Icon size={22} aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </div>
  )
}

export function SideRail(props: SideRailProps) {
  return (
    <aside className="side-rail" aria-label="Workspace navigation">
      <div className="rail-top">
        <MainNavigation {...props} />
        <CollectionNavigation {...props} />
        <CuratedNavigation {...props} />
      </div>
      <UtilityNavigation {...props} />
    </aside>
  )
}
