import { Building2, GitBranch, Landmark, Users } from 'lucide-react'

type OrgNode = { name: string; title: string; children?: OrgNode[] }

const profile = {
  name: 'Northwind Financial Group',
  industry: 'Insurance & Wealth',
  employees: '4,200',
  hq: 'Chicago, IL',
}

const hierarchy: OrgNode[] = [
  {
    name: 'Chief Operating Officer',
    title: 'Sarah Chen',
    children: [
      {
        name: 'Revenue Operations',
        title: 'Jordan Lee',
        children: [
          { name: 'Sales Systems', title: 'Priya Desai' },
          { name: 'Partner Ops', title: 'Marcus Holt' },
        ],
      },
      {
        name: 'Customer Success',
        title: 'Elena Ruiz',
        children: [{ name: 'Digital Onboarding', title: 'Noah Park' }],
      },
    ],
  },
]

function TreeNode({ node, depth = 0 }: { node: OrgNode; depth?: number }) {
  return (
    <li className="space-y-2">
      <div
        className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm"
        style={{ marginLeft: depth * 16 }}
      >
        <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-md bg-navy-50 text-navy-800">
          <Users className="h-4 w-4" />
        </div>
        <div>
          <p className="text-sm font-semibold text-navy-900">{node.name}</p>
          <p className="text-xs text-slate-500">{node.title}</p>
        </div>
      </div>
      {node.children?.length ? (
        <ul className="space-y-2 border-l border-dashed border-slate-200 pl-4">
          {node.children.map((c) => (
            <TreeNode key={c.name} node={c} depth={depth + 1} />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

export default function OrganizationPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-navy-900">Organization</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Business entity profiling, operating structure, and human-capital cost modeling across connected systems.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5 lg:col-span-1">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-navy-800 text-white shadow">
              <Building2 className="h-6 w-6" />
            </span>
            <div>
              <h2 className="text-lg font-semibold text-navy-900">Business Profile</h2>
              <p className="text-xs text-slate-500">Synced snapshot</p>
            </div>
          </div>
          <dl className="mt-6 space-y-4 text-sm">
            <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
              <dt className="text-slate-500">Company</dt>
              <dd className="font-medium text-slate-900">{profile.name}</dd>
            </div>
            <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
              <dt className="text-slate-500">Industry</dt>
              <dd className="font-medium text-slate-900">{profile.industry}</dd>
            </div>
            <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
              <dt className="text-slate-500">Employees</dt>
              <dd className="font-medium text-slate-900">{profile.employees}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-slate-500">Headquarters</dt>
              <dd className="font-medium text-slate-900">{profile.hq}</dd>
            </div>
          </dl>
        </section>

        <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5 lg:col-span-2">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <GitBranch className="h-6 w-6 text-navy-700" />
              <div>
                <h2 className="text-lg font-semibold text-navy-900">Org hierarchy</h2>
                <p className="text-sm text-slate-600">Leadership tree with key operational pillars</p>
              </div>
            </div>
          </div>
          <div className="mt-6 max-h-[420px] overflow-auto pr-2">
            <ul className="space-y-3">
              {hierarchy.map((n) => (
                <TreeNode key={n.name} node={n} />
              ))}
            </ul>
          </div>
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-200/80 bg-navy-800 p-6 text-white shadow-md ring-1 ring-black/10">
          <div className="flex items-center gap-3">
            <Landmark className="h-6 w-6 text-orange-300" />
            <div>
              <h2 className="text-lg font-semibold">Cost modeling</h2>
              <p className="text-sm text-slate-200">Annualized IT + labor baseline</p>
            </div>
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <div className="rounded-lg bg-white/5 p-4 ring-1 ring-white/10">
              <p className="text-xs uppercase tracking-wide text-slate-300">Annual IT spend</p>
              <p className="mt-2 text-2xl font-semibold">$48.2M</p>
              <p className="mt-1 text-xs text-emerald-200">−3.1% YoY efficiency</p>
            </div>
            <div className="rounded-lg bg-white/5 p-4 ring-1 ring-white/10">
              <p className="text-xs uppercase tracking-wide text-slate-300">Labor hours (ops)</p>
              <p className="mt-2 text-2xl font-semibold">1.05M</p>
              <p className="mt-1 text-xs text-slate-200">Attributable to manual workflows</p>
            </div>
            <div className="rounded-lg bg-white/5 p-4 ring-1 ring-white/10">
              <p className="text-xs uppercase tracking-wide text-slate-300">Automation runway</p>
              <p className="mt-2 text-2xl font-semibold">$9.4M</p>
              <p className="mt-1 text-xs text-orange-200">Projected 24-mo savings</p>
            </div>
          </div>
        </section>

        <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
          <h2 className="text-lg font-semibold text-navy-900">Human capital cost deflection</h2>
          <p className="mt-1 text-sm text-slate-600">
            Estimated hours redirected from swivel-chair work to higher judgment tasks.
          </p>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-emerald-100 bg-emerald-50/60 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Hours reclaimed</p>
              <p className="mt-2 text-3xl font-semibold text-emerald-900">18,400</p>
              <p className="mt-1 text-xs text-emerald-800/90">Per year (enterprise roll-up)</p>
            </div>
            <div className="rounded-lg border border-sky-100 bg-sky-50/60 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-sky-900">Deflection rate</p>
              <p className="mt-2 text-3xl font-semibold text-sky-900">22.6%</p>
              <p className="mt-1 text-xs text-sky-800/90">Of tier-1 operational workload</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
