import type { ActivePage } from '../catalog/config'

interface CatalogEmptyStateProps {
  activePage: ActivePage
  pageTitle: string
  onBrowseCatalog: () => void
}

export function CatalogEmptyState({ activePage, pageTitle, onBrowseCatalog }: CatalogEmptyStateProps) {
  if (activePage === 'catalog') {
    return (
      <div className="empty-state">
        <p>No games match these filters.</p>
        <button type="button" className="apply-button" onClick={onBrowseCatalog}>
          Reset filters
        </button>
      </div>
    )
  }

  const hint = activePage === 'suggestions'
    ? 'Suggestions exclude games you have played, liked, or saved — browse the catalog to get started.'
    : 'Add games with the action icons on any game card.'

  return (
    <div className="empty-state">
      <p>{activePage === 'suggestions' ? 'Nothing to suggest yet.' : `No games in ${pageTitle} yet.`}</p>
      <p className="empty-hint">{hint}</p>
      <button type="button" className="apply-button" onClick={onBrowseCatalog}>
        Browse the catalog
      </button>
    </div>
  )
}
