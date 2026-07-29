import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import type { CatalogSnapshot } from './snapshot'

// Masthead auto-hide tuning: the header only reacts once the user has scrolled
// a sustained distance in one direction, so small jitters never toggle it.
const MASTHEAD_ALWAYS_VISIBLE_Y = 96
const MIN_SCROLL_DELTA = 1
const HIDE_DISTANCE = 64
const SHOW_DISTANCE = 42

// Scroll-to-top animation
const TOP_SCROLL_MIN_MS = 420
const TOP_SCROLL_MAX_MS = 1200
const TOP_SCROLL_MS_PER_PX = 0.4
const TOP_SCROLL_INTERRUPT_EVENTS = ['wheel', 'touchstart', 'pointerdown', 'keydown'] as const

export interface CatalogScroll {
  /** Whether the masthead is currently expanded. */
  mastheadVisible: boolean
  /** Mirrors `mastheadVisible` without triggering re-renders — safe to read in effects. */
  mastheadVisibleRef: RefObject<boolean>
  /** Last scroll position seen by a real scroll event, not clamped by DOM teardown. */
  lastScrollYRef: RefObject<number>
  mastheadRef: RefObject<HTMLElement | null>
  /** Set masthead visibility directly (search focus, snapshot restore), keeping ref and state in sync. */
  setMastheadVisibility: (next: boolean) => void
  /** Eased scroll back to the top; any user input cancels it. */
  scrollToTop: () => void
}

export function useCatalogScroll(initialSnapshot: CatalogSnapshot | null = null): CatalogScroll {
  const initialMastheadVisible = initialSnapshot?.mastheadVisible ?? true
  const [mastheadVisible, setMastheadVisible] = useState(initialMastheadVisible)
  const mastheadRef = useRef<HTMLElement>(null)
  const mastheadVisibleRef = useRef(initialMastheadVisible)
  const lastScrollYRef = useRef(initialSnapshot?.scrollY ?? 0)
  const scrollDirectionRef = useRef<{ sign: -1 | 0 | 1; distance: number }>({ sign: 0, distance: 0 })
  const scrollFrameRef = useRef<number | null>(null)

  const setMastheadVisibility = useCallback((next: boolean) => {
    mastheadVisibleRef.current = next
    setMastheadVisible(next)
  }, [])

  useMastheadAutoHide({
    lastScrollYRef,
    mastheadRef,
    mastheadVisibleRef,
    scrollDirectionRef,
    scrollFrameRef,
    setMastheadVisible,
  })
  const scrollToTop = useAnimatedScrollToTop({
    lastScrollYRef,
    mastheadVisibleRef,
    scrollDirectionRef,
    setMastheadVisible,
  })

  return {
    mastheadVisible,
    mastheadVisibleRef,
    lastScrollYRef,
    mastheadRef,
    setMastheadVisibility,
    scrollToTop,
  }
}

interface MastheadAutoHideProps {
  lastScrollYRef: RefObject<number>
  mastheadRef: RefObject<HTMLElement | null>
  mastheadVisibleRef: RefObject<boolean>
  scrollDirectionRef: RefObject<{ sign: -1 | 0 | 1; distance: number }>
  scrollFrameRef: RefObject<number | null>
  setMastheadVisible: (next: boolean) => void
}

function useMastheadAutoHide({
  lastScrollYRef,
  mastheadRef,
  mastheadVisibleRef,
  scrollDirectionRef,
  scrollFrameRef,
  setMastheadVisible,
}: MastheadAutoHideProps) {
  useEffect(() => {
    if (lastScrollYRef.current === 0) lastScrollYRef.current = window.scrollY

    const setVisible = (next: boolean) => {
      if (mastheadVisibleRef.current === next) return
      mastheadVisibleRef.current = next
      setMastheadVisible(next)
    }

    function handleScroll() {
      if (scrollFrameRef.current !== null) return
      scrollFrameRef.current = window.requestAnimationFrame(() => {
        const currentY = window.scrollY
        const delta = currentY - lastScrollYRef.current
        const activeElement = document.activeElement

        if (mastheadRef.current?.contains(activeElement)) {
          setVisible(true)
          scrollDirectionRef.current = { sign: 0, distance: 0 }
        } else if (currentY < MASTHEAD_ALWAYS_VISIBLE_Y) {
          setVisible(true)
          scrollDirectionRef.current = { sign: 0, distance: 0 }
        } else if (Math.abs(delta) > MIN_SCROLL_DELTA) {
          const sign = delta > 0 ? 1 : -1
          const currentDirection = scrollDirectionRef.current
          const distance = currentDirection.sign === sign
            ? currentDirection.distance + Math.abs(delta)
            : Math.abs(delta)

          scrollDirectionRef.current = { sign, distance }

          if (sign > 0 && distance > HIDE_DISTANCE) {
            setVisible(false)
            scrollDirectionRef.current = { sign, distance: 0 }
          } else if (sign < 0 && distance > SHOW_DISTANCE) {
            setVisible(true)
            scrollDirectionRef.current = { sign, distance: 0 }
          }
        }

        lastScrollYRef.current = currentY
        scrollFrameRef.current = null
      })
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', handleScroll)
      if (scrollFrameRef.current !== null) {
        window.cancelAnimationFrame(scrollFrameRef.current)
      }
    }
  }, [
    lastScrollYRef,
    mastheadRef,
    mastheadVisibleRef,
    scrollDirectionRef,
    scrollFrameRef,
    setMastheadVisible,
  ])
}

interface AnimatedScrollProps {
  lastScrollYRef: RefObject<number>
  mastheadVisibleRef: RefObject<boolean>
  scrollDirectionRef: RefObject<{ sign: -1 | 0 | 1; distance: number }>
  setMastheadVisible: (next: boolean) => void
}

function useAnimatedScrollToTop({
  lastScrollYRef,
  mastheadVisibleRef,
  scrollDirectionRef,
  setMastheadVisible,
}: AnimatedScrollProps) {
  const topScrollFrameRef = useRef<number | null>(null)
  const topScrollCleanupRef = useRef<(() => void) | null>(null)
  const cancelTopScroll = useCallback(() => {
    if (topScrollFrameRef.current !== null) {
      window.cancelAnimationFrame(topScrollFrameRef.current)
      topScrollFrameRef.current = null
    }
    topScrollCleanupRef.current?.()
    topScrollCleanupRef.current = null
    lastScrollYRef.current = window.scrollY
  }, [lastScrollYRef])

  useEffect(() => () => cancelTopScroll(), [cancelTopScroll])

  const scrollToTop = useCallback(() => {
    cancelTopScroll()
    mastheadVisibleRef.current = true
    scrollDirectionRef.current = { sign: 0, distance: 0 }
    setMastheadVisible(true)
    const startY = window.scrollY
    if (startY <= 0) {
      lastScrollYRef.current = 0
      window.scrollTo(0, 0)
      return
    }

    const startedAt = performance.now()
    const duration = Math.min(TOP_SCROLL_MAX_MS, Math.max(TOP_SCROLL_MIN_MS, startY * TOP_SCROLL_MS_PER_PX))
    const previousBehavior = document.documentElement.style.scrollBehavior
    document.documentElement.style.scrollBehavior = 'auto'

    const cleanup = () => {
      TOP_SCROLL_INTERRUPT_EVENTS.forEach((eventName) => {
        window.removeEventListener(eventName, cancelTopScroll)
      })
      document.documentElement.style.scrollBehavior = previousBehavior
    }
    topScrollCleanupRef.current = cleanup
    TOP_SCROLL_INTERRUPT_EVENTS.forEach((eventName) => {
      window.addEventListener(eventName, cancelTopScroll, { passive: true })
    })

    const finish = () => {
      topScrollFrameRef.current = null
      topScrollCleanupRef.current?.()
      topScrollCleanupRef.current = null
    }

    const step = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / duration)
      const eased = 1 - Math.pow(1 - progress, 3)
      const nextY = Math.max(0, Math.round(startY * (1 - eased)))

      window.scrollTo(0, nextY)
      lastScrollYRef.current = window.scrollY

      if (progress < 1 && window.scrollY > 0) {
        topScrollFrameRef.current = window.requestAnimationFrame(step)
        return
      }

      window.scrollTo(0, 0)
      lastScrollYRef.current = 0
      finish()
    }

    topScrollFrameRef.current = window.requestAnimationFrame(step)
  }, [
    cancelTopScroll,
    lastScrollYRef,
    mastheadVisibleRef,
    scrollDirectionRef,
    setMastheadVisible,
  ])

  return scrollToTop
}
