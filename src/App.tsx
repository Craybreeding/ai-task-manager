import { useEffect, useRef, useState } from 'react'
import {
  ClipboardList, FlaskConical, Rocket, CheckCircle2,
  BarChart3, FileEdit, Star, Bot, MessageSquare, Monitor, Brain, Package,
  X, AlertTriangle, ExternalLink, ChevronRight, ChevronDown, RefreshCw, Info,
} from 'lucide-react'
import type { AppData, Condition, ConditionStatus, Milestone, OperationStatus, Project, Stage, Task, TaskStatus } from './types'

const STAGES: Stage[] = ['需求拆解', '验证中', '试运行(MVP)', '正式上线(PROD)']
const OP_STATUSES: OperationStatus[] = ['进行中', '待启动', '已暂停', '已废弃']

const STAGE_CONFIG: Record<Stage, { color: string; Icon: typeof ClipboardList }> = {
  '需求拆解':       { color: '#6B8AFF', Icon: ClipboardList },
  '验证中':         { color: '#F3B54A', Icon: FlaskConical },
  '试运行(MVP)':    { color: '#A78BFA', Icon: Rocket },
  '正式上线(PROD)': { color: '#34D399', Icon: CheckCircle2 },
}

const STAGE_DESC: Record<Stage, string> = {
  '需求拆解':       '只有想法/需求，没开始写代码',
  '验证中':         '本地开发中，功能还在迭代',
  '试运行(MVP)':    '核心功能可用，部署到可访问的环境，日常在用但还不稳定',
  '正式上线(PROD)': '部署到生产服务器，稳定运行，有人日常依赖',
}

const PROJECT_ICONS: Record<string, typeof BarChart3> = {
  'yuntu-datapicker': BarChart3,
  'draft-audit': FileEdit,
  'xingtu-selector': Star,
  'tech-assistant': Bot,
  'strategy-chat': MessageSquare,
  'ggn-workspace-frontend': Monitor,
  'ggn-workspace-agent': Brain,
}

const COND_STATUS_LABEL: Record<ConditionStatus, string> = {
  done: '已完成', active: '进行中', blocked: '阻塞', pending: '未开始',
}
const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  done: '已完成', active: '进行中', blocked: '阻塞', pending: '待处理',
}

const STATUS_DOT: Record<string, string> = {
  green: 'bg-[var(--color-good)]',
  amber: 'bg-[var(--color-warn)]',
  yellow: 'bg-[var(--color-warn)]',
  red: 'bg-[var(--color-risk)]',
}

const COND_DOT: Record<ConditionStatus, string> = {
  done: 'bg-[var(--color-good)]',
  active: 'bg-[var(--color-brand)]',
  blocked: 'bg-[var(--color-risk)]',
  pending: 'bg-slate-300',
}

const COND_BADGE: Record<ConditionStatus, string> = {
  done: 'bg-green-100 text-green-800',
  active: 'bg-[var(--color-brand-100)] text-[var(--color-brand-dark)]',
  blocked: 'bg-red-100 text-red-800',
  pending: 'bg-slate-100 text-[var(--color-text-muted)]',
}

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')  // e.g. "/ai-captain-dashboard"

function useAuth() {
  const [user, setUser] = useState<{ name: string; avatar: string } | null>(null)
  const [checking, setChecking] = useState(true)
  const [authEnabled, setAuthEnabled] = useState(false)

  useEffect(() => {
    // Check for token in URL fragment (OAuth callback)
    const hash = window.location.hash
    if (hash.includes('token=')) {
      const token = hash.split('token=')[1]?.split('&')[0]
      if (token) {
        localStorage.setItem('captain_token', token)
        window.location.hash = ''
      }
    }

    // Check health to see if auth is enabled
    fetch(`${BASE}/api/health`)
      .then(r => r.json())
      .then(h => {
        if (!h.auth) {
          setAuthEnabled(false)
          setUser({ name: 'Local', avatar: '' })
          setChecking(false)
          return
        }
        setAuthEnabled(true)
        // Validate stored token
        const token = localStorage.getItem('captain_token')
        if (!token) { setChecking(false); return }
        return fetch(`${BASE}/api/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        }).then(r => {
          if (!r.ok) { localStorage.removeItem('captain_token'); setChecking(false); return }
          return r.json().then(u => { setUser(u); setChecking(false) })
        })
      })
      .catch(() => {
        // If health check fails, assume local mode
        setUser({ name: 'Local', avatar: '' })
        setChecking(false)
      })
  }, [])

  async function login() {
    const r = await fetch(`${BASE}/api/auth/feishu/login`)
    const { url } = await r.json()
    if (url) window.location.href = url
  }

  function logout() {
    localStorage.removeItem('captain_token')
    setUser(null)
  }

  return { user, checking, authEnabled, login, logout }
}

export default function App() {
  const { user, checking, authEnabled, login, logout } = useAuth()
  const [data, setData] = useState<AppData | null>(null)
  const [opFilter, setOpFilter] = useState<OperationStatus>('进行中')
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [selectedCondition, setSelectedCondition] = useState<Condition | null>(null)
  const [drawerTab, setDrawerTab] = useState<'线' | '点'>('线')
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState('')

  useEffect(() => {
    fetch(`${BASE}/data.json`).then(r => r.json()).then(setData)
  }, [])

  async function handleSync() {
    setSyncing(true)
    setSyncMsg('')
    try {
      const token = localStorage.getItem('captain_token')
      const res = await fetch(`${BASE}/api/sync`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const body = await res.json()
      if (body.ok && body.data) {
        setData(body.data)
        setSyncMsg(`已同步 ${body.projects} 项目 · ${body.tasks} 任务`)
      } else {
        setSyncMsg(`同步失败: ${body.error || 'unknown'}`)
      }
    } catch (e) {
      setSyncMsg(`网络错误: ${e}`)
    } finally {
      setSyncing(false)
      setTimeout(() => setSyncMsg(''), 5000)
    }
  }

  async function handleConfirmMilestone(milestoneId: string) {
    const token = localStorage.getItem('captain_token')
    const res = await fetch(`${BASE}/api/confirm-milestone`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ milestoneId }),
    })
    const body = await res.json()
    if (body.ok) {
      fetch(`${BASE}/data.json`).then(r => r.json()).then(setData)
    }
    return body
  }

  // Auth gate
  if (checking) return (
    <div className="flex items-center justify-center min-h-screen text-lg text-slate-400 font-sans">验证中...</div>
  )
  if (authEnabled && !user) return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-6 bg-[var(--color-brand-50)]">
      <img src="favicon.png" alt="赞意" className="w-16 h-16 rounded-2xl shadow-lg" />
      <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">AI Captain 项目驾驶舱</h1>
      <button
        onClick={login}
        className="flex items-center gap-2 px-6 py-3 rounded-xl text-base font-medium bg-[var(--color-brand)] text-white hover:bg-[var(--color-brand-dark)] transition-all shadow-lg shadow-purple-200"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
        飞书登录
      </button>
    </div>
  )

  if (!data) return (
    <div className="flex items-center justify-center min-h-screen text-lg text-slate-400 font-sans">加载中...</div>
  )

  const visibleProjects = data.projects.filter(p => p.operationStatus === opFilter)

  const counts = {
    total: data.projects.filter(p => p.operationStatus === '进行中').length,
    red: data.projects.filter(p => p.operationStatus === '进行中' && p.status === 'red').length,
    blocked: data.tasks.filter(t => t.status === 'blocked').length,
    totalTasks: data.tasks.length,
    doneTasks: data.tasks.filter(t => t.status === 'done').length,
  }

  function selectProject(p: Project) {
    setSelectedProject(p)
    setSelectedCondition(null)
    setDrawerTab('线')
  }

  function selectCondition(c: Condition) {
    setSelectedCondition(prev => prev?.id === c.id ? null : c)
  }

  function closeDrawer() {
    setSelectedProject(null)
    setSelectedCondition(null)
  }

  const drawerConditions = selectedProject
    ? data.conditions.filter(c => c.projectId === selectedProject.id)
    : []

  const drawerMilestones = selectedProject
    ? (data.milestones ?? []).filter(m => m.projectId === selectedProject.id)
    : []

  const drawerTasks = selectedProject
    ? data.tasks.filter(t => t.projectId === selectedProject.id)
    : []

  const drawerOpen = !!selectedProject

  return (
    <div
      className="shell relative min-h-screen px-8 py-6 pb-10 bg-[var(--color-brand-50)]"
      onClick={e => { if ((e.target as HTMLElement).classList.contains('shell')) closeDrawer() }}
    >
      {/* ── Sticky Top: Header + Filters + Stage Headers ── */}
      <div className="sticky top-0 z-30 -mx-8 px-8 -mt-6 pt-6 pb-3 bg-[var(--color-brand-50)]/95 backdrop-blur-sm">
        <header className="flex items-center justify-between mb-4 gap-4 flex-wrap bg-white/80 backdrop-blur-sm rounded-2xl px-6 py-3 shadow-sm border border-white/60">
          <div className="flex items-center gap-3">
            <img src="favicon.png" alt="赞意" className="w-10 h-10 rounded-xl shadow-md" />
            <div>
              <span className="text-[10px] font-semibold tracking-wide uppercase text-[var(--color-brand)]">AI Captain</span>
              <h1 className="text-xl font-bold leading-tight text-[var(--color-text-primary)]">项目驾驶舱</h1>
            </div>
          </div>
          <div className="flex gap-3 flex-wrap items-center">
            <StatChip label="进行中" value={counts.total} />
            <StatChip label="红灯" value={counts.red} tone="red" />
            <StatChip label="阻塞" value={counts.blocked} tone="amber" />
            <StatChip
              label="任务完成率"
              value={counts.totalTasks > 0 ? Math.round((counts.doneTasks / counts.totalTasks) * 100) : 0}
              suffix="%"
            />
            <button
              onClick={handleSync}
              disabled={syncing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm font-medium bg-[var(--color-brand)] text-white hover:bg-[var(--color-brand-dark)] disabled:opacity-50 transition-all shadow-sm"
              title="从 GitHub 拉取最新数据"
            >
              <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
              {syncing ? '同步中...' : '刷新'}
            </button>
            {syncMsg && (
              <span className={`text-xs px-2 py-1 rounded-lg ${syncMsg.includes('失败') || syncMsg.includes('错误') ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-600'}`}>
                {syncMsg}
              </span>
            )}
            {user && authEnabled && (
              <div className="flex items-center gap-2 ml-2 pl-2 border-l border-slate-200">
                {user.avatar ? (
                  <img src={user.avatar} className="w-7 h-7 rounded-full" alt="" />
                ) : (
                  <div className="w-7 h-7 rounded-full bg-[var(--color-brand-100)] flex items-center justify-center text-xs font-bold text-[var(--color-brand)]">
                    {user.name?.[0] || '?'}
                  </div>
                )}
                <span className="text-xs text-slate-500">{user.name}</span>
                <button onClick={logout} className="text-[11px] text-slate-400 hover:text-red-500 transition-colors">退出</button>
              </div>
            )}
          </div>
        </header>

        {/* ── Op Status Filter ────────────────────── */}
        <div className="flex gap-2 mb-3 flex-wrap">
          {OP_STATUSES.map(s => (
            <button
              key={s}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium border transition-all shadow-sm
                ${opFilter === s
                  ? 'bg-[var(--color-brand)] text-white border-[var(--color-brand)] shadow-purple-200'
                  : 'bg-white border-slate-200 text-slate-500 hover:border-[var(--color-brand-light)] hover:text-[var(--color-brand)] hover:shadow-md'
                }`}
              onClick={() => setOpFilter(s)}
            >
              {s}
              <span className={`text-[11px] font-bold min-w-[20px] h-5 inline-flex items-center justify-center rounded-full
                ${opFilter === s ? 'bg-white/25' : 'bg-black/[0.06]'}`}>
                {data.projects.filter(p => p.operationStatus === s).length}
              </span>
            </button>
          ))}
        </div>

        {/* ── Stage Column Headers (frozen, hidden on mobile — inline labels used instead) ─────────── */}
        <div className={`grid grid-cols-4 gap-5 transition-all duration-300 max-md:hidden
          ${drawerOpen ? 'mr-[460px]' : ''}
          max-lg:grid-cols-2
          ${drawerOpen ? 'max-lg:mr-0' : ''}`}
        >
          {STAGES.map(stage => {
            const count = visibleProjects.filter(p => p.stage === stage).length
            const cfg = STAGE_CONFIG[stage]
            const StageIcon = cfg.Icon
            return (
              <div key={stage} className={`relative overflow-hidden rounded-xl bg-white border border-slate-200 shadow-sm ${count === 0 ? 'opacity-60' : ''}`}>
                <div className="h-1 w-full" style={{ background: cfg.color }} />
                <div className="flex items-center gap-2.5 px-4 py-2.5">
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: `${cfg.color}15` }}>
                    <StageIcon size={15} style={{ color: cfg.color }} />
                  </div>
                  <span className="text-sm font-semibold text-[var(--color-text-primary)]">{stage}</span>
                  <span className="relative group cursor-help">
                    <Info size={13} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors" />
                    <span className="absolute left-1/2 -translate-x-1/2 top-6 z-50 w-52 px-3 py-2 rounded-lg bg-slate-800 text-white text-xs leading-relaxed shadow-lg opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-opacity whitespace-normal">
                      {STAGE_DESC[stage]}
                    </span>
                  </span>
                  <span
                    className="text-xs font-bold ml-auto px-2.5 py-0.5 rounded-full"
                    style={{ background: `${cfg.color}15`, color: cfg.color }}
                  >
                    {count}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Stage Board Cards (scrollable) ──────────── */}
      <div className={`grid grid-cols-4 gap-5 mt-3 transition-all duration-300
        ${drawerOpen ? 'mr-[460px]' : ''}
        max-lg:grid-cols-2 max-md:grid-cols-1
        ${drawerOpen ? 'max-lg:mr-0' : ''}`}
      >
        {STAGES.map(stage => {
          const stageProjects = visibleProjects.filter(p => p.stage === stage)
          const isEmpty = stageProjects.length === 0
          const cfg = STAGE_CONFIG[stage]
          return (
            <div key={stage} className={`flex flex-col gap-3 min-w-0 ${isEmpty ? 'opacity-60' : ''}`}>
              {/* Mobile stage label — hidden on desktop where columns already have headers */}
              <div className="hidden max-lg:flex items-center gap-2 px-1 pt-2">
                <div className="w-2 h-2 rounded-full" style={{ background: cfg.color }} />
                <span className="text-xs font-semibold text-[var(--color-text-secondary)]">{stage}</span>
                <span className="text-[10px] text-[var(--color-text-muted)]">({stageProjects.length})</span>
              </div>
              {isEmpty && (
                <div className="p-8 text-center text-sm text-[var(--color-text-muted)] border-2 border-dashed border-slate-200 rounded-xl bg-white/50">
                  暂无项目
                </div>
              )}
              {stageProjects.map(p => (
                <ProjectCard
                  key={p.id}
                  project={p}
                  active={selectedProject?.id === p.id}
                  tasks={data.tasks.filter(t => t.projectId === p.id)}
                  conditions={data.conditions.filter(c => c.projectId === p.id)}
                  stageColor={cfg.color}
                  onClick={() => selectProject(p)}
                />
              ))}
            </div>
          )
        })}
      </div>

      {/* ── Drawer ───────────────────────────────── */}
      {selectedProject && (
        <aside className="fixed top-0 right-0 bottom-0 w-[440px] max-md:w-full max-lg:max-w-[440px] bg-white border-l border-slate-200 flex flex-col z-50 overflow-y-auto animate-slide-in shadow-2xl shadow-slate-300/50">
          {/* Drawer Head */}
          <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b border-slate-200 sticky top-0 bg-white z-10">
            <div className="flex items-start gap-3 flex-1">
              <ProjectIcon id={selectedProject.id} size={28} />
              <div>
                <p className="text-[11px] font-semibold tracking-wide uppercase text-[var(--color-brand)]">
                  {selectedProject.stage} → {selectedProject.targetStage}
                </p>
                <h2 className="text-base font-bold leading-snug">{selectedProject.name}</h2>
                {selectedProject.captain && selectedProject.captain !== '待确认' && (
                  <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                    Captain: {selectedProject.captain}
                  </p>
                )}
              </div>
            </div>
            <button
              className="w-8 h-8 rounded-lg flex items-center justify-center text-[var(--color-text-muted)] hover:bg-slate-100 hover:text-[var(--color-text-primary)] transition-colors"
              onClick={closeDrawer}
            >
              <X size={16} />
            </button>
          </div>

          {/* Drawer Tabs */}
          <div className="flex border-b border-slate-200 sticky top-[73px] bg-white z-10">
            {(['线', '点'] as const).map(tab => (
              <button
                key={tab}
                className={`flex-1 px-4 py-2.5 text-[13px] font-medium border-b-2 transition-colors
                  ${drawerTab === tab
                    ? 'text-[var(--color-brand)] border-[var(--color-brand)]'
                    : 'text-[var(--color-text-secondary)] border-transparent hover:text-[var(--color-text-primary)]'
                  }`}
                onClick={() => setDrawerTab(tab)}
              >
                {tab === '线' ? '线 · 升级路径' : `点 · 任务 (${drawerTasks.length})`}
              </button>
            ))}
          </div>

          {/* Drawer Content */}
          <div className="px-6 py-4 flex-1">
            {drawerTab === '线' && (
              <>
                {drawerConditions.length === 0 ? (
                  <EmptyConditions />
                ) : (
                  <UpgradePath
                    conditions={drawerConditions}
                    milestones={drawerMilestones}
                    selected={selectedCondition}
                    onSelect={selectCondition}
                    tasks={drawerTasks}
                    onConfirmMilestone={handleConfirmMilestone}
                  />
                )}
                <ProjectDetail project={selectedProject} />
              </>
            )}

            {drawerTab === '点' && (
              <TaskList
                tasks={drawerTasks}
                conditions={drawerConditions}
                activeConditionId={selectedCondition?.id ?? null}
                onConditionClick={c => { setSelectedCondition(c); setDrawerTab('线') }}
              />
            )}
          </div>
        </aside>
      )}
    </div>
  )
}

// ── Project Icon ────────────────────────────────────────
function ProjectIcon({ id, size = 18 }: { id: string; size?: number }) {
  const Icon = PROJECT_ICONS[id] || Package
  return <Icon size={size} className="text-[var(--color-brand)] flex-shrink-0" />
}

// ── Project Card ────────────────────────────────────────
function ProjectCard({
  project, active, tasks, conditions, stageColor, onClick
}: {
  project: Project
  active: boolean
  tasks: Task[]
  conditions: Condition[]
  stageColor: string
  onClick: () => void
}) {
  const done    = tasks.filter(t => t.status === 'done').length
  const blocked = tasks.filter(t => t.status === 'blocked').length
  const active_ = tasks.filter(t => t.status === 'active').length
  const total   = tasks.length

  const condDone  = conditions.filter(c => c.status === 'done').length
  const condTotal = conditions.length

  const isRed = project.status === 'red'

  return (
    <button
      className={`flex flex-col gap-2.5 text-left p-4 rounded-2xl bg-white border border-l-[4px] shadow-sm
        hover:shadow-md hover:-translate-y-0.5 transition-all w-full
        ${active
          ? 'border-slate-300 bg-[var(--color-brand-50)] shadow-md ring-2 ring-[var(--color-brand)]/20'
          : isRed
            ? 'border-slate-200 border-l-[var(--color-risk)] shadow-red-100'
            : 'border-slate-200 border-l-transparent hover:border-l-[var(--color-brand-light)]'
        }`}
      onClick={onClick}
      type="button"
      style={active ? { borderLeftColor: stageColor } : undefined}
    >
      {/* Head */}
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-[var(--color-brand-50)] flex items-center justify-center">
          <ProjectIcon id={project.id} />
        </div>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${STATUS_DOT[project.status] || 'bg-slate-300'}
            ${isRed ? 'ring-2 ring-red-200 animate-pulse' : ''}`} />
          <span className="text-sm font-semibold text-[var(--color-text-primary)] truncate">{project.name}</span>
        </div>
      </div>

      {/* People */}
      <div className="flex gap-3 flex-wrap pl-[42px]">
        <PersonChip label="业务" name={project.sponsor} />
        <PersonChip label="Dev" name={project.captain} />
      </div>

      {/* Blocker */}
      {project.blocker && project.blocker !== '待确认' && (
        <div className="text-xs text-[var(--color-risk)] px-3 py-1.5 bg-red-50 rounded-lg flex items-center gap-1.5 border border-red-100">
          <AlertTriangle size={12} /> {project.blocker}
        </div>
      )}

      {/* Condition progress bar */}
      {condTotal > 0 && (
        <div className="flex flex-col gap-1.5 mt-0.5">
          <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
            <div className="h-full bg-gradient-to-r from-[var(--color-brand)] to-[var(--color-brand-light)] rounded-full transition-[width] duration-300"
              style={{ width: `${(condDone / condTotal) * 100}%` }} />
          </div>
          <span className="text-[11px] text-[var(--color-text-muted)] font-medium">路径 {condDone}/{condTotal}</span>
        </div>
      )}

      {/* Task progress bar */}
      {total > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="h-1.5 rounded-full bg-slate-100 flex overflow-hidden">
            <div className="h-full bg-[var(--color-good)]" style={{ width: `${(done/total)*100}%` }} />
            <div className="h-full bg-[var(--color-brand-light)]" style={{ width: `${(active_/total)*100}%` }} />
            <div className="h-full bg-[var(--color-risk)]" style={{ width: `${(blocked/total)*100}%` }} />
          </div>
          <div className="flex justify-between text-[11px] text-[var(--color-text-muted)] font-medium">
            <span>{done}/{total} 完成</span>
            {blocked > 0 && (
              <span className="text-[var(--color-risk)] font-semibold flex items-center gap-0.5">
                <AlertTriangle size={10} /> {blocked}
              </span>
            )}
          </div>
        </div>
      )}
    </button>
  )
}

function PersonChip({ label, name }: { label: string; name: string }) {
  const unassigned = !name || name === '待确认'
  return (
    <span className={`text-[11px] flex gap-1 ${unassigned ? 'text-[var(--color-warn)] italic' : 'text-[var(--color-text-secondary)]'}`}>
      <span className="font-semibold text-[10px] uppercase text-[var(--color-text-muted)]">{label}</span>
      {unassigned ? '待确认' : name}
    </span>
  )
}

// ── Condition Node ─────────────────────────────────────────
function ConditionNode({
  c, isLast, selected, onSelect, tasks
}: {
  c: Condition
  isLast: boolean
  selected: Condition | null
  onSelect: (c: Condition) => void
  tasks: Task[]
}) {
  const isExpanded = selected?.id === c.id
  return (
    <div className="relative">
      <button
        className={`flex items-start gap-3 px-3 py-2.5 rounded-[10px] w-full text-left transition-colors
          ${isExpanded ? 'bg-[var(--color-brand-100)]' : 'hover:bg-slate-50'}`}
        onClick={() => onSelect(c)}
        type="button"
      >
        <div className="relative flex flex-col items-center flex-shrink-0">
          <div className={`w-2.5 h-2.5 rounded-full mt-[5px] border-2 relative z-[1]
            ${c.status === 'done' ? 'bg-[var(--color-good)] border-[var(--color-good)]' :
              c.status === 'active' ? 'bg-[var(--color-brand)] border-[var(--color-brand)]' :
              c.status === 'blocked' ? 'bg-[var(--color-risk)] border-[var(--color-risk)]' :
              'bg-white border-slate-300'}`}
          />
          {!isLast && (
            <div className="absolute left-1/2 -translate-x-1/2 top-[18px] w-0.5 bg-slate-200 z-0"
              style={{ height: 'calc(100% + 8px)' }} />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[13px] font-medium">{c.name}</span>
            <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-md flex-shrink-0 ${COND_BADGE[c.status]}`}>
              {COND_STATUS_LABEL[c.status]}
            </span>
          </div>
          <div className="flex gap-2 mt-1 text-[11px] text-[var(--color-text-muted)]">
            {c.owner && c.owner !== '待确认' && <span className="font-medium">{c.owner}</span>}
            {c.dueDate && <DueDate date={c.dueDate} done={c.status === 'done'} />}
          </div>
        </div>
        {isExpanded
          ? <ChevronDown size={14} className="text-[var(--color-text-muted)] flex-shrink-0 mt-1" />
          : <ChevronRight size={14} className="text-[var(--color-text-muted)] flex-shrink-0 mt-1" />
        }
      </button>
      {isExpanded && (
        <div className="pl-[34px] py-1 pb-2">
          {tasks.length === 0 ? (
            <div className="text-xs text-[var(--color-text-muted)] py-1.5">暂无关联任务</div>
          ) : (
            tasks.map(t => (
              <div key={t.id} className="flex items-center gap-2 py-1 text-xs">
                <span className={`w-[7px] h-[7px] rounded-full flex-shrink-0 ${COND_DOT[t.status as ConditionStatus] || 'bg-slate-300'}`} />
                <span className="flex-1 min-w-0 truncate">{t.title}</span>
                {t.url && (
                  <a href={t.url} target="_blank" rel="noreferrer"
                    className="text-[var(--color-brand)] hover:opacity-70 transition-opacity">
                    <ExternalLink size={12} />
                  </a>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ── Upgrade Path (线) ─────────────────────────────────────
function UpgradePath({
  conditions, milestones, selected, onSelect, tasks, onConfirmMilestone
}: {
  conditions: Condition[]
  milestones: Milestone[]
  selected: Condition | null
  onSelect: (c: Condition) => void
  tasks: Task[]
  onConfirmMilestone: (milestoneId: string) => Promise<{ok: boolean}>
}) {
  const done = conditions.filter(c => c.status === 'done').length
  const pct = conditions.length ? Math.round((done / conditions.length) * 100) : 0

  const tasksByCondition = new Map<string, Task[]>()
  for (const t of tasks) {
    if (!t.conditionId) continue
    const arr = tasksByCondition.get(t.conditionId) ?? []
    arr.push(t)
    tasksByCondition.set(t.conditionId, arr)
  }

  const [confirming, setConfirming] = useState<string | null>(null)
  const [confirmMsg, setConfirmMsg] = useState<Record<string, string>>({})

  async function handleConfirm(milestoneId: string) {
    setConfirming(milestoneId)
    try {
      const res = await onConfirmMilestone(milestoneId)
      setConfirmMsg(prev => ({ ...prev, [milestoneId]: res.ok ? '已同步到 GitHub ✓' : '同步失败' }))
    } finally {
      setConfirming(null)
      setTimeout(() => setConfirmMsg(prev => { const n = {...prev}; delete n[milestoneId]; return n }), 4000)
    }
  }

  // Group conditions by milestone
  const ungrouped = conditions.filter(c => !c.milestoneId)
  const byMilestone = milestones.map(m => ({
    milestone: m,
    conds: conditions.filter(c => c.milestoneId === m.id),
  })).filter(g => g.conds.length > 0)

  const renderConditions = (conds: Condition[]) =>
    conds.map((c, i) => (
      <ConditionNode
        key={c.id}
        c={c}
        isLast={i === conds.length - 1}
        selected={selected}
        onSelect={onSelect}
        tasks={tasksByCondition.get(c.id) ?? []}
      />
    ))

  return (
    <div className="mb-5">
      {/* Overall progress header */}
      <div className="mb-4">
        <div className="flex justify-between items-center text-xs text-[var(--color-text-secondary)] mb-1.5">
          <span>{done}/{conditions.length} 升级路径</span>
          <span className="font-bold text-[var(--color-brand)] text-sm">{pct}%</span>
        </div>
        <div className="h-1.5 bg-slate-200 rounded-[3px] overflow-hidden">
          <div className="h-full bg-[var(--color-brand)] rounded-[3px] transition-[width] duration-300"
            style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* Milestone groups */}
      {byMilestone.length > 0 ? (
        <div className="flex flex-col gap-4">
          {byMilestone.map(({ milestone: m, conds }) => {
            const mDone = conds.filter(c => c.status === 'done').length
            return (
              <div key={m.id} className={`rounded-[12px] border ${m.confirmed ? 'border-slate-200 bg-white' : 'border-dashed border-slate-300 bg-slate-50/60'}`}>
                {/* Milestone header */}
                <div className="px-3 pt-3 pb-2">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-[11px] font-bold px-2 py-0.5 rounded-md flex-shrink-0 ${m.confirmed ? 'bg-[var(--color-brand)] text-white' : 'bg-slate-200 text-slate-500'}`}>
                        {m.label}
                      </span>
                      <span className="text-[13px] font-semibold text-[var(--color-text-primary)]">{m.title}</span>
                      {!m.confirmed && (
                        <span className="text-[10px] font-medium text-slate-400 border border-slate-300 rounded px-1.5 py-0.5 flex-shrink-0">建议</span>
                      )}
                    </div>
                    <span className="text-[11px] text-[var(--color-text-muted)] flex-shrink-0 mt-0.5">{mDone}/{conds.length}</span>
                  </div>
                  <p className="text-[11px] text-[var(--color-text-muted)] leading-relaxed mb-2">{m.goal}</p>
                  {!m.confirmed && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleConfirm(m.id)}
                        disabled={confirming === m.id}
                        className="text-[11px] font-medium text-white bg-[var(--color-brand)] px-2.5 py-1 rounded-md hover:opacity-80 transition-opacity disabled:opacity-50"
                      >
                        {confirming === m.id ? '同步中...' : '确认并同步 GitHub'}
                      </button>
                      {confirmMsg[m.id] && (
                        <span className="text-[11px] text-[var(--color-good)] font-medium">{confirmMsg[m.id]}</span>
                      )}
                    </div>
                  )}
                </div>
                {/* Conditions */}
                <div className="px-1 pb-1">
                  {renderConditions(conds)}
                </div>
              </div>
            )
          })}
          {/* Ungrouped fallback */}
          {ungrouped.length > 0 && (
            <div className="flex flex-col">{renderConditions(ungrouped)}</div>
          )}
        </div>
      ) : (
        <div className="flex flex-col">{renderConditions(conditions)}</div>
      )}
    </div>
  )
}

function DueDate({ date, done }: { date: string; done: boolean }) {
  const due = new Date(date)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const diffDays = Math.round((due.getTime() - today.getTime()) / 86400000)
  const month = due.getMonth() + 1
  const day = due.getDate()

  let label = `${month}月${day}日`
  if (!done && diffDays < 0) label += ` · 逾期${Math.abs(diffDays)}天`
  else if (!done && diffDays <= 7) label += ` · 还剩${diffDays}天`

  return (
    <span className={`text-[11px] ${!done && diffDays < 0 ? 'text-[var(--color-risk)] font-semibold' : 'text-[var(--color-text-muted)]'}`}>
      {label}
    </span>
  )
}

function EmptyConditions() {
  return (
    <div className="p-6 text-center text-[var(--color-text-muted)] border border-dashed border-slate-200 rounded-[10px]">
      <p className="text-[13px] mb-1">还没有设置升级路径</p>
      <p className="text-xs">在 GitHub 仓库中创建 Milestone 即可自动同步为升级路径</p>
    </div>
  )
}

// ── Project Detail ────────────────────────────────────────
function ProjectDetail({ project }: { project: Project }) {
  return (
    <div className="mt-4">
      <DetailRow label="当前在做" value={project.currentFocus} />
      <DetailRow label="当前卡点" value={project.blocker} tone="risk" />
      <DetailRow label="下个检查点" value={project.nextCheckpoint} />
      {project.latestFeedback && (
        <DetailRow label={`反馈·${project.feedbackFrom}`} value={project.latestFeedback} tone="soft" />
      )}
      {(project.wau > 0 || project.weeklyRuns > 0) && (
        <div className="flex gap-3 mt-3">
          {project.wau > 0 && <Metric label="WAU" value={project.wau} />}
          {project.weeklyRuns > 0 && <Metric label="周运行" value={project.weeklyRuns} />}
          {project.hoursSaved > 0 && <Metric label="节省小时" value={project.hoursSaved} />}
        </div>
      )}
    </div>
  )
}

function DetailRow({ label, value, tone = 'default' }: { label: string; value: string; tone?: string }) {
  if (!value || value === '待确认') return null
  return (
    <div className="py-2.5 border-b border-slate-100">
      <span className="text-[11px] font-semibold text-[var(--color-text-muted)] uppercase">{label}</span>
      <p className={`text-[13px] mt-1 leading-relaxed
        ${tone === 'risk' ? 'text-[var(--color-risk)]' : ''}
        ${tone === 'soft' ? 'text-[var(--color-text-secondary)] italic' : ''}`}
      >{value}</p>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex-1 text-center p-3 bg-[var(--color-brand-50)] rounded-[10px]">
      <strong className="block text-xl text-[var(--color-brand)]">{value}</strong>
      <span className="text-[11px] text-[var(--color-text-secondary)]">{label}</span>
    </div>
  )
}

// ── Task List (点) ────────────────────────────────────────
function TaskList({
  tasks, conditions, activeConditionId, onConditionClick
}: {
  tasks: Task[]
  conditions: Condition[]
  activeConditionId: string | null
  onConditionClick: (c: Condition) => void
}) {
  const activeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (activeConditionId && activeRef.current) {
      activeRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [activeConditionId])

  if (tasks.length === 0) return (
    <div className="p-6 text-center text-[13px] text-[var(--color-text-muted)]">暂无任务</div>
  )

  const condMap = new Map(conditions.map(c => [c.id, c]))

  const byCondition = new Map<string, Task[]>()
  for (const t of tasks) {
    if (t.conditionId && condMap.has(t.conditionId)) {
      const arr = byCondition.get(t.conditionId) ?? []
      arr.push(t)
      byCondition.set(t.conditionId, arr)
    }
  }

  const unlinked = tasks.filter(t => !t.conditionId || !condMap.has(t.conditionId))
  const byStatus: Record<TaskStatus, Task[]> = { blocked: [], active: [], pending: [], done: [] }
  for (const t of unlinked) byStatus[t.status].push(t)

  const hasLinked = [...byCondition.values()].some(arr => arr.length > 0)

  const STATUS_GROUP_COLORS: Record<TaskStatus, string> = {
    blocked: 'text-[var(--color-risk)]',
    active: 'text-[var(--color-brand)]',
    done: 'text-[var(--color-good)]',
    pending: 'text-[var(--color-text-muted)]',
  }

  return (
    <div className="flex flex-col gap-0.5">
      {conditions.map(c => {
        const condTasks = byCondition.get(c.id)
        if (!condTasks?.length) return null
        const isActive = c.id === activeConditionId
        return (
          <div
            key={c.id}
            className={`mb-3 ${isActive ? 'bg-[var(--color-brand-50)] rounded-lg p-1' : ''}`}
            ref={isActive ? activeRef : null}
          >
            <button
              className="flex items-center justify-between w-full px-2.5 py-2 rounded-lg text-xs font-semibold text-[var(--color-text-secondary)] hover:bg-slate-100 transition-colors"
              onClick={() => onConditionClick(c)}
              title="点击跳回升级路径"
              type="button"
            >
              <span className="flex items-center gap-1.5">
                <span className={`w-[7px] h-[7px] rounded-full inline-block ${COND_DOT[c.status]}`} />
                {c.name}
              </span>
              <span className="flex items-center gap-2">
                <span className="text-[10px] font-bold px-1.5 py-px bg-slate-100 rounded-lg text-[var(--color-text-muted)]">
                  {condTasks.length}
                </span>
                <span className="text-[10px] text-[var(--color-brand)] opacity-0 group-hover:opacity-100 transition-opacity">
                  线 <ExternalLink size={9} className="inline" />
                </span>
              </span>
            </button>
            {condTasks.map(t => <TaskRow key={t.id} task={t} />)}
          </div>
        )
      })}

      {hasLinked && unlinked.length > 0 && (
        <div className="text-[11px] font-semibold text-[var(--color-text-muted)] px-2 pt-3 pb-1.5 uppercase tracking-wider border-t border-slate-200 mt-2">
          未关联升级路径
        </div>
      )}

      {(['blocked', 'active', 'pending', 'done'] as TaskStatus[]).map(status => {
        const group = byStatus[status]
        if (!group.length) return null
        return (
          <div key={status} className="mb-3">
            <div className={`flex items-center justify-between px-2 py-1.5 text-xs font-semibold ${STATUS_GROUP_COLORS[status]}`}>
              {TASK_STATUS_LABEL[status]}
              <span className="text-[10px] font-bold px-1.5 py-px bg-slate-100 rounded-lg text-[var(--color-text-muted)]">
                {group.length}
              </span>
            </div>
            {group.map(t => <TaskRow key={t.id} task={t} />)}
          </div>
        )
      })}
    </div>
  )
}

function TaskRow({ task: t }: { task: Task }) {
  return (
    <div className="flex items-center justify-between px-2.5 py-1.5 rounded-md hover:bg-slate-50 transition-colors">
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <span className={`w-[7px] h-[7px] rounded-full flex-shrink-0 ${COND_DOT[t.status as ConditionStatus] || 'bg-slate-300'}`} />
        <span className={`text-[13px] truncate ${t.status === 'done' ? 'line-through text-[var(--color-text-muted)]' : ''}`}>
          {t.title}
        </span>
      </div>
      <div className="flex items-center gap-2 text-[11px] text-[var(--color-text-muted)] flex-shrink-0">
        {t.assignee && t.assignee !== '待确认' && <span>{t.assignee}</span>}
        {t.url && (
          <a href={t.url} target="_blank" rel="noreferrer"
            className="text-[var(--color-brand)] hover:opacity-70 transition-opacity">
            GitHub
          </a>
        )}
      </div>
    </div>
  )
}

// ── Stat Chip ─────────────────────────────────────────────
function StatChip({ label, value, tone, suffix }: { label: string; value: number; tone?: string; suffix?: string }) {
  const valueColor = tone === 'red' ? 'text-[var(--color-risk)]'
    : tone === 'amber' ? 'text-[var(--color-warn)]'
    : 'text-[var(--color-brand)]'

  const bgTone = tone === 'red' ? 'bg-red-50 border-red-100'
    : tone === 'amber' ? 'bg-amber-50 border-amber-100'
    : 'bg-white border-slate-200'

  return (
    <div className={`flex flex-col items-center px-5 py-2.5 rounded-xl min-w-[80px] border shadow-sm hover:shadow-md transition-all ${bgTone}`}>
      <strong className={`text-2xl font-bold leading-tight font-mono ${valueColor}`}>
        {value}{suffix || ''}
      </strong>
      <span className="text-[11px] text-[var(--color-text-secondary)] font-medium">{label}</span>
    </div>
  )
}
