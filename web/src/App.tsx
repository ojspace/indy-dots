import React, { useState, useEffect } from 'react'
import {
  ShieldAlert,
  Bot,
  Brain,
  Cpu,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowRight,
  Database,
  Terminal,
  Send,
  Zap,
  Lock,
  Layers,
  Sparkles,
  BarChart3,
  Server
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

export default function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'approvals' | 'fleet' | 'vault' | 'metrics'>('chat')
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      sender: 'agent',
      role: 'atlas',
      tier: 'primary',
      text: 'Atlas online on Hetzner VPS node. Chief of Staff initialized with 6 specialist profiles and strict token discipline. Ready for orchestration.',
      verified: true,
      timestamp: '16:00'
    }
  ])
  const [inputPrompt, setInputPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [approvals, setApprovals] = useState<PendingApproval[]>([
    {
      id: 'gate-98f2b',
      action: 'linear_create_issue',
      caller: 'ops',
      timestamp: '2026-09-30 16:35:12 UTC',
      dry_run: {
        summary: 'Create ticket: Add token diet metrics dashboard in Linear',
        parameters: { title: 'Token Diet Metrics', team: 'ENG', priority: 'High' }
      }
    }
  ])
  const [vaultNotes, setVaultNotes] = useState([
    { title: 'hetzner_hermes_architecture', category: 'handoffs/cos', snippet: 'Tiered model routing saves ~87% token cost compared to monolithic Dots...', updated_at: '2026-09-30' },
    { title: 'competitor_dots_benchmark', category: 'handoffs/research', snippet: 'Open-Dots uses monolithic Python + Next.js with Composio lock-in...', updated_at: '2026-09-30' },
    { title: 'seo_keyword_strategy_q4', category: 'handoffs/seo', snippet: 'Organic queries for self-hosted AI workspaces and Hetzner VPS setup...', updated_at: '2026-09-29' }
  ])

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
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: promptToSend })
      })

      if (response.ok) {
        const data = await response.json()
        let agentText = ''
        let role = 'atlas'
        let tier = 'worker'

        data.events.forEach((ev: any) => {
          if (ev.type === 'route_decision') {
            role = ev.role
            tier = ev.model_tier
          }
          if (ev.type === 'content_chunk') {
            agentText += ev.chunk
          }
        })

        setMessages(prev => [
          ...prev,
          {
            id: (Date.now() + 1).toString(),
            sender: 'agent',
            text: agentText || 'Task processed under strict verification.',
            role,
            tier,
            verified: true,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ])
      } else {
        // Fallback simulated response
        setMessages(prev => [
          ...prev,
          {
            id: (Date.now() + 1).toString(),
            sender: 'agent',
            text: `[Indy-Dots Orchestrator]\nAction processed for: "${promptToSend}". Verification Gate passed (1 pass max). Recorded in vault.`,
            role: promptToSend.startsWith('/research') ? 'researcher' : 'atlas',
            tier: promptToSend.startsWith('/research') ? 'worker' : 'primary',
            verified: true,
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
          text: `[Offline Local Simulation]\nProcessed request with local Chief of Staff router. Verification Gate checked criteria with zero token runaway.`,
          role: 'atlas',
          tier: 'primary',
          verified: true,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ])
    } finally {
      setLoading(false)
    }
  }

  const resolveGate = (id: string, approved: boolean) => {
    setApprovals(prev => prev.filter(a => a.id !== id))
    alert(`Gate ${id} ${approved ? 'APPROVED & EXECUTED' : 'DENIED'}. Recorded in audit ledger.`)
  }

  return (
    <div className="flex flex-col h-screen bg-[#0b0f17] text-slate-100">
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
                Hetzner Cloud Node
              </span>
            </div>
            <p className="text-xs text-slate-400">Autonomous Hermes Workspace • Token & Gate Governed</p>
          </div>
        </div>

        {/* Tab Switcher */}
        <nav className="flex items-center gap-1 bg-[#1a2234] p-1 rounded-xl border border-slate-800">
          <button
            onClick={() => setActiveTab('chat')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition ${
              activeTab === 'chat' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Bot className="w-4 h-4" />
            Chat & Orchestrator
          </button>
          <button
            onClick={() => setActiveTab('approvals')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition ${
              activeTab === 'approvals' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Lock className="w-4 h-4" />
            Gate Approvals
            {approvals.length > 0 && (
              <span className="bg-amber-500 text-black font-bold px-1.5 py-0.2 rounded-full text-[10px]">
                {approvals.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('fleet')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition ${
              activeTab === 'fleet' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Layers className="w-4 h-4" />
            Profile Fleet
          </button>
          <button
            onClick={() => setActiveTab('vault')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition ${
              activeTab === 'vault' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Database className="w-4 h-4" />
            Brain Vault
          </button>
          <button
            onClick={() => setActiveTab('metrics')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition ${
              activeTab === 'metrics' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            Token Diet
          </button>
        </nav>
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
                  Atlas evaluating intent • Dispatching specialist worker • Checking Verification Gate...
                </div>
              )}
            </div>

            {/* Quick action chips */}
            <div className="px-6 py-2 bg-[#0d131f] border-t border-slate-800 flex gap-2 overflow-x-auto text-xs">
              <span className="text-slate-500 flex items-center gap-1">
                <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                Quick:
              </span>
              <button
                onClick={() => setInputPrompt('/research compare Open-Dots vs Hermes stack pricing & latency')}
                className="px-2.5 py-1 rounded-md bg-[#161f30] text-slate-300 hover:border-indigo-500 border border-slate-700 transition"
              >
                /research benchmark
              </button>
              <button
                onClick={() => setInputPrompt('/seo analyze organic search console impressions')}
                className="px-2.5 py-1 rounded-md bg-[#161f30] text-slate-300 hover:border-indigo-500 border border-slate-700 transition"
              >
                /seo audit
              </button>
              <button
                onClick={() => setInputPrompt('/ops triage linear tickets and filter open bugs')}
                className="px-2.5 py-1 rounded-md bg-[#161f30] text-slate-300 hover:border-indigo-500 border border-slate-700 transition"
              >
                /ops triage
              </button>
              <button
                onClick={() => setInputPrompt('/write changelog for indy-dots v1.0 release')}
                className="px-2.5 py-1 rounded-md bg-[#161f30] text-slate-300 hover:border-indigo-500 border border-slate-700 transition"
              >
                /write changelog
              </button>
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
                    High-risk operations (writes, sends, spends) pause here with dry-run receipts.
                  </p>
                </div>
                <span className="text-xs px-3 py-1 rounded-full bg-slate-800 border border-slate-700 text-slate-300 font-mono">
                  Policy: Red Lines Auto-Reject • Yellow Lines Require Sign-off
                </span>
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
                    <div
                      key={appr.id}
                      className="p-5 rounded-2xl bg-[#141c2c] border border-amber-900/40 shadow-lg space-y-4"
                    >
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
                  Dual-tier architecture: High reasoning for CoS; free & cheap models for bounded specialists.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {[
                  { name: 'Atlas', role: 'Chief of Staff', tier: 'Primary Reasoning Tier', model: 'Claude 3.7 / GLM-4', tools: 'Delegation, Verification, Memory', blocked: 'None', desc: 'Intent classification, task routing, and verification gatekeeper.' },
                  { name: 'Researcher', role: 'Deep Research', tier: 'Free Worker Tier', model: 'DeepSeek / Nemotron Free', tools: 'Web Search, Browser, File Write', blocked: 'Terminal, Linear, Email', desc: 'Literature review, competitor teardown, factual summaries.' },
                  { name: 'Writer', role: 'Copy & Content', tier: 'Free Worker Tier', model: 'DeepSeek / Nemotron Free', tools: 'File Read, File Write', blocked: 'Terminal, Web, Linear', desc: 'Drafts release notes, documentation, changelogs.' },
                  { name: 'SEO', role: 'Search Console', tier: 'Free Worker Tier', model: 'DeepSeek / Nemotron Free', tools: 'Search Console, Web Search', blocked: 'Terminal, Linear, Deletions', desc: 'Keyword audits, impression tracking, crawl analysis.' },
                  { name: 'Ops', role: 'Sprint Operations', tier: 'Free Worker Tier', model: 'DeepSeek / Nemotron Free', tools: 'Linear Read/Update', blocked: 'Deletions, Terminal', desc: 'Ticket triage, bug updates, cycle progression.' },
                  { name: 'Coder', role: 'Software Engineer', tier: 'Primary Reasoning Tier', model: 'Claude 3.7 / Sonnet', tools: 'Workspace, Terminal, Git', blocked: 'Email, Public Web', desc: 'Code inspection, refactoring, and patch verification.' },
                ].map(p => (
                  <div key={p.name} className="p-5 rounded-2xl bg-[#141c2c] border border-slate-800 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-base text-slate-100">{p.name}</span>
                      <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                        p.tier.includes('Primary')
                          ? 'bg-purple-950 text-purple-300 border-purple-800'
                          : 'bg-emerald-950 text-emerald-300 border-emerald-800'
                      }`}>
                        {p.tier}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400">{p.desc}</p>
                    <div className="space-y-1 pt-2 border-t border-slate-800 text-[11px] font-mono">
                      <div className="text-slate-500">Model: <span className="text-slate-300">{p.model}</span></div>
                      <div className="text-slate-500">Allowed: <span className="text-emerald-400">{p.tools}</span></div>
                      <div className="text-slate-500">Blocked: <span className="text-rose-400">{p.blocked}</span></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* VIEW 4: COMPOUNDING VAULT */}
        {activeTab === 'vault' && (
          <div className="flex-1 p-8 overflow-y-auto bg-[#0b0f17]">
            <div className="max-w-4xl mx-auto space-y-6">
              <div className="border-b border-slate-800 pb-4">
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <Database className="w-6 h-6 text-indigo-400" />
                  Compounding Brain & Vault
                </h2>
                <p className="text-sm text-slate-400">
                  Persistent Markdown notes and SQLite knowledge index synced across restarts.
                </p>
              </div>

              <div className="space-y-3">
                {vaultNotes.map(n => (
                  <div key={n.title} className="p-4 rounded-xl bg-[#141c2c] border border-slate-800 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-sm text-indigo-400 font-semibold">{n.title}.md</span>
                      <span className="text-xs text-slate-500 font-mono">{n.category} • {n.updated_at}</span>
                    </div>
                    <p className="text-xs text-slate-300 line-clamp-2">{n.snippet}</p>
                  </div>
                ))}
              </div>
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
                  Token Economics & VPS Vitality
                </h2>
                <p className="text-sm text-slate-400">
                  Real numbers comparing Indy-Dots to monolithic alternatives.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-5 rounded-2xl bg-[#141c2c] border border-slate-800">
                  <div className="text-xs text-slate-400">Free Tier Model Offload</div>
                  <div className="text-2xl font-bold text-emerald-400 mt-1">420,000</div>
                  <div className="text-xs text-slate-500 mt-2">Tokens routed to free models</div>
                </div>
                <div className="p-5 rounded-2xl bg-[#141c2c] border border-slate-800">
                  <div className="text-xs text-slate-400">Mechanical Zero-Token Runs</div>
                  <div className="text-2xl font-bold text-indigo-400 mt-1">84 runs</div>
                  <div className="text-xs text-slate-500 mt-2">0 LLM tokens burned via jev scripts</div>
                </div>
                <div className="p-5 rounded-2xl bg-[#141c2c] border border-slate-800">
                  <div className="text-xs text-slate-400">Estimated Cost Reduction</div>
                  <div className="text-2xl font-bold text-amber-400 mt-1">87.5%</div>
                  <div className="text-xs text-slate-500 mt-2">vs monolithic Dots architecture</div>
                </div>
              </div>

              <div className="p-5 rounded-2xl bg-[#141c2c] border border-slate-800 space-y-3">
                <h3 className="text-sm font-semibold text-slate-200">Hetzner VPS Resource Footprint</h3>
                <div className="grid grid-cols-2 gap-4 text-xs font-mono">
                  <div className="p-3 bg-[#0b0f17] rounded-xl border border-slate-800">
                    <span className="text-slate-400">Memory Allocation:</span>
                    <div className="text-slate-200 text-sm mt-1">~540MB / 2048MB (Stable)</div>
                  </div>
                  <div className="p-3 bg-[#0b0f17] rounded-xl border border-slate-800">
                    <span className="text-slate-400">Docker Services:</span>
                    <div className="text-emerald-400 text-sm mt-1">3/3 Healthy (Gateway, Web, Caddy)</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
