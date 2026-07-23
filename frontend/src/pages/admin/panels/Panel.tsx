import type { ReactNode } from 'react'

import { formatAdminNumber } from '../format'

type PanelWidth = 'default' | 'wide' | 'full'

const PANEL_CLASS: Record<PanelWidth, string> = {
  default: 'admin-panel',
  wide: 'admin-panel admin-panel-wide',
  full: 'admin-panel admin-panel-full',
}

export function Panel({
  title,
  width = 'default',
  action,
  children,
}: {
  title: string
  width?: PanelWidth
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <article className={PANEL_CLASS[width]}>
      <div className="admin-panel-head">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </article>
  )
}

export function RowList({ children }: { children: ReactNode }) {
  return <div className="admin-row-list">{children}</div>
}

export function TextRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="admin-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

export function AdminRow({ label, value }: { label: string; value: number }) {
  return <TextRow label={label} value={formatAdminNumber(value)} />
}

export function PathRow({ path, visits }: { path: string; visits: number }) {
  return (
    <div className="admin-row">
      <span title={path}>{path}</span>
      <strong>{formatAdminNumber(visits)}</strong>
    </div>
  )
}

/** Renders `children` when there is something to show, otherwise the empty note. */
export function ListOrEmpty({
  isEmpty,
  emptyText,
  children,
}: {
  isEmpty: boolean
  emptyText: string
  children: ReactNode
}) {
  if (isEmpty) {
    return <p className="admin-empty">{emptyText}</p>
  }
  return <>{children}</>
}
