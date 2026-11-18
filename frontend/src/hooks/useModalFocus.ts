import { useEffect, useRef, type RefObject } from 'react'

const FOCUSABLE = 'a[href], button:not([disabled]), iframe, [tabindex]:not([tabindex="-1"])'

// Moves focus into a modal, keeps Tab inside it, and gives focus back to the
// element that opened it when the modal unmounts.
export function useModalFocus<T extends HTMLElement>(): RefObject<T | null> {
  const ref = useRef<T | null>(null)

  useEffect(() => {
    const container = ref.current
    const previous = document.activeElement as HTMLElement | null
    const items = () => Array.from(container?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])
    const initial = container?.querySelector<HTMLElement>('[data-autofocus]') ?? items()[0]
    initial?.focus()

    function onKey(event: KeyboardEvent) {
      if (event.key !== 'Tab') return
      const list = items()
      if (list.length === 0) return
      const first = list[0]
      const last = list[list.length - 1]
      const active = document.activeElement
      if (event.shiftKey && (active === first || !container?.contains(active))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (active === last || !container?.contains(active))) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previous?.focus?.()
    }
  }, [])

  return ref
}
