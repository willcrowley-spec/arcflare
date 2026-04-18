import { useEffect, useRef, useState } from 'react'

const WORD_INTERVAL_MS = 35

/**
 * Progressively reveals `text` word-by-word when `enabled` is true.
 * Returns `{ displayed, done }` — `displayed` is the currently visible
 * substring and `done` flips to true once the full text is shown.
 *
 * If `enabled` is false the full text is returned immediately (for older
 * messages that shouldn't animate).
 */
export function useTypewriter(text: string, enabled: boolean) {
  const [wordIndex, setWordIndex] = useState(0)
  const wordsRef = useRef<string[]>([])
  const prevTextRef = useRef('')

  if (text !== prevTextRef.current) {
    prevTextRef.current = text
    wordsRef.current = text.split(/(\s+)/)
    if (enabled) {
      setWordIndex(0)
    }
  }

  const words = wordsRef.current
  const total = words.length

  useEffect(() => {
    if (!enabled || wordIndex >= total) return

    const id = window.setTimeout(() => {
      setWordIndex((i) => Math.min(i + 1, total))
    }, WORD_INTERVAL_MS)

    return () => window.clearTimeout(id)
  }, [enabled, wordIndex, total])

  if (!enabled || total === 0) {
    return { displayed: text, done: true }
  }

  const displayed = words.slice(0, wordIndex).join('')
  return { displayed, done: wordIndex >= total }
}
