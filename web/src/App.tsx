import React, { useState, useEffect, useCallback } from 'react'
import {
  ShieldAlert,
  Bot,
  Cpu,
  CheckCircle2,
  XCircle,
  Database,
  Send,
  Zap,
  Lock,
  Layers,
  Sparkles,
  BarChart3,
  KeyRound,
  RefreshCw
} from 'lucide-react'

interface Message {
  id: string
  sender: 'user' | 'agent'
  text: string
  role?: string
  tier?: string
  verified?: boolean
  timestamp: string
}

interface PendingApproval {
  id: string
  action: string
  caller: string
  timestamp: string
  dry_run: {
    summary: string
    parameters: any
  }
}

interface Profile {
  name: string
  role: string
  tier: string
  model: string
  description: string
  max_turns: number
  allowed_toolsets: string[]
  disabled_toolsets: string[]
}

interface VaultNote {
  title: string
  category: string
  snippet: string
  updated_at: string
}

interface Metrics {
  token_economy: {
    zero_token_mechanical_runs: number
    model_dispatched_tasks: number
    verification_failures_prevented: number
    note: string
  }
  governance: {
    total_gate_actions: number
    red_lines_rejected: number
    operator_approved: number
    operator_denied: number
    pending_approval: number
    auto_approved_safe: number
  }
  memory: {
    vault_notes: number
  }
  system: {
    environment: string
  }
}

// Resolve the API base: same-origin via Caddy/nginx proxy, or a configured override.
const API_BASE = import.meta.env.VITE_GATEWAY_URL?.replace(/\/$/, '') || ''

const TOKEN_STORAGE_KEY = 'indy_dots_auth_token'

export default function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'approvals' | 'fleet' | 'vault' | 'metrics'>('chat')
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      sender: 'agent',
      role: 'atlas',
      tier: 'primary',
      text: 'Atlas online. Chief of Staff initialized with governed routing, red-line enforcement, and a 1-pass verification gate. Dispatch a task to begin.',
      verified: false,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ])
  const [inputPrompt, setInputPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [approvals, setApprovals] = useState<PendingApproval[]>([])
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [vaultNotes, setVaultNotes] = useState<VaultNote[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)

  // Auth token: build-time env or user-entered (stored locally).
  const [authToken, setAuthToken] = useState<string>(
    import.meta.env.VITE_AUTH_TOKEN || localStorage.getItem(TOKEN_STORAGE_KEY) || ''
  )
  const [showTokenModal, setShowTokenModal] = useState(false)
  const [tokenInput, setTokenInput] = useState('')

  const authHeaders = useCallback((): Record<string, string> => {
    return authToken ? { Authorization: `Bearer ${authToken}` } : {}
  }, [authToken])

  const saveToken = () => {
    const t = tokenInput.trim()
    setAuthToken(t)
    if (t) localStorage.setItem(TOKEN_STORAGE_KEY, t)
    else localStorage.removeItem(TOKEN_STORAGE_KEY)
    setShowTokenModal(false)
  }

  const refreshApprovals = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/approvals`, { headers: authHeaders() })
      if (!res.ok) return
      const data = await res.json()
      setApprovals(
        (data.pending || []).map((p: any) => ({
          id: p.id,
          action: p.action,
          caller: p.caller || 'orchestrator',
          timestamp: p.timestamp,
          dry_run: p.dry_run || { summary: 'Pending operator review', parameters: p.payload || {} }
        }))
      )
    } catch { /* stale until gateway reachable */ }
  }, [authHeaders])

  useEffect(() => {
    if (activeTab === 'approvals') refreshApprovals()
    if (activeTab === 'fleet' && profiles.length === 0) {
      fetch(`${API_BASE}/api/profiles`, { headers: authHeaders() })
        .then(r => (r.ok ? r.json() : Promise.reject()))
        .then(d => setProfiles(d.profiles || []))
        .catch(() => setProfiles([]))
    }
    if (activeTab === 'vault' && vaultNotes.length === 0) {
      fetch(`${API_BASE}/api/vault?limit=50`, { headers: authHeaders() })
        .then(r => (r.ok ? r.json() : Promise.reject()))
        .then(d => setVaultNotes(d.notes || []))
        .catch(() => setVaultNotes([]))
    }
    if (activeTab === 'metrics') {
      fetch(`${API_BASE}/api/metrics`, { headers: authHeaders() })
        .then(r => (r.ok ? r.json() : Promise.reject()))
        .then(d => setMetrics(d))
        .catch(() => setMetrics(null))
    }
  }, [activeTab, authToken, authHeaders, refreshApprovals])

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    if (!inputPrompt.trim() || loading) return

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: 'user',
      text: inputPrompt,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
    setMessages(prev => [...prev, userMsg])
    const promptToSend = inputPrompt
    setInputPrompt('')
    setLoading(true)

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ prompt: promptToSend })
      })

      if (response.ok) {
        const data = await response.json()
        let agentText = ''
        let role = 'atlas'
        let tier = 'worker'
        let verified = false

        data.events.forEach((ev: any) => {
          if (ev.type === 'route_decision') {
            role = ev.role
            tier = ev.model_tier
          }
          if (ev.type === 'content_chunk') {
            agentText += ev.chunk
          }
          if (ev.type === 'verification_gate_result' && ev.passed) {
            verified = true
          }
          if (ev.type === 'approval_required') {
            agentText = `⏸ Approval required (gate ${ev.gate_id}).\n\n${ev.message}\n\nReview it under Gate Approvals.`
            refreshApprovals()
          }
          if (ev.type === 'action_rejected') {
            agentText = `⛔ Rejected by Red Lines (gate ${ev.gate_id}).\n\n${ev.message}`
          }
          if (ev.type === 'model_error') {
            agentText = `⚠ Model call failed (${ev.model}).\n\n${ev.error}\n\nNo response was fabricated. Check the model API key and base URL.`
          }
        })

        setMessages(prev => [
          ...prev,
          {
            id: (Date.now() + 1).toString(),
            sender: 'agent',
            text: agentText || 'Task processed, but the agent returned no content.',
            role,
            tier,
            verified,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ])
      } else if (response.status === 401) {
        setShowTokenModal(true)
        setMessages(prev => [
          ...prev,
          {
            id: (Date.now() + 1).toString(),
            sender: 'agent',
            text: '🔒 Unauthorized. Enter the gateway AUTH_TOKEN to continue (lock icon, top right).',
            role: 'atlas',
            tier: 'primary',
            verified: false,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ])
      } else {
        const detail = await response.text().catch(() => '')
        setMessages(prev => [
          ...prev,
          {
            id: (Date.now() + 1).toString(),
            sender: 'agent',
            text: `⚠ Gateway error ${response.status}. ${detail.slice(0, 200)}`.trim(),
            role: 'atlas',
            tier: 'primary',
            verified: false,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ])
      }
    } catch {
      setMessages(prev => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: 'agent',
          text: '⚠ Cannot reach the gateway. Check that the indy-gateway service is running and that /api routes are proxied correctly.',
          role: 'atlas',
          tier: 'primary',
          verified: false,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ])
    } finally {
      setLoading(false)
    }
  }

  const resolveGate = async (id: string, approved: boolean) => {
    try {
      const res = await fetch(`${API_BASE}/api/approvals/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ gate_id: id, approved })
      })
      if (!res.ok) {
        const detail = await res.text().catch(() => '')
        window.alert(`Failed to resolve gate ${id}: ${res.status}. ${detail.slice(0, 200)}`)
        return
      }
      setApprovals(prev => prev.filter(a => a.id !== id))
    } catch {
      window.alert(`Network error while resolving gate ${id}.`)
    }
  }

  return (
    <div className="flex flex-col h-screen bg-[#0b0f17] text-slate-100">
      {/* Token Modal */}
      {showTokenModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={() => setShowTokenModal(false)}>
          <div className="w-96 p-6 rounded-2xl bg-[#141c2c] border border-slate-700 space-y-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2">
              <KeyRound className="w-5 h-5 text-indigo-400" />
              <h3 className="font-semibold">Gateway Authentication</h3>
            </div>
            <p className="text-xs text-slate-400">
              Paste the AUTH_TOKEN configured on the gateway (.env). It is stored only in this browser's local storage.
            </p>
            <input
              type="password"
              value={tokenInput}
              onChange={e => setTokenInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && saveToken()}
              placeholder="AUTH_TOKEN"
              className="w-full bg-[#1a2234] border border-slate-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-indigo-500"
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowTokenModal(false)} className="px-3 py-2 rounded-lg text-xs text-slate-400 hover:text-slate-200">Cancel</button>
              <button onClick={saveToken} className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-medium">Save token</button>
            </div>
          </div>
        </div>
      )}

      {/* Top Navigation Bar */}
      <header className="flex items-center justify-between px-6 py-3.5 bg-[#111827] border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold shadow-lg shadow-indigo-500/20">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-lg tracking-tight">Indy-Dots</span>
              <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                Self-Hosted Node
              </span>
            </div>
            <p className="text-xs text-slate-400">Autonomous Hermes Workspace • Token & Gate Governed</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => { setTokenInput(authToken); setShowTokenModal(true) }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
              authToken
                ? 'bg-emerald-950 text-emerald-400 border-emerald-800 hover:border-emerald-600'
                : 'bg-amber-950 text-amber-400 border-amber-800 hover:border-amber-600'
            }`}
            title={authToken ? 'Authenticated — click to change token' : 'No token set — click to authenticate'}
          >
            {authToken ? <Lock className="w-3.5 h-3.5" /> : <KeyRound className="w-3.5 h-3.5" />}
            {authToken ? 'Authenticated' : 'Set token'}
          </button>

          <nav className="flex items-center gap-1 bg-[#1a2234] p-1 rounded-xl border border-slate-800">
            {([
              ['chat', 'Chat & Orchestrator', <Bot key="b" className="w-4 h-4" />],
              ['approvals', 'Gate Approvals', <ShieldAlert key="s" className="w-4 h-4" />],
              ['fleet', 'Profile Fleet', <Layers key="l" className="w-4 h-4" />],
              ['vault', 'Brain Vault', <Database key="d" className="w-4 h-4" />],
              ['metrics', 'Token Diet', <BarChart3 key="m" className="w-4 h-4" />],
            ] as const).map(([tab, label, icon]) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition ${
                  activeTab === tab ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {icon}
                {label}
                {tab === 'approvals' && approvals.length > 0 && (
                  <span className="bg-amber-500 text-black font-bold px-1.5 py-0.2 rounded-full text-[10px]">
                    {approvals.length}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 overflow-hidden flex">
        {/* VIEW 1: CHAT & ORCHESTRATOR */}
        {activeTab === 'chat' && (
          <div className="flex-1 flex flex-col h-full bg-[#0b0f17]">
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {messages.map(msg => (
                <div
                  key={msg.id}
                  className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}
                >
                  {msg.sender === 'agent' && (
                    <div className="flex items-center gap-2 mb-1 text-xs">
                      <span className="font-semibold text-indigo-400 flex items-center gap-1">
                        <Bot className="w-3.5 h-3.5" />
                        {msg.role?.toUpperCase() || 'ATLAS'}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${
                        msg.tier === 'primary'
                          ? 'bg-purple-950 text-purple-300 border-purple-800'
                          : 'bg-emerald-950 text-emerald-300 border-emerald-800'
                      }`}>
                        {msg.tier === 'primary' ? 'High Reasoning Tier' : 'Free Worker Tier'}
                      </span>
                      {msg.verified && (
                        <span className="flex items-center gap-1 text-[10px] text-emerald-400 font-mono">
                          <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                          Gate Verified
                        </span>
                      )}
                      <span className="text-slate-500 font-mono">{msg.timestamp}</span>
                    </div>
                  )}

                  <div
                    className={`max-w-2xl px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                      msg.sender === 'user'
                        ? 'bg-indigo-600 text-white rounded-br-none shadow-md'
                        : 'bg-[#161f30] text-slate-200 rounded-bl-none border border-slate-800 shadow-md'
                    }`}
                  >
                    {msg.text}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex items-center gap-3 text-xs text-indigo-400 animate-pulse p-2">
                  <Cpu className="w-4 h-4 animate-spin" />
                  Routing intent • Checking governance gates • Dispatching...
                </div>
              )}
            </div>

            {/* Quick action chips */}
            <div className="px-6 py-2 bg-[#0d131f] border-t border-slate-800 flex gap-2 overflow-x-auto text-xs">
              <span className="text-slate-500 flex items-center gap-1">
                <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                Quick:
              </span>
              {[
                ['/research compare self-hosted AI workspace stacks on pricing & latency', '/research benchmark'],
                ['/seo analyze organic search console impressions', '/seo audit'],
                ['/ops summarize open sprint tickets', '/ops triage'],
                ['/write changelog for indy-dots v1.1 release', '/write changelog'],
              ].map(([prompt, label]) => (
                <button
                  key={label}
                  onClick={() => setInputPrompt(prompt)}
                  className="px-2.5 py-1 rounded-md bg-[#161f30] text-slate-300 hover:border-indigo-500 border border-slate-700 transition whitespace-nowrap"
                >
                  {label}
                </button>
              ))}
            </div>

            {/* Input Bar */}
            <form onSubmit={handleSend} className="p-4 bg-[#111827] border-t border-slate-800 flex gap-3">
              <input
                type="text"
                value={inputPrompt}
                onChange={e => setInputPrompt(e.target.value)}
                placeholder="Ask Chief of Staff (e.g. /research, /ops, /seo, /write, /code)..."
                className="flex-1 bg-[#1a2234] border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
              />
              <button
                type="submit"
                disabled={loading || !inputPrompt.trim()}
                className="px-5 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium text-sm flex items-center gap-2 shadow-lg shadow-indigo-600/20 transition"
              >
                <Send className="w-4 h-4" />
                Dispatch
              </button>
            </form>
          </div>
        )}

        {/* VIEW 2: GATE APPROVALS */}
        {activeTab === 'approvals' && (
          <div className="flex-1 p-8 overflow-y-auto bg-[#0b0f17]">
            <div className="max-w-4xl mx-auto space-y-6">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div>
                  <h2 className="text-xl font-bold flex items-center gap-2">
                    <ShieldAlert className="w-6 h-6 text-amber-400" />
                    Yellow Gate Approvals Queue
                  </h2>
                  <p className="text-sm text-slate-400">
                    High-risk operations pause here with dry-run receipts. Red Lines auto-reject before this queue.
                  </p>
                </div>
                <button
                  onClick={refreshApprovals}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:border-indigo-500 transition"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Refresh
                </button>
              </div>

              {approvals.length === 0 ? (
                <div className="text-center py-16 border border-dashed border-slate-800 rounded-2xl">
                  <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-3" />
                  <h3 className="font-medium text-slate-200">All clear</h3>
                  <p className="text-sm text-slate-500">No actions currently pending operator review.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {approvals.map(appr => (
                    <div key={appr.id} className="p-5 rounded-2xl bg-[#141c2c] border border-amber-900/40 shadow-lg space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="px-2.5 py-1 rounded-md bg-amber-950 text-amber-400 border border-amber-800 text-xs font-mono font-bold">
                            {appr.action}
                          </span>
                          <span className="text-xs text-slate-400 font-mono">ID: {appr.id}</span>
                          <span className="text-xs text-slate-500">• Requested by: {appr.caller}</span>
                        </div>
                        <span className="text-xs text-slate-500 font-mono">{appr.timestamp}</span>
                      </div>

                      <div className="bg-[#0b0f17] p-3.5 rounded-xl border border-slate-800 font-mono text-xs text-slate-300 space-y-2">
                        <div className="text-slate-400 font-semibold">{appr.dry_run.summary}</div>
                        <pre className="text-slate-400 overflow-x-auto p-2 bg-[#111827] rounded">
                          {JSON.stringify(appr.dry_run.parameters, null, 2)}
                        </pre>
                      </div>

                      <div className="flex justify-end gap-3 pt-2">
                        <button
                          onClick={() => resolveGate(appr.id, false)}
                          className="px-4 py-2 rounded-xl bg-rose-950/60 hover:bg-rose-900 border border-rose-800 text-rose-300 text-xs font-medium flex items-center gap-1.5 transition"
                        >
                          <XCircle className="w-4 h-4" />
                          Reject Action
                        </button>
                        <button
                          onClick={() => resolveGate(appr.id, true)}
                          className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium flex items-center gap-1.5 shadow-lg shadow-emerald-600/20 transition"
                        >
                          <CheckCircle2 className="w-4 h-4" />
                          Approve & Execute
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* VIEW 3: PROFILE FLEET */}
        {activeTab === 'fleet' && (
          <div className="flex-1 p-8 overflow-y-auto bg-[#0b0f17]">
            <div className="max-w-5xl mx-auto space-y-6">
              <div className="border-b border-slate-800 pb-4">
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <Layers className="w-6 h-6 text-indigo-400" />
                  Specialized Sub-Agent Fleet
                </h2>
                <p className="text-sm text-slate-400">
                  Loaded live from <span className="font-mono text-xs">profiles/*.yaml</span> — dual-tier architecture: high reasoning for CoS; free & cheap models for bounded specialists.
                </p>
              </div>

              {profiles.length === 0 ? (
                <div className="text-center py-16 border border-dashed border-slate-800 rounded-2xl text-sm text-slate-500">
                  Could not load profiles from the gateway{authToken ? '' : ' — set your token first'}.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {profiles.map(p => (
                    <div key={p.name} className="p-5 rounded-2xl bg-[#141c2c] border border-slate-800 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-base text-slate-100 capitalize">{p.name}</span>
                        <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                          p.tier === 'primary'
                            ? 'bg-purple-950 text-purple-300 border-purple-800'
                            : 'bg-emerald-950 text-emerald-300 border-emerald-800'
                        }`}>
                          {p.tier === 'primary' ? 'Primary Tier' : 'Worker Tier'}
                        </span>
                      </div>
                      {p.description && <p className="text-xs text-slate-400">{p.description}</p>}
                      <div className="space-y-1 pt-2 border-t border-slate-800 text-[11px] font-mono">
                        <div className="text-slate-500">Role: <span className="text-slate-300">{p.role}</span></div>
                        <div className="text-slate-500">Model: <span className="text-slate-300">{p.model}</span></div>
                        <div className="text-slate-500">Max turns: <span className="text-slate-300">{p.max_turns}</span></div>
                        {p.allowed_toolsets.length > 0 && (
                          <div className="text-slate-500">Allowed: <span className="text-emerald-400">{p.allowed_toolsets.join(', ')}</span></div>
                        )}
                        {p.disabled_toolsets.length > 0 && (
                          <div className="text-slate-500">Blocked: <span className="text-rose-400">{p.disabled_toolsets.join(', ')}</span></div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* VIEW 4: COMPOUNDING VAULT */}
        {activeTab === 'vault' && (
          <div className="flex-1 p-8 overflow-y-auto bg-[#0b0f17]">
            <div className="max-w-4xl mx-auto space-y-6">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div>
                  <h2 className="text-xl font-bold flex items-center gap-2">
                    <Database className="w-6 h-6 text-indigo-400" />
                    Compounding Brain & Vault
                  </h2>
                  <p className="text-sm text-slate-400">
                    Verified research outputs persisted as Markdown + SQLite index across restarts.
                  </p>
                </div>
                <button
                  onClick={() => setVaultNotes([])}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:border-indigo-500 transition"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Refresh
                </button>
              </div>

              {vaultNotes.length === 0 ? (
                <div className="text-center py-16 border border-dashed border-slate-800 rounded-2xl">
                  <Database className="w-12 h-12 text-slate-600 mx-auto mb-3" />
                  <h3 className="font-medium text-slate-200">Vault is empty</h3>
                  <p className="text-sm text-slate-500">Verified /research outputs longer than 400 chars compound here automatically.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {vaultNotes.map(n => (
                    <div key={n.title} className="p-4 rounded-xl bg-[#141c2c] border border-slate-800 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-sm text-indigo-400 font-semibold">{n.title}</span>
                        <span className="text-xs text-slate-500 font-mono">{n.category} • {n.updated_at?.slice(0, 10)}</span>
                      </div>
                      <p className="text-xs text-slate-300 line-clamp-2">{n.snippet}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* VIEW 5: TOKEN DIET & METRICS */}
        {activeTab === 'metrics' && (
          <div className="flex-1 p-8 overflow-y-auto bg-[#0b0f17]">
            <div className="max-w-4xl mx-auto space-y-6">
              <div className="border-b border-slate-800 pb-4">
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <BarChart3 className="w-6 h-6 text-emerald-400" />
                  Token Economics & Governance
                </h2>
                <p className="text-sm text-slate-400">
                  Live numbers from the gate ledger and vault index — no estimates, no placeholders.
                </p>
              </div>

              {!metrics ? (
                <div className="text-center py-16 border border-dashed border-slate-800 rounded-2xl text-sm text-slate-500">
                  Could not load metrics{authToken ? '' : ' — set your token first'}.
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="p-5 rounded-2xl bg-[#141c2c] border border-slate-800">
                      <div className="text-xs text-slate-400">Zero-Token Runs</div>
                      <div className="text-2xl font-bold text-indigo-400 mt-1">{metrics.token_economy.zero_token_mechanical_runs}</div>
                      <div className="text-xs text-slate-500 mt-2">Safe actions handled without any model call</div>
                    </div>
                    <div className="p-5 rounded-2xl bg-[#141c2c] border border-slate-800">
                      <div className="text-xs text-slate-400">Model-Dispatched Tasks</div>
                      <div className="text-2xl font-bold text-emerald-400 mt-1">{metrics.token_economy.model_dispatched_tasks}</div>
                      <div className="text-xs text-slate-500 mt-2">Tasks that used the model fleet</div>
                    </div>
                    <div className="p-5 rounded-2xl bg-[#141c2c] border border-slate-800">
                      <div className="text-xs text-slate-400">Red Lines Enforced</div>
                      <div className="text-2xl font-bold text-amber-400 mt-1">{metrics.token_economy.verification_failures_prevented}</div>
                      <div className="text-xs text-slate-500 mt-2">Dangerous actions auto-rejected</div>
                    </div>
                  </div>

                  <div className="p-5 rounded-2xl bg-[#141c2c] border border-slate-800 space-y-3">
                    <h3 className="text-sm font-semibold text-slate-200">Governance Ledger</h3>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs font-mono">
                      <div className="p-3 bg-[#0b0f17] rounded-xl border border-slate-800">
                        <span className="text-slate-400">Total actions:</span>
                        <div className="text-slate-200 text-sm mt-1">{metrics.governance.total_gate_actions}</div>
                      </div>
                      <div className="p-3 bg-[#0b0f17] rounded-xl border border-slate-800">
                        <span className="text-slate-400">Approved / Denied:</span>
                        <div className="text-slate-200 text-sm mt-1">{metrics.governance.operator_approved} / {metrics.governance.operator_denied}</div>
                      </div>
                      <div className="p-3 bg-[#0b0f17] rounded-xl border border-slate-800">
                        <span className="text-slate-400">Pending:</span>
                        <div className="text-slate-200 text-sm mt-1">{metrics.governance.pending_approval}</div>
                      </div>
                      <div className="p-3 bg-[#0b0f17] rounded-xl border border-slate-800">
                        <span className="text-slate-400">Vault notes:</span>
                        <div className="text-slate-200 text-sm mt-1">{metrics.memory.vault_notes}</div>
                      </div>
                      <div className="p-3 bg-[#0b0f17] rounded-xl border border-slate-800">
                        <span className="text-slate-400">Environment:</span>
                        <div className="text-slate-200 text-sm mt-1">{metrics.system.environment}</div>
                      </div>
                    </div>
                    <p className="text-[11px] text-slate-500">{metrics.token_economy.note}</p>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
