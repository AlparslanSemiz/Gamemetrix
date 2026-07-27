import type { Game, PriceSnapshot } from '../../types/game'
import { trackProductEvent } from '../../services/analytics'
import { newestFetchedAt } from '../../utils/prices'
import { steamAppIdFromGame } from '../../utils/steam'
import { safeExternalUrl } from '../../utils/url'
import { formatDate, formatMoney } from './format'

const MS_PER_HOUR = 60 * 60 * 1000
const MS_PER_DAY = 24 * MS_PER_HOUR

// Snapshots up to a week old are shown rather than hidden, so the panel has to
// say how current they are.
function freshnessLabel(prices: PriceSnapshot[]): string | null {
  const newest = newestFetchedAt(prices)
  if (newest === null) return null
  const age = Date.now() - newest
  if (age < MS_PER_HOUR) return 'Updated just now'
  if (age < MS_PER_DAY) return `Updated ${Math.floor(age / MS_PER_HOUR)}h ago`
  const days = Math.floor(age / MS_PER_DAY)
  return `Updated ${days} day${days === 1 ? '' : 's'} ago`
}

function sortedPrices(prices: PriceSnapshot[]): PriceSnapshot[] {
  return [...prices].sort((a, b) => {
    const aPrice = a.sale_price ?? a.list_price ?? Number.POSITIVE_INFINITY
    const bPrice = b.sale_price ?? b.list_price ?? Number.POSITIVE_INFINITY
    return aPrice - bPrice
  })
}

function priceAmount(price: PriceSnapshot): number | null {
  if (price.is_free) return 0
  return price.sale_price ?? price.list_price ?? null
}

function storeSearchUrl(store: string, game: Game): string | null {
  const q = encodeURIComponent(game.title)
  const steamAppId = steamAppIdFromGame(game)
  if (store === 'Steam') return steamAppId ? `https://store.steampowered.com/app/${steamAppId}/` : `https://store.steampowered.com/search/?term=${q}`
  if (store === 'Epic Games Store') return `https://store.epicgames.com/browse?q=${q}&sortBy=relevancy&sortDir=DESC&count=40`
  if (store === 'GOG') return `https://www.gog.com/en/games?query=${q}`
  if (store === 'Xbox Store') return `https://www.xbox.com/search?q=${q}`
  if (store === 'PlayStation Store') return `https://store.playstation.com/search/${q}`
  if (store === 'Nintendo eShop') return `https://www.nintendo.com/search/#q=${q}&p=1&cat=gme`
  return null
}

const STORE_INITIALS: Record<string, string> = {
  Steam: 'ST',
  'Epic Games Store': 'EP',
  GOG: 'GOG',
  'Xbox Store': 'XB',
  'PlayStation Store': 'PS',
  'Nintendo eShop': 'NS',
  Fanatical: 'FN',
  GreenManGaming: 'GM',
  GameBillet: 'GB',
  GamersGate: 'GG',
}

function storeInitials(store: string): string {
  if (STORE_INITIALS[store]) return STORE_INITIALS[store]
  return store.split(/\s+/).map((part) => part[0]).join('').slice(0, 3).toUpperCase()
}

interface StoreOffer {
  id: string
  store: string
  platform: string
  priceLabel: string
  listLabel?: string
  meta: string
  url: string | null
  discount?: number | null
  amount: number | null
}

function buildStoreOffers(prices: PriceSnapshot[], game: Game): StoreOffer[] {
  const ordered = sortedPrices(prices)
  const byStore = new Map<string, StoreOffer>()

  ordered.forEach((price) => {
    const amount = priceAmount(price)
    const label = price.is_free ? 'Free' : amount === null ? 'N/A' : formatMoney(amount, price.currency)
    const key = price.store.toLowerCase()
    const offer: StoreOffer = {
      id: `${price.source}-${price.store}-${price.fetched_at}`,
      store: price.store,
      platform: price.platform ?? 'PC',
      priceLabel: label,
      listLabel: price.list_price !== null && price.list_price !== undefined ? formatMoney(price.list_price, price.currency) : undefined,
      meta: [price.source, price.region, 'Base game'].filter(Boolean).join(' · '),
      url: safeExternalUrl(price.url) ?? storeSearchUrl(price.store, game),
      discount: price.discount_percent,
      amount,
    }
    const existing = byStore.get(key)
    if (!existing || (amount ?? Number.POSITIVE_INFINITY) < (existing.amount ?? Number.POSITIVE_INFINITY)) {
      byStore.set(key, offer)
    }
  })

  return [...byStore.values()].sort((a, b) => (a.amount ?? Number.POSITIVE_INFINITY) - (b.amount ?? Number.POSITIVE_INFINITY))
}

function buildPricePanelModel(prices: PriceSnapshot[], game: Game) {
  const ordered = sortedPrices(prices)
  const offers = buildStoreOffers(prices, game)
  if (offers.length === 0) return null

  const best = ordered[0]
  const bestOffer = offers[0]
  const historicalLow = ordered
    .filter((price) => price.historical_low !== null && price.historical_low !== undefined)
    .sort((a, b) => (a.historical_low ?? Number.POSITIVE_INFINITY) - (b.historical_low ?? Number.POSITIVE_INFINITY))[0]
  const pricedTrackedOffers = offers.filter((offer) => offer.amount !== null)
  const highestCurrent = pricedTrackedOffers[pricedTrackedOffers.length - 1]
  const priceRange = offers.length > 1 && highestCurrent && bestOffer
    ? `${bestOffer.priceLabel} - ${highestCurrent.priceLabel}`
    : bestOffer?.priceLabel ?? 'N/A'
  const chartItems = [
    { label: 'List', value: best?.list_price ?? null, text: best ? formatMoney(best.list_price, best.currency) : 'N/A' },
    { label: 'Now', value: bestOffer?.amount ?? null, text: bestOffer?.priceLabel ?? 'N/A' },
    { label: 'Low', value: historicalLow?.historical_low ?? null, text: historicalLow ? formatMoney(historicalLow.historical_low, historicalLow.currency) : 'N/A' },
  ]
  const chartMax = Math.max(1, ...chartItems.map((item) => item.value ?? 0))
  return {
    best,
    bestOffer,
    chartItems,
    chartMax,
    current: bestOffer?.priceLabel ?? 'N/A',
    freshness: freshnessLabel(prices),
    hasDiscount: Boolean(best?.discount_percent && best.discount_percent > 0),
    historicalLow,
    offers,
    priceRange,
  }
}

type PricePanelModel = NonNullable<ReturnType<typeof buildPricePanelModel>>

function PriceOverview({ model }: { model: PricePanelModel }) {
  const {
    best,
    bestOffer,
    chartItems,
    chartMax,
    current,
    freshness,
    hasDiscount,
    historicalLow,
    offers,
    priceRange,
  } = model
  return (
    <>
      <div className="dp-price-top">
        <div className="dp-price-primary">
          <span>Best current price</span>
          <strong>{current}</strong>
          <small>
            {bestOffer?.store ?? 'Tracked stores'}
            {hasDiscount ? ` · ${best?.discount_percent}% off` : ''}
            {best?.region ? ` · ${best.region}` : ''}
          </small>
          {freshness ? <small className="dp-price-age">{freshness}</small> : null}
        </div>
        <div className="dp-price-chart" aria-label="Price comparison">
          {chartItems.map((item) => (
            <div key={item.label} className="dp-price-bar-row">
              <span>{item.label}</span>
              <div className="dp-price-bar"><i style={{ width: `${Math.max(8, ((item.value ?? 0) / chartMax) * 100)}%` }} /></div>
              <strong>{item.text}</strong>
            </div>
          ))}
        </div>
      </div>
      <div className="dp-price-meta">
        <div>
          <span>Price range</span>
          <strong>{priceRange}</strong>
        </div>
        <div>
          <span>Historical low</span>
          <strong>{historicalLow ? formatMoney(historicalLow.historical_low, historicalLow.currency) : 'N/A'}</strong>
          <small>{formatDate(historicalLow?.historical_low_date)}</small>
        </div>
        <div>
          <span>Stores</span>
          <strong>{offers.length}</strong>
          <small>priced stores</small>
        </div>
      </div>
    </>
  )
}

function StoreOfferList({ gameSlug, offers }: { gameSlug: string; offers: StoreOffer[] }) {
  return (
    <div className="dp-store-list">
      {offers.slice(0, 10).map((offer) => {
        const content = (
          <>
            <span className="dp-store-name">
              <i>{storeInitials(offer.store)}</i>
              <span>
                <strong>{offer.store}</strong>
                <small>{offer.platform}{offer.meta ? ` · ${offer.meta}` : ''}</small>
              </span>
            </span>
            <span className="dp-store-price">
              <strong>{offer.priceLabel}</strong>
              {offer.discount && offer.discount > 0 ? <small>-{offer.discount}%</small> : null}
            </span>
          </>
        )
        return offer.url ? (
          <a key={offer.id} href={offer.url} target="_blank" rel="noopener noreferrer" className="dp-store-row" onClick={() => trackProductEvent('store_outbound', { game_slug: gameSlug, store: offer.store })}>
            {content}
          </a>
        ) : (
          <div key={offer.id} className="dp-store-row">{content}</div>
        )
      })}
    </div>
  )
}

export function PricePanel({ prices, game }: { prices: PriceSnapshot[]; game: Game }) {
  const model = buildPricePanelModel(prices, game)
  if (!model) return null
  return (
    <div className="dp-price-panel">
      <PriceOverview model={model} />
      <StoreOfferList gameSlug={game.slug} offers={model.offers} />
    </div>
  )
}
