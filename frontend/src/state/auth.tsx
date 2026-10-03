import { useQuery } from '@tanstack/react-query'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

import { getJson, onUnauthorized } from '../api/client'
import type { Me } from '../api/types'

interface AuthState {
  me: Me | undefined
  sessionLost: boolean
}

const AuthContext = createContext<AuthState>({ me: undefined, sessionLost: false })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [sessionLost, setSessionLost] = useState(false)
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: () => getJson<Me>('/api/me'), staleTime: 5 * 60_000 })
  useEffect(() => onUnauthorized(() => setSessionLost(true)), [])
  return <AuthContext.Provider value={{ me, sessionLost }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  return useContext(AuthContext)
}
