import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer, LabelList } from 'recharts'

const ZONE_COLORS = ['#4f8ef7', '#f7934f', '#c44fff']

function ScoreRing({ score, color, size = 52 }) {
  const r = 20
  const circ = 2 * Math.PI * r
  const dash = score != null ? Math.min(score / 100, 1) * circ : 0
  return (
    <svg width={size} height={size} viewBox="0 0 52 52" style={{ flexShrink: 0 }}>
      <circle cx="26" cy="26" r={r} fill="none" stroke="#1f2d45" strokeWidth="4" />
      <circle cx="26" cy="26" r={r} fill="none"
        stroke={score != null ? color : '#1f2d45'} strokeWidth="4"
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        transform="rotate(-90 26 26)"
        style={{ transition: 'stroke-dasharray 0.5s ease' }}
      />
      <text x="26" y="30" textAnchor="middle" fill={score != null ? color : '#475569'}
        fontSize="11" fontFamily="DM Mono, monospace" fontWeight="500">
        {score ?? '—'}
      </text>
    </svg>
  )
}

export default function ComparePanel({ compareList, scores, activeIndicateur, onRemove }) {
  if (!activeIndicateur) return null

  const scoreIndex = useMemo(() => {
    const map = new Map()
    scores.forEach(s => {
      const id = s.code_quartier !== undefined
        ? parseInt(s.code_quartier)
        : s.arrondissement !== undefined
          ? parseInt(s.arrondissement)
          : parseInt(s.code_postal) - 75000
      map.set(id, s)
    })
    return map
  }, [scores])

  const getLabel = (id, data) => {
    if (!data) return `Zone ${id}`
    if (data.nom_quartier) return data.nom_quartier
    const arr = data.arrondissement ?? (data.code_postal - 75000)
    return `Paris ${arr}e`
  }

  const zones = useMemo(() => compareList.map((id, i) => {
    const data = scoreIndex.get(parseInt(id)) ?? null
    const bars = (data && activeIndicateur.scoreBars) ? activeIndicateur.scoreBars(data) : []
    return { id, data, color: ZONE_COLORS[i], bars, label: getLabel(id, data) }
  }), [compareList, scoreIndex, activeIndicateur])

  const bestScore = Math.max(...zones.map(z => z.data?.[activeIndicateur.scoreKey] ?? 0))

  const barData = useMemo(() => zones.map(({ label, data, color }) => ({
    label,
    score: data?.[activeIndicateur.scoreKey] ?? 0,
    color,
  })), [zones])

  if (compareList.length === 0) {
    return (
      <div className="compare-bar">
        <div className="compare-bar-empty">Cliquez sur des zones de la carte pour les comparer</div>
      </div>
    )
  }

  return (
    <div className="compare-bar">

      {/* Cards en haut */}
      <div className="compare-cards-row">
        {zones.map(({ id, data, color, bars, label }) => {
          const score = data?.[activeIndicateur.scoreKey] ?? null
          const isBest = score !== null && score === bestScore
          return (
            <div className="compare-zone-card" key={id}>
              <div className="compare-zone-card-header">
                <span className="compare-zone-dot" style={{ background: color }} />
                <span className="compare-zone-name" title={label}>{label}</span>
                <button className="compare-remove-btn" onClick={() => onRemove(id)}>✕</button>
              </div>
              <div className="compare-zone-score-row">
                <ScoreRing score={score} color={color} />
                <div className="compare-zone-score-info">
                  {isBest && <span className="compare-best-badge" style={{ color, borderColor: color }}>✦ Meilleur</span>}
                  <div className="compare-zone-meta">
                    {data?.categorie ?? '—'}
                    {data?.rang ? <span> · Rang <strong>#{data.rang}</strong></span> : null}
                  </div>
                </div>
              </div>
              <div className="compare-zone-bars">
                {bars.map(bar => (
                  <div className="compare-mini-bar" key={bar.label}>
                    <span className="compare-mini-bar-label">{bar.label}</span>
                    <div className="compare-mini-bar-bg">
                      <div className="compare-mini-bar-fill" style={{ width: `${bar.value * 100}%`, background: color }} />
                    </div>
                    <span className="compare-mini-bar-val">{(bar.value * 100).toFixed(0)}</span>
                  </div>
                ))}
              </div>
            </div>
          )
        })}

        {compareList.length < 3 && (
          <div className="compare-add-card">
            <span style={{ fontSize: 16, opacity: 0.3 }}>+</span>
            Cliquer sur une zone
          </div>
        )}
      </div>

      {/* Bar chart en bas, pleine largeur */}
      {zones.length >= 2 && (
        <div className="compare-radar">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData} margin={{ top: 16, right: 24, bottom: 12, left: 24 }} barCategoryGap="30%" barSize={48}>
              <XAxis
                dataKey="label"
                tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'DM Mono' }}
                axisLine={{ stroke: '#1f2d45' }}
                tickLine={false}
              />
              <YAxis hide domain={[0, 110]} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #1f2d45', borderRadius: 6, fontSize: 11, fontFamily: 'DM Mono' }}
                labelStyle={{ color: '#e2e8f0', marginBottom: 4 }}
                itemStyle={{ color: '#e2e8f0' }}
                cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                formatter={(val) => [`${val} / 100`, 'Score']}
              />
              <Bar dataKey="score" radius={[4, 4, 0, 0]} maxBarSize={64}>
                <LabelList
                  dataKey="score"
                  position="top"
                  style={{ fill: '#e2e8f0', fontSize: 11, fontFamily: 'DM Mono', fontWeight: 700 }}
                />
                {barData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} fillOpacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
