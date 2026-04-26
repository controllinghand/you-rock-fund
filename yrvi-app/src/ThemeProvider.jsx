import { createContext, useCallback, useContext, useEffect, useState } from 'react'

const ThemeContext = createContext(null)
const STORAGE_KEY = 'yrvi-theme'

function resolveIsDark(theme) {
  if (theme === 'dark') return true
  if (theme === 'light') return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function applyTheme(theme) {
  document.documentElement.classList.toggle('dark', resolveIsDark(theme))
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(
    () => localStorage.getItem(STORAGE_KEY) ?? 'dark'
  )

  useEffect(() => {
    applyTheme(theme)
    if (theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e) => document.documentElement.classList.toggle('dark', e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [theme])

  const setTheme = useCallback((t) => {
    localStorage.setItem(STORAGE_KEY, t)
    setThemeState(t)
  }, [])

  const isDark = resolveIsDark(theme)

  return (
    <ThemeContext.Provider value={{ theme, setTheme, isDark }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useThemeContext() {
  return useContext(ThemeContext)
}
