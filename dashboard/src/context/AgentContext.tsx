import { createContext, useContext } from 'react'
import type { AgentState } from '../types'
import { useAgentSocket } from '../hooks/useAgentSocket'

interface AgentCtx {
  state: AgentState
  selectMarket: (id: string | null) => void
}

const Ctx = createContext<AgentCtx | null>(null)

export function AgentProvider({ children }: { children: React.ReactNode }) {
  const { state, selectMarket } = useAgentSocket()
  return <Ctx.Provider value={{ state, selectMarket }}>{children}</Ctx.Provider>
}

export function useAgent() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAgent must be inside AgentProvider')
  return ctx
}
