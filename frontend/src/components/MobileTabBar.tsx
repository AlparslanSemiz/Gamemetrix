import { Info, LogIn, MoreHorizontal, Settings, UserRound } from 'lucide-react'
import { mobileNavItems, type ActivePage, type MainPage, type UtilityPage } from '../catalog/config'

interface MobileTabBarProps {
  activePage: ActivePage
  activePreset: string | null
  isSignedIn: boolean
  moreOpen: boolean
  onOpenAccount: () => void
  onOpenMainPage: (id: MainPage) => void
  onOpenUtilityPage: (id: UtilityPage) => void
  onToggleMore: () => void
}

export function MobileTabBar({
  activePage,
  activePreset,
  isSignedIn,
  moreOpen,
  onOpenAccount,
  onOpenMainPage,
  onOpenUtilityPage,
  onToggleMore,
}: MobileTabBarProps) {
  return (
    <nav className="mobile-tabbar" aria-label="Mobile navigation">
      {mobileNavItems.map(({ icon: Icon, id, label }) => (
        <button
          type="button"
          className={activePage === id && (id !== 'catalog' || activePreset === null) ? 'is-active' : ''}
          key={id}
          onClick={() => {
            if (id === 'alerts') onOpenUtilityPage(id)
            else onOpenMainPage(id)
          }}
        >
          <Icon size={20} aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
      <button
        type="button"
        className={moreOpen ? 'is-active' : ''}
        onClick={onToggleMore}
        aria-expanded={moreOpen}
      >
        <MoreHorizontal size={20} aria-hidden="true" />
        <span>More</span>
      </button>
      {moreOpen ? (
        <div className="mobile-more-menu">
          <button type="button" onClick={onOpenAccount}>
            {isSignedIn ? <UserRound size={18} /> : <LogIn size={18} />}{isSignedIn ? 'Account' : 'Login'}
          </button>
          <button type="button" onClick={() => onOpenUtilityPage('settings')}><Settings size={18} />Settings</button>
          <button type="button" onClick={() => onOpenUtilityPage('about')}><Info size={18} />About</button>
        </div>
      ) : null}
    </nav>
  )
}
