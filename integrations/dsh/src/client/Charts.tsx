import type { AllocationItem, PositionPoint } from './api.ts'
import type { BeancountKey } from './locales.ts'
import { grouped } from './money.ts'
import css from './Page.module.css'

type T = (key: BeancountKey, values?: Record<string, string | number>) => string

/** The drawing area inside the 320x150 viewBox, leaving room for the axis labels underneath. */
const TOP = 22
const BOTTOM = 126

const number = (value: string | undefined): number | null => {
  if (value === undefined) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const reference = (point: PositionPoint, key: 'assets' | 'liabilities' | 'net'): number | null =>
  number(point[key].reference_value?.number)

/**
 * One scale for all three series so they stay comparable. It always contains zero: a net position below zero then
 * draws below the zero line instead of leaving the chart.
 */
const scaleOf = (values: Array<number | null>) => {
  const known = values.filter((value): value is number => value !== null)
  const low = Math.min(0, ...known)
  const high = Math.max(0, ...known)
  const span = high - low || 1
  const y = (value: number) => BOTTOM - ((value - low) / span) * (BOTTOM - TOP)
  return { y, zero: y(0), negative: low < 0 }
}

const path = (values: Array<number | null>, y: (value: number) => number): string => values
  .map((value, index) => value === null ? null : `${index === 0 || values[index - 1] === null ? 'M' : 'L'} ${16 + index * (288 / Math.max(values.length - 1, 1))} ${y(value)}`)
  .filter(Boolean)
  .join(' ')

export function PositionChart({ points, t }: { points: PositionPoint[]; t: T }) {
  const series = [
    { key: 'assets' as const, label: t('assets') },
    { key: 'liabilities' as const, label: t('liabilities') },
    { key: 'net' as const, label: t('netPosition') },
  ]
  const scale = scaleOf(series.flatMap(item => points.map(point => reference(point, item.key))))
  return (
    <div className={css.chartBlock}>
      <svg className={css.lineChart} viewBox="0 0 320 150" role="img" aria-label={t('positionChart')}>
        <line className={css.chartGrid} x1="16" y1={TOP} x2="304" y2={TOP} />
        <line className={css.chartGrid} x1="16" y1={(TOP + BOTTOM) / 2} x2="304" y2={(TOP + BOTTOM) / 2} />
        <line className={css.chartGrid} x1="16" y1={BOTTOM} x2="304" y2={BOTTOM} />
        {scale.negative && <line className={css.chartZero} x1="16" y1={scale.zero} x2="304" y2={scale.zero} />}
        {series.map(item => <g key={item.key}>
          <path className={`${css.chartLine} ${css[item.key]}`} d={path(points.map(point => reference(point, item.key)), scale.y)} />
          {points.map((point, index) => {
            const value = reference(point, item.key)
            if (value === null) return null
            const x = 16 + index * (288 / Math.max(points.length - 1, 1))
            return <circle key={point.date} className={`${css.chartPoint} ${css[item.key]}`} cx={x} cy={scale.y(value)} r="3"><title>{`${point.date}: ${item.label} ${grouped(point[item.key].reference_value?.number ?? '—')} ${point[item.key].reference_value?.currency ?? ''}`}</title></circle>
          })}
        </g>)}
      </svg>
      <div className={css.legend}>
        {series.map(item => <span key={item.key}><i className={`${css.legendLine} ${css[item.key]}`} />{item.label}</span>)}
      </div>
      <div className={css.axisLabels}><span>{points[0]?.date ?? ''}</span><span>{points.at(-1)?.date ?? ''}</span></div>
    </div>
  )
}

const SEGMENT_COLORS = [
  'var(--dsw-alias-brand-primary)',
  'var(--dsw-alias-state-business-primary)',
  'var(--dsw-alias-state-success-primary)',
  'var(--dsw-alias-label-secondary)',
  'var(--dsw-alias-border-l4)',
]

export function AllocationChart({ items, t }: { items: AllocationItem[]; t: T }) {
  let offset = 0
  const visible = items.filter(item => Number(item.share ?? 0) > 0)
  return (
    <div className={css.allocationLayout}>
      <svg className={css.donut} viewBox="0 0 120 120" role="img" aria-label={t('allocationChart')}>
        <circle className={css.donutTrack} cx="60" cy="60" r="42" />
        {visible.map((item, index) => {
          const share = Number(item.share)
          const start = offset
          offset += share
          return <circle key={item.account} className={css.donutSegment} cx="60" cy="60" r="42" pathLength="100" strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={-start} style={{ stroke: SEGMENT_COLORS[index % SEGMENT_COLORS.length] }}><title>{`${item.account}: ${grouped(item.share ?? '—')}%`}</title></circle>
        })}
      </svg>
      <div className={css.allocationLegend}>
        {items.map((item, index) => <div className={css.allocationRow} key={item.account}>
          <i style={{ background: SEGMENT_COLORS[index % SEGMENT_COLORS.length] }} />
          <span className={css.grow}>{item.account.replace(/^Assets:/, '')}</span>
          <span className={css.amount}>{item.share == null ? '—' : `${grouped(item.share)}%`}</span>
        </div>)}
      </div>
    </div>
  )
}
