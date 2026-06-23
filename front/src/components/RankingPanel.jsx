import { useRef, useState } from 'react'

export default function RankingPanel({ scores = [], activeIndicateur, granularite, onSelect, selected }) {
  if (!activeIndicateur || !scores.length) return null

  const isQuartier = granularite === 'quartier'
  const activeColor = activeIndicateur.color || '#4f8ef7'

  const [pos, setPos] = useState({ top: 80, right: 12, left: null })
  const dragOffset = useRef(null)
  const panelRef = useRef(null)

  const onMouseDown = (e) => {
    e.preventDefault()
    const rect = panelRef.current.getBoundingClientRect()
    const parentRect = panelRef.current.offsetParent?.getBoundingClientRect() ?? { top: 0, left: 0 }

    dragOffset.current = {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
      parentTop: parentRect.top,
      parentLeft: parentRect.left,
    }

    const onMouseMove = (e) => {
      setPos({
        top: e.clientY - dragOffset.current.parentTop - dragOffset.current.y,
        left: e.clientX - dragOffset.current.parentLeft - dragOffset.current.x,
        right: null,
      })
    }
    const onMouseUp = () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }

  const sorted = [...scores]
    .filter(s => s[activeIndicateur.scoreKey] != null)
    .sort((a, b) => b[activeIndicateur.scoreKey] - a[activeIndicateur.scoreKey])
    .slice(0, 10)

  const getLabel = (s) => {
    if (s.nom_quartier) return s.nom_quartier
    const arr = s.arrondissement ?? (s.code_postal - 75000)
    return `Paris ${arr}e`
  }

  const getId = (s) => {
    if (s.code_quartier !== undefined) return parseInt(s.code_quartier)
    if (s.arrondissement !== undefined) return parseInt(s.arrondissement)
    return parseInt(s.code_postal) - 75000
  }

  const style = {
    top: pos.top,
    ...(pos.left !== null ? { left: pos.left, right: 'unset' } : { right: 12 }),
  }

  return (
    <aside ref={panelRef} className="ranking-panel" style={style}>
      <div className="ranking-drag-handle" onMouseDown={onMouseDown}>
        <p className="ranking-title">
          Top 10 {isQuartier ? 'quartiers' : 'arrondissements'}
        </p>
        <span className="ranking-drag-icon">⠿</span>
      </div>
      <div className="ranking-list">
        {sorted.map((s, i) => {
          const id = getId(s)
          const isSelected = parseInt(selected) === id
          const score = s[activeIndicateur.scoreKey]
          return (
            <div
              key={id}
              className={`ranking-item ${isSelected ? 'active' : ''}`}
              style={{ '--active-color': activeColor }}
              onClick={() => onSelect(id)}
            >
              <span className="ranking-pos" style={{ color: i < 3 ? activeColor : '#64748b' }}>
                #{i + 1}
              </span>
              <span className="ranking-label">{getLabel(s)}</span>
              <span className="ranking-score" style={{ color: activeColor }}>{score}</span>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
