import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  GitBranch,
  Plus,
  Sparkles,
  Timer,
  Workflow,
} from 'lucide-react'
import clsx from 'clsx'
import { KpiCard } from '@/components/KpiCard'
import { SearchBar } from '@/components/SearchBar'
import { StatusBadge } from '@/components/StatusBadge'

type AccKey = 'rev' | 'lead' | 'post' | 'onb' | 'gov'

export default function ProcessesPage() {
  const [open, setOpen] = useState<Record<AccKey, boolean>>({
    rev: false,
    lead: true,
    post: false,
    onb: false,
    gov: false,
  })
  const [q, setQ] = useState('')

  function toggle(key: AccKey) {
    setOpen((s) => ({ ...s, [key]: !s[key] }))
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-navy-900">Business Processes</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            End-to-end operational map with automation coverage, latency hotspots, and agent-assisted steps.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/processes/map"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
          >
            <GitBranch className="h-4 w-4" />
            Process Map
          </Link>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-lg bg-navy-800 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900"
          >
            <Plus className="h-4 w-4" />
            + Add New Process
          </button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard icon={Workflow} label="Total Active Workflows" value="142" sublabel="Across 6 business domains" />
        <KpiCard icon={Activity} label="Automation Coverage" value="84.2%" trend="up" trendLabel="+4.1% vs last quarter" />
        <KpiCard icon={AlertTriangle} label="Critical Bottlenecks" value="7" sublabel="SLA risk in next 30 days" />
      </div>

      <div className="max-w-xl">
        <SearchBar
          value={q}
          onChange={setQ}
          placeholder="Search processes, owners, or systems…"
        />
      </div>

      <div className="space-y-3">
        <AccordionRow
          title="Revenue Operations"
          meta="4 sub-processes · 12 assets · High impact"
          status="OPTIMIZED"
          expanded={open.rev}
          onToggle={() => toggle('rev')}
          muted={q !== '' && !'revenue operations'.includes(q.toLowerCase())}
        >
          <p className="text-sm text-slate-600">Drill-down content can list child workflows when expanded.</p>
        </AccordionRow>

        <AccordionRow
          title="Lead Management & Qualification"
          meta="6 sub-processes · 32 assets · Partial automation"
          status="NEEDS ATTENTION"
          expanded={open.lead}
          onToggle={() => toggle('lead')}
          muted={q !== '' && !'lead'.includes(q.toLowerCase())}
        >
          <div className="space-y-3">
            <SubProcess
              title="Inbound Lead Routing"
              tags={['Salesforce Flow', 'Apex Trigger']}
              stat="98% success rate"
              tone="ok"
            />
            <SubProcess
              title="Manual Lead Enrichment"
              tags={['Human step', 'CRM']}
              stat="HIGH LATENCY · 4.2H avg"
              tone="bad"
              action={
                <button
                  type="button"
                  className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-red-700"
                >
                  Automate Now
                </button>
              }
            />
            <SubProcess
              title="AI Lead Scoring"
              tags={['Einstein Discovery', 'Active Agent']}
              stat="Model v3.2 in production"
              tone="ai"
            />
          </div>
        </AccordionRow>

        <AccordionRow
          title="Post-Sale & Retention"
          meta="2 sub-processes · 8 assets · Low volume"
          status="DRAFT"
          expanded={open.post}
          onToggle={() => toggle('post')}
          muted={q !== '' && !'post-sale'.includes(q.toLowerCase()) && !'retention'.includes(q.toLowerCase())}
        >
          <p className="text-sm text-slate-600">Lifecycle playbooks are still being modeled.</p>
        </AccordionRow>

        <AccordionRow
          title="Customer Onboarding"
          meta="5 sub-processes · 18 assets · High impact"
          status="OPTIMIZED"
          expanded={open.onb}
          onToggle={() => toggle('onb')}
          muted={q !== '' && !'onboarding'.includes(q.toLowerCase())}
        >
          <p className="text-sm text-slate-600">Provisioning, KYC handoffs, and welcome journeys.</p>
        </AccordionRow>

        <AccordionRow
          title="Data Governance & Compliance"
          meta="3 sub-processes · 22 assets · Partial automation"
          status="NEEDS ATTENTION"
          expanded={open.gov}
          onToggle={() => toggle('gov')}
          muted={q !== '' && !'governance'.includes(q.toLowerCase())}
        >
          <p className="text-sm text-slate-600">Policy attestation and lineage checkpoints.</p>
        </AccordionRow>
      </div>
    </div>
  )
}

function AccordionRow({
  title,
  meta,
  status,
  expanded,
  onToggle,
  children,
  muted,
}: {
  title: string
  meta: string
  status: 'OPTIMIZED' | 'NEEDS ATTENTION' | 'DRAFT'
  expanded: boolean
  onToggle: () => void
  children: ReactNode
  muted?: boolean
}) {
  if (muted) return null
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm ring-1 ring-slate-900/5">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start justify-between gap-4 px-5 py-4 text-left hover:bg-slate-50/80"
      >
        <div className="flex items-start gap-3">
          <span className="mt-0.5 text-slate-400">{expanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}</span>
          <div>
            <p className="text-base font-semibold text-navy-900">{title}</p>
            <p className="mt-1 text-sm text-slate-600">{meta}</p>
          </div>
        </div>
        <StatusBadge status={status} />
      </button>
      {expanded ? <div className="border-t border-slate-100 bg-slate-50/40 px-5 py-4">{children}</div> : null}
    </div>
  )
}

function SubProcess({
  title,
  tags,
  stat,
  tone,
  action,
}: {
  title: string
  tags: string[]
  stat: string
  tone: 'ok' | 'bad' | 'ai'
  action?: ReactNode
}) {
  return (
    <div
      className={clsx(
        'flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between',
        tone === 'bad' ? 'border-red-200 bg-red-50/60' : 'border-slate-200 bg-white',
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={clsx(
            'mt-0.5 flex h-9 w-9 items-center justify-center rounded-lg ring-1 ring-inset',
            tone === 'ai' && 'bg-violet-50 text-violet-700 ring-violet-200',
            tone === 'ok' && 'bg-emerald-50 text-emerald-700 ring-emerald-200',
            tone === 'bad' && 'bg-red-100 text-red-800 ring-red-200',
          )}
        >
          {tone === 'ai' ? <Sparkles className="h-4 w-4" /> : tone === 'bad' ? <Timer className="h-4 w-4" /> : <Workflow className="h-4 w-4" />}
        </span>
        <div>
          <p className="font-semibold text-navy-900">{title}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {tags.map((t) => (
              <span
                key={t}
                className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-slate-700 ring-1 ring-slate-200/80"
              >
                {t}
              </span>
            ))}
          </div>
          <p className={clsx('mt-2 text-xs font-semibold', tone === 'bad' ? 'text-red-800' : 'text-slate-600')}>
            {stat}
          </p>
        </div>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
}
