import { useEffect, useState } from 'react'

/**
 * Trails `value` by `delayMs`. A falsy-length reset (`immediate`) applies at once,
 * so clearing a search box never waits.
 */
export function useDebouncedValue<T>(value: T, delayMs: number, immediate?: (next: T) => boolean): T {
  const [debounced, setDebounced] = useState(value)
  const skipDelay = !Object.is(debounced, value) && immediate?.(value) === true

  useEffect(() => {
    if (Object.is(debounced, value)) return
    const timer = setTimeout(() => setDebounced(value), skipDelay ? 0 : delayMs)
    return () => clearTimeout(timer)
  }, [debounced, delayMs, skipDelay, value])

  return debounced
}
